import time
from imapclient import IMAPClient
from llmail.utils import logger, args, responding


def main():
    """Main entry point for the script."""
    match args.subcommand:
        case "list-folders":
            with IMAPClient(args.imap_host) as client:
                client.login(args.imap_username, args.imap_password)
                folders = client.list_folders()
                for folder in folders:
                    print(folder[2])
        case None:
            logger.debug(args)
            logger.info(f'Looking for emails that match the subject key "{args.subject_key}"')
            if args.watch_interval:
                logger.info(f"Watching for new emails every {args.watch_interval} seconds")
                while True:
                    responding.fetch_and_process_emails(
                        look_for_subject=args.subject_key,
                        alias=args.alias,
                        system_prompt=args.system_prompt,
                    )
                    time.sleep(args.watch_interval)
                    # **EMPTY THREADS**
                    responding.email_threads = {}
            else:
                responding.fetch_and_process_emails(
                    look_for_subject=args.subject_key,
                    alias=args.alias,
                    system_prompt=args.system_prompt,
                )


if __name__ == "__main__":
    main()
