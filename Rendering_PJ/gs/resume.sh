#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  gs/resume.sh — Gaussian Splatting 이어서 학습
#  기존 체크포인트에서 재개 → Gaussian PLY 추출 → 렌더링
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행 (sdfstudio 아님!)
#  2. ~/Rendering_Contest 에서 실행: bash gs/resume.sh
#  3. LOAD_DIR에 nerfstudio_models/ 경로를 정확히 지정
#  4. TOTAL_ITERS는 기존 step 포함한 총합
#     (e.g. 기존 30000 + 추가 60000 = 90000)
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate nerfstudio
set -u
cd "$ROOT"

# ── 설정 (여기만 수정) ────────────────────────────────────────────────────────
DATA="data/processed/object"
EXP="object-resumed"
MODEL="splatfacto"          # splatfacto | splatfacto-big

# 기존 체크포인트 폴더 (nerfstudio_models/)
LOAD_DIR="outputs/object/splatfacto/2026-06-01_155116/nerfstudio_models"

TOTAL_ITERS=120000          # 기존 step 포함 총합 (120000 + 100000)
VIS="viewer+tensorboard"    # tensorboard 로깅 활성화 → loss_monitor.sh로 실시간 확인
GPU_ID="0"
# ─────────────────────────────────────────────────────────────────────────────

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1
[[ ! -d "$LOAD_DIR" ]] && echo "❌ 체크포인트 폴더 없음: $LOAD_DIR" && exit 1

TIMESTAMP=$(date "+%Y-%m-%d_%H%M%S")
LATEST_CKPT=$(ls "$LOAD_DIR"/*.ckpt 2>/dev/null | sort -V | tail -1)
CURRENT_STEP=$(basename "$LATEST_CKPT" | grep -oE '[0-9]+' | tail -1 | sed 's/^0*//')

echo "════════════════════════════════════════"
echo "  [1/3] 이어서 학습"
echo "  현재: step ${CURRENT_STEP}  →  목표: ${TOTAL_ITERS}"
echo "  체크포인트: $LOAD_DIR"
echo "════════════════════════════════════════"

export CUDA_VISIBLE_DEVICES="$GPU_ID"
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"  # A100 네이티브, Hopper+ PTX 포워드 호환
ns-train "$MODEL" \
    --vis "$VIS" \
    --experiment-name "$EXP" \
    --load-dir "$LOAD_DIR" \
    --max-num-iterations "$TOTAL_ITERS" \
    --relative-model-dir nerfstudio_models/ \
    --steps-per-save 5000 \
    --timestamp "$TIMESTAMP" \
    nerfstudio-data --data "$DATA"

CONFIG="outputs/${EXP}/${MODEL}/${TIMESTAMP}/config.yml"
mkdir -p meshes renders

echo "════════════════════════════════════════"
echo "  [2/3] Gaussian PLY 추출"
echo "════════════════════════════════════════"
bash "${ROOT}/gs/extract_mesh.sh" -c "$CONFIG" -e "$EXP"

echo "════════════════════════════════════════"
echo "  [3/3] 렌더링"
echo "════════════════════════════════════════"
ns-render interpolate \
    --load-config "$CONFIG" \
    --output-path "renders/${EXP}.mp4"

echo ""
echo "✅ 완료"
echo "   GS .ply : meshes/${EXP}_gaussians/splat.ply  ← superspl.at/editor 에서 확인"
echo "   영상    : renders/${EXP}.mp4"
