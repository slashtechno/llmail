from sys import stderr

from icecream import ic
from imapclient import IMAPClient
from loguru import logger

from llmail.utils.cli_args import argparser



args = None

def main():
    '''Main entry point for the script.'''
    global args
    args = argparser.parse_args()

    # Set up logging
    set_primary_logger(args.log_level)
    ic(args)
    fetch_and_process_emails()

def fetch_and_process_emails():
    '''Fetch and process emails from the IMAP server.'''
    with IMAPClient(args.imap_host) as client:
        client.login(args.imap_username, args.imap_password)
        client.select_folder("INBOX", readonly=True)
        # logger.debug(f"All folders: {client.list_folders()}")

def set_primary_logger(log_level):
    '''Set up the primary logger with the specified log level. Output to stderr and use the format specified.'''
    logger.remove()
    # ^10 is a formatting directive to center with a padding of 10
    logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> |<level>{level: ^10}</level>| <level>{message}</level>"
    logger.add(stderr, format=logger_format, colorize=True, level=log_level)
