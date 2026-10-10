"""Reading terminal state out of /proc.

GNOME Terminal runs every window and tab of a session inside a single
``gnome-terminal-server`` process, so each tab is visible here only as a direct
child process (the shell). That gives us the working directory reliably, but
not which window a tab belongs to -- see :mod:`gnome_terminal_restore.a11y`.
"""
import os

SERVER_EXE = "gnome-terminal-server"
_SHELLS = ("bash", "sh", "zsh", "fish", "dash", "ksh", "tcsh", "csh")


def _iter_pids():
    for entry in os.listdir("/proc"):
        if entry.isdigit():
            yield int(entry)


def _exe_name(pid):
    try:
        return os.path.basename(os.readlink("/proc/%d/exe" % pid))
    except OSError:
        return None


def server_pids():
    """PIDs of every running gnome-terminal-server."""
    return [pid for pid in _iter_pids() if _exe_name(pid) == SERVER_EXE]


def open_tab_count():
    """How many tabs (shells) every terminal server has open right now."""
    return sum(len(children(server)) for server in server_pids())


def children(pid):
    try:
        with open("/proc/%d/task/%d/children" % (pid, pid)) as handle:
            return [int(x) for x in handle.read().split()]
    except OSError:
        return []


def read_link(pid, what):
    try:
        return os.readlink("/proc/%d/%s" % (pid, what))
    except OSError:
        return None


def environ(pid):
    """A process's environment *as of exec time*.

    The kernel snapshots this when the process starts; a variable exported later
    (``source .venv/bin/activate`` in a running shell) never appears here. That is
    why the shell hook exists.
    """
    try:
        with open("/proc/%d/environ" % pid, "rb") as handle:
            raw = handle.read()
    except OSError:
        return {}
    env = {}
    for item in raw.split(b"\0"):
        if b"=" in item:
            key, _, value = item.partition(b"=")
            env[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return env


def _ppid(pid):
    with open("/proc/%d/stat" % pid) as handle:
        # the comm field may contain spaces and parentheses, so split after the last ')'
        return int(handle.read().rsplit(")", 1)[1].split()[1])


def own_process_chain():
    """Our own PID and ancestors, so a tab never records this tool as its command."""
    chain, current = set(), os.getpid()
    while current > 1:
        chain.add(current)
        try:
            current = _ppid(current)
        except (OSError, IndexError, ValueError):
            break
    return chain


def cmdline(pid):
    try:
        with open("/proc/%d/cmdline" % pid, "rb") as handle:
            return handle.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
    except OSError:
        return ""


def foreground_command(pid, exclude=()):
    """What the tab is actually running: its deepest descendant process.

    Returns '' when the tab is sitting at a bare shell prompt.
    """
    current = pid
    while True:
        kids = [k for k in children(current) if k not in exclude]
        if not kids:
            break
        current = kids[0]
    if current == pid:
        return ""
    return cmdline(current)


def is_shell(command):
    if not command:
        return True
    return os.path.basename(command.split(" ")[0]) in _SHELLS
