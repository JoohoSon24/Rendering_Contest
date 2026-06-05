#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  scripts/render_custom.sh — 커스텀 카메라 경로로 렌더링
#
#  사용법:
#    bash scripts/render_custom.sh                        # 기본값
#    bash scripts/render_custom.sh -c camera_path.json   # 경로 지정
#    bash scripts/render_custom.sh -o renders/fly.mp4    # 출력 파일 지정
#    bash scripts/render_custom.sh -e background         # 실험 이름 지정
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate nerfstudio
set -u

CAMERA_PATH="${ROOT}/camera_path.json"
OUTPUT="${ROOT}/renders/custom.mp4"
EXP="background"

while getopts "c:o:e:h" opt; do
    case "$opt" in
        c) CAMERA_PATH="$OPTARG" ;;
        o) OUTPUT="$OPTARG" ;;
        e) EXP="$OPTARG" ;;
        h) sed -n '2,8p' "$0"; exit 0 ;;
    esac
done

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1
[[ ! -f "$CAMERA_PATH" ]] && echo "❌ camera_path.json 없음: $CAMERA_PATH" && echo "   먼저: python3 scripts/make_camera_path.py -k 0,50,100,..." && exit 1

# config.yml 자동 탐색 (가장 최근 학습)
CONFIG=$(find "${ROOT}/outputs/${EXP}" -name "config.yml" 2>/dev/null | sort | tail -1 || true)
[[ -z "$CONFIG" ]] && echo "❌ config.yml 없음: outputs/${EXP}/" && exit 1

mkdir -p "$(dirname "$OUTPUT")"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  커스텀 경로 렌더링"
echo "  config      : $CONFIG"
echo "  camera_path : $CAMERA_PATH"
echo "  output      : $OUTPUT"
echo "════════════════════════════════════════════════════════"

export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"

ns-render camera-path \
    --load-config "$CONFIG" \
    --camera-path-filename "$CAMERA_PATH" \
    --output-path "$OUTPUT"

echo ""
echo "✅ 렌더링 완료: $OUTPUT"
