"""Asks any OpenAI-compatible /chat/completions endpoint (AI_BASE_URL, AI_API_KEY, AI_MODEL) to translate
Creator's strings. Your provider and your key: nothing goes to SurveyJS. Swap this file for your provider's
SDK if you like; the view only needs a list back. When you copy ai-translation, copy this file too."""

import json
import logging
import re
from typing import Any

import httpx2
from django.conf import settings

from examples.errors import ApiError
from examples.integration import http

log = logging.getLogger("examples.ai")
_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


class AiTranslation:
    async def translate(self, strings: list[str], source: str, target: str) -> Any:
        """The translated strings as the model returned them (a list if all went well), or None. An unreachable
        provider or an HTTP error ends the request here with 502."""
        try:
            reply = await http.client().post(
                f"{settings.AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
                json={
                    "model": settings.AI_MODEL,
                    "messages": [
                        {"role": "system", "content": f"Translate each string from {source} to {target}. "
                                                      "Return a JSON array in the same order."},
                        {"role": "user", "content": json.dumps(strings, ensure_ascii=False)},
                    ],
                },
                timeout=60,
            )
            reply.raise_for_status()
        except httpx2.HTTPError as error:
            log.error("Translation provider failed: %s", error)
            raise ApiError(502, "The translation provider is unavailable. Please try again.") from None
        try:
            content = reply.json()["choices"][0]["message"]["content"]
        except (ValueError, LookupError, TypeError):
            return None

        # Models sometimes wrap the array in prose or a code fence: take the array itself
        match = _ARRAY.search(content) if isinstance(content, str) else None
        try:
            return json.loads(match.group(0)) if match else None
        except ValueError:
            return None
