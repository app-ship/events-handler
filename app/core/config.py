from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from typing import List

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
    allowed_hosts_raw: str = "*"  # Accept as string first
    
    # Slack settings
    slack_signing_secret: str = Field(default="", alias="SLACK_SIGNING_SECRET")
    slack_webhook_verify_signature: bool = Field(default=True, alias="SLACK_WEBHOOK_VERIFY_SIGNATURE")
    
    @field_validator('allowed_hosts_raw')
    @classmethod
    def validate_allowed_hosts_raw(cls, v):
        # Handle the conversion here
        if v == "*":
            return "*"
        # If it's a comma-separated list, split it
        if "," in v:
            return v
        return v
    
    @property
    def allowed_hosts(self) -> List[str]:
        """Convert the raw string to a list"""
        if self.allowed_hosts_raw == "*":
            return ["*"]
        return [host.strip() for host in self.allowed_hosts_raw.split(",")]


settings = Settings()