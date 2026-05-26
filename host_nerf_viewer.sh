#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <load-dir> [websocket-port]" >&2
    exit 1
fi

LOAD_DIR="$1"
WEBSOCKET_PORT="${2:-7008}"

cd /home/ubuntu/JW/rend/sdfstudio
source /home/ubuntu/miniconda3/etc/profile.d/conda.sh
conda activate sdfstudio

ns-train nerfacto \
    --vis viewer \
    --data data/nerfstudio/pond_nerf \
    --experiment-name pond-nerfacto-viewer \
    --viewer.start-train False \
    --viewer.websocket-port "${WEBSOCKET_PORT}" \
    --viewer.quit-on-train-completion False \
    --trainer.load-dir "${LOAD_DIR}"
