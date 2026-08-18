# Contributing

Thanks for taking a look. Bug reports, environment reports and patches are all
welcome.

## Reporting a bug

The parts most likely to differ between systems are the accessibility tree and
GNOME Terminal's command-line behaviour, so please include:

```console
$ gnome-terminal --version
$ echo "$XDG_SESSION_TYPE"          # x11 or wayland
$ python3 --version
$ lsb_release -ds || cat /etc/os-release | head -2
$ gt-save                            # any warning it prints
$ gt-restore --list
```

If windows are grouped wrongly, the output of `gt-restore --list` next to a
description of your actual layout is the single most useful thing to attach.

## Development

No build step and no runtime dependencies beyond the standard library and
PyGObject. Run straight from a clone:

```console
$ PYTHONPATH=src python3 -m gnome_terminal_restore.save
$ PYTHONPATH=src python3 -m gnome_terminal_restore.restore --list
```

Tests use only `unittest` and do not need a desktop session — the accessibility
tree and terminal are faked:

```console
$ python3 -m unittest discover -s tests -v
$ bash -n install.sh uninstall.sh && shellcheck install.sh uninstall.sh
```

Install into a throwaway prefix to try the full setup without touching your
own:

```console
$ ./install.sh --prefix /tmp/gtr-test --no-systemd --no-autostart --no-hook
```

## Code layout

| Module | Responsibility |
|---|---|
| `procs.py` | reading tabs, directories and commands out of `/proc` |
| `a11y.py` | window grouping through the accessibility tree |
| `tty.py` | writing a title to a tab's pty |
| `save.py` | assembling and writing a snapshot |
| `restore.py` | turning a snapshot back into terminal windows |
| `paths.py` | XDG locations |

## Things worth adding

- **zsh and fish support.** Two pieces are bash-only: `shell/hook.bash`, and
  `render_rc()` in `restore.py`. A zsh version needs a `precmd` hook and a
  generated `ZDOTDIR`; fish needs a `fish_prompt` event handler and
  `--init-command`. Please test on a real session before submitting.
- **Other terminals.** The `/proc` and title-tagging approach is not specific to
  GNOME Terminal; anything running its tabs under one server process could work
  the same way.
- **Window geometry**, if a reliable way to restore it under Wayland exists.

## Style

- Standard library only, no new runtime dependencies.
- Comments explain *why*, not *what* — the non-obvious constraints are the
  valuable part of this codebase.
- New behaviour comes with a test where it can be tested without a desktop.
