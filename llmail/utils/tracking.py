import imaplib
from email import message_from_bytes
from email.message import Message

# from email.utils import getaddresses, parsedate_to_datetime, make_msgid
from email.utils import getaddresses, parsedate_to_datetime

from imapclient import IMAPClient

from llmail.utils.cli_args import args, bot_email
from llmail.utils import logger
from llmail.utils.utils import get_plain_email_content, make_tz_aware


class EmailThread:
    def __init__(self, initial_email):
        self.initial_email = initial_email
        self.replies = []

    def add_reply(self, reply_email):
        # If the message_id of the reply email is not in the list of messages add it
        # Also, don't do it if the email is the inital/top-level email itself
        if (
            reply_email.message_id not in [email.message_id for email in self.replies]
            and reply_email.message_id != self.initial_email.message_id
        ):
            logger.debug(
                f"Reply sent by {reply_email.sender} at {reply_email.timestamp} does not exist in thread. Adding it to thread for email {self.initial_email.message_id}"
            )
            self.replies.append(reply_email)
            self.sort_replies()
        else:
            logger.debug(f"Reply email {reply_email} already exists in thread")

    @property
    def user_replies(self):
        """Return the replies that are from the user"""
        return [reply for reply in self.replies if reply.sender != bot_email]

    def sort_replies(self):
        self.replies = sorted(self.replies, key=lambda x: x.timestamp)
        # Honestly, it might be better to sort by the message_id. This also goes for the get_thread_history function
        # However, this **significantly** reduces complexity so for now, it's fine

    def __repr__(self):
        return (
            f"EmailThread(initial_email={self.initial_email}, replies={self.replies})"
        )


class Email:
    def __init__(
        self, imap_id, message_id, subject, sender, timestamp, body, references
    ):
        self.imap_id = imap_id
        self.message_id = message_id
        self.subject = subject
        self.sender = sender
        self.timestamp = timestamp
        self.body = body
        self.references = references

    def __repr__(self):
        # return f"Email(imap_id={self.imap_id}, message_id={self.message_id}, subject={self.subject}, sender={self.sender}, timestamp={self.timestamp})"
        return f"Email(imap_id={self.imap_id}, timestamp={self.timestamp})"


# Function to check if an email has been read
def is_new_email(client, msg_id):
    flags = client.get_flags([msg_id])
    return b"\\Seen" not in flags.get(msg_id, [])


def is_uid_user_email(client, msg_id, sender):
    # Fetch the header of the email to get the "In-Reply-To" header
    msg_data = client.fetch([msg_id], ["RFC822.HEADER"])
    headers_bytes = msg_data[msg_id][b"RFC822.HEADER"]
    headers = message_from_bytes(headers_bytes)
    timestamp = headers.get("Date")
    logger.debug(
        f"Checking if email with UID {msg_id} from {sender} sent on {timestamp} is most recent user email"
    )
    return sender != args.imap_username


