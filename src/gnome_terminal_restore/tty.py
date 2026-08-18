"""Writing a terminal title to a tab's pty.

An OSC 0 sequence sets the window/tab title and produces no visible output, so
it can be used as a temporary identifier without disturbing what is on screen.
Only the terminal emulator sees it; it is never delivered to the shell as input.
"""
import os

OSC_TITLE = "\033]0;%s\007"


def set_title(tty, title):
    """Best-effort title write. Never raises: a tab may close at any moment."""
    if not tty or not tty.startswith("/dev/pts/"):
        return False
    try:
        fd = os.open(tty, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK)
    except OSError:
        return False
    try:
        os.write(fd, (OSC_TITLE % title).encode("utf-8", "replace"))
        return True
    except OSError:
        return False
    finally:
        os.close(fd)
