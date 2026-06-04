#!/usr/bin/env bash
set -euo pipefail

############################################################
# Usage
############################################################
# Recursively delete macOS-generated cruft (Finder/Spotlight/AppleDouble
# leftovers) from a directory tree. Useful after copying files from a Mac
# to a non-Mac filesystem (USB drive, NAS, archive, ...).
#
#   clean-temp.sh [--dry-run] [PATH]
#
# Args:
#   PATH        Directory to clean. Defaults to current directory.
#
# Flags:
#   --dry-run   Print what would be deleted without removing anything.
#   --no-wake   Skip cleanup if the disk backing PATH is spun down
#               (standby/sleeping). Linux only; needs `hdparm` (usually
#               root). Use in cron on NAS/HDD so cleanup never wakes the
#               drive on its own.
#   -h|--help   Show this help.
#
# Examples:
#   clean-temp.sh                       # clean cwd
#   clean-temp.sh /mnt/usb              # clean a mounted drive
#   clean-temp.sh --dry-run /mnt/usb    # preview only
#   clean-temp.sh --no-wake /mnt/nas    # only run if disk already spinning
#
# Extending: add new entries to PATTERNS below. Each entry is matched by
# `find -name`, against both files and directories, so glob metacharacters
# work (e.g. `._*`).
############################################################

PATTERNS=(
    '.DS_Store'                         # Finder folder metadata
    '._*'                               # AppleDouble resource forks
    '__MACOSX'                          # zip extraction artifacts
)

DRY_RUN=0
NO_WAKE=0
TARGET=""

while [ "$#" -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=1; shift ;;
        --no-wake) NO_WAKE=1; shift ;;
        -h|--help)
            sed -n '4,33p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        --) shift; break ;;
        -*) echo "Unknown flag: $1" >&2; exit 1 ;;
        *)
            [ -z "$TARGET" ] || { echo "Multiple paths given: $TARGET, $1" >&2; exit 1; }
            TARGET="$1"; shift
            ;;
    esac
done

TARGET="${TARGET:-.}"

if [ ! -d "$TARGET" ]; then
    echo "Not a directory: $TARGET" >&2
    exit 1
fi

# Bail early if the target's backing disk is parked. `hdparm -C` reports
# spin state without waking the drive (note: `-c`, lowercase, *would* wake
# it). We resolve TARGET → mount source → parent block device, since hdparm
# wants the whole disk (e.g. /dev/sda), not a partition (/dev/sda1) or LVM
# mapper node.
if [ "$NO_WAKE" -eq 1 ]; then
    for cmd in findmnt lsblk hdparm; do
        command -v "$cmd" >/dev/null 2>&1 \
            || { echo "--no-wake requires $cmd (Linux + util-linux + hdparm)" >&2; exit 1; }
    done

    src=$(findmnt -no SOURCE -T "$TARGET")
    parent=$(lsblk -no pkname "$src" 2>/dev/null | awk 'NF{print; exit}')

    if [ -z "$parent" ]; then
        # No backing block device (tmpfs, NFS, FUSE, ...) — nothing to wake.
        :
    else
        dev="/dev/$parent"
        if ! state_out=$(hdparm -C "$dev" 2>&1); then
            echo "hdparm -C $dev failed: $state_out" >&2
            echo "Hint: --no-wake usually needs root." >&2
            exit 1
        fi
        state=$(awk '/drive state is:/{print $NF}' <<<"$state_out")
        case "$state" in
            standby|sleeping)
                echo "Disk $dev is $state — skipping to avoid wake-up."
                exit 0
                ;;
        esac
        # active/idle or unknown (SSD, USB bridge that lies) → fall through.
    fi
fi

# Build a single `find` invocation: `\( -name p1 -o -name p2 ... \)`. One
# traversal is much faster than re-walking the tree per pattern, and `-prune`
# stops descent into matched directories (e.g. don't recurse into .Trashes
# just to delete its contents — kill it whole).
expr=()
for i in "${!PATTERNS[@]}"; do
    [ "$i" -gt 0 ] && expr+=(-o)
    expr+=(-name "${PATTERNS[$i]}")
done

if [ "$DRY_RUN" -eq 1 ]; then
    find "$TARGET" \( "${expr[@]}" \) -prune -print
else
    # `-print` before `-exec rm` so we get a log of what went; `+` batches.
    find "$TARGET" \( "${expr[@]}" \) -prune -print -exec rm -rf {} +
fi
