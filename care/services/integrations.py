"""External adapters fail closed until genuine vendor implementations are configured."""

from typing import Protocol


class IntegrationUnavailable(RuntimeError):
    pass


class Payments(Protocol):
    def authorize(
        self, booking_id: int, amount_paise: int, idempotency_key: str
    ) -> str: ...
    def capture(
        self, authorization_id: str, amount_paise: int, idempotency_key: str
    ) -> str: ...
    def refund(
        self, payment_id: str, amount_paise: int, idempotency_key: str
    ) -> str: ...
    def payout(
        self, provider_id: int, amount_paise: int, idempotency_key: str
    ) -> str: ...


class DisabledPayments:
    def authorize(self, *args, **kwargs):
        raise IntegrationUnavailable(
            "Payments are not configured. No funds were collected."
        )

    capture = authorize
    refund = authorize
    payout = authorize


class Notifications(Protocol):
    def deliver(
        self, channel: str, recipient: str, message: str, idempotency_key: str
    ) -> str: ...


class CameraAccess(Protocol):
    def issue_viewing_token(
        self, booking_id: int, viewer_id: int, expires_in_seconds: int
    ) -> str: ...


class Insurance(Protocol):
    def quote_terms(self, booking_id: int) -> dict: ...
    def submit_claim(self, booking_id: int, evidence_keys: list[str]) -> str: ...
