from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    vm_api_url: str
    vm_username: str
    vm_password: str

    class Config:
        env_file = ".env"


settings = Settings()
