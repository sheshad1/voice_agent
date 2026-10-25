"""Domain exceptions shared across modules."""


class DialerError(RuntimeError):
    """Raised when an outbound call could not be placed."""


class UnknownAttemptError(LookupError):
    """Raised when a call-status webhook cannot be tied to a known lead."""
