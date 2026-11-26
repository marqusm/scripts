# Command Executor

Runs a YAML list of rename / move / delete operations against a folder.
**Dry-run by default**: nothing changes until you pass `--execute`.

## Installation

```bash
pip install -r requirements.txt
```

## Running

```bash
python command_executor.py --commands commands.yaml                 # preview
python command_executor.py --commands commands.yaml --execute       # apply
python command_executor.py --commands command_undo_<ts>.yaml --execute   # reverse
```

| Argument          | Default                          | Comment                                    |
|-------------------|----------------------------------|--------------------------------------------|
| `--commands FILE` | `commands.yaml`                  | YAML list of operations                    |
| `--base DIR`      | `.`                              | Folder that `src` / `dst` are relative to  |
| `--undo FILE`     | `command_undo_<timestamp>.yaml`  | Where the reverse plan is written          |
| `--execute`       | off                              | Apply changes (otherwise dry-run)          |

Exit code is `1` if any operation failed during `--execute`, else `0`.

## Command format

```yaml
- action: rename          # or: move (same thing)
  src: IMG_0042.jpg
  dst: 2023/2023-04-15_09-30-12.jpg
- action: delete
  src: Thumbs.db
```

Paths are relative to `--base`. Missing parent folders for `dst` are created.

## Safety

- **Never leaves `--base`.** Absolute paths, `..` that climbs out, and the
  base folder itself are skipped.
- **Never overwrites.** A move onto an existing path is only allowed when
  another operation in the same batch vacates it, and the target is checked
  again right before the move.
- **Swaps and cycles work** (`a → b`, `b → a`): moves run in two phases via
  temporary names.
- **Deletes go to a trash folder** (`<base>/.command_executor_trash_<ts>/`),
  not the recycle bin. Remove it yourself once you're happy.
- **Undo file** reverses every completed move and delete. Each run writes a
  new timestamped file unless `--undo` is given.
- **Per-operation isolation.** A failed operation is reported and skipped;
  the rest still run. A move that fails halfway gets its source name back.
- Plans are validated first: duplicate sources, two moves onto one target,
  missing sources and invalid filename characters are reported as skips.
- Case-only renames (`a.jpg → A.jpg`) work on Windows.
