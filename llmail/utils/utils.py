import re
from loguru import logger
from sys import stderr

logging_file = stderr


def redact_email_sink(message: str):
    """Custom sink function that redacts email addresses before logging."""
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    redacted_message = re.sub(email_pattern, "[redacted]", message)
    print(redacted_message, file=logging_file)


def set_primary_logger(log_level, redact_email_addresses):
    """Set up the primary logger with the specified log level. Output to stderr and use the format specified."""
    logger.remove()
    # ^10 is a formatting directive to center with a padding of 10
    logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> |<level>{level: ^10}</level>| <level>{message}</level>"
    sink = redact_email_sink if redact_email_addresses else stderr
    logger.add(sink=sink, format=logger_format, colorize=True, level=log_level)
