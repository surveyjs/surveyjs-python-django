"""The error the integration helpers raise when a request can't go on: read_json() for a body that isn't JSON, the
SurveyJS service client for a service that times out or isn't running, the AI translation client for a provider
that fails. examples/middleware.py answers it under /api/ as JSON { error } with its status."""


class ApiError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message
