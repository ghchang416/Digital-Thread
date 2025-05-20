from enum import Enum

class ExceptionEnum(Enum):
    # 400 BAD REQUEST
    INVALID_INPUT_FORMAT = ("Only .stp or .step files are supported.", 400)
    
    # 500 BAD REQUEST
    FILE_GENERATION_FAILED = ("Failed to create converted file.", 500)

    def __init__(self, detail, status_code):
        self.detail = detail
        self.status_code = status_code

class CustomException(Exception):
    def __init__(self, exception_enum: ExceptionEnum):
        self.detail = exception_enum.detail
        self.status_code = exception_enum.status_code