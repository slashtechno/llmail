from email import message_from_bytes
from email.message import Message
import yagmail
import html2text
from imapclient import IMAPClient
import imaplib
from loguru import logger
from openai import OpenAI
from email.utils import getaddresses, parsedate_to_datetime, make_msgid
from datetime import timezone
import time
import re


from llmail.utils.cli_args import argparser
from llmail.utils.utils import set_primary_logger


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


args = None
bot_email = None

email_threads = {}


def main():
    """Main entry point for the script."""
    global args
    global bot_email
    global email_threads
    args = argparser.parse_args()

    match args.subcommand:
        case "list-folders":
            with IMAPClient(args.imap_host) as client:
                client.login(args.imap_username, args.imap_password)
                folders = client.list_folders()
                for folder in folders:
                    print(folder[2])
        case None:
            bot_email = args.imap_username

            # Set up logging
            set_primary_logger(args.log_level, args.redact_email_addresses)
            logger.debug(args)
            if args.watch_interval:
                logger.info(
                    f"Watching for new emails every {args.watch_interval} seconds"
                )
                while True:
                    fetch_and_process_emails(
                        look_for_subject=args.subject_key,
                        alias=args.alias,
                        system_prompt=args.system_prompt,
                    )
                    time.sleep(args.watch_interval)
                    # **EMPTY THREADS**
                    email_threads = {}
            else:
                fetch_and_process_emails(
                    look_for_subject=args.subject_key,
                    alias=args.alias,
                    system_prompt=args.system_prompt,
                )


def fetch_and_process_emails(
    look_for_subject: str,
    alias: str = None,
    system_prompt: str = None,
):
    """Fetch and process emails from the IMAP server."""
    global email_threads
    openai = OpenAI(api_key=args.openai_api_key, base_url=args.openai_base_url)
    with IMAPClient(args.imap_host) as client:
        client.login(args.imap_username, args.imap_password)

        email_threads = {}
        folders = (
            args.folder
            if args.folder
            else [folder[2] for folder in client.list_folders()]
        )
        # for folder in client.list_folders():
        # Disabling fetching from all folders due it not being inefficient
        # Instead, just fetch from INBOX and get the threads later
        for folder in folders:
            try:
                client.select_folder(folder)
            # If the error is imaplib.IMAP4.error: select failed:...
            except imaplib.IMAP4.error:
                logger.debug(f"Failed to select folder {folder[2]}. Skipping...")
                continue
            # Might be smart to also search for forwarded emails
            messages = client.search(
                [
                    "OR",
                    "SUBJECT",
                    look_for_subject,
                    "SUBJECT",
                    f"Re: {look_for_subject}",
                ]
            )
            for msg_id in messages:
                # TODO: It seems this will throw a KeyError if an email is sent while this for loop is running. May have been fixed by emptying email_threads at the end of the while loop? This should be tested again to confirm
                msg_data = client.fetch(
                    [msg_id], ["ENVELOPE", "BODY[]", "RFC822.HEADER"]
                )
                envelope = msg_data[msg_id][b"ENVELOPE"]
                subject = envelope.subject.decode()
                # Use regex to verify that the subject optionally starts with "Fwd: " or "Re: " and then the intended subject (nothing case-sensitive)
                # re.escape is used to escape any special characters in the subject
                if not re.match(
                    r"^(Fwd: ?|Re: ?)*" + re.escape(look_for_subject) + r"$",
                    subject,
                    re.IGNORECASE,
                ):
                    logger.warning(
                        f"Skipping email with subject '{subject}' as it does not match the intended subject"
                    )
                    continue
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
                            logger.debug(
                                f"Created new thread for email {message_id} sent at {timestamp}"
                            )

        logger.debug(email_threads)
        # Check if there are any emails wherein the last email in the thread is a user email
        # If so, send a reply
        for message_id, email_thread in email_threads.items():
            # Check if the email only has an initial email
            # If it does, then there won't be any replies and an index error will occur
            if len(email_thread.replies) == 0:
                logger.debug(f"No replies in thread for email {message_id}")
                message_id = email_thread.initial_email.message_id
                msg_id = email_thread.initial_email.imap_id
                references_ids = email_thread.initial_email.references
            elif (
                len(email_thread.replies) > 0
                and email_thread.replies[-1].sender != bot_email
            ):
                logger.debug(
                    f"Last email in thread for email {message_id} is from {email_thread.replies[-1].sender}"
                )
                message_id = email_thread.replies[-1].message_id
                msg_id = email_thread.replies[-1].imap_id
                references_ids = email_thread.replies[-1].references
            elif (
                len(email_thread.replies) > 0
                and email_thread.replies[-1].sender == bot_email
            ):
                logger.debug(
                    f"Last email in thread for email {message_id} is from the bot"
                )
                continue
            else:
                ValueError("Invalid email thread")
            send_reply(
                thread=get_thread_history(client, email_thread),
                subject=subject,
                alias=args.alias,
                client=client,
                msg_id=msg_id,
                message_id=message_id,
                references_ids=references_ids,
                openai=openai,
                system_prompt=system_prompt,
                model=args.openai_model,
            )

        logger.info (f"Current number of email threads: {len(email_threads.keys())}")


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


def send_reply(
    thread: list[dict],
    subject: str,
    alias: str,
    client: IMAPClient,
    msg_id: int,
    message_id: str,
    references_ids: list[str],
    openai: OpenAI,
    system_prompt: str,
    model: str,
):
    """Send a reply to the email with the specified message ID."""
    # Set roles deletes the sender key so we need to store the sender before calling it
    sender = thread[-1]["sender"]
    thread = set_roles(thread)
    if system_prompt:
        thread.insert(0, {"role": "system", "content": system_prompt})
    references_ids.append(message_id)
    generated_response = openai.chat.completions.create(
        model=model,
        messages=thread,
    )
    generated_response = generated_response.choices[0].message.content
    logger.debug(f"Generated response: {generated_response}")
    yag = yagmail.SMTP(
        user={args.smtp_username: alias} if alias else args.smtp_username,
        password=args.smtp_password,
        host=args.smtp_host,
        port=int(args.smtp_port),
    )
    yag.send(
        to=sender,
        # subject=f"Re: {subject}" if not subject.startswith("Re: ") else subject,
        subject=f"Re: {subject}",
        headers={"In-Reply-To": message_id, "References": " ".join(references_ids)},
        contents=generated_response,
        message_id=make_msgid(
            domain=args.message_id_domain if args.message_id_domain else "llmail"
        ),
    )
    # thread_from_msg_id = get_thread_history(client, msg_id)
    # logger.debug(f"Thread history (message_identifier): {thread_from_msg_id}")
    # logger.debug(f"Thread history length (message_identifier): {len(thread_from_msg_id)}")
    # thread_from_object = get_thread_history(client, email_threads[list(email_threads.keys())[-1]])
    # logger.debug(f"Thread history (EmailThread object): {thread_from_object}")
    # logger.debug(f"Thread history length (EmailThread object): {len(thread_from_object)}")
    logger.info(f"Sending reply to email {message_id} to {sender}")
    logger.debug(f"Thread history: {thread}")
    logger.debug(f"Thread history length: {len(thread)}")


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
                    logger.debug(
                        "UnicodeDecodeError occurred. Trying to get payload as string."
                    )
                    body = str(part.get_payload())
                if content_type == "text/plain":
                    markdown = html2text.html2text(
                        str(body.decode("unicode_escape"))
                    ).strip()
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
