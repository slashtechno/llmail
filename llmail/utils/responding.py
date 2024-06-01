import imaplib
import re
from email import message_from_bytes
from email.utils import make_msgid
from ssl import SSLError

import yagmail
from imapclient import IMAPClient
from openai import OpenAI
from phi.assistant import Assistant
from phi.llm.openai.like import OpenAILike


# Uses utils/__init__.py to import from utils/logging.py and utils/cli_args.py respectively
from llmail.utils import logger, args, bot_email

# Import files from utils/
from llmail.utils import tracking

# Import utilites from utils/utils.py
from llmail.utils.utils import get_plain_email_content

email_threads = {}


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
        folders = args.folder if args.folder else [folder[2] for folder in client.list_folders()]
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
                # It seems this will throw a KeyError if an email is sent while this for loop is running. However, I think the real cause is when an email is deleted (via another client) while testing the code
                msg_data = client.fetch([msg_id], ["ENVELOPE", "BODY[]", "RFC822.HEADER"])
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
                sender = tracking.get_sender(message)["email"]
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
                    parent_email_id = tracking.get_top_level_email(client, msg_id, message_id)

                    # Unless EmailThread is being used for threads, this is mainly useful for debugging
                    if parent_email_id in email_threads:
                        # Add the reply to the existing thread
                        email_threads[parent_email_id].add_reply(
                            tracking.Email(
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
                            email_thread = tracking.EmailThread(
                                tracking.Email(
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
            elif len(email_thread.replies) > 0 and email_thread.replies[-1].sender != bot_email:
                logger.debug(
                    f"Last email in thread for email {message_id} is from {email_thread.replies[-1].sender}"
                )
                message_id = email_thread.replies[-1].message_id
                msg_id = email_thread.replies[-1].imap_id
                references_ids = email_thread.replies[-1].references
            elif len(email_thread.replies) > 0 and email_thread.replies[-1].sender == bot_email:
                logger.debug(f"Last email in thread for email {message_id} is from the bot")
                continue
            else:
                ValueError("Invalid email thread")
            send_reply(
                thread=tracking.get_thread_history(client, email_thread),
                subject=subject,
                alias=args.alias,
                client=client,
                msg_id=msg_id,
                message_id=message_id,
                references_ids=references_ids,
                assistant=Assistant(
                    llm=OpenAILike(
                        model=args.openai_model,
                        api_key=openai.api_key,
                        base_url=args.openai_base_url,
                    )
                ),
                system_prompt=system_prompt,
            )

        logger.info(f"Current number of email threads: {len(email_threads.keys())}")


def send_reply(
    thread: list[dict],
    subject: str,
    alias: str,
    client: IMAPClient,
    msg_id: int,
    message_id: str,
    references_ids: list[str],
    assistant: Assistant,
    system_prompt: str,
):
    """Send a reply to the email with the specified message ID."""
    # Set roles deletes the sender key so we need to store the sender before calling it
    sender = thread[-1]["sender"]
    thread = set_roles(thread)
    if system_prompt:
        thread.insert(0, {"role": "system", "content": system_prompt})
    references_ids.append(message_id)
    generated_response = assistant.run(
        messages=thread, stream=False
    )
    logger.debug(f"Generated response: {generated_response}")
    yag = yagmail.SMTP(
        user={args.smtp_username: alias} if alias else args.smtp_username,
        password=args.smtp_password,
        host=args.smtp_host,
        port=int(args.smtp_port),
    )
    try:
        yag.send(
            to=sender,
            subject=f"Re: {subject}" if not subject.startswith("Re: ") else subject,
            # subject=f"Re: {subject}",
            headers={"In-Reply-To": message_id, "References": " ".join(references_ids)},
            contents=generated_response,
            message_id=make_msgid(
                domain=args.message_id_domain if args.message_id_domain else "llmail"
            ),
        )
    except SSLError as e:
        if "WRONG_VERSION_NUMBER" in str(e):
            logger.info("SSL error occurred. Trying to connect with starttls=True instead.")
            yag = yagmail.SMTP(
                user={args.smtp_username: alias} if alias else args.smtp_username,
                password=args.smtp_password,
                host=args.smtp_host,
                port=int(args.smtp_port),
                smtp_starttls=True,
                smtp_ssl=False,
            )
            yag.send(
                to=sender,
                subject=f"Re: {subject}" if not subject.startswith("Re: ") else subject,
                # subject=f"Re: {subject}",
                headers={"In-Reply-To": message_id, "References": " ".join(references_ids)},
                contents=generated_response,
                message_id=make_msgid(
                    domain=args.message_id_domain if args.message_id_domain else "llmail"
                ),
            )
        else:
            raise e
    # thread_from_msg_id = get_thread_history(client, msg_id)
    # logger.debug(f"Thread history (message_identifier): {thread_from_msg_id}")
    # logger.debug(f"Thread history length (message_identifier): {len(thread_from_msg_id)}")
    # thread_from_object = get_thread_history(client, email_threads[list(email_threads.keys())[-1]])
    # logger.debug(f"Thread history (EmailThread object): {thread_from_object}")
    # logger.debug(f"Thread history length (EmailThread object): {len(thread_from_object)}")
    logger.info(f"Sending reply to email {message_id} to {sender}")
    logger.debug(f"Thread history: {thread}")
    logger.debug(f"Thread history length: {len(thread)}")


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
