import argparse
import os
import dotenv
import sys
from pathlib import Path

argparser = None

"""
For reference, Gmail's IMAP settings are:
- Hostname: imap.gmail.com
- Port: 993
- Username: Your full Gmail address
- Password: App token (when using 2FA) or perhaps your regular password (if not using 2FA ?)
"""



def set_argparse():
    global argparser

    if Path(".env").is_file():
        dotenv.load_dotenv()
        print("Loaded .env file")
    else:
        print("No .env file found")

    # Set up argparse
    argparser = argparse.ArgumentParser(
        prog="LLMail",
        description="Interact with an LLM through email.",
        epilog=":)",
    )
    # Subcommands
    subparsers = argparser.add_subparsers(
        # Dest means that the current subcommand can be accessed via args.subcommand
        dest="subcommand",
        title="Subcommands",
        )
    # Subcommand: list-folders
    _ = subparsers.add_parser("list-folders", help="List all folders in the IMAP account and exit")
    # General arguments
    argparser.add_argument(
        "--log-level",
        "-l",
        help="Log level",
        default=os.getenv("LOG_LEVEL") if os.getenv("LOG_LEVEL") else "INFO",
    )
    argparser.add_argument(
        "--watch-interval",
        "-w",
        help="Interval in seconds to check for new emails. If not set, will only check once.",
        type=int,
        default=int(os.getenv("WATCH_INTERVAL")) if os.getenv("WATCH_INTERVAL") else None,
    )
    # OpenAI-compatible API arguments
    ai_api = argparser.add_argument_group("OpenAI-compatible API")
    ai_api.add_argument(
        "--openai-api-key", help="OpenAI API key", default=os.getenv("OPENAI_API_KEY")
    )
    ai_api.add_argument(
        "--openai-base-url",
        help="OpenAI API endpoint",
        default=os.getenv("OPENAI_BASE_URL"),
    )
    ai_api.add_argument(
        "--openai-model",
        help="Model to use for the LLM",
        default=os.getenv("OPENAI_MODEL") if os.getenv("OPENAI_MODEL") else "mistralai/mistral-7b-instruct:free",
    )
    # Email arguments
    email = argparser.add_argument_group("Email")
    email.add_argument(
        "--folder",
        "-f",
        help="IMAP folder(s) to watch for new emails",
        # Argparse should append to a list if None is the default
        default=os.getenv("FOLDER").split(",") if os.getenv("FOLDER") else None,
        action="append",
    )
    email.add_argument(
        "--subject-key",
        "-s",
        help="Emails with this subject will be replied to",
        default=os.getenv("SUBJECT_KEY") if os.getenv("SUBJECT_KEY") else "llmail autoreply",
    )
    imap = email.add_argument_group("IMAP")
    imap.add_argument("--imap-host", help="IMAP server hostname", default=os.getenv("IMAP_HOST"))
    imap.add_argument("--imap-port", help="IMAP server port", default=os.getenv("IMAP_PORT"))
    imap.add_argument(
        "--imap-username",
        help="IMAP server username",
        default=os.getenv("IMAP_USERNAME"),
    )
    imap.add_argument(
        "--imap-password",
        help="IMAP server password",
        default=os.getenv("IMAP_PASSWORD"),
    )
    smtp = email.add_argument_group("SMTP")
    smtp.add_argument("--smtp-host", help="SMTP server hostname", default=os.getenv("SMTP_HOST"))
    smtp.add_argument("--smtp-port", help="SMTP server port", default=os.getenv("SMTP_PORT"))
    smtp.add_argument(
        "--smtp-username",
        help="SMTP server username",
        default=os.getenv("SMTP_USERNAME"),
    )
    smtp.add_argument(
        "--smtp-password",
        help="SMTP server password",
        default=os.getenv("SMTP_PASSWORD"),
    )
    smtp.add_argument(
        "--message-id-domain",
        help="Domain to use for Message-ID header",
        default=os.getenv("MESSAGE_ID_DOMAIN") if os.getenv("MESSAGE_ID_DOMAIN") else None,
    )

    check_required_args(
        [
            "imap_host",
            "imap_port",
            "imap_username",
            "imap_password",
            "smtp_host",
            "smtp_port",
            "smtp_username",
            "smtp_password",
            "openai_api_key",
            "openai_base_url",
        ],
        argparser,
    )


def check_required_args(required_args: list[str], argparser: argparse.ArgumentParser):
    """
    Check if required arguments are set
    Useful if using enviroment variables with argparse as default and required are mutually exclusive
    """
    for arg in required_args:
        args = argparser.parse_args()
        if getattr(args, arg) is None:
            # raise ValueError(f"{arg} is required")
            print(f"{arg} is required")
            sys.exit(1)


# This will run when this file is imported
set_argparse()
