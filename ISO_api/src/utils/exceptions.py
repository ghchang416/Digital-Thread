from enum import Enum


class ExceptionEnum(Enum):
    # 404 NOT FOUND
    PROJECT_NOT_FOUND = ("Project file not found.", 404)
    STP_NOT_FOUND = ("STEP file not found", 404)
    NO_DATA_FOUND = ("Requested data not found", 404)
    NC_NOT_EXIST = ("Please enter the nc code first", 404)

    # 400 BAD REQUEST
    INVALID_XML_FORMAT = ("Invalid XML format", 400)
    INVALID_ROOT_TAG = ("Invalid root tag, must be 'project'", 400)
    INVALID_PARENT_TYPE = ("Invalid parent type specified", 400)
    INVALID_FORMAT = ("Invalid data format", 422)
    INVALID_ATTRIBUTE = ("Invalid attribute provided", 400)
    NO_DATA_PROVIDED = ("No data provided in the request", 400)
    NO_FILE_NAME_PROVIDED = ("No file name provided", 400)
    NO_JSON_DATA_PROVIDED = ("No JSON data provided", 400)
    UNSUPPORTED_FILE_TYPE = ("Unsupported file type", 400)
    WORKPLAN_EXIST = ("Already Workplan Exist", 400)

    # 500 INTERNAL SERVER ERROR
    PROJECT_UPLOAD_FAILED = ("Project file upload failed.", 500)
    PROJECT_CREATION_FAILED = ("Project creation failed", 500)
    PROJECT_DELETE_FAILED = ("Project deletion failed", 500)
    STP_UPLOAD_FAILED = ("STEP file upload failed", 500)
    STP_DELETE_FAILED = ("STEP file deletion failed", 500)
    NO_FILE_UPLOADED = ("No file uploaded", 500)
    VM_AUTH_FAIL = ("vm server authauthorization fail", 500)
    VM_NOT_TOKEN = ("vm not access token", 500)
    VM_PRJ_FAIL = ("vm fail to create project", 500)

    def __init__(self, detail, status_code):
        self.detail = detail
        self.status_code = status_code


class CustomException(Exception):
    def __init__(self, exception_enum: ExceptionEnum):
        self.detail = exception_enum.detail
        self.status_code = exception_enum.status_code
