#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════════╗
#  generate_final.sh
#
#  GLB 애니메이션 + 배경 영상 → final_transition_output_ver2.mp4
#
#  전제 조건:
#    - conda 환경 nerfstudio 설치 완료
#    - meshes/deformation1.glb 존재
#    - renders/background_flyin_final.mp4 존재
#
#  사용법:
#    bash generate_final.sh                        # 기본값으로 실행
#    bash generate_final.sh --eye "X Y Z"          # 고정 시점 지정
#    bash generate_final.sh --traj orbit           # orbit 렌더링
#    bash generate_final.sh --trim-start 6.58 --trim-end 7.0
#    bash generate_final.sh --skip-deform          # deformation 렌더 생략
#    bash generate_final.sh --help
#
#  단계:
#    [1] 환경 확인 (conda, ffmpeg, GLB, 배경 영상)
#    [2] deformation.mp4 렌더링  (render_deformation.py)
#    [3] crossfade 합성          (ffmpeg xfade)
#    [4] 앞뒤 트림               (ffmpeg trim)
# ╚══════════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(conda run -n nerfstudio which python 2>/dev/null || true)"
[[ -z "$PYTHON" ]] && PYTHON="$(find /home/ubuntu -path "*/envs/nerfstudio/bin/python" 2>/dev/null | head -1)"

# ── 기본값 ─────────────────────────────────────────────────────────
GLB="${ROOT}/meshes/deformation1.glb"
BG="${ROOT}/renders/background_flyin_final.mp4"
DEFORM_OUT="${ROOT}/renders/deformation.mp4"
COMBINED_OUT="${ROOT}/renders/final_transition_output.mp4"
FINAL_OUT="${ROOT}/renders/final_transition_output_ver2.mp4"

TRAJ="fixed"
EYE="1.179537 0.486765 0.260652"   # camera_preview.py로 선택한 시점
SECONDS_DUR=10
FPS=24
WIDTH=540
HEIGHT=963

XFADE_DUR=1.5        # crossfade 길이 (초)
TRIM_START=6.58      # 최종 영상 앞 제거 (초)
TRIM_END=7.0         # 최종 영상 뒤 제거 (초)

SKIP_DEFORM=false
SKIP_COMBINE=false
SKIP_TRIM=false
DRY_RUN=false

# ── 인수 파싱 ───────────────────────────────────────────────────────
usage() {
cat <<EOF
사용법: bash generate_final.sh [옵션]

주요 옵션:
  --glb PATH           GLB 애니메이션 파일  (기본: meshes/deformation1.glb)
  --bg  PATH           배경 영상 파일       (기본: renders/background_flyin_final.mp4)
  --out PATH           최종 출력 경로       (기본: renders/final_transition_output_ver2.mp4)

  --traj fixed|orbit   카메라 트라젝토리    (기본: fixed)
  --eye "X Y Z"        고정 시점 eye 좌표   (기본: 1.179537 0.486765 0.260652)
  --seconds N          deformation 길이(초) (기본: 10)

  --xfade N            crossfade 길이(초)   (기본: 1.5)
  --trim-start N       앞 제거(초)          (기본: 6.58)
  --trim-end   N       뒤 제거(초)          (기본: 7.0)

  --skip-deform        deformation 렌더링 생략 (기존 파일 사용)
  --skip-combine       합성 생략 (기존 combined 파일 사용)
  --skip-trim          트림 생략
  --dry-run            실제 실행 없이 계획만 출력

  --help               이 도움말 출력
EOF
exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --glb)          GLB="$2";          shift 2 ;;
        --bg)           BG="$2";           shift 2 ;;
        --out)          FINAL_OUT="$2";    shift 2 ;;
        --traj)         TRAJ="$2";         shift 2 ;;
        --eye)          EYE="$2";          shift 2 ;;
        --seconds)      SECONDS_DUR="$2";  shift 2 ;;
        --xfade)        XFADE_DUR="$2";    shift 2 ;;
        --trim-start)   TRIM_START="$2";   shift 2 ;;
        --trim-end)     TRIM_END="$2";     shift 2 ;;
        --skip-deform)  SKIP_DEFORM=true;  shift ;;
        --skip-combine) SKIP_COMBINE=true; shift ;;
        --skip-trim)    SKIP_TRIM=true;    shift ;;
        --dry-run)      DRY_RUN=true;      shift ;;
        --help|-h)      usage ;;
        *) echo "❌ 알 수 없는 옵션: $1"; usage ;;
    esac
