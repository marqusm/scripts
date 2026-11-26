#!/usr/bin/env bash
set -euo pipefail

# run this directly from web by running following command
# curl "https://raw.githubusercontent.com/marqusm/scripts/main/bash/setup-shell-defaults.sh" | sudo bash

# Set update alias. Only when no `update` command exists, so it doesn't shadow
# bash/update.sh installed as /usr/local/bin/update (aliases win over PATH).
if ! grep -q "alias update=" /etc/bash.bashrc; then
    sudo tee -a /etc/bash.bashrc >/dev/null <<'EOF'

# -------
# Aliases
# -------
command -v update >/dev/null 2>&1 || alias update="sudo apt update && sudo apt -y upgrade && sudo apt -y dist-upgrade && sudo apt -y autoremove"
EOF
fi

# Make history work
if ! grep -q "history-search-backward" /etc/inputrc; then
    sudo tee -a /etc/inputrc >/dev/null <<'EOF'

"\e[A": history-search-backward
"\eOA": history-search-backward
"\e[B": history-search-forward
"\eOB": history-search-forward
EOF
fi

# Install Joe
if ! dpkg -s joe >/dev/null 2>&1; then
    sudo apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y joe
fi
