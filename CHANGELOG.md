# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-08-19

First release.

### Added
- `gt-save`: snapshots every GNOME Terminal window, its tabs in order, each
  tab's working directory, active virtualenv or conda environment, and the
  command running in it.
- Window grouping through the AT-SPI accessibility tree, which works on Wayland
  where no per-tab window id exists. Tabs are matched to shells with a
  temporary OSC title tag, retried for applications that manage their own
  title, with slot inference as a fallback.
- `gt-restore`: reopens the saved layout, one terminal window per saved window,
  reactivating each tab's environment. A command that was running is put in the
  shell history rather than re-executed.
- Bash hook recording each tab's directory and environment, needed because
  `/proc/<pid>/environ` cannot see a virtualenv activated after the shell started.
- systemd user timer for periodic snapshots and a unit that takes a final
  snapshot at logout or shutdown, ordered before `gnome-terminal-server` stops.
- XDG autostart entry that restores the layout at login, skipped when a terminal
  is already open.
- `install.sh` / `uninstall.sh` with configurable prefix and snapshot interval.
