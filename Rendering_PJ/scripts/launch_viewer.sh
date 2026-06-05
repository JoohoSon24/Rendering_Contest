#!/bin/bash
# launch_viewer.sh — 가상 디스플레이 시작 + 인터랙티브 뷰어 실행
# 사용법: bash scripts/launch_viewer.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="/home/ubuntu/miniconda3/envs/nerfstudio/bin/python"

# Xvfb 가상 디스플레이 시작 (이미 실행 중이면 재사용)
DISPLAY_NUM=99
if ! pgrep -f "Xvfb :${DISPLAY_NUM}" > /dev/null 2>&1; then
    echo "🖥  Xvfb 가상 디스플레이 시작 (:${DISPLAY_NUM})..."
    Xvfb :${DISPLAY_NUM} -screen 0 1280x1024x24 &
    sleep 1.5
    echo "   Xvfb PID: $!"
else
    echo "🖥  Xvfb :${DISPLAY_NUM} 이미 실행 중."
fi

export DISPLAY=:${DISPLAY_NUM}

echo ""
echo "🚀 인터랙티브 뷰어 실행..."
echo "   조작법: 좌클릭 드래그=회전 | 우클릭 드래그=이동 | 휠=줌 | SPACE=렌더링 | Q=종료"
echo ""

exec "${PYTHON}" "${SCRIPT_DIR}/viewer_render.py" "$@"
