from email import message_from_bytes
from email.message import Message
from sys import stderr
import yagmail
import html2text
from icecream import ic
from imapclient import IMAPClient
import imaplib
from loguru import logger
from openai import OpenAI
from email.utils import getaddresses, parsedate_to_datetime
from datetime import timezone
import time


from llmail.utils.cli_args import argparser


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
            logger.info(
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
        return f"EmailThread(initial_email={self.initial_email}, replies={self.replies})"


class Email:
    def __init__(self, imap_id, message_id, subject, sender, timestamp, body, references):
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


args = None
bot_email = None
email_threads = {}
SUBJECT = "autoreply password"


def main():
    """Main entry point for the script."""
    global args
    global bot_email
    args = argparser.parse_args()

    bot_email = args.imap_username

    # Set up logging
    set_primary_logger(args.log_level)
    ic(args)
    if args.watch_interval:
        while True:
            fetch_and_process_emails()
            time.sleep(args.watch_interval)
    else:
        fetch_and_process_emails()


def fetch_and_process_emails():
    """Fetch and process emails from the IMAP server."""
    global email_threads
    openai = OpenAI(api_key=args.openai_api_key, base_url=args.openai_base_url)
    with IMAPClient(args.imap_host) as client:
        client.login(args.imap_username, args.imap_password)

        email_threads = {}
        # for folder in client.list_folders():
        # Disabling fetching from all folders due it not being inefficient
        # Instead, just fetch from INBOX and get the threads later
        for folder in [(None, None, "INBOX")]:
            try:
                client.select_folder(folder[2])
            # If the error is imaplib.IMAP4.error: select failed:...
            except imaplib.IMAP4.error:
                logger.debug(f"Failed to select folder {folder[2]}. Skipping...")
                continue
            # messages = client.search([f"(OR SUBJECT \"{SUBJECT}\" SUBJECT \"Re: {SUBJECT}\")"])
            messages = client.search(["OR", "SUBJECT", SUBJECT, "SUBJECT", f"Re: {SUBJECT}"])
            for msg_id in messages:
                msg_data = client.fetch([msg_id], ["ENVELOPE", "BODY[]", "RFC822.HEADER"])
                envelope = msg_data[msg_id][b"ENVELOPE"]
                subject = envelope.subject.decode()
                timestamp = envelope.date
                # Parse the headers from the email data
                message = message_from_bytes(msg_data[msg_id][b"RFC822.HEADER"])
                sender = get_sender(message)["email"]
                headers = dict(message.items())
                # Extract references from the email
                references_header = headers.get("References", "")
                references_ids = [
                    m_id.strip() for m_id in references_header.split() if m_id.strip()
                ]
                # Extract the Message-ID header
                message_id_header = headers.get("Message-ID")
                # If the Message-ID header doesn't exist, fallback to the IMAP message ID
                message_id = message_id_header if message_id_header else msg_id

                # Check if the email is new (not replied to by the bot yet)
                # if is_uid_user_email(client, msg_id, sender):
                if True:
                    logger.debug(
                        f"On email from {sender} sent at {timestamp} with subject {subject}"
                    )
                    # Put this as message_id so the key for email_threads is the top-level if this email is top-level
                    parent_email_id = get_top_level_email(client, msg_id, message_id)

                    # Unless EmailThread is being used for threads, this is mainly useful for debugging
                    if parent_email_id in email_threads:
                        # Add the reply to the existing thread
                        email_threads[parent_email_id].add_reply(
                            Email(
                                imap_id=msg_id,
                                message_id=message_id,
                                subject=subject,
                                sender=sender,
                                timestamp=timestamp,
                                # Get just the normal email content
                                body=get_plain_email_content(
                                    message_from_bytes(msg_data[msg_id][b"BODY[]"])
                                ),
                                references=references_ids,
                            )
                        )
                        # logger.debug(f"Added message {message_id} to existing thread for email {parent_email_id}")
                    else:
                        # Create a new thread for the email, unless it's a bot email
                        if sender != bot_email:
                            email_thread = EmailThread(
                                Email(
                                    imap_id=msg_id,
                                    message_id=message_id,
                                    subject=subject,
                                    sender=sender,
                                    timestamp=timestamp,
                                    # Get just the normal email content
                                    body=get_plain_email_content(
                                        message_from_bytes(msg_data[msg_id][b"BODY[]"])
                                    ),
                                    references=references_ids,
                                )
                            )
                            email_threads[parent_email_id] = email_thread
                            logger.info(
                                f"Created new thread for email {message_id} sent at {timestamp}"
                            )

        # Send replies outside of the loop
        for email_thread in email_threads.values():
            # Check if we're on the last email in the
            # We don't have to use user_replies since we're checking if the bot replied to the email later
            if len(email_thread.replies) == 0:
                uid = email_thread.initial_email.imap_id
                message_id = email_thread.initial_email.message_id
                references_ids = email_thread.initial_email.references
            elif len(email_thread.replies) > 0:
                uid = email_thread.replies[-1].imap_id
                message_id = email_thread.replies[-1].message_id
                references_ids = email_thread.replies[-1].references
                logger.debug(
                    f"Most recent email in thread: {email_thread.replies[-1]} | Sent at {email_thread.replies[-1].timestamp}"
                )
                if email_thread.replies[-1].sender == bot_email:
                    logger.debug(
                        f"Most recent email in thread for email {message_id} is from the bot. Skipping..."
                    )
                    continue

            if is_newer_reference(client, message_id):
                logger.debug(f"Email {message_id} has newer references. Skipping...")
                continue

            # If only INBOX is fetched, the bot's replies may not be in EmailThread
            # Thus, we can't just do if email_thread.replies[-1].sender != bot_email
            thread = get_thread_history(client, msg_id)
            send_reply(thread, client, uid, message_id, references_ids, openai)

        ic([thread for thread in email_threads.values()])
        logger.debug(f"Keys in email_threads: {len(email_threads.keys())}")


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
    return sender != bot_email


def get_thread_history(
    client: IMAPClient, message_identifier: str | int | EmailThread
) -> list[dict]:
    """Fetch the entire thread history for the specified message ID."""

    if isinstance(message_identifier, EmailThread):
        # TODO: At this point, EmaiLThread should be the default due to it only needing to search all folders once.
        logger.warning(
            "Getting thread history from EmailThread object. If EmailThread does not include sent emails (not just INBOX fetched) this will exclude the bot's replies."
        )  # noqa E501
        thread_history = []
        thread_history.append(
            {
                "sender": message_identifier.initial_email.sender,
                "content": message_identifier.initial_email.body,
            }
        )
        for email in message_identifier.replies:
            thread_history.append(
                {"sender": email.sender, "content": email.body, "timestamp": email.timestamp}
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
                    "sender": get_sender(message),
                    "content": get_plain_email_content(message),
                    "timestamp": make_tz_aware(parsedate_to_datetime(message.get("Date"))),
                }
            )
            message = prev_message
        # Sort the thread history by timestamp
        thread_history = sorted(thread_history, key=lambda x: x["timestamp"])
        return thread_history
    else:
        raise TypeError("Invalid type for message. Must be an int, str, or EmailThread object.")


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
    references_ids = [m_id.strip() for m_id in references_header.split() if m_id.strip()]

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


