"""Calls the SurveyJS service (SurveyJS Server, SURVEYJS_SERVICE_URL) for Run Server-Side Workflows:
validate-response validates, lint-definition lints, server-pdf prints a PDF and extract-from-paper
extracts. It turns what isn't an answer (a timeout, a refused connection) into the same { error } on
every platform, so the views only match the answers they recognize. When you copy one of those
examples, copy this file too.

httpx2 doesn't raise on 4xx or 5xx, and the service answers some errors with 200 { error }: a status
alone never means success, so each view compares the answer itself (fail closed).
"""

import logging
from typing import Any, NoReturn

import httpx2
from django.conf import settings

from examples.errors import ApiError
from examples.integration import http
from examples.integration.stored_json import dumps

log = logging.getLogger("examples.surveyjs")


class SurveyJsService:
    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.SURVEYJS_SERVICE_URL).rstrip("/")

    async def post(self, path: str, body: Any, timeout: float) -> httpx2.Response:
        """POST JSON to the service and return its answer, whatever the status. When nothing answers, the
        request ends here: 504 when the service timed out, 503 when it isn't running."""
        try:
            return await http.client().post(
                self.base_url + path,
                content=dumps(body).encode(),   # 1.0 stays 1.0, "naïve" stays readable
                headers={"Content-Type": "application/json"},
                timeout=httpx2.Timeout(timeout),
            )
        except httpx2.TimeoutException:
            log.error("SurveyJS service: %s timed out after %s s", path, timeout)
            raise ApiError(504, "SurveyJS service timed out") from None
        except httpx2.ConnectError:
            log.error("SurveyJS service: nothing answers at %s", self.base_url)
            raise ApiError(503, f"SurveyJS service is not running at {self.base_url}") from None
        except httpx2.TransportError as error:   # the connection broke mid-answer
            log.error("SurveyJS service: %s failed: %s", path, type(error).__name__)
            raise ApiError(502, "SurveyJS service error") from None

    @staticmethod
    def unexpected(path: str, answer: httpx2.Response, message: str = "SurveyJS service error", *,
                   log_body: bool = True) -> NoReturn:
        """An answer the view doesn't recognize: log it and end the request with 502 { error }. Extraction
        answers are logged by status only, never by body: it may hold the answers written on the form."""
        if log_body:
            log.error("SurveyJS service: unexpected answer from %s: %s %s", path, answer.status_code, answer.text[:2000])
        else:
            log.error("SurveyJS service: unexpected answer from %s: %s", path, answer.status_code)
        raise ApiError(502, message)