done

# ── 컬러 출력 헬퍼 ──────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}▶ $*${NC}"; }
warn()  { echo -e "${YELLOW}⚠  $*${NC}"; }
error() { echo -e "${RED}❌ $*${NC}" >&2; exit 1; }
step()  { echo ""; echo -e "${GREEN}══ [$1/4] $2 ══${NC}"; }

# ── 계획 출력 ──────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "  generate_final.sh — Deformation + Background → Final Video"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "  %-16s %s\n" "GLB:"          "$GLB"
printf "  %-16s %s\n" "Background:"   "$BG"
printf "  %-16s %s  (traj=%s)\n" "Deform out:"  "$DEFORM_OUT" "$TRAJ"
printf "  %-16s %s\n" "Combined:"     "$COMBINED_OUT"
printf "  %-16s %s\n" "Final out:"    "$FINAL_OUT"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "  %-16s eye=[%s]\n" "Camera:"  "$EYE"
printf "  %-16s xfade=%.1fs  trim_start=%.2fs  trim_end=%.1fs\n" \
       "Timing:" "$XFADE_DUR" "$TRIM_START" "$TRIM_END"
echo "╠══════════════════════════════════════════════════════════════╣"
printf "  [1] 환경 확인\n"
printf "  [2] Deformation 렌더링  %s\n" "$(${SKIP_DEFORM} && echo '⏭ SKIP' || echo '▶ RUN')"
printf "  [3] Crossfade 합성      %s\n" "$(${SKIP_COMBINE} && echo '⏭ SKIP' || echo '▶ RUN')"
printf "  [4] 앞뒤 트림           %s\n" "$(${SKIP_TRIM} && echo '⏭ SKIP' || echo '▶ RUN')"
echo "╚══════════════════════════════════════════════════════════════╝"

$DRY_RUN && warn "dry-run 모드 — 실제 실행하지 않습니다." && exit 0

mkdir -p "${ROOT}/renders"

# ══════════════════════════════════════════════════════════════════
# [1] 환경 확인
# ══════════════════════════════════════════════════════════════════
step 1 "환경 확인"

[[ ! -f "$PYTHON" ]] && error "Python 없음: $PYTHON\n  bash scripts/setup_nerfstudio_env.sh 먼저 실행"
[[ ! -f "$GLB" ]]    && error "GLB 파일 없음: $GLB"
[[ ! -f "$BG" ]]     && error "배경 영상 없음: $BG"
command -v ffmpeg >/dev/null || error "ffmpeg 없음: sudo apt-get install -y ffmpeg"

# pyrender EGL 확인
"$PYTHON" -c "
import os; os.environ['PYOPENGL_PLATFORM']='egl'
import pyrender
" 2>/dev/null || error "pyrender EGL 초기화 실패. conda activate nerfstudio 확인"

info "환경 확인 완료"
echo "   Python : $PYTHON"
echo "   GLB    : $GLB  ($(du -sh "$GLB" | cut -f1))"
echo "   BG     : $BG   ($(du -sh "$BG" | cut -f1))"

export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"

# ══════════════════════════════════════════════════════════════════
# [2] Deformation 렌더링
# ══════════════════════════════════════════════════════════════════
step 2 "Deformation 렌더링"

if $SKIP_DEFORM; then
    warn "SKIP — 기존 파일 사용: $DEFORM_OUT"
    [[ ! -f "$DEFORM_OUT" ]] && error "deformation 파일 없음: $DEFORM_OUT"
else
    RENDER_ARGS=(
        --seconds "$SECONDS_DUR"
        --fps     "$FPS"
        --width   "$WIDTH"
        --height  "$HEIGHT"
        -o        "$DEFORM_OUT"
    )

    if [[ "$TRAJ" == "fixed" ]]; then
        read -ra EYE_ARR <<< "$EYE"
        RENDER_ARGS+=(--traj fixed --eye "${EYE_ARR[@]}")
        echo "   traj=fixed  eye=[$EYE]"
    else
        RENDER_ARGS+=(--traj orbit)
        echo "   traj=orbit"
    fi

    echo "   실행: python scripts/render_deformation.py ..."
    "$PYTHON" "${ROOT}/scripts/render_deformation.py" "${RENDER_ARGS[@]}"

    [[ ! -f "$DEFORM_OUT" ]] && error "deformation 렌더링 실패"
    DEFORM_DUR=$(ffprobe -v quiet -select_streams v:0 \
        -show_entries stream=duration -of csv=p=0 "$DEFORM_OUT")
    info "Deformation 렌더링 완료  (${DEFORM_DUR}s)"
