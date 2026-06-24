import functools
from app.utils.exceptions import (
    CalendarToolError,
    AuthError,
    EventNotFoundError,
    RateLimitError,
    InvalidEventDataError,
    GoogleServerError,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def handle_tool_errors(func):
    """
    Catches calendar errors and turns them into plain text instead of
    crashing the agent. The agent only understands string results, not
    Python exceptions, so every failure has to come back as a message
    it can read and react to.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except AuthError as e:
            logger.error(f"{func.__name__} auth error: {e}")
            return ("Authentication with Google Calendar failed. "
                    "The user's session may need to be re-authorized.")
        except EventNotFoundError as e:
            logger.warning(f"{func.__name__} event not found: {e}")
            return (f"{e} Try listing events first to confirm the exact "
                     f"title, date, or event ID before retrying.")
        except RateLimitError as e:
            logger.warning(f"{func.__name__} rate limited: {e}")
            return ("Google Calendar's rate limit was hit. Wait a moment "
                     "and try the same request again.")
        except InvalidEventDataError as e:
            logger.warning(f"{func.__name__} invalid data: {e}")
            return (f"{e} Ask the user for the missing or corrected "
                     f"details, then retry.")
        except GoogleServerError as e:
            logger.error(f"{func.__name__} server error: {e}")
            return "Google Calendar is temporarily unavailable. Try again shortly."
        except CalendarToolError as e:
            logger.error(f"{func.__name__} calendar tool error: {e}")
            return f"Could not complete the request: {e}"
        except Exception as e:
            logger.error(f"{func.__name__} unexpected error: {e}", exc_info=True)
            return "An unexpected error occurred while processing this request."
    return wrapper