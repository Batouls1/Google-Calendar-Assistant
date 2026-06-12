class CalendarToolError(Exception):
    """Base exception for calendar tool failures."""
    pass


class AuthError(CalendarToolError):
    """Raised when OAuth authentication fails."""
    pass


class EventNotFoundError(CalendarToolError):
    """Raised when a requested event doesn't exist (HTTP 404)."""
    pass


class RateLimitError(CalendarToolError):
    """Raised when Google's API rate limit is hit (HTTP 429)."""
    pass


class InvalidEventDataError(CalendarToolError):
    """Raised when the request data is invalid (HTTP 400)."""
    pass


class GoogleServerError(CalendarToolError):
    """Raised when Google's servers have an error (HTTP 5xx)."""
    pass