def get_thread_history(
    client: IMAPClient, message_identifier: str | int | EmailThread
) -> list[dict]:
    """Fetch the entire thread history for the specified message ID."""
    # Might be better to use "is"
    if isinstance(message_identifier, EmailThread):
        thread_history = []
        thread_history.append(
            {
                "sender": message_identifier.initial_email.sender,
                "content": message_identifier.initial_email.body,
            }
        )
        for email in message_identifier.replies:
            thread_history.append(
                {
                    "sender": email.sender,
                    "content": email.body,
                    "timestamp": email.timestamp,
                }
            )
        return thread_history
    elif isinstance(message_identifier, int) or isinstance(message_identifier, str):
        client.select_folder("INBOX")
        if isinstance(message_identifier, str):
            message_id = message_identifier
            msg_id = get_uid_from_message_id(client, message_id)
            logger.debug(
                f"Getting thread history from Message-ID {message_id} with IMAP UID {msg_id}"
            )
        else:
            msg_id = message_identifier
            logger.debug(f"Getting thread history from IMAP UID {msg_id}")
        thread_history = []
        for folder in client.list_folders():
            try:
                client.select_folder(folder[2])
            # If the error is imaplib.IMAP4.error: select failed:...
            except imaplib.IMAP4.error:
                logger.debug(f"Failed to select folder {folder[2]}. Skipping...")
                continue
            msg_data = client.fetch([msg_id], ["RFC822"])
            if msg_data:
                break
        raw_message = msg_data[msg_id][b"RFC822"]
        message = message_from_bytes(raw_message)
        thread_history.append(
            {
                "sender": get_sender(message)["email"],
                "content": get_plain_email_content(message),
                "timestamp": make_tz_aware(parsedate_to_datetime(message.get("Date"))),
            }
        )

        # Fetch previous emails in the thread if available
        while message.get("In-Reply-To"):
            prev_message_id = message.get("In-Reply-To")
            prev_msg_id = get_uid_from_message_id(client, prev_message_id)
            prev_msg_data = client.fetch([prev_msg_id], ["RFC822"])
            prev_raw_message = prev_msg_data[prev_msg_id][b"RFC822"]
            prev_message = message_from_bytes(prev_raw_message)
            thread_history.append(
                {
                    "sender": get_sender(message)["email"],
                    "content": get_plain_email_content(message),
                    "timestamp": make_tz_aware(
                        parsedate_to_datetime(message.get("Date"))
                    ),
                }
            )
            message = prev_message
        # Sort the thread history by timestamp
        thread_history = sorted(thread_history, key=lambda x: x["timestamp"])
        return thread_history
    else:
        raise TypeError(
            "Invalid type for message. Must be an int, str, or EmailThread object."
        )


def get_sender(message: Message) -> dict:
    """Extract the sender information from an email message."""
    sender = message.get("From", "")
    sender_name, sender_email = getaddresses([sender])[0]
    return {"name": sender_name, "email": sender_email}


def get_top_level_email(client, msg_id, message_id=None):
    """Get the top-level email in the thread for the specified message ID (IMAP)"""
    message_id = msg_id if message_id is None else message_id
    msg_data = client.fetch([msg_id], ["RFC822.HEADER"])
    headers_bytes = msg_data[msg_id][b"RFC822.HEADER"]

    # Parse the headers using the email library
    msg = message_from_bytes(headers_bytes)
    headers = dict(msg.items())

    # Extract the References header and split it into individual message IDs
    references_header = headers.get("References", "")
    references_ids = [
        m_id.strip() for m_id in references_header.split() if m_id.strip()
    ]

    # Extract the first message ID, which represents the top-level email in the thread
    # If it doesn't exist, use the current message ID. Not msg_id since msg_id is only for IMAP
    top_level_email_id = references_ids[0] if references_ids else message_id
    return top_level_email_id


def is_newer_reference(client, message_id) -> bool:
    """Do a search through all folders to see if any message references message_id. If so, return True."""
    for folder in client.list_folders():
        try:
            client.select_folder(folder[2])
        # If the error is imaplib.IMAP4.error: select failed:...
        except imaplib.IMAP4.error:
            logger.debug(f"Failed to select folder {folder[2]}. Skipping...")
            continue
        search_result = client.search(["HEADER", "In-Reply-To", message_id])
        if search_result:
            return True
    logger.debug(f"No newer references found for email {message_id}")
    return False


def get_uid_from_message_id(imap_client, message_id):
    """Get the UID of a message using its Message-ID."""
    # In some cases, it might not be in Inbox
    # For example, for me, I think when the bot sends an email it was in [Gmail]/All Mail
    for folder in imap_client.list_folders():
        try:
            imap_client.select_folder(folder[2])
        # If the error is imaplib.IMAP4.error: select failed:...
        except imaplib.IMAP4.error:
            logger.debug(f"Failed to select folder {folder[2]}. Skipping...")
            continue
        search_result = imap_client.search(["HEADER", "Message-ID", message_id])
        if search_result:
            uid = search_result[0]  # Assuming search_result is a list of UIDs
            logger.info(
                f"UID of message with Message-ID {message_id} is {uid}. Email subject: {imap_client.fetch([uid], ['ENVELOPE'])[uid][b'ENVELOPE'].subject}"
            )
            return uid
    logger.warning(
        f"UID of message with Message-ID {message_id} not found. Trying to check all headers and text."
    )
    return None
