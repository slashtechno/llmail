from datetime import timezone
from email.message import Message

import html2text

from llmail.utils import logger


def make_tz_aware(timestamp):
    # dt = parsedate_to_datetime(timestamp)
    dt = timestamp
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def get_plain_email_content(message: Message | str) -> str:
    """Get the content of the email message. If a  message object is provided, it will be parsed
    Otherwise, it is assumed that the content is already a string and will be converted to markdown.
    """
    if isinstance(message, str):
        return html2text.html2text(message)
    else:
        if message.is_multipart():
            for part in message.walk():
                content_type = part.get_content_type()
                try:
                    body = part.get_payload(decode=True)
                except UnicodeDecodeError:
                    logger.debug("UnicodeDecodeError occurred. Trying to get payload as string.")
                    body = str(part.get_payload())
                if content_type == "text/plain":
                    markdown = html2text.html2text(str(body.decode("unicode_escape"))).strip()
                    # logger.debug(f"Converted to markdown: {markdown}")
                    # if len(markdown) < 5:
                    #     logger.warning(
                    #         f"Content is less than 5 characters | Content: {markdown}"
                    #     )
                    return markdown
        else:
            logger.debug("Message is not multipart. Getting payload as string.")
            body = message.get_payload(decode=True).decode()
            # if len(body) < 5:
            #     logger.warning(f"Content is less than 5 characters | Content: {body}")
            return html2text.html2text(str(body.decode("unicode_escape")))
