#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  make_flyin_render.sh — Part1(interpolate) + Part2(fly-in) 합성
#
#  개요:
#    ns-render interpolate (eval 카메라 경로) 영상과
#    커스텀 fly-in 카메라 경로 영상을 xfade로 이어붙여
#    최종 영상을 만드는 전체 파이프라인.
#
#  사용법:
#    bash scripts/make_flyin_render.sh
#    bash scripts/make_flyin_render.sh -c config.yml -o renders/out.mp4
#
#  핵심 설계 결정:
#    ① 두 영상을 따로 렌더한 뒤 ffmpeg xfade로 합산
#       → 카메라 경로를 하나의 json으로 통합하면 Part1 렌더가
#         background.mp4와 달라지는 문제 때문 (interpolate vs camera-path
#         파이프라인 차이)
#    ② Part2 첫 웨이포인트 = Part1 마지막 위치
#       → 위치 gap = 0 보장
#    ③ xfade duration = 1.0초
#       → 6.36° 시선 방향 차이를 자연스럽게 블렌딩
#    ④ xfade offset = Part1_duration - xfade_duration
#       → fps 변환(816/35 → 24fps) 후 실제 duration 기준 계산
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
eval "$(conda shell.bash hook)"
conda activate nerfstudio
set -u
cd "$ROOT"

# ── 설정 ──────────────────────────────────────────────────────────────────
CONFIG="${ROOT}/outputs/background/splatfacto/2026-06-01_063932/config.yml"
PART2_JSON="${ROOT}/camera_path.json"   # make_camera_path.py로 생성한 fly-in 경로
OUTPUT="${ROOT}/renders/background_flyin_final.mp4"
XFADE_DURATION=1.0    # 경계 페이드 길이 (초). 늘릴수록 전환이 부드러움
DOWNSCALE=4           # 렌더 해상도 축소 배율 (Part1 interpolate 기본값 맞춤)

while getopts "c:p:o:f:d:h" opt; do
    case "$opt" in
        c) CONFIG="$OPTARG" ;;
        p) PART2_JSON="$OPTARG" ;;
        o) OUTPUT="$OPTARG" ;;
        f) XFADE_DURATION="$OPTARG" ;;
        d) DOWNSCALE="$OPTARG" ;;
        h) sed -n '2,25p' "$0"; exit 0 ;;
    esac
done

export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"

TMP_PART1="${ROOT}/renders/_tmp_part1.mp4"
TMP_PART2="${ROOT}/renders/_tmp_part2.mp4"
mkdir -p "${ROOT}/renders"

# ── Step 1: Part1 렌더 (ns-render interpolate) ───────────────────────────
echo ""
echo "▶ [1/3] Part1 렌더 — ns-render interpolate"
echo "   config: $CONFIG"
ns-render interpolate \
    --load-config "$CONFIG" \
    --output-path "$TMP_PART1"
echo "   ✅ $TMP_PART1"

# ── Step 2: Part2 렌더 (커스텀 fly-in 경로) ──────────────────────────────
echo ""
echo "▶ [2/3] Part2 렌더 — ns-render camera-path"
echo "   camera_path: $PART2_JSON"
ns-render camera-path \
    --load-config "$CONFIG" \
    --camera-path-filename "$PART2_JSON" \
    --output-path "$TMP_PART2" \
    --downscale-factor "$DOWNSCALE"
echo "   ✅ $TMP_PART2"

# ── Step 3: xfade 합성 ───────────────────────────────────────────────────
echo ""
echo "▶ [3/3] xfade 합성 (duration=${XFADE_DURATION}초)"

# Part1 실제 duration 계산 (fps 변환 후 기준)
PART1_DUR=$(ffprobe -v quiet -select_streams v:0 \
    -show_entries stream=duration -of csv=p=0 "$TMP_PART1")
XFADE_OFFSET=$(python3 -c "print(round(float('${PART1_DUR}') - float('${XFADE_DURATION}'), 4))")
echo "   Part1 duration: ${PART1_DUR}s  →  xfade offset: ${XFADE_OFFSET}s"

ffmpeg -y \
    -i "$TMP_PART1" \
    -i "$TMP_PART2" \
    -filter_complex \
        "[0:v]fps=24,scale=iw:ih,setsar=1,format=yuv420p[v0];
         [1:v]fps=24,scale=iw:ih,setsar=1,format=yuv420p[v1];
         [v0][v1]xfade=transition=fade:duration=${XFADE_DURATION}:offset=${XFADE_OFFSET}[outv]" \
    -map "[outv]" \
    -c:v libx264 -crf 18 -preset fast \
    "$OUTPUT"

# 임시 파일 삭제
rm -f "$TMP_PART1" "$TMP_PART2"

echo ""
FRAMES=$(ffprobe -v quiet -select_streams v:0 \
    -show_entries stream=nb_frames -of csv=p=0 "$OUTPUT")
SECS=$(ffprobe  -v quiet -select_streams v:0 \
    -show_entries stream=duration  -of csv=p=0 "$OUTPUT")
echo "╔══════════════════════════════════════════════╗"
echo "  ✅ 완료: $OUTPUT"
echo "     ${FRAMES}프레임  ${SECS}초"
echo "╚══════════════════════════════════════════════╝"
