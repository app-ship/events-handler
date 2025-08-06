from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )
    
    # Application settings
    app_name: str = "Events Handler API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Google Cloud settings
    google_cloud_project_id: str = Field(..., alias="GOOGLE_CLOUD_PROJECT")
    google_application_credentials: str = Field(
        default="", alias="GOOGLE_APPLICATION_CREDENTIALS"
    )
    
    # Pub/Sub settings
    pubsub_timeout: float = 60.0
    max_messages_per_pull: int = 100
    
    # Port settings
    port: int = os.getenv("PORT", 8001)
    
    # API settings
    api_v1_prefix: str = "/api/v1"
    allowed_hosts: list[str] = ["*"]


settings = Settings()