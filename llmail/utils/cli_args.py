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

# TODO: Add argument for specific IMAP folder. Default to INBOX


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

    # General arguments
    argparser.add_argument(
        "--log-level",
        "-l",
        help="Log level",
        default=os.getenv("LOG_LEVEL") if os.getenv("LOG_LEVEL") else "INFO",
    )
    # OpenAI-compatible API arguments
    ai_api = argparser.add_argument_group("OpenAI-compatible API")
    ai_api.add_argument("--openai-api-key", help="OpenAI API key", default=os.getenv("OPENAI_API_KEY"))
    ai_api.add_argument(
        "--openai-base-url",
        help="OpenAI API endpoint",
        default=os.getenv("OPENAI_BASE_URL"),
    )
    # Email arguments
    email = argparser.add_argument_group("Email")
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

    check_required_args(["imap_host", "imap_port", "imap_username", "imap_password", "openai_api_key", "openai_base_url"], argparser)


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
