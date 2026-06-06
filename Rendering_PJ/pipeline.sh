#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  pipeline.sh — GS 전체 파이프라인 오케스트레이터
#
#  config.sh 에서 설정을 읽어 아래 순서로 자동 실행:
#    [1] COLMAP 전처리  (영상 입력 시 자동)
#    [2] GS 학습        (splatfacto)
#    [3] Gaussian PLY 추출
#    [4] GS → OBJ + UV 텍스처  (SuGaR 스타일)
#    [5] OBJ → GLB      (VSCode 뷰어용)
#    [6] 렌더링 영상    (.mp4)
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행
#  2. ~/Rendering_Contest 에서 실행: bash pipeline.sh
#  3. config.sh 에서 DATA 경로만 설정하면 끝
#  4. 특정 단계 건너뜀: config.sh 에서 SKIP_* = true 설정
# ╠══════════════════════════════════════════════════════════════╣
#  사용법:
#    bash pipeline.sh               # config.sh 기본 설정으로 실행
#    bash pipeline.sh -c my.sh      # 다른 config 파일 사용
#    bash pipeline.sh --dry-run     # 실행 없이 경로만 미리 출력
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
set +u
eval "$(conda shell.bash hook)"
conda activate nerfstudio
set -u
cd "$ROOT"

# ── 인수 파싱 ─────────────────────────────────────────────────────────────────
CONFIG_FILE="${ROOT}/config.sh"
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -c|--config)  CONFIG_FILE="$2"; shift 2 ;;
        --dry-run)    DRY_RUN=true; shift ;;
        -h|--help)    sed -n '2,20p' "$0"; exit 0 ;;
        *) echo "❌ 알 수 없는 옵션: $1"; exit 1 ;;
    esac
done

[[ ! -f "$CONFIG_FILE" ]] && echo "❌ config 파일 없음: $CONFIG_FILE" && exit 1
source "$CONFIG_FILE"

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1

