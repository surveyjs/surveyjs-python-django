"""Translate with AI: POST /api/translate, Creator's strings translated by your OpenAI-compatible provider.

Nothing is stored. examples/integration/ai_translation.py calls the provider; async, so a request that waits up
to 60 s on it doesn't hold up anyone else.
"""

from django.conf import settings
from django.http import HttpRequest, JsonResponse

from examples.integration.ai_translation import AiTranslation
from examples.integration.stored_json import read_json


# region sjs:ai-translation.server
# POST /api/translate — strings in, translated strings out (same order); nothing goes to SurveyJS
async def translate(request: HttpRequest) -> JsonResponse:
    if not settings.AI_API_KEY:
        return JsonResponse({"error": "Set AI_API_KEY to enable translation"}, status=501)
    body = read_json(request)
    strings = body.get("strings", []) if isinstance(body, dict) else None
    if not isinstance(strings, list) or not all(isinstance(text, str) for text in strings):
        return JsonResponse({"error": "Expected { strings, from, to }"}, status=400)

    translated = await AiTranslation().translate(strings, body.get("from", ""), body.get("to", ""))   # your provider
    if not isinstance(translated, list) or len(translated) != len(strings) \
            or not all(isinstance(text, str) for text in translated):
        return JsonResponse({"error": "The AI provider returned an unexpected answer"}, status=502)

    return JsonResponse(translated, safe=False)   # what options.callback() takes
# endregion
