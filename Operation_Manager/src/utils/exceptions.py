# src/utils/exceptions.py
from enum import Enum

class ExceptionEnum(Enum):
    # 404 NOT FOUND
    PROJECT_NOT_FOUND = ("Project not found.", 404)
    NC_NOT_FOUND = ("NC code not found.", 404)
    MACHINE_NOT_FOUND = ("No matching machine id found.", 404)
    LOG_NOT_FOUND = ("Log not found.", 404)

    # 400 BAD REQUEST
    INVALID_XML_FORMAT = ("Invalid XML format.", 400)
    INVALID_FILE_NAME_FORMAT = ("Invalid filename format.", 400)
    INVALID_SIMENSE_FORMAT = ("Simense G-code O number missing.", 400)
    INVALID_REQUEST = ("Invalid request.", 400)
    NO_DATA_PROVIDED = ("No data provided in the request.", 400)

    # 500 INTERNAL SERVER ERROR
    EXTERNAL_REQUEST_ERROR = ("Failed to connect to Torus Application.", 500)
    DATABASE_ERROR = ("Database operation failed.", 500)
    FILE_OPERATION_ERROR = ("File operation failed.", 500)
    REDIS_ERROR = ("Redis operation failed.", 500)

    def __init__(self, detail, status_code):
        self.detail = detail
        self.status_code = status_code

class CustomException(Exception):
    def __init__(self, exception_enum: ExceptionEnum, detail: str = None):
        self.name = exception_enum.detail
        self.detail = detail
        self.status_code = exception_enum.status_code
