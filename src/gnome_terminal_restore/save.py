"""Take a snapshot of the current GNOME Terminal layout."""
import argparse
import json
import os
import signal
import sys
import time

from . import __version__
from . import a11y, paths, procs
from .tty import set_title

SNAPSHOT_VERSION = 1
GROUPING_TIMEOUT = 20


def live_state(pid):
    """Per-tab state written by the shell hook.

    This is the only source that sees an environment activated *after* the shell
    started, which is the normal case for a virtualenv.
    """
    try:
        with open(os.path.join(paths.live_dir(), str(pid))) as handle:
            fields = handle.read().rstrip("\n").split("\t")
    except OSError:
        return {}
    fields += [""] * (4 - len(fields))
    return {
        "cwd": fields[0],
        "venv": fields[1],
        "conda_env": fields[2],
        "conda_prefix": fields[3],
    }


def collect_tabs():
    """Every open tab, with its directory, environment and running command."""
    own = procs.own_process_chain()
    tabs = []
    for server in procs.server_pids():
        for pid in procs.children(server):
            cwd = procs.read_link(pid, "cwd")
            if not cwd:
                continue
            env = procs.environ(pid)
            hook = live_state(pid)
            tabs.append(
                {
                    "pid": pid,
                    "tty": procs.read_link(pid, "fd/0"),
                    "cwd": hook.get("cwd") or cwd,
                    # the hook wins; /proc/environ only knows what was set at exec time
                    "venv": hook.get("venv") or env.get("VIRTUAL_ENV", ""),
                    "conda_env": hook.get("conda_env") or env.get("CONDA_DEFAULT_ENV", ""),
                    "conda_prefix": hook.get("conda_prefix") or env.get("CONDA_PREFIX", ""),
                    "cmd": procs.foreground_command(pid, exclude=own),
                    "has_hook": bool(hook),
                }
            )
    return tabs


class _Timeout(Exception):
    pass


def _group(tabs):
    """Group tabs into windows. Returns True if real grouping was determined."""

    def on_alarm(_signum, _frame):
        raise _Timeout()

    previous = signal.signal(signal.SIGALRM, on_alarm)
    signal.alarm(GROUPING_TIMEOUT)
    try:
        atspi = a11y.load_atspi()
        a11y.group_tabs(tabs, atspi, set_title)
        return True
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def build_snapshot(tabs, grouped):
    windows = {}
    for tab in tabs:
        windows.setdefault(tab["window"], []).append(tab)
    keys = ("cwd", "venv", "conda_env", "conda_prefix", "cmd", "has_hook")
    return {
        "version": SNAPSHOT_VERSION,
        "saved_at": int(time.time()),
        "grouped": grouped,
        "windows": [
            [{key: tab[key] for key in keys} for tab in sorted(windows[index], key=lambda t: t["tab"])]
            for index in sorted(windows)
        ],
    }


def write_snapshot(snapshot):
    """Write atomically, keeping the previous snapshot as a fallback."""
    target = paths.snapshot_path()
    os.makedirs(os.path.dirname(target), exist_ok=True)
    if os.path.exists(target):
        os.replace(target, paths.previous_snapshot_path())
    tmp = target + ".tmp"
    with open(tmp, "w") as handle:
        json.dump(snapshot, handle, indent=1)
        handle.write("\n")
    os.replace(tmp, target)


def prune_live_state(tabs):
    alive = {str(tab["pid"]) for tab in tabs}
    try:
        for name in os.listdir(paths.live_dir()):
            if name not in alive:
                os.unlink(os.path.join(paths.live_dir(), name))
    except OSError:
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gt-save", description="Snapshot the current GNOME Terminal layout."
    )
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress the summary line")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = parser.parse_args(argv)

    tabs = collect_tabs()
    if not tabs:
        # No terminal open: keep whatever snapshot we already have rather than
        # replacing a good layout with an empty one.
        return 0

    grouped = False
    try:
        grouped = _group(tabs)
    except Exception as exc:  # never let grouping failure cost us the snapshot
        print(
            "gt-save: window grouping unavailable (%s); saving as a single window" % exc,
            file=sys.stderr,
        )
    if not grouped:
        for index, tab in enumerate(tabs):
            tab["window"], tab["tab"] = 0, index

    snapshot = build_snapshot(tabs, grouped)
    write_snapshot(snapshot)
    prune_live_state(tabs)

    if not args.quiet and sys.stdout.isatty():
        count = sum(len(window) for window in snapshot["windows"])
        print(
            "saved %d tab(s) across %d window(s) -> %s"
            % (count, len(snapshot["windows"]), paths.snapshot_path())
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
