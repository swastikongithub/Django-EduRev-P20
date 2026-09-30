"""Domain errors. Each carries a machine code and a sentence a student can act on."""


class DomainError(Exception):
    code = "error"
    status = 400

    def __init__(self, message: str, *, code: str | None = None, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        self.detail = detail or {}


class BookingRejected(DomainError):
    """The request breaks a rule (policy, hours, blackout, quota, permission...)."""

    code = "rejected"
    status = 422


class SlotUnavailable(BookingRejected):
    """Somebody or something already holds (part of) the requested time."""

    code = "conflict"
    status = 409


class NotPermitted(DomainError):
    code = "forbidden"
    status = 403


class InvalidTransition(DomainError):
    code = "invalid_state"
    status = 409
