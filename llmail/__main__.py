from sys import stderr

from icecream import ic
from imapclient import IMAPClient
from loguru import logger

from llmail.utils.cli_args import argparser


class EmailThread:
    def __init__(self, initial_email):
        self.initial_email = initial_email
        self.replies = []

    def add_reply(self, reply_email):
        self.replies.append(reply_email)

    def __repr__(self):
        return f"EmailThread(initial_email={self.initial_email}, replies={self.replies})"


class Email:
    def __init__(self, imap_id, message_id, subject, sender, date, body):
        self.imap_id = imap_id
        self.message_id = message_id
        self.subject = subject
        self.sender = sender
        self.date = date
        self.body = body

    def __repr__(self):
        return f"Email(imap_id={self.imap_id}, message_id={self.message_id}, subject={self.subject}, sender={self.sender}, date={self.date})"


args = None
bot_email = None


def main():
    """Main entry point for the script."""
    global args
    global bot_email
    args = argparser.parse_args()

    bot_email = args.imap_username

    # Set up logging
    set_primary_logger(args.log_level)
    ic(args)
    fetch_and_process_emails()


def fetch_and_process_emails():
    """Fetch and process emails from the IMAP server."""
    with IMAPClient(args.imap_host) as client:
        client.login(args.imap_username, args.imap_password)
        client.select_folder("INBOX")

        password_subject = f"autoreply password"
        messages = client.search(["SUBJECT", password_subject])

        email_threads = {}

        for msg_id in messages:
            msg_data = client.fetch([msg_id], ["ENVELOPE", "BODY[]", "RFC822.HEADER"])
            envelope = msg_data[msg_id][b"ENVELOPE"]
            subject = envelope.subject.decode()
            sender = envelope.sender[0].mailbox.decode() + "@" + envelope.sender[0].host.decode()
            date = envelope.date
            headers_bytes = msg_data[msg_id][b"RFC822.HEADER"]
            headers_str = headers_bytes.decode("utf-8")  # Assuming UTF-8 encoding
            headers_list = [line.split(": ", 1) for line in headers_str.split("\r\n") if ": " in line]
            headers = {key.strip(): value.strip() for key, value in headers_list}

            # Extract the Message-ID header
            message_id_header = headers.get("Message-ID")
            # No need to decode the message ID header since it's already a string
            message_id = message_id_header if message_id_header else msg_id

            # Check if the email is new (not replied to by the bot yet)
            if is_most_recent_user_email(client, msg_id, sender):
                # Put this as message_id so the key for email_threads is the top-level email
                parent_email_id = get_top_level_email(client, msg_id, message_id)

                if parent_email_id in email_threads:
                    # Add the reply to the existing thread
                    email_threads[parent_email_id].add_reply(
                        Email(
                            imap_id=msg_id,
                            message_id=message_id,
                            subject=subject,
                            sender=sender,
                            date=date,
                            body=msg_data[msg_id][b"BODY[]"],
                        )
                    )
                    logger.debug(f"Added message {message_id} to existing thread for email {parent_email_id}")
                else:
                    # Create a new thread for the email
                    email_thread = EmailThread(
                        Email(
                            imap_id=msg_id,
                            message_id=message_id,
                            subject=subject,
                            sender=sender,
                            date=date,
                            body=msg_data[msg_id][b"BODY[]"],
                        )
                    )
                    email_threads[parent_email_id] = email_thread
                    logger.info(f"Created new thread for email {message_id} sent at {date}")

    # Send replies outside of the loop
    for email_thread in email_threads.values():
        most_recent_imap_id = email_thread.replies[-1].imap_id
        most_recent_message_id = email_thread.replies[-1].message_id
        send_reply(client, most_recent_imap_id, most_recent_message_id)
    ic([thread for thread in email_threads.values()])
    logger.debug(f"Keys in email_threads: {len(email_threads.keys())}")


# Function to check if an email has been read
def is_new_email(client, msg_id):
    flags = client.get_flags([msg_id])
    return b"\\Seen" not in flags.get(msg_id, [])


def is_most_recent_user_email(client, msg_id, sender):
    # Fetch the header of the email to get the "In-Reply-To" header
    msg_data = client.fetch([msg_id], ["RFC822.HEADER"])
    headers_bytes = msg_data[msg_id][b"RFC822.HEADER"]
    headers_str = headers_bytes.decode()
    headers = dict(header.split(": ", 1) for header in headers_str.split("\r\n") if ": " in header)
    timestamp = headers.get("Date")
    logger.debug(f"Checking if email {msg_id} from {sender} sent on {timestamp} is most recent user email")
    return sender != bot_email


def get_top_level_email(client, msg_id, message_id=None):
    """Get the top-level email in the thread for the specified message ID (IMAP)"""
    message_id = msg_id if message_id is None else message_id
    msg_data = client.fetch([msg_id], ["RFC822.HEADER"])
    headers_bytes = msg_data[msg_id][b"RFC822.HEADER"]
    headers_str = headers_bytes.decode()
    headers_list = [line.split(": ", 1) for line in headers_str.split("\r\n") if ": " in line]
    headers = {key.strip(): value.strip() for key, value in headers_list}

    # Extract the References header and split it into individual message IDs
    references_header = headers.get("References", "")
    references_ids = [msg_id.strip() for msg_id in references_header.split() if msg_id.strip()]

    # Extract the first message ID, which represents the top-level email in the thread
    # If it doesn't exist, use the current message ID. Not msg_id since msg_id is only for IMAP
    top_level_email_id = references_ids[0] if references_ids else message_id
    return top_level_email_id


def set_primary_logger(log_level):
    """Set up the primary logger with the specified log level. Output to stderr and use the format specified."""
    logger.remove()
    # ^10 is a formatting directive to center with a padding of 10
    logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> |<level>{level: ^10}</level>| <level>{message}</level>"
    logger.add(stderr, format=logger_format, colorize=True, level=log_level)


def send_reply(client, msg_id, message_id=None):
    """Send a reply to the email with the specified message ID."""
    message_id = msg_id if message_id is None else message_id
    logger.debug(f"Sending reply to email {message_id}")
    logger.error("Replying not implemented yet")


if __name__ == "__main__":
    main()
