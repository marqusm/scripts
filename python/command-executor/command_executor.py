#!/usr/bin/env python3
"""
command_executor.py
Execute a YAML list of rename/move/delete file operations. DRY-RUN by default.

  python command_executor.py --commands commands.yaml                 # preview
  python command_executor.py --commands commands.yaml --execute       # apply
  python command_executor.py --commands command_undo_<ts>.yaml --execute   # reverse

See README.md for the command format, options, and safety details.
"""

import argparse
import datetime
import os
import sys
import uuid
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML is required: pip install pyyaml", file=sys.stderr)
    raise SystemExit(1)

INVALID = set('<>:"/\\|?*')
MOVE_ACTIONS = {"rename", "move"}


def fskey(path: str) -> str:
    """Filesystem identity key: case-insensitive on Windows, exact on POSIX."""
    return os.path.normcase(os.path.normpath(path))


def lexists(p: Path) -> bool:
    """True if the path exists, including broken symlinks."""
    return p.exists() or p.is_symlink()


def rel_inside(base: Path, path) -> str | None:
    """Normalized base-relative form of `path`, or None if it is absolute
    outside base, climbs out via `..`, or is base itself. abspath, not
    resolve(), so a symlink is handled as the link rather than its target."""
    p = Path(os.path.abspath(base / str(path)))
    if p == base or not p.is_relative_to(base):
        return None
    return p.relative_to(base).as_posix()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Execute a YAML list of rename/move/delete file operations."
    )
    ap.add_argument("--commands", default="commands.yaml",
                    help="YAML list of {action, src, dst} commands.")
    ap.add_argument("--base", default=".",
                    help="Directory the src/dst paths are relative to.")
    ap.add_argument("--undo", default=None,
                    help="Where to write the reverse plan "
                         "(default: command_undo_<timestamp>.yaml, so runs never overwrite each other).")
    ap.add_argument("--execute", action="store_true",
                    help="Without this it is a dry-run and nothing changes.")
    args = ap.parse_args()

    cmd_path = Path(args.commands)
    if not cmd_path.is_file():
        print(f"Commands file not found: {cmd_path}", file=sys.stderr)
        return 1

    # utf-8-sig tolerates a BOM, which PowerShell's ">" and Notepad add on Windows.
    commands = yaml.safe_load(cmd_path.read_text(encoding="utf-8-sig"))
    if not isinstance(commands, list):
        print("Commands file must contain a YAML list.", file=sys.stderr)
        return 1

    base = Path(args.base).resolve()
    if not base.is_dir():
        print(f"Base folder not found: {base}", file=sys.stderr)
        return 1

    moves = []     # (src_rel, dst_rel) for rename/move
    deletes = []   # src_rel
    seen_src = {}  # fskey(src) -> src_rel, so a path isn't touched twice
    targets = {}   # fskey(dst) -> src_rel, catches two moves onto one name
    issues = 0

    for c in commands:
        if not isinstance(c, dict):
            print(f"SKIP (entry is not a mapping): {c!r}")
            issues += 1
            continue
        action = c.get("action")
        src, dst = c.get("src"), c.get("dst")

        if action not in MOVE_ACTIONS and action != "delete":
            print(f"SKIP (unsupported action): {action!r}")
            issues += 1
            continue
        if not src:
            print(f"SKIP (no src): {c}")
            issues += 1
            continue
        src_rel = rel_inside(base, src)
        if src_rel is None:
            print(f"SKIP (src outside base): {src}")
            issues += 1
            continue
        src = src_rel

        skey = fskey(src)
        if skey in seen_src:
            print(f"SKIP (source already used): {src}")
            issues += 1
            continue
        if not lexists(base / src):
            print(f"SKIP (source missing): {src}")
            issues += 1
            continue

        if action == "delete":
            seen_src[skey] = src
            deletes.append(src)
            continue

        # rename / move
        if not dst:
            print(f"SKIP (no target): {src}")
            issues += 1
            continue
        dst_rel = rel_inside(base, dst)
        if dst_rel is None:
            print(f"SKIP (target outside base): {dst}")
            issues += 1
            continue
        dst = dst_rel
        # Exact compare (both already normalized): on Windows a case-only
        # rename has equal fskeys but is a real change, done via the temp name.
        if src == dst:
            continue  # no-op
        if INVALID & set(Path(dst).name):
            print(f"SKIP (invalid chars in name): {dst}")
            issues += 1
            continue
        tkey = fskey(dst)
        if tkey in targets:
            print(f"SKIP (duplicate target): {dst} (from '{src}' and '{targets[tkey]}')")
            issues += 1
            continue
        seen_src[skey] = src
        targets[tkey] = src
        moves.append((src, dst))

    # A move onto an existing path is only safe if that path is itself being
    # vacated by another move or a delete in this same batch.
    vacated = {fskey(s) for s in deletes} | {fskey(s) for s, _ in moves}
    safe = []
    for src, dst in moves:
        if lexists(base / dst) and fskey(dst) not in vacated:
            print(f"SKIP (target exists, not in plan): {dst}")
            issues += 1
            continue
        safe.append((src, dst))
    moves = safe

    print()
    print(f"Planned moves: {len(moves)}    Deletes: {len(deletes)}    Issues/skips: {issues}")
    print("-" * 58)
    for src, dst in moves:
        print(f"{src}  ->  {dst}")
    for src in deletes:
        print(f"DELETE  {src}")
    print("-" * 58)

    if not args.execute:
        print("DRY-RUN only. Nothing changed. Re-run with --execute to apply.")
        return 0

    if issues:
        print(f"WARNING: {issues} issue(s) above will be skipped.")

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    trash = base / f".command_executor_trash_{ts}"
    undo_path = args.undo
    if undo_path is None:  # unique name, even for two runs in the same second
        undo_path = f"command_undo_{ts}.yaml"
        n = 1
        while Path(undo_path).exists():
            undo_path = f"command_undo_{ts}_{n}.yaml"
            n += 1

    # Deletes go first (to trash, freeing paths a move may want), then a
    # two-phase move (via temp names) so swaps and cycles can't clobber each
    # other. Each operation is isolated: if one fails it is reported and
    # skipped, and the rest of the batch still runs. A move that fails in
    # phase 2 has its source put back so nothing is left stranded.
    trashed = []    # (trash_path, orig_path, src_rel)
    temps = []      # (tmp, dst_path, src_rel, dst_rel) — phase 1 done
    committed = []  # (tmp, dst_path, src_rel, dst_rel) — phase 2 done
    failures = 0

    for src in deletes:
        srcp = base / src
        tdst = trash / src
        try:
            tdst.parent.mkdir(parents=True, exist_ok=True)
            srcp.rename(tdst)
            trashed.append((tdst, srcp, src))
        except Exception as exc:
            failures += 1
            print(f"SKIP (delete failed): {src}: {exc}", file=sys.stderr)

    for src, dst in moves:
        srcp = base / src
        tmp = srcp.with_name(srcp.name + ".__cmdtmp_" + uuid.uuid4().hex)
        try:
            srcp.rename(tmp)
            temps.append((tmp, base / dst, src, dst))
        except Exception as exc:
            failures += 1
            print(f"SKIP (move failed): {src} -> {dst}: {exc}", file=sys.stderr)

    for tmp, dstp, src, dst in temps:
        try:
            # The plan only allowed an existing target if another op vacates
            # it; if that op failed, the target is still here. POSIX rename()
            # would silently replace it, so check right before committing.
            if lexists(dstp):
                raise FileExistsError(f"target still exists: {dst}")
            dstp.parent.mkdir(parents=True, exist_ok=True)
            tmp.rename(dstp)
            committed.append((tmp, dstp, src, dst))
        except Exception as exc:
            failures += 1
            print(f"SKIP (move failed): {src} -> {dst}: {exc}", file=sys.stderr)
            try:  # put the source back so it isn't left under a temp name
                tmp.rename(base / src)
            except Exception as rexc:
                print(f"  could not restore {src}: {rexc}", file=sys.stderr)

    if not trashed:
        _prune_empty(trash)  # drop an empty trash tree if no delete landed

    # Build the reverse plan: undo the last operation first.
    undo = []
    for tmp, dstp, src, dst in reversed(committed):
        undo.append({"action": "move", "src": dst, "dst": src})
    for tdst, srcp, src in reversed(trashed):
        undo.append({"action": "move", "src": tdst.relative_to(base).as_posix(), "dst": src})
    if undo:
        Path(undo_path).write_text(
            yaml.safe_dump(undo, sort_keys=False, allow_unicode=True, default_flow_style=False),
            encoding="utf-8")

    print()
    print(f"Done. Moved {len(committed)} file(s), deleted {len(trashed)} file(s).")
    if failures:
        print(f"Skipped {failures} failed operation(s) (see above).")
    if trashed:
        print(f"Deleted files are in: {trash}")
    if undo:
        print(f"Undo file written: {undo_path} "
              f"(run with --commands {undo_path} --base \"{base}\" --execute to reverse).")
    return 1 if failures else 0


def _prune_empty(trash: Path) -> None:
    """Best-effort removal of an empty trash tree."""
    if not trash.exists():
        return
    for d in sorted(trash.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass
    try:
        trash.rmdir()
    except OSError:
        pass


if __name__ == "__main__":
    raise SystemExit(main())
