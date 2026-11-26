import sys

import pytest
import yaml

import command_executor


@pytest.fixture
def run(tmp_path, monkeypatch):
    """Write `commands` to a YAML file and run main() against tmp_path/base."""
    base = tmp_path / "base"
    base.mkdir()
    undo = tmp_path / "undo.yaml"

    def _run(commands, execute=True, commands_file=None):
        cmd_file = commands_file or tmp_path / "commands.yaml"
        if commands_file is None:
            cmd_file.write_text(yaml.safe_dump(commands), encoding="utf-8")
        argv = ["command_executor.py", "--commands", str(cmd_file),
                "--base", str(base), "--undo", str(undo)]
        if execute:
            argv.append("--execute")
        monkeypatch.setattr(sys, "argv", argv)
        return command_executor.main()

    _run.base = base
    _run.undo = undo
    return _run


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def names(base):
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file())


def test_dry_run_changes_nothing(run):
    write(run.base / "a", "A")
    assert run([{"action": "move", "src": "a", "dst": "b"}], execute=False) == 0
    assert names(run.base) == ["a"]
    assert not run.undo.exists()


def test_move_creates_parent_dirs(run):
    write(run.base / "a", "A")
    assert run([{"action": "rename", "src": "a", "dst": "x/y/b"}]) == 0
    assert (run.base / "x/y/b").read_text() == "A"


def test_swap(run):
    write(run.base / "a", "A")
    write(run.base / "b", "B")
    assert run([{"action": "move", "src": "a", "dst": "b"},
                {"action": "move", "src": "b", "dst": "a"}]) == 0
    assert (run.base / "a").read_text() == "B"
    assert (run.base / "b").read_text() == "A"


def test_never_overwrites_target_not_in_plan(run):
    write(run.base / "a", "A")
    write(run.base / "b", "B")
    assert run([{"action": "move", "src": "a", "dst": "b"}]) == 0
    assert (run.base / "a").read_text() == "A"
    assert (run.base / "b").read_text() == "B"


def test_target_still_present_when_vacating_op_fails(run, monkeypatch):
    # b -> c is planned to vacate b, but b can't be moved (e.g. locked);
    # a -> b must then refuse instead of clobbering b, and a keeps its name.
    write(run.base / "a", "A")
    write(run.base / "b", "B")
    real_rename = command_executor.Path.rename

    def flaky_rename(self, target):
        if self.name == "b":
            raise OSError("simulated lock")
        return real_rename(self, target)

    monkeypatch.setattr(command_executor.Path, "rename", flaky_rename)
    assert run([{"action": "move", "src": "a", "dst": "b"},
                {"action": "move", "src": "b", "dst": "c"}]) == 1
    assert (run.base / "a").read_text() == "A"
    assert (run.base / "b").read_text() == "B"
    assert names(run.base) == ["a", "b"]


@pytest.mark.parametrize("src,dst", [
    ("../outside", "x"),
    ("a", "../outside"),
    ("a", "."),
])
def test_paths_outside_base_are_skipped(run, src, dst):
    write(run.base / "a", "A")
    write(run.base.parent / "outside", "O")
    run([{"action": "move", "src": src, "dst": dst}])
    assert names(run.base) == ["a"]
    assert (run.base.parent / "outside").read_text() == "O"


def test_absolute_src_outside_base_is_skipped(run, tmp_path):
    write(tmp_path / "elsewhere", "E")
    run([{"action": "delete", "src": str(tmp_path / "elsewhere")}])
    assert (tmp_path / "elsewhere").exists()


def test_duplicate_target_skips_second(run):
    write(run.base / "a", "A")
    write(run.base / "b", "B")
    run([{"action": "move", "src": "a", "dst": "c"},
         {"action": "move", "src": "b", "dst": "c"}])
    assert names(run.base) == ["b", "c"]
    assert (run.base / "c").read_text() == "A"


def test_case_only_rename(run):
    write(run.base / "a.jpg", "A")
    assert run([{"action": "move", "src": "a.jpg", "dst": "A.jpg"}]) == 0
    assert [p.name for p in run.base.iterdir()] == ["A.jpg"]


def test_delete_goes_to_trash(run):
    write(run.base / "junk", "J")
    assert run([{"action": "delete", "src": "junk"}]) == 0
    assert not (run.base / "junk").exists()
    [trashed] = run.base.rglob("junk")
    assert trashed.parent.name.startswith(".command_executor_trash_")


def test_undo_round_trip(run):
    write(run.base / "a", "A")
    write(run.base / "b", "B")
    write(run.base / "junk", "J")
    assert run([{"action": "move", "src": "a", "dst": "sub/a2"},
                {"action": "move", "src": "b", "dst": "a"},
                {"action": "delete", "src": "junk"}]) == 0
    undo_copy = run.undo.with_name("undo_copy.yaml")
    undo_copy.write_text(run.undo.read_text(encoding="utf-8"), encoding="utf-8")

    assert run(None, commands_file=undo_copy) == 0
    assert (run.base / "a").read_text() == "A"
    assert (run.base / "b").read_text() == "B"
    assert (run.base / "junk").read_text() == "J"


def test_invalid_commands_file(run, tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("not: a list", encoding="utf-8")
    assert run(None, commands_file=bad) == 1
