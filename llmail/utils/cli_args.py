import argparse
import os
import sys
from pathlib import Path

import dotenv

"""
For reference, Gmail's IMAP settings are:
- Hostname: imap.gmail.com
- Port: 993
- Username: Your full Gmail address
- Password: App token (when using 2FA) or perhaps your regular password (if not using 2FA ?)
"""


def set_argparse():
    global args

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
        "--watch-interval",
        "-w",
        help="Interval in seconds to check for new emails. If set to 0, will only check once.",
        type=int,
        default=(int(os.getenv("WATCH_INTERVAL")) if os.getenv("WATCH_INTERVAL") else None),
    )
    # OpenAI-compatible API arguments
    ai_api = argparser.add_argument_group("OpenAI-compatible API")
    ai_api.add_argument(
        "--llm-provider",
        help="LLM provider provider",
        choices=["openai-like", "ollama"],
        default=os.getenv("LLM_PROVIDER") if os.getenv("LLM_PROVIDER") else "openai-like",
    )
    ai_api.add_argument(
        "--llm-api-key", help="LLM provider API key", default=os.getenv("LLM_API_KEY")
    )
    ai_api.add_argument(
        "--llm-base-url",
        help="Base URL for the LLM provider",
        default=os.getenv("LLM_BASE_URL"),
    )
    ai_api.add_argument(
        "--llm-model",
        help="Model to use for the LLM",
        default=(
            os.getenv("LLM_MODEL")
            if os.getenv("LLM_MODEL")
            else "mistralai/mistral-7b-instruct:free"
        ),
    )
    # AI-related arguments
    ai = argparser.add_argument_group("AI")
    argparser.add_argument(
        "--exa-api-key",
        help="Exa API key for searching with Exa (disables DuckDuckGo)",
        default=os.getenv("EXA_API_KEY") if os.getenv("EXA_API_KEY") else None,
    )
    ai.add_argument(
        "--scrapable-url",
        help="URL(s) that can be scraped for information",
        default=(os.getenv("SCRAPABLE_URL").split(",") if os.getenv("SCRAPABLE_URL") else None),
        action="append",
    )
    ai.add_argument(
        "--no-tools",
        help="Do not use any tools via function calling",
        action="store_true",
        default=(
            True
            if (
                os.getenv("NO_TOOLS")
                and os.getenv("NO_TOOLS").lower() == "true"
                and os.getenv("NO_TOOLS").lower() != "false"
            )
            else False
        ),
    )
    ai.add_argument(
        "--system-prompt",
        help="Prepend this to the message history sent to the LLM as a message from the system role",
        default=os.getenv("SYSTEM_PROMPT") if os.getenv("SYSTEM_PROMPT") else None,
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
        default=(os.getenv("SUBJECT_KEY") if os.getenv("SUBJECT_KEY") else "llmail autoreply"),
    )
    email.add_argument(
        "--alias",
        help="Name to use in the 'From' in addition to the email address",
        default=os.getenv("ALIAS") if os.getenv("ALIAS") else "LLMail",
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
        default=(os.getenv("MESSAGE_ID_DOMAIN") if os.getenv("MESSAGE_ID_DOMAIN") else None),
    )

    # Debuggiongm arguments
    debug = argparser.add_argument_group("Debugging")
    debug.add_argument(
        "--log-level",
        "-l",
        help="Log level",
        default=os.getenv("LOG_LEVEL") if os.getenv("LOG_LEVEL") else "INFO",
    )
    debug.add_argument(
        "--redact-email-addresses",
        help="Replace email addresses with '[redacted]' in logs",
        action="store_true",
        default=(
            True
            if (
                os.getenv("REDACT_EMAIL_ADDRESSES")
                and os.getenv("REDACT_EMAIL_ADDRESSES").lower() == "true"
                and os.getenv("REDACT_EMAIL_ADDRESSES").lower() != "false"
            )
            else False
        ),
    )
    debug.add_argument(
        "--show-tool-calls",
        help="Pass show_tool_calls=True to phidata",
        action="store_true",
        default=(
            True
            if (
                os.getenv("SHOW_TOOL_CALLS")
                and os.getenv("SHOW_TOOL_CALLS").lower() == "true"
                and os.getenv("SHOW_TOOL_CALLS").lower() != "false"
            )
            else False
        ),
    )
    debug.add_argument(
        "--phidata-debug",
        help="Pass debug=True to phidata",
        action="store_true",
        default=(
            True
            if (
                os.getenv("PHIDATA_DEBUG")
                and os.getenv("PHIDATA_DEBUG").lower() == "true"
                and os.getenv("PHIDATA_DEBUG").lower() != "false"
            )
            else False
        ),
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
            # "llm_api_key",
            # "llm_base_url",
        ],
        argparser,
    )
    args = argparser.parse_args()
    # Setting bot_email instead of using imap_username directly in case support is needed for imap_username and bot_email being different
    global bot_email
    bot_email = args.imap_username


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
