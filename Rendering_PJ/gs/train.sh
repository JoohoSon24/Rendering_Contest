#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  gs/train.sh — Gaussian Splatting 전체 파이프라인
#  영상 → COLMAP 전처리 → 학습
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행 (sdfstudio 아님!)
#  2. ~/Rendering_Contest 에서 실행: bash gs/train.sh
#  3. 입력: data/*.mp4 또는 data/processed/* (이미 전처리된 경우 -d 지정)
#  4. 출력: outputs/{EXP}/splatfacto/{TIMESTAMP}/
#  5. COLMAP은 CPU 모드 (헤드리스 서버 OpenGL 제한)
#  6. 메시 추출은 gs/extract_mesh.sh 별도 실행
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate nerfstudio
set -u

# ── 하이퍼파라미터 ────────────────────────────────────────────────────────────
MODEL="splatfacto"          # splatfacto | splatfacto-big
DATA_PATH="data/background.mov"
DATA_TYPE="auto"
EXP_NAME=""
VIS="viewer"
GPU_ID="0"
MAX_ITERS=30000
NUM_FRAMES=300
PREPROCESS_ONLY=false
SKIP_RENDER=false
SKIP_MESH=false

while getopts "m:d:t:e:v:g:i:f:prxh" opt; do
    case "$opt" in
        m) MODEL="$OPTARG" ;;        d) DATA_PATH="$OPTARG" ;;
        t) DATA_TYPE="$OPTARG" ;;    e) EXP_NAME="$OPTARG" ;;
        v) VIS="$OPTARG" ;;          g) GPU_ID="$OPTARG" ;;
        i) MAX_ITERS="$OPTARG" ;;    f) NUM_FRAMES="$OPTARG" ;;
        p) PREPROCESS_ONLY=true ;;   r) SKIP_RENDER=true ;;
        x) SKIP_MESH=true ;;
        h) sed -n '2,10p' "$0"; exit 0 ;;
    esac
done

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1
[[ "$DATA_PATH" != /* ]] && DATA_PATH="${ROOT}/${DATA_PATH}"
[[ ! -e "$DATA_PATH" ]] && echo "❌ 데이터 없음: $DATA_PATH" && exit 1

IS_VIDEO=false; TRAIN_DATA_PATH=""

if [[ -f "$DATA_PATH" ]]; then
    EXT=$(echo "${DATA_PATH##*.}" | tr '[:upper:]' '[:lower:]')
    case "$EXT" in mp4|mov|avi|mkv|webm|m4v) IS_VIDEO=true ;;
        *) echo "❌ 지원하지 않는 형식: .$EXT" && exit 1 ;; esac
fi

if $IS_VIDEO; then
    BASENAME=$(basename "$DATA_PATH" | sed 's/\.[^.]*$//')
    PROCESSED="${ROOT}/data/processed/${BASENAME}"
    mkdir -p "${ROOT}/data/processed"

    echo "════════════════════════════════════════"
    echo "  [1/2] COLMAP 전처리"
    echo "════════════════════════════════════════"

    export QT_QPA_PLATFORM=offscreen
    ns-process-data video \
        --data "$DATA_PATH" --output-dir "$PROCESSED" \
        --num-frames-target "$NUM_FRAMES" \
        --matching-method sequential --no-gpu

    $PREPROCESS_ONLY && echo "✅ 전처리 완료: $PROCESSED" && exit 0
    TRAIN_DATA_PATH="$PROCESSED"
    [[ "$DATA_TYPE" == "auto" ]] && DATA_TYPE="nerfstudio-data"

elif [[ -d "$DATA_PATH" ]]; then
    TRAIN_DATA_PATH="$DATA_PATH"
    if [[ "$DATA_TYPE" == "auto" ]]; then
        [[ -f "$DATA_PATH/transforms_train.json" ]] && DATA_TYPE="blender-data" \
        || { [[ -f "$DATA_PATH/transforms.json" ]] && DATA_TYPE="nerfstudio-data"; } \
        || { echo "❌ 데이터 타입 감지 실패. -t 옵션 사용"; exit 1; }
    fi
fi

TIMESTAMP=$(date "+%Y-%m-%d_%H%M%S")
[[ -z "$EXP_NAME" ]] && EXP_NAME="${MODEL}-$(basename "$DATA_PATH" | sed 's/\.[^.]*$//')-${TIMESTAMP}"

echo "════════════════════════════════════════"
$IS_VIDEO && echo "  [2/2] Gaussian Splatting 학습" || echo "  Gaussian Splatting 학습"
echo "  모델: $MODEL  iter: $MAX_ITERS"
echo "════════════════════════════════════════"

export CUDA_VISIBLE_DEVICES="$GPU_ID"
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"  # A100 네이티브, Hopper+ PTX 포워드 호환
ns-train "$MODEL" \
    --vis "$VIS" \
    --experiment-name "$EXP_NAME" \
    --max-num-iterations "$MAX_ITERS" \
    --relative-model-dir nerfstudio_models/ \
    --steps-per-save 5000 \
    --timestamp "$TIMESTAMP" \
    --pipeline.model.cull_alpha_thresh 0.15 \
    --pipeline.model.cull_scale_thresh 0.4 \
    --pipeline.model.random_scale 3.0 \
    --pipeline.model.max_gauss_ratio 5.0 \
    "$DATA_TYPE" --data "$TRAIN_DATA_PATH"

CONFIG="outputs/${EXP_NAME}/${MODEL}/${TIMESTAMP}/config.yml"
mkdir -p "${ROOT}/meshes" "${ROOT}/renders"

$SKIP_MESH || bash "${ROOT}/gs/extract_mesh.sh" -c "$CONFIG" -e "$EXP_NAME"

if ! $SKIP_RENDER; then
    ns-render interpolate \
        --load-config "$CONFIG" \
        --output-path "${ROOT}/renders/${EXP_NAME}.mp4"
    echo "✅ 렌더링: renders/${EXP_NAME}.mp4"
fi
