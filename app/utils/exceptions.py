from typing import Any, Dict, Optional


class EventsHandlerException(Exception):
    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class PubSubServiceException(EventsHandlerException):
    pass


class TopicCreationException(PubSubServiceException):
    pass


class TopicNotFoundException(PubSubServiceException):
    pass


class MessagePublishException(PubSubServiceException):
    pass


class AuthenticationException(EventsHandlerException):
    pass


class ConfigurationException(EventsHandlerException):
    pass