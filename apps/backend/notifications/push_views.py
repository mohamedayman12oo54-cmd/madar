"""Device subscription endpoints. User-level (a person's browser), so no environment header is needed."""
from urllib.parse import urlparse

from django.conf import settings
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PushSubscription


class PushPublicKeyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"enabled": bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY),
                         "public_key": settings.VAPID_PUBLIC_KEY})


class SubscribeSerializer(serializers.Serializer):
    endpoint = serializers.CharField(max_length=700)
    p256dh = serializers.CharField(max_length=200)
    auth = serializers.CharField(max_length=100)

    def validate_endpoint(self, v):
        u = urlparse(v)
        # Push endpoints are always https URLs on the browser vendor's service; refuse anything else so the
        # server can never be made to POST to an arbitrary address (SSRF).
        if u.scheme != "https" or not u.hostname or u.username or u.password:
            raise serializers.ValidationError("عنوان غير صالح.")
        return v


class PushSubscribeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = SubscribeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        # update_or_create by endpoint: the device now belongs to whoever is signed in on it.
        PushSubscription.objects.update_or_create(
            endpoint=d["endpoint"],
            defaults={"user": request.user, "p256dh": d["p256dh"], "auth": d["auth"],
                      "user_agent": (request.META.get("HTTP_USER_AGENT") or "")[:200]},
        )
        return Response({"subscribed": True}, status=status.HTTP_201_CREATED)


class PushUnsubscribeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        endpoint = request.data.get("endpoint") if isinstance(request.data, dict) else None
        if isinstance(endpoint, str):
            PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
        return Response({"subscribed": False})