def set_primary_logger(log_level):
    """Set up the primary logger with the specified log level. Output to stderr and use the format specified."""
    logger.remove()
    # ^10 is a formatting directive to center with a padding of 10
    logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> |<level>{level: ^10}</level>| <level>{message}</level>"
    logger.add(stderr, format=logger_format, colorize=True, level=log_level)


def send_reply(
    thread: list[dict],
    client: IMAPClient,
    msg_id: int,
    message_id: str,
    references_ids: list[str],
    openai: OpenAI,
    model="mistralai/mistral-7b-instruct:free",
):
    """Send a reply to the email with the specified message ID."""
    # smtp = yagmail.SMTP(user=args.smtp_username, password=args.smtp_password, host=args.smtp_host, port=args.smtp_port)
    logger.info(f"Sending reply to email {message_id}")
    thread = get_thread_history(client, msg_id)
    # Set roles deletes the sender key so we need to store the sender before calling it
    sender = thread[-1]["sender"]
    thread = set_roles(thread)
    references_ids.append(message_id)
    logger.debug(f"Thread history (message_identifier): {thread}")
    logger.debug(f"Thread history length (message_identifier): {len(thread)}")
    generated_response = openai.chat.completions.create(
        model=model,
        messages=thread,
    )
    generated_response = generated_response.choices[0].message.content
    logger.info(f"Generated response: {generated_response}")
    yag = yagmail.SMTP(
        user=args.smtp_username,
        password=args.smtp_password,
        host=args.smtp_host,
        port=int(args.smtp_port),
    )
    logger.debug(f"Sending email to {sender}")
    yag.send(
        to=sender["email"],
        subject=f"Re: {SUBJECT}",
        headers={"In-Reply-To": message_id, "References": " ".join(references_ids)},
        contents=generated_response,
    )


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
                    return markdown
        else:
            logger.debug("Message is not multipart. Getting payload as string.")
            body = message.get_payload(decode=True).decode()
            return html2text.html2text(str(body.decode("unicode_escape")))


def set_roles(thread_history: list[dict]) -> list[dict]:
    """Change all email senders to roles (assistant or user)"""
    # Change email senders to roles
    for email in thread_history:
        if email["sender"] == bot_email:
            email["role"] = "assistant"
        else:
            email["role"] = "user"
    # Delete the sender key
    for email in thread_history:
        del email["sender"]
    # Delete timestamp key
    for email in thread_history:
        if "timestamp" in email:
            del email["timestamp"]

    return thread_history


def make_tz_aware(timestamp):
    # dt = parsedate_to_datetime(timestamp)
    dt = timestamp
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


if __name__ == "__main__":
    main()
