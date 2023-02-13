"""
Syncs wiki page revisions to git commits.
"""

import argparse
import copy
import logging
import os
import pathlib
import subprocess
import uuid
from typing import Optional, Union

import praw
from praw.models.reddit.wikipage import WikiPage


# Attempt to use .env file if possible (for running locally).
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


CONFIG = {
    "log_level": os.environ.get("LOG_LEVEL", logging.INFO),
    "subreddit": os.environ.get("SUBREDDIT_NAME_TO_ACT_ON"),
    "email": os.environ.get("SUBREDDIT_COMMIT_EMAIL"),
    "auth": {
        "client_id": os.environ.get("REDDIT_CLIENT_ID"),
        "client_secret": os.environ.get("REDDIT_CLIENT_SECRET"),
        "user_agent": os.environ.get("REDDIT_USER_AGENT"),
        "username": os.environ.get("REDDIT_USERNAME"),
        "password": os.environ.get("REDDIT_USER_PASSWORD"),
        "totp_secret": os.environ.get("REDDIT_TOTP_SECRET"),  # Only set if using 2FA for the bot account.
    },
}

PERMLEVEL_MOD_ONLY = 2


reddit = None
subreddit = None
logger: logging.Logger = None


def get_reddit_instance(config_dict: dict):
    """
    Initialize a reddit instance and return it.

    :param config_dict: dict containing necessary values for authenticating
    :return: reddit instance
    """

    auth_dict = copy.copy(config_dict)
    password = config_dict["password"]
    totp_secret = config_dict.get("totp_secret")

    if totp_secret:
        logger.debug("Including two-factor authentication for authentication")
        import mintotp

        auth_dict["password"] = f"{password}:{mintotp.totp(totp_secret)}"

    logger.debug("Authenticating with reddit")
    reddit_instance = praw.Reddit(**auth_dict)
    return reddit_instance


def add_commit(file_path: pathlib.Path, commit_timestamp: int, commit_author: str, commit_message: str):
    subprocess.run(["git", "add", file_path])

    env = os.environ.copy()
    commit_email = CONFIG["email"]
    if not commit_email:
        commit_email = f"{commit_author}@{subreddit.display_name}.reddit"

    env["GIT_AUTHOR_DATE"] = str(int(commit_timestamp))
    env["GIT_AUTHOR_NAME"] = commit_author if commit_author else "[deleted]"
    env["GIT_AUTHOR_EMAIL"] = commit_email
    env["GIT_COMMITTER_DATE"] = str(int(commit_timestamp))
    env["GIT_COMMITTER_NAME"] = commit_author if commit_author else "[deleted]"
    env["GIT_COMMITTER_EMAIL"] = commit_email

    subprocess.run(["git", "commit", "-m", commit_message], env=env)


def get_last_saved_revision(file_path: pathlib.Path) -> Optional[str]:
    if not file_path.exists():
        return None

    output_bytes = subprocess.check_output(f"git log -n 1 --pretty=medium -- {file_path}".split())
    output_list = output_bytes.decode().strip().split()
    try:
        revision_uuid = uuid.UUID(output_list[-1])
    except ValueError:
        return None

    return str(revision_uuid)


def save_revision(revision: Union[dict, WikiPage]):
    # Get PRAW model from dict form if necessary.
    if isinstance(revision, dict):
        revision = revision["page"].revision(revision["id"])

    file_path = pathlib.Path(subreddit.display_name) / f"{revision.name}.md"

    # Ensure intermediate directories exist before writing to the file.
    if not file_path.parent.exists():
        os.makedirs(file_path.parent)

    with file_path.open("w") as revision_file:
        revision_file.write(revision.content_md)

    logger.debug(f"Wrote revision {revision.revision_id} to file {file_path}")

    author = revision.revision_by.name if revision.revision_by else None
    commit_message = f"{revision.reason}\n\n{revision.revision_id}" if revision.reason else revision.revision_id
    add_commit(file_path, revision.revision_date, author, commit_message)
    logger.debug(f"Completed git commit for {revision.revision_id} to file {file_path}")


def get_recent_revisions(page: WikiPage, last_revision: Optional[str]):
    # Revisions are returned most recent first so need to reverse and go from the beginning.
    if last_revision is None:
        return list(page.revisions(limit=None))[::-1]

    revision_list = []
    for revision in page.revisions(limit=None):
        # Don't include the last saved revision or older.
        if revision["id"] == last_revision:
            break
        revision_list.insert(0, revision)

    return revision_list


def _handle_full_page(
    page: WikiPage, ignore_list: Optional[list[str]] = None, include_mod: bool = True, include_unlisted: bool = True
):
    # Skip if explicitly ignored.
    if ignore_list and page.name in ignore_list:
        logger.info(f"Skipping {page.name} as it's being ignored...")
        return

    # Don't cover mod-only pages if flag's off.
    if (not include_mod) and page.mod.settings()["permlevel"] == PERMLEVEL_MOD_ONLY:
        logger.info(f"Skipping {page.name} as it's mod only...")
        return

    # Don't cover unlisted pages if flag's off.
    if (not include_unlisted) and not page.mod.settings()["listed"]:
        logger.info(f"Skipping {page.name} as it's unlisted...")
        return

    page_path = pathlib.Path(subreddit.display_name) / f"{page.name}.md"

    # Get most recent revision then update from there.
    last_revision = get_last_saved_revision(page_path)
    logger.info(f"Most recent revision for page {page.name}: {last_revision}")
    revisions = get_recent_revisions(page, last_revision)
    logger.info(f"Saving {len(revisions)} revisions for page {page.name}")

    for revision in revisions:
        save_revision(revision)


