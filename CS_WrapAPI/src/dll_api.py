import os
import clr

DLL_PATH = os.path.abspath("./packages/stepdata.dll")
clr.AddReference(DLL_PATH)

from stepdata import step242data

def get_step242_instance():
    return step242data()
