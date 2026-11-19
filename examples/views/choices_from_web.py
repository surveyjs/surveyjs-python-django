"""Load Choices from Web: GET /api/offices?region= and GET /api/countries, a proxy for restcountries.com."""

import json
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, JsonResponse

from examples.integration import http
from examples.models import Office

log = logging.getLogger("examples")

BUNDLED_COUNTRIES = settings.BASE_DIR / "shared" / "seed" / "countries.json"
DAY = 24 * 3600


# region sjs:choices-from-web.server
# GET /api/offices?region= — {region} from the form arrives as a query parameter
def offices(request: HttpRequest) -> JsonResponse:
    region = request.GET.get("region", "")
    return JsonResponse(list(Office.objects.filter(region=region).order_by("name").values("id", "name")), safe=False)


# GET /api/countries — a proxy: the browser can't call a service without CORS, your server can
async def countries(request: HttpRequest) -> JsonResponse:
    countries = await cache.aget("countries")
    if countries is None:
        try:
            answer = await http.client().get("https://restcountries.com/v3.1/all", params={"fields": "name,cca2"}, timeout=5)
            countries = sorted(({"code": c["cca2"], "name": c["name"]["common"]} for c in answer.raise_for_status().json()),
                               key=lambda country: country["name"])
            await cache.aset("countries", countries, DAY)
        except Exception as error:   # down, or a different answer: the bundled list for 10 minutes, not a timeout each
            log.warning("restcountries.com failed (%s); serving shared/seed/countries.json", error)
            countries = json.loads(BUNDLED_COUNTRIES.read_text(encoding="utf-8"))
            await cache.aset("countries", countries, 10 * 60)
    return JsonResponse(countries, safe=False, headers={"Cache-Control": "public, max-age=86400"})
# endregion
