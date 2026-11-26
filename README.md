# scripts

Personal collection of Bash / PowerShell / Python utilities for day-to-day
maintenance of home servers, a Raspberry Pi, and a Windows workstation.

## Installation

Most Bash scripts are intended to be installed into `/usr/local/bin` and run
directly by name. For scripts that read a sibling config file (`sync.sh`
reads `.env` next to itself), use a **symlink** so the script can resolve
back to its real directory and find the config:

```sh
# sync.sh — keeps .env next to the real script
sudo ln -s "$(pwd)/bash/sync.sh"      /usr/local/bin/sync
sudo ln -s "$(pwd)/bash/sync-kill.sh" /usr/local/bin/sync-kill

# scripts without sibling config — copying is fine too
sudo install -m 755 bash/update.sh /usr/local/bin/update
```

> `sync.sh` reads `.env` (next to the script) for `SOURCE` and `DESTINATION`.
> Copy `bash/.env.example` → `bash/.env` and replace the `<SOURCE>` /
> `<DESTINATION>` placeholders — the script refuses to run while they remain.

Typical cron candidates: `sync.sh`, `temp-monitoring.sh`, `update.sh`. Add
them to the host's crontab with `sudo crontab -e`.

## Scripts

### bash/
- **update.sh** — Runs `apt-get update/upgrade/autoremove/clean` and, if a
  compose file is present, `docker compose pull` + `up -d`. Flags: `--full`
  (adds `dist-upgrade`), `--force-recreate`, `--compose-dir=PATH`.
  _Requires: `apt-get`, optionally `docker compose`._
- **sync.sh** — `rclone copy SOURCE DESTINATION` with time-of-day bandwidth
  limits, a flock guard, and `.env`-driven config. See `.env.example`.
  Optional flags `--max-age VALUE` and `--source PATH` override `.env`.
  _Requires: `rclone`, `flock`._
- **sync-kill.sh** — Stops a running `sync.sh` cleanly by signaling the
  process group that holds the lock file.
- **temp-monitoring.sh** — Reads CPU temperature via `vcgencmd` and reboots
  the box if it exceeds the threshold (default 75 °C; override with
  `MAX_TEMP=<n>`). Logs to syslog (tag `temp-monitor`). Must run as root.
  Intended for Raspberry Pi. _Requires: `vcgencmd`, `logger`._
- **setup-shell-defaults.sh** — Bootstrap a fresh Debian-like box with a
  personal `update` alias (skipped when an `update` command such as
  `update.sh` is installed), arrow-key history search, and the `joe` editor.
  Idempotent. See header for the `curl | sudo bash` invocation.
- **clean-temp.sh** — Deletes macOS junk (`.DS_Store`, `._*`, `__MACOSX`)
  from a directory tree on one filesystem. `--dry-run` lists only;
  `--no-wake` (root) exits if the disk is spun down. Leaves `.Trashes` and
  `.TemporaryItems` alone. _`--no-wake` requires: `findmnt`, `hdparm`._

### powershell/
- **batch-encode.ps1** — Re-encodes any HD+ video in the current directory
  to AV1 + Opus using ffmpeg. Skips already-encoded files (`*_av1`) and HDR
  sources (no tonemap). Output mtime is copied from the source.
  _Requires: `ffmpeg`, `ffprobe` on `PATH`. PowerShell 5.1+ (Windows
  PowerShell or PowerShell 7)._

  Run from the directory you want to scan:

  ```powershell
  cd D:\Videos
  powershell -ExecutionPolicy Bypass -File C:\path\to\batch-encode.ps1
  ```

  Or, to invoke `.ps1` files directly without `-ExecutionPolicy Bypass`,
  relax the policy once per user:

  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```
- **upgrade-apps.bat** — Self-elevates to admin and runs
  `winget upgrade --all` (accepting agreements, including unknown-version
  apps). Double-click to run.

### python/media-renamer/
- Renames image/video files to `YYYY-MM-DD_HH-MM-SS[_DEVICE].ext` using
  EXIF / ffprobe metadata (with filename and file-attribute fallbacks).
  Run `python media_renamer.py <path> [--execute|--draft]`. See its
  `README.md` for details.

### python/command-executor/
- Applies a YAML list of rename / move / delete operations, dry-run by
  default. Moves are two-phase (swaps work), deletes go to a trash folder,
  and every run writes an undo file. Run
  `python command_executor.py --commands commands.yaml [--execute]`. See its
  `README.md` for the format and safety rules.

## Development

- Bash scripts standardize on `#!/usr/bin/env bash` + `set -euo pipefail`.
- Lint locally before pushing:
  - `shellcheck bash/*.sh`
  - `Invoke-ScriptAnalyzer -Path powershell -Recurse` (PowerShell)
  - `pytest` in `python/media-renamer` and `python/command-executor`
- CI (`.github/workflows/lint.yml`) re-runs all three on every push / PR.
- `.editorconfig` + `.gitattributes` pin formatting and EOLs (LF, with
  `*.ps1` / `*.bat` kept as CRLF for Windows-native tooling).
