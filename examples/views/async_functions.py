"""Async Calculations and Validation: GET /api/customers/exists?email= and GET /api/shipping?postcode=."""

import re

from django.db.models.functions import Length
from django.http import HttpRequest, JsonResponse

from examples.models import Customer, ShippingRate

# Only a whole German (10115) or UK (SW1A 1AA) postcode gets a price, not anything that starts with a prefix
POSTCODE = re.compile(r"^(\d{5}|[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2})$")


# region sjs:async-functions.server
# GET /api/customers/exists?email= — answers emailExists()
def customer_exists(request: HttpRequest) -> JsonResponse:
    email = request.GET.get("email", "").strip().lower()
    return JsonResponse({"exists": Customer.objects.filter(email=email).exists()})


# GET /api/shipping?postcode= — answers shippingCost(): the longest matching postcode prefix wins,
# { "price": null } when none matches (the form shows "We don't deliver to this postcode yet")
def shipping(request: HttpRequest) -> JsonResponse:
    postcode = request.GET.get("postcode", "").replace(" ", "").upper()
    if not POSTCODE.match(postcode):
        return JsonResponse({"price": None})
    prefixes = [postcode[:length] for length in range(1, len(postcode) + 1)]
    rate = ShippingRate.objects.filter(postcode_prefix__in=prefixes).order_by(Length("postcode_prefix").desc()).first()
    return JsonResponse({"price": float(rate.price) if rate else None})   # a DecimalField: send it as a number
# endregion
