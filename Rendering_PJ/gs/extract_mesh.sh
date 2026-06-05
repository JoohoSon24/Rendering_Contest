#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  gs/extract_mesh.sh — Gaussian Splatting 메시 추출
#  Gaussian Splat .ply  (3DGS 원본 포맷, 색상 포함)
#
#  ※ TSDF는 splatfacto와 호환 안 됨 (레이캐스팅 vs 래스터화 구조 차이)
#    → 컬러 폴리곤 메시가 필요하면 nerf/extract_mesh.sh (NeuS-facto) 사용
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행 (sdfstudio 아님!)
#  2. ~/Rendering_Contest 에서 실행
#  3. -c 로 config.yml 경로 반드시 지정
#  4. splat.ply → Supersplat(https://superspl.at), Polycam 등 3DGS 뷰어에서 확인
# ╠══════════════════════════════════════════════════════════════╣
#  사용법:
#    bash gs/extract_mesh.sh -c outputs/.../config.yml -e 실험이름
#    bash gs/extract_mesh.sh -c outputs/.../config.yml -e exp -C rgb  # 일반 PLY 뷰어용
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate nerfstudio
set -u
cd "$ROOT"

# ── 하이퍼파라미터 ────────────────────────────────────────────────────────────
CONFIG=""
EXP_NAME="gs-output"

GS_COLOR_MODE="sh_coeffs"  # sh_coeffs: 구면조화함수 원본 → 3DGS 뷰어(Supersplat)용
                            # rgb       : 단순 RGB 색상  → MeshLab 등 일반 PLY 뷰어용
# ─────────────────────────────────────────────────────────────────────────────

while getopts "c:e:C:h" opt; do
    case "$opt" in
        c) CONFIG="$OPTARG" ;;
        e) EXP_NAME="$OPTARG" ;;
        C) GS_COLOR_MODE="$OPTARG" ;;
        h)
            echo "Options:"
            echo "  -c PATH   config.yml 경로 (필수)"
            echo "  -e STR    실험 이름 (출력 폴더명에 사용)"
            echo "  -C STR    GS 색상 모드: sh_coeffs (3DGS 뷰어용) | rgb (일반 PLY 뷰어용)"
            exit 0 ;;
    esac
done

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1
[[ -z "$CONFIG" ]] && echo "❌ -c config.yml 경로를 지정하세요" && exit 1
[[ ! -f "$CONFIG" ]] && echo "❌ config 파일 없음: $CONFIG" && exit 1

GS_DIR="${ROOT}/meshes/${EXP_NAME}_gaussians"
mkdir -p "$GS_DIR"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  Gaussian Splatting 추출"
echo "════════════════════════════════════════════════════════"
echo "  config     : $CONFIG"
echo "  color_mode : $GS_COLOR_MODE"
echo "  출력       : $GS_DIR/splat.ply"
echo "════════════════════════════════════════════════════════"
echo ""

ns-export gaussian-splat \
    --load-config "$CONFIG" \
    --output-dir "$GS_DIR" \
    --output-filename "splat.ply" \
    --ply-color-mode "$GS_COLOR_MODE"

echo ""
echo "  ✅ $GS_DIR/splat.ply"
echo ""
echo "  뷰어: https://superspl.at/editor  (splat.ply 드래그앤드롭)"
echo "════════════════════════════════════════════════════════"
