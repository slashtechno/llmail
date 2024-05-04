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
    def __init__(self, msg_id, subject, sender, date, body):
        self.msg_id = msg_id
        self.subject = subject
        self.sender = sender
        self.date = date
        self.body = body
    def __repr__(self):
        return f"Email(subject={self.subject}, sender={self.sender}"

args = None
bot_email = None

def main():
    '''Main entry point for the script.'''
    global args
    global bot_email
    args = argparser.parse_args()

    bot_email = args.imap_username

    # Set up logging
    set_primary_logger(args.log_level)
    ic(args)
    fetch_and_process_emails()
def fetch_and_process_emails():
    '''Fetch and process emails from the IMAP server.'''
    with IMAPClient(args.imap_host) as client:
        client.login(args.imap_username, args.imap_password)
        client.select_folder("INBOX")

        password_subject = f"autoreply password"
        messages = client.search(['SUBJECT', password_subject])

        email_threads = {}

        for msg_id in messages:
            msg_data = client.fetch([msg_id], ['ENVELOPE', 'BODY[]', 'RFC822.HEADER'])
            envelope = msg_data[msg_id][b'ENVELOPE']
            subject = envelope.subject.decode()
            sender = envelope.sender[0].mailbox.decode() + "@" + envelope.sender[0].host.decode()
            date = envelope.date
            in_reply_to = envelope.in_reply_to

            # Check if the email is new (not replied to by the bot yet)
            if is_most_recent_user_email(client, msg_id, sender):
                if in_reply_to and in_reply_to.decode() in email_threads:
                    # Add the reply to the existing thread
                    email_threads[in_reply_to.decode()].add_reply(Email(
                        msg_id=msg_id,
                        subject=subject,
                        sender=sender,
                        date=date,
                        body=msg_data[msg_id][b'BODY[]']
                    ))
                    logger.info(f"Added reply to thread {in_reply_to.decode()}")
                else:
                    # Create a new thread for the email
                    email_thread = EmailThread(Email(
                        msg_id=msg_id,
                        subject=subject,
                        sender=sender,
                        date=date,
                        body=msg_data[msg_id][b'BODY[]']
                    ))
                    email_threads[msg_id] = email_thread
                    logger.info(f"Created new thread for email {msg_id}")

                # Send reply if the most recent email in the thread is from the user (not the bot)
                if sender != bot_email:
                    send_reply(client, msg_id)

    ic([thread for thread in email_threads.values()])


# Function to check if an email has been read
def isNewEmail(client, msg_id):
    flags = client.get_flags([msg_id])
    return b'\\Seen' not in flags.get(msg_id, [])


def is_most_recent_user_email(client, msg_id, sender):
    # Fetch the header of the email to get the "In-Reply-To" header
    msg_data = client.fetch([msg_id], ['RFC822.HEADER'])
    headers_bytes = msg_data[msg_id][b'RFC822.HEADER']
    headers_str = headers_bytes.decode()
    headers = dict(header.split(": ", 1) for header in headers_str.split("\r\n") if ": " in header)
    timestamp = headers.get("Date")


    # Check if the email is in reply to another email and if the sender is not the bot
    logger.info(f"Checking email {msg_id} from {sender}. Date: {timestamp}")
    return sender != bot_email


def send_reply(client, msg_id):
    # Send a reply to the most recent user email in the thread
    # Example code to send a reply using IMAPClient
    client.fetch([msg_id], ['RFC822'])
    # Add code here to compose and send the reply email

def set_primary_logger(log_level):
    '''Set up the primary logger with the specified log level. Output to stderr and use the format specified.'''
    logger.remove()
    # ^10 is a formatting directive to center with a padding of 10
    logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> |<level>{level: ^10}</level>| <level>{message}</level>"
    logger.add(stderr, format=logger_format, colorize=True, level=log_level)


def send_reply(client, msg_id):
    '''Send a reply to the email with the specified message ID.'''
    logger.info("Replying not implemented yet")

if __name__ == '__main__':
    main()