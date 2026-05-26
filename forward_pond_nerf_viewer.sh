#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <user@host> [local-port] [remote-port]" >&2
    exit 1
fi

REMOTE_HOST="$1"
LOCAL_PORT="${2:-7008}"
REMOTE_PORT="${3:-7008}"

exec ssh -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" "${REMOTE_HOST}"
