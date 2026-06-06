#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  convert_gs_mesh.sh — GS PLY → OBJ + UV 텍스처 (Blender/Unity용)
#
#  SuGaR 스타일 간이 파이프라인:
#    Gaussian 필터링 → Poisson 메시 → KNN 색상 전이
#    → xatlas UV 언래핑 → 텍스처 베이킹 → OBJ + PNG 출력
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행
#  2. ~/Rendering_Contest 에서 실행
#  3. 입력: GS splat.ply (ns-export gaussian-splat 결과)
#  4. 출력: {입력폴더}/{파일명}_mesh/  (mesh.obj + mesh.mtl + texture.png)
# ╠══════════════════════════════════════════════════════════════╣
#  사용법:
#    bash convert_gs_mesh.sh meshes/gs-IMG_1217_gaussians/splat.ply
#    bash convert_gs_mesh.sh meshes/gs-IMG_1217_gaussians/splat.ply -o out/
#    bash convert_gs_mesh.sh meshes/.../splat.ply --opacity 0.05 --depth 10 --tex 4096
#
#  주요 옵션:
#    -o DIR     출력 폴더
#    --opacity  Gaussian 필터 임계값 (default: 0.1, 낮출수록 더 많은 Gaussian 포함)
#    --scale    최대 scale 임계값 (default: 0.3, 플로터 제거)
#    --depth    Poisson 재구성 깊이 (default: 9, 클수록 세밀·느림)
#    --tex      텍스처 해상도 px (default: 2048, 4096이면 고품질)
#    --knn      색상 전이 KNN 이웃 수 (default: 5)
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
eval "$(conda shell.bash hook)"
conda activate nerfstudio
set -u

# ── 인수 파싱 ─────────────────────────────────────────────────────────────────
INPUT=""
OUTPUT_DIR=""
OPACITY=0.1
SCALE=0.3
DEPTH=9
DENSITY=0.1
TEX=2048
KNN=5

usage() {
    sed -n '2,25p' "$0"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)   usage ;;
        -o)          OUTPUT_DIR="$2"; shift 2 ;;
        --output)    OUTPUT_DIR="$2"; shift 2 ;;
        --opacity)   OPACITY="$2";    shift 2 ;;
        --scale)     SCALE="$2";      shift 2 ;;
        --depth)     DEPTH="$2";      shift 2 ;;
        --density)   DENSITY="$2";    shift 2 ;;
        --tex)       TEX="$2";        shift 2 ;;
        --knn)       KNN="$2";        shift 2 ;;
        -*)          echo "❌ 알 수 없는 옵션: $1"; exit 1 ;;
        *)           INPUT="$1";      shift ;;
    esac
done

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1
[[ -z "$INPUT" ]] && echo "❌ 입력 PLY 파일을 지정하세요" && usage
[[ "$INPUT" != /* ]] && INPUT="${ROOT}/${INPUT}"
[[ ! -f "$INPUT" ]] && echo "❌ 파일 없음: $INPUT" && exit 1

# ── 실행 ─────────────────────────────────────────────────────────────────────
ARGS=(
    "$INPUT"
    --opacity-threshold "$OPACITY"
    --scale-threshold   "$SCALE"
    --poisson-depth     "$DEPTH"
    --density-quantile  "$DENSITY"
    --texture-size      "$TEX"
    --knn               "$KNN"
)
[[ -n "$OUTPUT_DIR" ]] && ARGS+=(-o "$OUTPUT_DIR")

python3 "${ROOT}/scripts/gs_to_mesh.py" "${ARGS[@]}"