def _handle_revisions_for_page(revisions: list[dict]):
    if not revisions:
        return

    page = revisions[0]["page"]
    page_path = pathlib.Path(subreddit.display_name) / f"{page.name}.md"
    logger.info(f"Handling recent revisions for {page.name}")

    last_revision = get_last_saved_revision(page_path)

    for index, revision in enumerate(revisions):
        # If this revision is the most recent, we need to save everything after it.
        if revision["id"] == last_revision:
            revisions_to_save = revisions[index + 1 :]
            break
    # Didn't break, which means last revision is older than the list of recent revisions and we need to go back further.
    else:
        _handle_full_page(page)
        return

    for revision in revisions_to_save:
        save_revision(revision)


def main(
    page_list: Optional[list[str]] = None,
    ignore_list: Optional[list[str]] = None,
    include_full: bool = False,
    include_mod: bool = False,
    include_unlisted: bool = False,
):
    global reddit, subreddit
    logger.debug("Getting reddit instance")
    reddit = get_reddit_instance(CONFIG["auth"])
    logger.debug("Getting subreddit instance")
    subreddit = reddit.subreddit(CONFIG["subreddit"])

    subreddit_name = subreddit.display_name

    if ignore_list is None:
        ignore_list = []

    # All revisions for all pages, slowest but most broad coverage.
    if include_full and not page_list:
        logger.info(f"Getting all revisions for entire wiki of {subreddit_name}")
        for page in subreddit.wiki:
            _handle_full_page(page, ignore_list, include_mod, include_unlisted)
        return

    # All revisions for a specific set of pages.
    if include_full and page_list:
        logger.info(f"Getting all revisions for pages: {page_list}")
        for page_name in page_list:
            page = subreddit.wiki[page_name]
            _handle_full_page(page, ignore_list, include_mod, include_unlisted)
        return

    # Recent revisions for all pages, generator starts from most recent so need to reverse.
    logger.info("Getting recent wiki revisions...")
    revisions_by_page = {}
    for revision in list(subreddit.wiki.revisions())[::-1]:
        page_name = revision["page"].name
        if page_name not in revisions_by_page:
            revisions_by_page[page_name] = []
        revisions_by_page[page_name].append(revision)

    # For each page with recent revisions, see if we need to save them before handling them.
    for page_name, revisions in revisions_by_page.items():
        mod_settings = subreddit.wiki[page_name].mod.settings()
        if page_list and page_name not in page_list:
            logger.debug(f"Skipping {page_name} as it's not in the specified page list...")
            continue
        if ignore_list and page_name in ignore_list:
            logger.debug(f"Skipping {page_name} as it's being ignored...")
            continue
        if (not include_mod) and mod_settings["permlevel"] == PERMLEVEL_MOD_ONLY:
            logger.debug(f"Skipping {page_name} as it's mod only...")
            continue
        if (not include_unlisted) and not mod_settings["listed"]:
            logger.debug(f"Skipping {page_name} as it's unlisted...")
            continue
        _handle_revisions_for_page(revisions)


def _setup_logging():

    global logger

    logger = logging.getLogger("wiki_sync")
    logger.setLevel(CONFIG["log_level"])
    formatter = logging.Formatter("%(asctime)s %(levelname)07s [%(filename)s:%(lineno)d] - %(message)s")

    console_handler = logging.StreamHandler()
    console_handler.setLevel(CONFIG["log_level"])
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)


def _get_parser() -> argparse.ArgumentParser:
    new_parser = argparse.ArgumentParser(description="Archive wiki revisions as git commits.")
    new_parser.add_argument(
        "-p",
        "--pages",
        type=str,
        help="Comma-separated list of wiki page names to save, or all listed pages if * or not provided",
    )
    new_parser.add_argument("-i", "--ignore", type=str, help="Comma-separated list of wiki page names to ignore")
    new_parser.add_argument(
        "-f",
        "--full",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include all of a page's history rather than just recent updates",
    )
    new_parser.add_argument(
        "-m",
        "--mod",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include mod-only pages in archive",
    )
    new_parser.add_argument(
        "-u",
        "--unlisted",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Include unlisted pages in archive",
    )
    new_parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        default=False,
        help="Add more logging",
    )
    return new_parser


if __name__ == "__main__":
    _setup_logging()
    parser = _get_parser()
    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    pages = args.pages if args.pages != "*" else None
    if pages:
        pages = pages.split(",")

    ignore = args.ignore
    if ignore:
        ignore = ignore.split(",")

    logger.info(f"Args: {pages=}, {ignore=}, {args.full=}, {args.mod=}, {args.unlisted=}")
    main(pages, ignore, args.full, args.mod, args.unlisted)