fi

# ══════════════════════════════════════════════════════════════════
# [3] Crossfade 합성
# ══════════════════════════════════════════════════════════════════
step 3 "Crossfade 합성"

if $SKIP_COMBINE; then
    warn "SKIP — 기존 파일 사용: $COMBINED_OUT"
    [[ ! -f "$COMBINED_OUT" ]] && error "합성 파일 없음: $COMBINED_OUT"
else
    BG_DUR=$(ffprobe -v quiet -select_streams v:0 \
        -show_entries stream=duration -of csv=p=0 "$BG")
    XFADE_OFFSET=$(python3 -c "print(max(0, float('$BG_DUR') - float('$XFADE_DUR')))")

    echo "   배경:   ${BG_DUR}s"
    echo "   xfade:  offset=${XFADE_OFFSET}s  duration=${XFADE_DUR}s"

    ffmpeg -y -i "$BG" -i "$DEFORM_OUT" \
        -filter_complex "
          [0:v]fps=${FPS},scale=${WIDTH}:${HEIGHT},setsar=1,format=yuv420p[v0];
          [1:v]fps=${FPS},scale=${WIDTH}:${HEIGHT},setsar=1,format=yuv420p[v1];
          [v0][v1]xfade=transition=fade:duration=${XFADE_DUR}:offset=${XFADE_OFFSET}[outv]
        " \
        -map "[outv]" \
        -c:v libx264 -crf 18 -preset fast \
        "$COMBINED_OUT" 2>&1 | grep -E "frame=|time=|Error" || true

    [[ ! -s "$COMBINED_OUT" ]] && error "합성 실패: $COMBINED_OUT"
    COMBINED_DUR=$(ffprobe -v quiet -select_streams v:0 \
        -show_entries stream=duration -of csv=p=0 "$COMBINED_OUT")
    info "합성 완료  (${COMBINED_DUR}s)"
fi

# ══════════════════════════════════════════════════════════════════
# [4] 앞뒤 트림
# ══════════════════════════════════════════════════════════════════
step 4 "앞뒤 트림"

if $SKIP_TRIM; then
    warn "SKIP — 트림 생략"
    FINAL_OUT="$COMBINED_OUT"
else
    COMBINED_DUR=$(ffprobe -v quiet -select_streams v:0 \
        -show_entries stream=duration -of csv=p=0 "$COMBINED_OUT")
    TRIM_DUR=$(python3 -c "
d = float('$COMBINED_DUR') - float('$TRIM_START') - float('$TRIM_END')
print(max(0.1, d))
")
    echo "   원본: ${COMBINED_DUR}s"
    echo "   제거: 앞 ${TRIM_START}s  뒤 ${TRIM_END}s  → 남은 길이: ${TRIM_DUR}s"

    # yuv420p 홀수 높이 대응: HEIGHT-1 (짝수)
    ENCODE_H=$(python3 -c "h=int('$HEIGHT'); print(h if h%2==0 else h-1)")

    ffmpeg -y -ss "$TRIM_START" -i "$COMBINED_OUT" -t "$TRIM_DUR" \
        -vf "scale=${WIDTH}:${ENCODE_H}" \
        -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p \
        "$FINAL_OUT" 2>&1 | grep -E "frame=|time=|Error" || true

    [[ ! -s "$FINAL_OUT" ]] && error "트림 실패: $FINAL_OUT"
    FINAL_DUR=$(ffprobe -v quiet -select_streams v:0 \
        -show_entries stream=duration -of csv=p=0 "$FINAL_OUT")
    info "트림 완료  (${FINAL_DUR}s)"
fi

# ══════════════════════════════════════════════════════════════════
# 최종 요약
# ══════════════════════════════════════════════════════════════════
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "  ✅ 완료!"
echo "╠══════════════════════════════════════════════════════════════╣"
for f in "$DEFORM_OUT" "$COMBINED_OUT" "$FINAL_OUT"; do
    [[ -f "$f" ]] && printf "  %-40s %s\n" "$(basename "$f")" "$(du -sh "$f" | cut -f1)"
done
echo "╚══════════════════════════════════════════════════════════════╝"
