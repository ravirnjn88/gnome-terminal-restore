"""Recovering the window -> tab structure through the accessibility tree.

GNOME Terminal exposes no API for "which window is this tab in", and on Wayland
there is no per-tab ``WINDOWID`` either. The accessibility (AT-SPI) tree *does*
model the real structure: one ``frame`` per window, each containing a
``page tab list`` whose children are that window's tabs, in order.

The tree does not expose process IDs, so tabs are matched to shells by briefly
setting each tab's title to a unique tag (an OSC escape written to the tab's
pty, which produces no visible output), reading the tree, then writing the
original titles back.
"""
import time

TAG_PREFIX = "GTSNAP-"
TAG_ATTEMPTS = 8
TAG_SETTLE = 0.2


class AccessibilityUnavailable(RuntimeError):
    """AT-SPI is missing or the terminal exports no accessible tree."""


def load_atspi():
    try:
        import gi

        gi.require_version("Atspi", "2.0")
        from gi.repository import Atspi
    except (ImportError, ValueError) as exc:  # pragma: no cover - environment specific
        raise AccessibilityUnavailable(str(exc))
    return Atspi


def read_structure(atspi):
    """Return ``[(frame_title, [tab_label, ...]), ...]`` for every terminal window."""
    windows = []
    desktop = atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app is None or "gnome-terminal" not in (app.get_name() or ""):
            continue
        for j in range(app.get_child_count()):
            frame = app.get_child_at_index(j)
            if frame is None or frame.get_role_name() != "frame":
                continue
            windows.append((frame.get_name() or "", _tab_labels(frame)))
    return windows


def _tab_labels(node, out=None):
    if out is None:
        out = []
    for index in range(node.get_child_count()):
        child = node.get_child_at_index(index)
        if child is None:
            continue
        if child.get_role_name() == "page tab list":
            for tab_index in range(child.get_child_count()):
                tab = child.get_child_at_index(tab_index)
                out.append(tab.get_name() if tab else "")
        else:
            _tab_labels(child, out)
    return out


def effective_labels(window):
    """Tab labels for a window, falling back to the frame title.

    A window with a single tab has no populated tab list, so its frame title is
    that one tab's title.
    """
    frame_title, labels = window
    if not any(labels):
        return [frame_title]
    return labels


def group_tabs(tabs, atspi, set_title_fn, sleep=time.sleep):
    """Assign ``window`` and ``tab`` indices to each tab dict, in place.

    ``tabs`` entries need ``pid`` and ``tty`` keys.

    Tagging is retried because applications that manage their own title (tmux,
    Claude Code, some TUIs) can overwrite the tag before it is read. Anything
    still unidentified afterwards is inferred from the tab slots no other shell
    claimed, which keeps the grouping correct even when the tag never survives.
    """
    before = read_structure(atspi)
    original = {}
    for window_index, window in enumerate(before):
        for tab_index, label in enumerate(effective_labels(window)):
            original[(window_index, tab_index)] = label

    known_pids = {tab["pid"] for tab in tabs}
    found = {}
    structure = before
    for _ in range(TAG_ATTEMPTS):
        pending = [tab for tab in tabs if tab["pid"] not in found]
        if not pending:
            break
        for tab in pending:
            set_title_fn(tab["tty"], TAG_PREFIX + str(tab["pid"]))
        sleep(TAG_SETTLE)
        structure = read_structure(atspi)
        for window_index, window in enumerate(structure):
            for tab_index, label in enumerate(effective_labels(window)):
                pid = parse_tag(label)
                if pid is not None and pid in known_pids:
                    found.setdefault(pid, (window_index, tab_index))

    _assign_leftovers(tabs, structure, found)

    for tab in tabs:
        tab["window"], tab["tab"] = found[tab["pid"]]
        set_title_fn(tab["tty"], original.get((tab["window"], tab["tab"]), ""))
    return found


def parse_tag(label):
    if not label or not label.startswith(TAG_PREFIX):
        return None
    try:
        return int(label[len(TAG_PREFIX):])
    except ValueError:
        return None


def _assign_leftovers(tabs, structure, found):
    slots = [
        (window_index, tab_index)
        for window_index, window in enumerate(structure)
        for tab_index in range(len(effective_labels(window)))
    ]
    taken = set(found.values())
    free = [slot for slot in slots if slot not in taken]
    spare_window = len(structure)
    for tab in tabs:
        if tab["pid"] in found:
            continue
        if free:
            found[tab["pid"]] = free.pop(0)
        else:
            found[tab["pid"]] = (spare_window, 0)
            spare_window += 1
