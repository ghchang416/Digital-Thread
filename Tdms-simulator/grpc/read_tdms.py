import grpc
from concurrent import futures
import json
import os
import yaml
from nptdms import TdmsFile
from proto import tdms_service_pb2, tdms_service_pb2_grpc
import logging
import re
import numpy as np
import pandas as pd
import pika

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logging.getLogger("pika").setLevel(logging.WARNING)

def load_config(config_path="config.yml"):
    """
    YAML 기반 설정 파일 로딩 함수
    - RabbitMQ, 기타 환경 변수 세팅을 위함
    """
    try:
        with open(config_path, "r") as config_file:
            config = yaml.safe_load(config_file)
        return config
    except Exception as e:
        raise

class TdmsService(tdms_service_pb2_grpc.TdmsServiceServicer):
    """
    gRPC를 통한 TDMS 파일 처리 및 RabbitMQ 메시지 발행/수신 기능 제공
    """
    def __init__(self):
        self.config = load_config()
        self.sampling_rate = 12800
        # CNC 블록 내 product change 감지용 패턴
        self.product_change_pattern = re.compile(r"G90G00X([-\d\.#+\-\*/\[\]]+)Y([-\d\.#+\-\*/\[\]]+)")
        
        # RabbitMQ 연결 세팅
        self.rabbitmq_host = self.config["rabbitmq"]["host"]
        self.raw_data_queue = self.config["rabbitmq"]["raw_data_queue"]
        self.result_queue = self.config["rabbitmq"]["result_queue"]

        self.connection = pika.BlockingConnection(pika.ConnectionParameters(host=self.rabbitmq_host))
        self.channel = self.connection.channel()
        self.channel.queue_declare(queue=self.raw_data_queue)
        self.channel.queue_declare(queue=self.result_queue)

    def ReadTdms(self, request, context):
        """
        클라이언트로부터 TDMS 파일 경로를 받아,
        - TDMS 데이터 파싱 및 공구 변환/제품 분할
        - 각 구간별 신호(Spindle, ACC) chunk를 Json으로 스트리밍 반환

        (클라이언트는 각 chunk별로 inference 요청 가능)
        """
        tdms_path = request.tdms_data 
        file_name = os.path.basename(tdms_path)
        
        logging.info(f"Opening TDMS file: {tdms_path}")
        with TdmsFile.open(tdms_path) as tdms_file:
            logging.info("TDMS File Opened Successfully.")
            # CNC/DAQ 데이터 로드
            cnc_tool_data = tdms_file["CNC"]["CNC-ToolNumber"][:]
            cnc_time_raw = tdms_file["CNC"]["Time Channel CNC"][:]
            cnc_block_data = tdms_file["CNC"]["CNC-CurrentBlock"][:]
            cnc_time = pd.to_datetime(cnc_time_raw)
            cnc_time_seconds = [(time - cnc_time[0]).total_seconds() for time in cnc_time]

            # TDMS 파일명에 따라 tool index/구간 결정
            target_tool_index = 5 if "YPH 020" in file_name or "YPH 021" in file_name or "YPH 016" in file_name else 4
            time_start, time_end = (180, 200) if target_tool_index == 5 else (158, 165)

            tool_number_list = cnc_tool_data
            tool_indices = []
            count = 1  
            for i in range(1, len(tool_number_list)):
                if tool_number_list[i] != tool_number_list[i - 1]:
                    count += 1
                if count == target_tool_index:
                    tool_indices.append(i)
                    
            if len(tool_indices) == 0:
                logging.info(f"No Tool {target_tool_index} found, skipping.")
                return

            # 제품 분할: 공구 변환 지점, CNC 블록 내 패턴 감지 시각 등으로 구간 산출
            time_start, time_end = 158, 163
            product_change_time = next(
                (
                    cnc_time_seconds[idx] for idx in tool_indices
                    if time_start <= cnc_time_seconds[idx] <= time_end and self.product_change_pattern.search(cnc_block_data[idx])
                ),
                cnc_time_seconds[tool_indices[-1]]
            )

            # 두 제품 구간 (시간 구간) 생성
            intervals = [
                ("Product 1", cnc_time_seconds[tool_indices[0]], product_change_time),
                ("Product 2", product_change_time, cnc_time_seconds[tool_indices[-1]])
            ]

            daq_spindle_data = tdms_file["DAQ"]["DAQ-Spindle-C-R"]
            daq_acc_data = tdms_file["DAQ"]["DAQ-ACC-1"]

            for product_label, start_time, end_time in intervals:
                daq_start_idx = int(start_time * self.sampling_rate)
                daq_end_idx = int(end_time * self.sampling_rate)

                if daq_start_idx >= len(daq_spindle_data) or daq_end_idx > len(daq_spindle_data):
                    continue

                # 샘플링 주기마다 신호데이터 chunk 생성
                for chunk_start in range(daq_start_idx, daq_end_idx, self.sampling_rate):
                    chunk_end = min(chunk_start + self.sampling_rate, daq_end_idx)
                    spindle_segment = daq_spindle_data[chunk_start:chunk_end]
                    acc_segment = daq_acc_data[chunk_start:chunk_end]

                    if len(spindle_segment) == 0 or len(acc_segment) == 0:
                        continue
                    
                    # Json 직렬화 후 gRPC 스트리밍으로 반환
                    raw_data = json.dumps({
                        "spindle": spindle_segment.tolist(), 
                        "acc": acc_segment.tolist(), 
                        "product": product_label,
                        "file_name": file_name,
                        })
                    yield tdms_service_pb2.TdmsReadResponse(tdms_data=raw_data)

    def SendTdms(self, request, context):
        """
        클라이언트가 gRPC로 받은 raw_data(신호 chunk)를 RabbitMQ로 전송
        """
        data = json.loads(request.tdms_data)
        data["timer"] = request.timer

        self.channel.basic_publish(exchange='', routing_key=self.raw_data_queue, body=json.dumps(data))
        return tdms_service_pb2.TdmsSendResponse()

    def ReceivedData(self, request, context):
        """
        AI서버(inference)에서 결과 메시지를 받을 때까지 MQ 대기 후 반환
        """
        for method_frame, properties, body in self.channel.consume(self.result_queue, auto_ack=True):
            return tdms_service_pb2.DataReceivedResponse(received_data=body.decode())

def serve():
    """
    gRPC 서버 구동 (멀티스레드)
    """
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    tdms_service_pb2_grpc.add_TdmsServiceServicer_to_server(TdmsService(), server)
    server.add_insecure_port("[::]:50051")
    server.start()
    logging.info("gRPC Server is running on port 50051...")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()
