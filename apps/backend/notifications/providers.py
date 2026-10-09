"""
Internal Push provider abstraction (spec: "the notification system must have
an internal abstraction for external Push providers" / "do not tightly
couple business logic to a vendor").

`NullPushProvider` is the only implementation available in this environment
(no SMS/push credentials are configured anywhere in this project). It is a
faithful, honest stand-in: it does the same job a real provider's client
would (accepts a Notification, returns success/failure), it just doesn't
actually reach a network. Swapping in a real provider (Twilio, FCM, ...)
later means writing one more class with the same `send()` signature and
pointing `get_provider()` at it — nothing calling `send_notification()`
(services.py) or the worker (management/commands/process_notifications.py)
would need to change.
"""
from dataclasses import dataclass


@dataclass
class DeliveryResult:
    success: bool
    error: str = ""


class PushProvider:
    def send(self, notification) -> DeliveryResult:  # pragma: no cover - interface
        raise NotImplementedError


class NullPushProvider(PushProvider):
    """Always "succeeds" without contacting anything. This is a deliberate
    stub, not a placeholder left by accident — see module docstring."""

    def send(self, notification) -> DeliveryResult:
        return DeliveryResult(success=True)


def get_provider() -> PushProvider:
    return NullPushProvider()
