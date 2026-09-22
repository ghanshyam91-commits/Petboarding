import time
from django.db import transaction
from django.http import HttpResponse
from django.utils.crypto import salted_hmac
from .models import RateBucket


class LoginThrottle:
    """Shared database buckets, no raw IP/username retention or trusted forwarded headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.path in ["/login/", "/admin/login/", "/signup/"]:
            window = int(time.time()) // 900
            identities = [
                ("ip", request.META.get("REMOTE_ADDR", "unknown"), 50),
                ("account", request.POST.get("username", "").casefold(), 10),
            ]
            for kind, identity, limit in identities:
                key = salted_hmac("login-throttle", kind + ":" + identity).hexdigest()
                with transaction.atomic():
                    bucket, _ = RateBucket.objects.get_or_create(key=key, window=window)
                    bucket = RateBucket.objects.select_for_update().get(pk=bucket.pk)
                    if bucket.count >= limit:
                        response = HttpResponse(
                            "Too many sign-in attempts. Please try again later.",
                            status=429,
                        )
                        response["Retry-After"] = "900"
                        return response
                    bucket.count += 1
                    bucket.save(update_fields=["count"])
        return self.get_response(request)
