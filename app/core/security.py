import os
from typing import Optional

from google.auth import default
from google.auth.credentials import Credentials
from google.oauth2 import service_account

from app.core.config import settings


class GCPAuth:
    def __init__(self):
        self._credentials: Optional[Credentials] = None
        self._project_id: Optional[str] = None

    def get_credentials(self) -> Credentials:
        if self._credentials is None:
            if settings.google_application_credentials:
                # Use service account file if provided
                if os.path.exists(settings.google_application_credentials):
                    self._credentials = service_account.Credentials.from_service_account_file(
                        settings.google_application_credentials
                    )
                else:
                    raise FileNotFoundError(
                        f"Service account file not found: {settings.google_application_credentials}"
                    )
            else:
                # Use default credentials (ADC or compute metadata)
                self._credentials, project = default()
                if not settings.google_cloud_project_id and project:
                    self._project_id = project
        
        return self._credentials

    def get_project_id(self) -> str:
        if not self._project_id:
            if settings.google_cloud_project_id:
                self._project_id = settings.google_cloud_project_id
            else:
                # Try to get from default credentials
                self.get_credentials()
        
        if not self._project_id:
            raise ValueError(
                "Google Cloud project ID not found. "
                "Set GOOGLE_CLOUD_PROJECT environment variable."
            )
        
        return self._project_id


# Global auth instance
gcp_auth = GCPAuth()