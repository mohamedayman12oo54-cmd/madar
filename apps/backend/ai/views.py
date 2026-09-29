from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from accounts.throttles import AISubmitRateThrottle
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import AIOperation
from .serializers import AIOperationSerializer, AIOperationSubmitSerializer

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


class AIOperationListSubmitView(TenantScopedQuerySetMixin, generics.ListAPIView):
    """GET: my past operations. POST: SUBMIT — inserts a `pending` row and
    returns its id immediately (202). Never calls a model; the worker does
    (see management/commands/process_ai_operations.py)."""

    permission_classes = IS_ENV_OWNER
    serializer_class = AIOperationSerializer
    queryset = AIOperation.objects.all()

    def get_throttles(self):
        # Only submissions cost money/compute; listing is unthrottled.
        return [AISubmitRateThrottle()] if self.request.method == "POST" else []

    def get_queryset(self):
        return super().get_queryset().filter(requested_by=self.request.user)

    def post(self, request):
        ser = AIOperationSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        prompt = ser.validated_data["prompt"]
        key = ser.validated_data.get("idempotency_key")

        if key:
            existing = AIOperation.objects.filter(
                environment=request.environment, requested_by=request.user, idempotency_key=key
            ).first()
            if existing:
                return self._replay(existing, prompt)

        try:
            with transaction.atomic():
                op = AIOperation.objects.create(
                    environment=request.environment, requested_by=request.user, prompt=prompt, idempotency_key=key,
                )
        except IntegrityError:
            # Lost a race with a concurrent submit carrying the same key.
            op = AIOperation.objects.get(
                environment=request.environment, requested_by=request.user, idempotency_key=key
            )
            return self._replay(op, prompt)
        return Response(AIOperationSerializer(op).data, status=status.HTTP_202_ACCEPTED)

    @staticmethod
    def _replay(op, prompt):
        if op.prompt != prompt:
            # Same key, different request: a client bug, never silently "merged".
            return Response(
                {"detail": "مفتاح التكرار مستخدم مسبقًا مع طلب مختلف.", "code": "idempotency_conflict"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(AIOperationSerializer(op).data, status=status.HTTP_200_OK)


class AIOperationDetailView(APIView):
    """POLL. Only ever the caller's own operation, in the caller's own
    environment — someone else's id is a plain 404."""

    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        op = generics.get_object_or_404(
            AIOperation.objects.filter(environment=request.environment, requested_by=request.user), pk=pk
        )
        return Response(AIOperationSerializer(op).data)
