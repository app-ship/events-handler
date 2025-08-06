from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application settings
    app_name: str = "Events Handler API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Google Cloud settings
    google_cloud_project_id: str = Field(..., env="GOOGLE_CLOUD_PROJECT")
    google_application_credentials: str = Field(
        default="", env="GOOGLE_APPLICATION_CREDENTIALS"
    )
    
    # Pub/Sub settings
    pubsub_timeout: float = 60.0
    max_messages_per_pull: int = 100
    
    # API settings
    api_v1_prefix: str = "/api/v1"
    allowed_hosts: list[str] = ["*"]
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()