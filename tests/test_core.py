"""Unit tests for the parts that do not need a running desktop."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from gnome_terminal_restore import a11y, procs, restore, save  # noqa: E402


class FakeNode:
    def __init__(self, name, role, children=()):
        self.name = name
        self.role = role
        self.children = list(children)

    def get_name(self):
        return self.name

    def get_role_name(self):
        return self.role

    def get_child_count(self):
        return len(self.children)

    def get_child_at_index(self, index):
        return self.children[index]


class FakeTerminal:
    """A terminal whose accessible tree can be read and whose titles can be set.

    ``hostile`` ttys ignore title changes, standing in for an application that
    keeps rewriting its own title and so overwrites our tag before we read it.
    """

    def __init__(self, windows, hostile=()):
        self.hostile = set(hostile)
        self.windows = []
        for ttys in windows:
            self.windows.append({tty: "" for tty in ttys})

    # --- the Atspi surface used by a11y.read_structure ---
    def get_desktop(self, _index):
        frames = []
        for window in self.windows:
            titles = list(window.values())
            if len(titles) == 1:
                frame_children = [FakeNode("", "page tab list", [FakeNode("", "page tab")])]
                frame = FakeNode(titles[0], "frame", frame_children)
            else:
                tabs = [FakeNode(title, "page tab") for title in titles]
                frame = FakeNode("window", "frame", [FakeNode("", "page tab list", tabs)])
            frames.append(frame)
        app = FakeNode("gnome-terminal-server", "application", frames)
        return FakeNode("desktop", "desktop", [app])

    def set_title(self, tty, title):
        if tty in self.hostile:
            return
        for window in self.windows:
            if tty in window:
                window[tty] = title


def tabs_for(*ttys):
    return [{"pid": 1000 + i, "tty": tty} for i, tty in enumerate(ttys)]


class TestGrouping(unittest.TestCase):
    def test_tabs_are_grouped_into_their_windows(self):
        terminal = FakeTerminal([["/dev/pts/1", "/dev/pts/2"], ["/dev/pts/3"]])
        tabs = tabs_for("/dev/pts/1", "/dev/pts/2", "/dev/pts/3")
        a11y.group_tabs(tabs, terminal, terminal.set_title, sleep=lambda _s: None)
        self.assertEqual([(t["window"], t["tab"]) for t in tabs], [(0, 0), (0, 1), (1, 0)])

    def test_a_tab_that_overwrites_its_title_still_lands_in_the_right_window(self):
        terminal = FakeTerminal(
            [["/dev/pts/1", "/dev/pts/2"], ["/dev/pts/3"]], hostile=["/dev/pts/2"]
        )
        tabs = tabs_for("/dev/pts/1", "/dev/pts/2", "/dev/pts/3")
        a11y.group_tabs(tabs, terminal, terminal.set_title, sleep=lambda _s: None)
        placements = {t["tty"]: (t["window"], t["tab"]) for t in tabs}
        self.assertEqual(placements["/dev/pts/1"], (0, 0))
        self.assertEqual(placements["/dev/pts/3"], (1, 0))
        # inferred from the only slot nothing else claimed
        self.assertEqual(placements["/dev/pts/2"], (0, 1))

    def test_original_titles_are_restored(self):
        terminal = FakeTerminal([["/dev/pts/1", "/dev/pts/2"]])
        terminal.windows[0]["/dev/pts/1"] = "ravi@host: ~/code"
        terminal.windows[0]["/dev/pts/2"] = "vim notes.md"
        tabs = tabs_for("/dev/pts/1", "/dev/pts/2")
        a11y.group_tabs(tabs, terminal, terminal.set_title, sleep=lambda _s: None)
        self.assertEqual(
            list(terminal.windows[0].values()), ["ravi@host: ~/code", "vim notes.md"]
        )

    def test_parse_tag(self):
        self.assertEqual(a11y.parse_tag("GTSNAP-42"), 42)
        self.assertIsNone(a11y.parse_tag("GTSNAP-x"))
        self.assertIsNone(a11y.parse_tag("bash"))
        self.assertIsNone(a11y.parse_tag(""))

    def test_single_tab_window_falls_back_to_the_frame_title(self):
        self.assertEqual(a11y.effective_labels(("frame title", [""])), ["frame title"])
        self.assertEqual(a11y.effective_labels(("frame title", ["a", "b"])), ["a", "b"])


class TestRestoreRendering(unittest.TestCase):
    def test_virtualenv_is_activated(self):
        rc = restore.render_rc({"cwd": "/x", "venv": "/home/u/proj/.venv", "cmd": ""})
        self.assertIn(". /home/u/proj/.venv/bin/activate", rc)
        self.assertIn('. "$HOME/.bashrc"', rc)

    def test_paths_with_spaces_are_quoted(self):
        rc = restore.render_rc({"cwd": "/x", "venv": "/home/u/my projects/.venv", "cmd": ""})
        self.assertIn("'/home/u/my projects/.venv/bin/activate'", rc)

    def test_previous_command_is_recalled_not_run(self):
        rc = restore.render_rc({"cwd": "/x", "venv": "", "cmd": "vim notes.md"})
        self.assertIn("history -s 'vim notes.md'", rc)
        lines = [line for line in rc.splitlines() if line.strip().startswith("vim")]
        self.assertEqual(lines, [], "the command must never be executed on restore")

    def test_plain_shell_tab_needs_no_rc(self):
        self.assertFalse(restore.needs_rc({"cwd": "/x", "venv": "", "conda_env": "", "cmd": "bash"}))
        self.assertTrue(restore.needs_rc({"cwd": "/x", "venv": "/v", "conda_env": "", "cmd": ""}))

    def test_window_and_tab_flags(self):
        tabs = [
            {"cwd": "/", "venv": "", "conda_env": "", "cmd": ""},
            {"cwd": "/tmp", "venv": "", "conda_env": "", "cmd": ""},
        ]
        argv = restore.build_command(0, tabs, use_rc=False)
        self.assertEqual(argv[1], "--window")
        self.assertIn("--tab", argv)
        self.assertIn("--working-directory=/tmp", argv)


class TestSnapshot(unittest.TestCase):
    def test_windows_and_tabs_keep_their_order(self):
        tabs = [
            {"window": 1, "tab": 0, "cwd": "/b", "venv": "", "conda_env": "", "conda_prefix": "",
             "cmd": "", "has_hook": True},
            {"window": 0, "tab": 1, "cwd": "/a2", "venv": "", "conda_env": "", "conda_prefix": "",
             "cmd": "", "has_hook": True},
            {"window": 0, "tab": 0, "cwd": "/a1", "venv": "", "conda_env": "", "conda_prefix": "",
             "cmd": "", "has_hook": True},
        ]
        snapshot = save.build_snapshot(tabs, grouped=True)
        self.assertEqual(
            [[tab["cwd"] for tab in window] for window in snapshot["windows"]],
            [["/a1", "/a2"], ["/b"]],
        )
        self.assertTrue(snapshot["grouped"])


class TestProcs(unittest.TestCase):
    def test_is_shell(self):
        self.assertTrue(procs.is_shell(""))
        self.assertTrue(procs.is_shell("/bin/bash"))
        self.assertTrue(procs.is_shell("/usr/bin/zsh -l"))
        self.assertFalse(procs.is_shell("vim notes.md"))
        self.assertFalse(procs.is_shell("ssh host"))


if __name__ == "__main__":
    unittest.main()
