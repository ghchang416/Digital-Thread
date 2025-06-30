import json
import pika
import torch
import numpy as np
import mlflow.pyfunc
import yaml
import os
import logging
import tsfel

# 로그 포맷 및 레벨 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("pika").setLevel(logging.WARNING)

class ConfigLoader:
    """
    YAML 기반 설정 파일 로더 (RabbitMQ, MLflow 등 설정 관리)
    """
    @staticmethod
    def load_config(file_path="config.yml"):
        with open(file_path, "r") as config_file:
            return yaml.safe_load(config_file)

class RabbitMQHandler:
    """
    RabbitMQ 연결, 데이터 소비 및 결과 전송 담당 클래스
    """
    def __init__(self, config):
        self.host = config["rabbitmq"]["host"]
        self.raw_data_queue = config["rabbitmq"]["raw_data_queue"]
        self.result_queue = config["rabbitmq"]["result_queue"]

        # MQ 연결 및 큐 선언
        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.host))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.raw_data_queue)
        self.channel.queue_declare(queue=self.result_queue)

    def consume_messages(self, callback):
        """
        raw_data_queue에서 메시지를 소비(Consume)하며,
        각 메시지 도착 시 callback(AI 추론 함수) 호출
        """
        self.channel.basic_consume(queue=self.raw_data_queue, on_message_callback=callback, auto_ack=True)
        logging.info("AI Server is running...")
        self.channel.start_consuming()

    def publish_result(self, result):
        """
        추론 결과를 result_queue에 JSON 형태로 전송
        """
        self.channel.basic_publish(exchange='', routing_key=self.result_queue, body=json.dumps(result))

class AIModel:
    """
    MLflow에 등록된 모델을 불러와 실시간 추론, RMS 기반 피처 추출 및 이상/정상 판별
    """
    def __init__(self, config):
        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", ""))
        print("Tracking URI:", mlflow.get_tracking_uri())
        self.model = mlflow.pyfunc.load_model(config["mlflow"]["model_uri"])
        # 데이터 전처리용 정규화 값 (훈련셋 기준)
        self.sampling_rate = 12800
        self.mean_spindle = 11.5064
        self.mean_acc = 0.1516
        self.std_spindle = 0.6916
        self.std_acc = 0.07386

    def process_data(self, ch, method, properties, body):
        """
        RabbitMQ에서 데이터 수신 시 호출되는 콜백 함수
        - 신호(RAW) 데이터 → RMS 특성 추출 → 정규화 → 모델 추론 → 결과 MQ에 전송
        """
        data = json.loads(body)
        file_name = data["file_name"]
        spindle_segment = np.array(data["spindle"])
        acc_segment = np.array(data["acc"])
        product_label = data["product"]

        cfg = tsfel.get_features_by_domain()

        # spindle_segment, acc_segment를 2D array로 변환
        spindle_segment_2d = np.array(spindle_segment).reshape(-1, 1)
        acc_segment_2d = np.array(acc_segment).reshape(-1, 1)

        # TSFEL로 RMS 특징 추출
        spindle_features = tsfel.time_series_features_extractor(cfg, spindle_segment_2d, fs=self.sampling_rate, window_size=12800, verbose=1)
        acc_features = tsfel.time_series_features_extractor(cfg, acc_segment_2d, fs=self.sampling_rate, window_size=12800, verbose=1)

        spindle_rms = spindle_features["0_Root mean square"].mean()
        acc_rms = acc_features["0_Root mean square"].mean()

        # 정규화
        scaled_spindle = (spindle_rms - self.mean_spindle) / self.std_spindle
        scaled_acc = (acc_rms - self.mean_acc) / self.std_acc

        input_tensor = np.array([[scaled_spindle, scaled_acc]], dtype=np.float32)
        with torch.no_grad():
            # MLflow PyFunc 모델로 예측 (확률)
            y_prob = self.model.predict(input_tensor)[0]
            y_pred = "Anomalous" if y_prob.item() > 0.5 else "Normal"

        # 결과 구성 및 MQ 전송
        result = {
            "File": file_name,
            "Product": product_label,
            "Scaled Mean Spindle": scaled_spindle.item(),
            "Scaled Mean ACC": scaled_acc.item(),
            "Prediction Probability": y_prob.item(),
            "Predicted Class": y_pred,
            "Spindle Mean": spindle_rms,
            "ACC Mean": acc_rms
        }
        rabbitmq_handler.publish_result(result)

if __name__ == "__main__":
    # 설정 로딩
    config = ConfigLoader.load_config()
    # MQ 핸들러 및 모델 준비
    rabbitmq_handler = RabbitMQHandler(config)
    ai_model = AIModel(config)

    # MQ에서 데이터 소비(수신) 및 추론 시작
    rabbitmq_handler.consume_messages(ai_model.process_data)
