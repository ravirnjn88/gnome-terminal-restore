# Design notes

Why this tool is built the way it is, including the things that did not work.

## The problem

GNOME Terminal exposes no way to save and reopen a session. Restoring a layout
from the outside needs four facts about every tab:

1. its working directory,
2. which window it belongs to, and its position among that window's tabs,
3. the Python environment active in it,
4. what it was running.

Facts 1 and 4 come out of `/proc` directly. Facts 2 and 3 are the interesting
ones: the obvious source for each turns out to be wrong.

## Finding the tabs

All windows and tabs of one GNOME Terminal session run inside a single
`gnome-terminal-server` process. Every tab's shell is a direct child of it:

```
gnome-terminal-server
├── bash        (window A, tab 1)
├── bash        (window A, tab 2)
└── bash        (window B, tab 1)
```

So enumerating tabs is easy — the children of that process — and each one gives
its directory through `/proc/<pid>/cwd`, its pty through `/proc/<pid>/fd/0`, and
whatever it is running through its deepest descendant process.

What the process tree does *not* contain is any hint of window membership. The
flat list above is all the kernel knows.

## Problem 1: which window is a tab in?

### What does not work

**`WINDOWID`.** VTE sets this in each tab's environment on X11, and it would be
a perfect grouping key. It does not exist on Wayland, where most current GNOME
sessions run.

**Window manager tools.** `wmctrl` and `xdotool` cannot see Wayland windows at
all. Even under X11 they report `_NET_WM_PID` as the *server's* pid for every
window, which is the same number for all of them.

**GNOME Shell's `Eval` D-Bus method.** Blocked since GNOME 41 unless unsafe mode
is enabled.

**GNOME Terminal's own D-Bus interface.** It registers a `/org/gnome/Terminal/window/N`
object per window (a GTK convention) and one `/org/gnome/Terminal/screen/<uuid>`
object per tab, but exposes no relationship between the two. Each tab does know
its own screen path via `$GNOME_TERMINAL_SCREEN` — that identifies the tab, not
its window.

### What does work

The **accessibility tree**. GTK exports one through AT-SPI, and it models the
real widget hierarchy:

```
application  "gnome-terminal-server"
├── frame  "ravi@host: ~/code"            ← window
│   └── page tab list
│       ├── page tab  "ravi@host: ~/code"      ← tab 1
│       └── page tab  "vim notes.md"           ← tab 2
└── frame  "ravi@host: /var/log"          ← another window
    └── page tab list
        └── page tab  ""
```

This is exactly the missing structure. The catch: accessible objects carry no
process id, so the tree tells us *a window has two tabs* without saying which
shell each one is.

### Joining the two views

Each tab's title is set by writing an `OSC 0` escape sequence to its pty. This
is terminal *output*, consumed by the emulator, so it produces no visible
characters and is never delivered to the shell as input. The tab's label in the
accessibility tree changes to match.

So: tag every tab with a unique marker derived from its pid, read the tree, map
labels back to pids, then write the original titles back.

Two wrinkles turned up in practice:

**Single-tab windows.** A window with one tab has no populated tab list, so its
frame title stands in as that tab's label. `effective_labels()` handles this.

**Applications that manage their own title.** tmux, Claude Code and various TUIs
rewrite their title on a timer, and will overwrite the tag before the tree is
read — the tab then looks unidentifiable and would be split into a phantom
window of its own. Two defences:

- the tag/read cycle is retried (up to 8 times), which catches most such tabs;
- anything still unmatched is assigned to the tab slots no other shell claimed.
  Since the tree already told us how many windows exist and how many tabs each
  has, a leftover tab has only leftover slots to go in — with one unidentified
  tab the placement is exact, and with several the *grouping* is still right
  even if two tabs within a window could swap places.

Failure is never fatal: if AT-SPI is missing entirely, the snapshot records
`grouped: false` and restores every tab into one window.

## Problem 2: which virtualenv is active?

The obvious source is `/proc/<pid>/environ`, and it is a trap. The kernel
snapshots a process's environment when it execs and never updates that region
again. A shell that runs `source .venv/bin/activate` sets `VIRTUAL_ENV` in its
own memory; `/proc` keeps showing the environment the shell started with.

That means reading `/proc` would correctly report a venv only if you launched
the terminal from a shell that already had one active — the rare case — and
silently miss the normal one.

The only component that reliably knows is the shell. A `PROMPT_COMMAND` hook
writes `$PWD`, `$VIRTUAL_ENV`, `$CONDA_DEFAULT_ENV` and `$CONDA_PREFIX` to a
small per-pid file after every command. `gt-save` prefers that file and falls
back to `/proc` for tabs that predate the hook.

The hook preserves `$?` so it cannot disturb prompts or scripts that inspect the
previous exit status, and registers itself only once even if sourced repeatedly.

## Restoring

One `gnome-terminal` invocation per saved window, with `--window` for the first
tab and `--tab` for the rest, each carrying `--working-directory`.

Tabs that need an environment also get `-e "bash --rcfile <generated file>"`.
The deprecated `-e` is used deliberately: it is the only way to give each tab in
a window its own command, since `--` applies to the whole invocation. The
generated rc file sources the user's `~/.bashrc` first, so the tab behaves
normally, then activates the environment — which is also what makes the `(venv)`
prompt prefix appear, rather than just setting variables.

Tabs that need nothing get no command at all, so they launch the user's default
shell exactly as a manually opened tab would.

**A command that was running is not re-run.** Restoring a layout should never
execute anything on its own: the tab could have been running a deploy, a
database migration, or an editor with unsaved state. The command is put into the
shell history so Up recalls it, and printed once.

## Snapshot integrity

- Writes are atomic (`write to .tmp`, then `os.replace`), and the previous
  snapshot is always kept as `.prev`.
- An empty result never overwrites a good snapshot: if no terminal is running,
  `gt-save` exits without writing.
- The shutdown unit is ordered `After=gnome-terminal-server.service`, so systemd
  stops it — and takes the final snapshot — *before* the terminal server dies.
  Without that ordering the last snapshot could find nothing to record.

## What is deliberately not attempted

**Restoring processes.** A shutdown kills them. Recreating them would mean
re-running arbitrary commands, which is unsafe and often wrong.

**Window geometry and workspaces.** The accessibility tree exposes position and
size, but GNOME Terminal's `--geometry` is unreliable under Wayland, where
clients cannot position their own windows.

**Being a tmux replacement.** If you want panes, detachable sessions and
processes that survive a disconnect, use tmux. This tool is for people who do
not want to change how they work.
