#!/usr/bin/env bash

set -euo pipefail

PORT="${1:-7008}"

exec /home/ubuntu/JW/rend/sdfstudio/host_nerf_viewer.sh \
    /home/ubuntu/JW/rend/sdfstudio/outputs/pond-nerfacto/nerfacto/2026-05-22_134600/sdfstudio_models \
    "${PORT}"
