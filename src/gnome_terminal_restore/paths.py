"""Filesystem locations, all XDG-based so nothing is tied to a particular machine."""
import os

from . import APP


def _xdg(var, default):
    value = os.environ.get(var)
    if value and os.path.isabs(value):
        return value
    return os.path.join(os.path.expanduser("~"), *default)


def data_dir():
    """Where snapshots and per-tab state live. Override with GTR_DATA_DIR."""
    override = os.environ.get("GTR_DATA_DIR")
    if override:
        return os.path.expanduser(override)
    return os.path.join(_xdg("XDG_DATA_HOME", (".local", "share")), APP)


def snapshot_path():
    return os.path.join(data_dir(), "snapshot.json")


def previous_snapshot_path():
    return snapshot_path() + ".prev"


def live_dir():
    """One small file per live tab, written by the shell hook."""
    return os.path.join(data_dir(), "live")


def rc_dir():
    """Generated per-tab rc files used to reactivate environments on restore."""
    return os.path.join(data_dir(), "rc")
