import os
import clr

# stepdata.dll (C# 빌드 DLL) 경로
DLL_PATH = os.path.abspath("./packages/stepdata.dll")
# pythonnet의 clr로 DLL 참조 추가
clr.AddReference(DLL_PATH)

from stepdata import step242data

def get_step242_instance():
    """
    step242data 클래스 인스턴스 반환.
    각 요청마다 새 객체를 만들도록 설계.
    """
    return step242data()
