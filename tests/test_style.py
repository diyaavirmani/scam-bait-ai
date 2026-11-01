"""Style rule: no em dashes and no emojis in tracked files (testset excluded) or the last commit message."""
import re
import subprocess

BANNED = r"\x{2014}|[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{1F000}-\x{1F2FF}\x{FE0F}]"


def _run(args: list[str]) -> str:
    return subprocess.run(args, capture_output=True, text=True).stdout


def test_no_em_dash_or_emoji_in_tracked_files():
    assert _run(["git", "grep", "-nP", BANNED, "--", ".", ":!testset"]) == ""


def test_no_em_dash_or_emoji_in_last_commit_message():
    msg = _run(["git", "log", "-1", "--format=%B"])
    assert re.findall(r"[\u2014\U0001F300-\U0001FAFF\u2600-\u27BF]", msg) == []
