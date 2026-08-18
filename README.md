# gnome-terminal-restore

Reopen your GNOME Terminal windows and tabs after a reboot — same windows, same
tabs, same directories, same virtualenvs.

```console
$ gt-restore --list
window 0 (3 tabs):
    ~/code/api        |  venv:api-env  |  was:python manage.py runserver
    ~/code/api/tests
    ~/notes
window 1 (2 tabs):
    ~/code/frontend
    /var/log

$ gt-restore
restored 2 window(s)
```

---

## Why this exists

GNOME Terminal has no session restore. GNOME removed session-save support years
ago, and the terminal never had a layout-save feature of its own. If you work
with a dozen tabs spread over several windows, every reboot costs you the same
five minutes of reopening tabs and `cd`-ing back into projects.

The usual advice is "use tmux". That is good advice, but it is a different tool
with a different workflow, and its layout restore (via
[tmux-resurrect](https://github.com/tmux-plugins/tmux-resurrect)) only helps if
you were already living inside tmux. This project takes the other approach: it
leaves your workflow exactly as it is, watches the terminal from the outside,
and puts it back the way it was.

Two problems had to be solved to make that work, and neither has an obvious
solution — see [docs/DESIGN.md](docs/DESIGN.md) for the full story:

1. **Which window is a tab in?** Every window and tab of a GNOME Terminal
   session lives inside one `gnome-terminal-server` process, so `/proc` shows
   tabs but not windows. On Wayland there is no per-tab `WINDOWID` either. This
   tool reads the **accessibility tree**, which models the real window → tab
   structure, and matches tabs to shells with a temporary, invisible title tag.

2. **Which virtualenv is active?** `/proc/<pid>/environ` is frozen at exec time,
   so a virtualenv activated inside a running shell never appears there —
   which is nearly every real case. A small bash hook records it instead.

## What is restored

| | |
|---|---|
| ✅ | Every window, as a separate window |
| ✅ | Each window's tabs, in order |
| ✅ | Each tab's working directory |
| ✅ | Each tab's virtualenv or conda environment, reactivated |
| ✅ | The command a tab was running — placed in history, not re-executed |
| ❌ | Running processes (a shutdown kills them; nothing can bring them back) |
| ❌ | Window geometry, monitor placement, and workspace |
| ❌ | Scrollback |

## Requirements

- GNOME Terminal (tested against 3.44 on Ubuntu, X11 and Wayland)
- Python 3.7+
- `python3-gi` with the AT-SPI typelib, for window grouping:
  `sudo apt install python3-gi gir1.2-atspi-2.0`
  Without it everything still works, but all tabs are restored into one window.
- systemd (user session) for automatic snapshots — optional
- bash, for virtualenv reactivation — optional, see [Other shells](#other-shells)

## Install

```console
$ git clone https://github.com/YOUR-USERNAME/gnome-terminal-restore.git
$ cd gnome-terminal-restore
$ ./install.sh
```

That installs into `~/.local` and sets up automatic snapshots every 30 minutes,
a final snapshot at logout, and restore at login. Nothing needs root.

```console
$ ./install.sh --help
  --prefix DIR      install under DIR (default: $HOME/.local, or $PREFIX)
  --interval SPEC   snapshot interval: 15min, 30min, 1h, or any systemd
                    OnCalendar expression (default: 30min)
  --no-autostart    do not restore the layout automatically at login
  --no-hook         do not add the shell hook to ~/.bashrc
  --no-systemd      install the commands only, no timer or shutdown unit
```

Then, once:

```console
$ source ~/.bashrc     # in tabs that are already open, so they report their venv
$ gt-save              # take a first snapshot
```

Prefer pip? `pip install --user .` installs `gt-save` and `gt-restore`, but not
the timer, autostart entry or shell hook — `./install.sh --no-systemd` style
pieces are shell-script territory. Run `./install.sh` for the full setup.

## Usage

### Saving

Snapshots happen on a timer and at logout, so normally you never run this. To
capture the layout right now:

```console
$ gt-save
saved 7 tab(s) across 3 window(s) -> ~/.local/share/gnome-terminal-restore/snapshot.json
```

### Restoring

```console
$ gt-restore              # reopen every saved window with its tabs
$ gt-restore --list       # show the saved layout without touching anything
$ gt-restore --dry-run    # print the exact commands that would run
$ gt-restore -w 1         # restore only window 1 (repeatable: -w 0 -w 2)
$ gt-restore --prev       # use the previous snapshot
$ gt-restore -f FILE      # restore from a snapshot file you saved elsewhere
```

Windows are numbered as they appear in `--list`.

### Keeping a named layout

The snapshot is a plain JSON file, so a layout worth keeping can just be copied
and restored on demand:

```console
$ gt-save
$ cp ~/.local/share/gnome-terminal-restore/snapshot.json ~/layouts/release-day.json
$ gt-restore -f ~/layouts/release-day.json
```

## How it works

```
              every 30 min, and at logout
                         │
   gt-save ──────────────┼──────────────────────────────► snapshot.json
      │                  │                                     │
      ├─ /proc ..........│... tabs, working directories, cmds   │
      ├─ shell hook .....│... active virtualenv per tab         │
      └─ AT-SPI tree ....│... which window each tab is in       │
                                                                │
   gt-restore ◄─────────────────────────────────────────────────┘
      │
      └─ one gnome-terminal invocation per window, each tab with its
         directory and a generated rc file that reactivates its environment
```

Three sources are combined because no single one knows everything: `/proc`
knows directories but not windows, the accessibility tree knows windows but not
processes, and only the shell itself knows which virtualenv is active.

[docs/DESIGN.md](docs/DESIGN.md) explains each of these, including the failure
modes that shaped the implementation.

## Files and locations

Everything respects the XDG base directory spec.

| Path | What |
|---|---|
| `~/.local/bin/gt-save`, `gt-restore` | the two commands |
| `~/.local/lib/gnome-terminal-restore/` | the Python package and shell hook |
| `~/.local/share/gnome-terminal-restore/snapshot.json` | current snapshot |
| `~/.local/share/gnome-terminal-restore/snapshot.json.prev` | the one before it |
| `~/.local/share/gnome-terminal-restore/live/` | per-tab state from the hook |
| `~/.local/share/gnome-terminal-restore/rc/` | generated rc files, one per restored tab |
| `~/.config/systemd/user/gt-save.{service,timer}` | periodic snapshots |
| `~/.config/systemd/user/gt-save-shutdown.service` | final snapshot at logout |
| `~/.config/autostart/gt-restore.desktop` | restore at login |

Set `GTR_DATA_DIR` to move the data directory, or `GTR_TERMINAL` to launch a
different terminal binary.

## Configuration

**Snapshot interval.** Reinstall with `--interval`, or edit the timer directly:

```console
$ systemctl --user edit --full gt-save.timer     # change OnCalendar
$ systemctl --user restart gt-save.timer
$ systemctl --user list-timers gt-save.timer     # confirm the next run
```

Interval only matters for an *unclean* shutdown. A normal logout or reboot
triggers the shutdown unit, which snapshots before the terminal server exits,
so nothing is lost regardless of the interval.

**Turn off login restore.** Delete `~/.config/autostart/gt-restore.desktop`, or
untick it in GNOME Tweaks → Startup Applications.

**Take a snapshot on demand from a keyboard shortcut.** Bind a key to
`gt-save` in Settings → Keyboard → Custom Shortcuts.

## Troubleshooting

**Everything comes back in one window.** Window grouping needs AT-SPI:

```console
$ python3 -c "import gi; gi.require_version('Atspi','2.0'); from gi.repository import Atspi; print('ok')"
$ gt-save          # prints a warning explaining what went wrong
```

Install `python3-gi` and `gir1.2-atspi-2.0` if the import fails. The snapshot
records whether grouping succeeded, in its `grouped` field.

**A virtualenv is not restored.** The tab must have had the hook loaded while
the venv was active. Check that the tab reported itself:

```console
$ ls ~/.local/share/gnome-terminal-restore/live/    # one file per hooked tab
$ grep -c gnome-terminal-restore ~/.bashrc          # hook installed?
```

Tabs opened before the hook was installed need `source ~/.bashrc` once.

**Nothing restored at login.** Autostart runs `gt-restore --if-none`, which does
nothing when a terminal is already open. To see what happened:

```console
$ journalctl --user -b | grep -i gt-restore
$ gt-restore --list      # is there a snapshot at all?
```

**A tab's title briefly changed.** Grouping sets a temporary title on each tab
and puts the original back. If a snapshot is interrupted mid-run, a title can
be left reading `GTSNAP-<number>`; the next prompt or `gt-save` run clears it.

## Other shells

The snapshot side is shell-independent: directories, windows and tabs are
recovered from `/proc` and the accessibility tree no matter which shell you run.

Two pieces are bash-specific: the hook that reports the active virtualenv, and
the generated rc file that reactivates it. Under another shell you get windows,
tabs and directories, and `gt-restore` says so rather than failing. Zsh and fish
support are welcome contributions — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Security notes

- A command that was running in a tab is **never re-executed** on restore. It is
  written into the shell history so that pressing Up recalls it, and printed
  once when the tab opens.
- Generated rc files live under your data directory and contain only your own
  `~/.bashrc`, an `activate` line, and a `history -s` line. Paths are shell-quoted.
- Title tags are written to a tab's pty as terminal output. They are consumed by
  the terminal emulator and never delivered to the shell as input; nothing is
  typed into your shells.

## Uninstall

```console
$ ./uninstall.sh            # remove everything, keep snapshots
$ ./uninstall.sh --purge    # remove snapshots too
```

## Contributing

Bug reports and patches are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).
Especially useful: reports from other GNOME versions and distributions, since
the accessibility tree layout is the part most likely to differ.

## License

MIT — see [LICENSE](LICENSE).
