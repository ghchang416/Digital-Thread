import torch
import torch.nn as nn
import mlflow
import mlflow.pytorch
import os

# MLflow 서버 주소 환경변수에서 세팅
mlflow.set_tracking_uri(uri=os.getenv("MLFLOW_TRACKING_URI", ""))

class MLPModel(nn.Module):
    """
    간단한 다층 퍼셉트론(MLP) 모델 정의 (입력: 2, 히든 3개, 출력: 1)
    """
    def __init__(self, input_size=2):
        super(MLPModel, self).__init__()
        self.fc1 = nn.Linear(input_size, 64)  
        self.fc2 = nn.Linear(64, 32)  
        self.fc3 = nn.Linear(32, 16)  
        self.fc4 = nn.Linear(16, 1) 
        self.relu = nn.ReLU()  
        self.sigmoid = nn.Sigmoid() 

    def forward(self, x):
        # 순전파: ReLU → ReLU → ReLU → Sigmoid
        x = self.relu(self.fc1(x))
        x = self.relu(self.fc2(x))
        x = self.relu(self.fc3(x))
        x = self.sigmoid(self.fc4(x)) 
        return x

# 모델 인스턴스 생성 및 파라미터 로드
model = MLPModel()
model.load_state_dict(torch.load("mlp_model.pth"))  # 저장된 PyTorch 모델 파라미터 불러오기
model.eval()  # 추론 모드로 전환

# MLflow에 모델 아티팩트 등록 및 모델 레지스트리에 등록
with mlflow.start_run() as run:
    mlflow.pytorch.log_model(model, artifact_path="mlp_model", registered_model_name="mlp")
print(f"모델이 MLflow 레지스트리에 등록됨")
