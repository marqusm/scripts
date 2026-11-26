#!/usr/bin/env bash
# Delete macOS junk from a directory tree. Not .Trashes -- that holds files
# deleted on a Mac but not yet emptied from the Trash.
#
#   clean-temp.sh [--dry-run] [--no-wake] [PATH]
#
#   --dry-run  Print what would be deleted, delete nothing.
#   --no-wake  Exit without cleaning if the disk is spun down. Needs root.
#              Assumes a /dev/sdaN-style disk.
set -eu

# Not .TemporaryItems: macOS stages in-flight copies and saves there, so
# deleting it can break a transfer that is running right now.
PATTERNS=(.DS_Store '._*' __MACOSX)

dry=0
no_wake=0
while [ $# -gt 0 ]; do
    case $1 in
        --dry-run) dry=1 ;;
        --no-wake) no_wake=1 ;;
        *) break ;;
    esac
    shift
done
target="${1:-.}"

if [ "$no_wake" = 1 ]; then
    # Without root hdparm fails silently and we'd clean (and wake) anyway.
    [ "$(id -u)" = 0 ] || { echo "--no-wake needs root" >&2; exit 1; }
    dev=$(findmnt -no SOURCE -T "$target" | sed 's/[0-9]*$//')
    # -C reports spin state without waking the drive; -c would wake it.
    case $(hdparm -C "$dev") in
        *standby*|*sleeping*) exit 0 ;;
    esac
fi

# Turn PATTERNS into `-name a -o -name b -o ...` for a single find pass.
expr=()
for p in "${PATTERNS[@]}"; do
    expr+=(-name "$p" -o)
done
unset 'expr[-1]'

action=(-print -exec rm -rf {} +)
[ "$dry" = 1 ] && action=(-print)

# -xdev stays on one filesystem, -prune skips descending into dirs we delete.
find "$target" -xdev \( "${expr[@]}" \) -prune "${action[@]}"