# ── 경로 정규화 & 이름 자동 생성 ─────────────────────────────────────────────
[[ "$DATA" != /* ]] && DATA="${ROOT}/${DATA}"
[[ ! -e "$DATA" ]] && echo "❌ 데이터 없음: $DATA" && exit 1
[[ -z "$EXP" ]] && EXP=$(basename "$DATA" | sed 's/\.[^.]*$//')

# ── 출력 경로 정의 (여기서 한 번에 확정) ─────────────────────────────────────
SPLAT_PLY="${ROOT}/meshes/${EXP}_gaussians/splat.ply"
MESH_DIR="${ROOT}/meshes/${EXP}_gaussians/splat_mesh"
OBJ_PATH="${MESH_DIR}/mesh.obj"
GLB_PATH="${MESH_DIR}/mesh.glb"
RENDER_PATH="${ROOT}/renders/${EXP}.mp4"

# ── 실행 계획 출력 ────────────────────────────────────────────────────────────
run_or_skip() { $1 && echo "⏭ SKIP" || echo "▶ RUN"; }
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "  GS 파이프라인"
printf "  %-10s %s\n" "config:"  "$CONFIG_FILE"
printf "  %-10s %s\n" "DATA:"    "$DATA"
printf "  %-10s %s\n" "EXP:"     "$EXP"
printf "  %-10s %s  iter=%s\n" "모델:" "$MODEL" "$MAX_ITERS"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "  [1] 학습          outputs/%s/%s/.../  %s\n"  "$EXP" "$MODEL" "$(run_or_skip $SKIP_TRAIN)"
printf "  [2] PLY 추출      %s  %s\n"  "$SPLAT_PLY"  "$(run_or_skip $SKIP_EXTRACT_PLY)"
printf "  [3] GS→OBJ+tex    %s/  %s\n" "$MESH_DIR"   "$(run_or_skip $SKIP_GS_TO_MESH)"
printf "  [4] OBJ→GLB       %s  %s\n"  "$GLB_PATH"   "$(run_or_skip $SKIP_GLB)"
printf "  [5] 렌더링        %s  %s\n"  "$RENDER_PATH" "$(run_or_skip $SKIP_RENDER)"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

$DRY_RUN && echo "  [dry-run] 실제 실행하지 않습니다." && exit 0

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────
step() { echo ""; echo "▶▶ [$1/$TOTAL_STEPS] $2"; echo "────────────────────────────────"; }
TOTAL_STEPS=5

# gsplat JIT 빌드가 항상 올바른 아키텍처를 사용하도록 전역에서 설정
# (8.0=A100 네이티브, 9.0+PTX=Hopper 이상 향후 GPU 포워드 호환)
export CUDA_VISIBLE_DEVICES="$GPU_ID"
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"

# ── [1] GS 학습 ──────────────────────────────────────────────────────────────
if ! $SKIP_TRAIN; then
    step 1 "GS 학습 (COLMAP 전처리 포함)"
    bash "${ROOT}/gs/train.sh" \
        -d "$DATA" -e "$EXP" -m "$MODEL" \
        -i "$MAX_ITERS" -g "$GPU_ID" -f "$NUM_FRAMES" \
        -r -x
    echo "✅ 학습 완료"
else
    echo "⏭  [1/$TOTAL_STEPS] GS 학습 — SKIP"
fi

# config.yml 탐색
CONFIG=$(find "${ROOT}/outputs/${EXP}/${MODEL}" -name "config.yml" 2>/dev/null | sort | tail -1 || true)
if [[ -z "$CONFIG" ]]; then
    echo "❌ config.yml 을 찾을 수 없습니다: outputs/${EXP}/${MODEL}/"
    echo "   SKIP_TRAIN=true 인 경우 학습이 먼저 완료되어 있어야 합니다."
    exit 1
fi
echo "   config: $CONFIG"

# ── [2] Gaussian PLY 추출 ────────────────────────────────────────────────────
if ! $SKIP_EXTRACT_PLY; then
    step 2 "Gaussian PLY 추출"
    bash "${ROOT}/gs/extract_mesh.sh" -c "$CONFIG" -e "$EXP"
    echo "✅ $SPLAT_PLY"
else
    echo "⏭  [2/$TOTAL_STEPS] PLY 추출 — SKIP"
    [[ ! -f "$SPLAT_PLY" ]] && echo "❌ PLY 없음: $SPLAT_PLY" && exit 1
fi

# ── [3] GS → OBJ + UV 텍스처 ────────────────────────────────────────────────
if ! $SKIP_GS_TO_MESH; then
    step 3 "GS → OBJ + UV 텍스처 (SuGaR 스타일)"
    bash "${ROOT}/scripts/convert_gs_mesh.sh" "$SPLAT_PLY" \
        -o "$MESH_DIR" \
        --opacity "$OPACITY_THRESH" \
        --scale   "$SCALE_THRESH" \
        --depth   "$POISSON_DEPTH" \
        --tex     "$TEXTURE_SIZE"
    echo "✅ $OBJ_PATH"
else
    echo "⏭  [3/$TOTAL_STEPS] GS→OBJ — SKIP"
    [[ ! -f "$OBJ_PATH" ]] && echo "❌ OBJ 없음: $OBJ_PATH" && exit 1
fi

# ── [4] OBJ → GLB ────────────────────────────────────────────────────────────
if ! $SKIP_GLB; then
    step 4 "OBJ → GLB (VSCode 뷰어용)"
    bash "${ROOT}/scripts/convert_to_glb.sh" "$OBJ_PATH" -o "$GLB_PATH"
    echo "✅ $GLB_PATH"
else
    echo "⏭  [4/$TOTAL_STEPS] OBJ→GLB — SKIP"
fi

# ── [5] 렌더링 영상 ──────────────────────────────────────────────────────────
if ! $SKIP_RENDER; then
    step 5 "렌더링 영상 생성"
    mkdir -p "${ROOT}/renders"
    ns-render interpolate \
        --load-config "$CONFIG" \
        --output-path "$RENDER_PATH"
    echo "✅ $RENDER_PATH"
else
    echo "⏭  [5/$TOTAL_STEPS] 렌더링 — SKIP"
fi

# ── 최종 요약 ────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "  ✅ 파이프라인 완료!"
echo "╠══════════════════════════════════════════════════════════════╣"
[[ -f "$SPLAT_PLY"   ]] && echo "  Gaussian PLY  : $SPLAT_PLY"
[[ -f "$OBJ_PATH"    ]] && echo "  OBJ + 텍스처  : $OBJ_PATH"
[[ -f "$GLB_PATH"    ]] && echo "  GLB (VSCode)   : $GLB_PATH"
[[ -f "$RENDER_PATH" ]] && echo "  렌더링 영상   : $RENDER_PATH"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "  뷰어:"
echo "    Gaussian → https://superspl.at/editor  (splat.ply 드래그앤드롭)"
echo "    메시/GLB → VSCode에서 mesh.glb 클릭"
echo "╚══════════════════════════════════════════════════════════════╝"
