from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # VM 관련
    vm_api_url: str
    vm_username: str
    vm_password: str

    # DP 관련
    dp_base_url: str
    dp_api_key: str

    class Config:
        env_file = ".env"


settings = Settings()
