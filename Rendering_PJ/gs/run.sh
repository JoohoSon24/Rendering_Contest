#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  gs/run.sh — Gaussian Splatting 학습 (전처리 완료 후)
#  학습 → 메시 추출 → 렌더링 한 번에
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행 (sdfstudio 아님!)
#  2. ~/Rendering_Contest 에서 실행: bash gs/run.sh
#  3. data/processed/ 안에 전처리된 폴더가 있어야 함
#  4. DATA, EXP, MAX_ITERS 변수를 수정해 사용
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
EXP="object2"           # 실험 이름 (폴더명)   
MODEL="splatfacto"          # splatfacto | splatfacto-big
MAX_ITERS=10000
VIS="viewer"
GPU_ID="0"
# ─────────────────────────────────────────────────────────────────────────────

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1

TIMESTAMP=$(date "+%Y-%m-%d_%H%M%S")

echo "════════════════════════════════════════"
echo "  [1/3] Gaussian Splatting 학습"
echo "  모델: $MODEL  iter: $MAX_ITERS"
echo "════════════════════════════════════════"

export CUDA_VISIBLE_DEVICES="$GPU_ID"
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"  # A100 네이티브, Hopper+ PTX 포워드 호환
ns-train "$MODEL" \
    --vis "$VIS" \
    --experiment-name "$EXP" \
    --max-num-iterations "$MAX_ITERS" \
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
