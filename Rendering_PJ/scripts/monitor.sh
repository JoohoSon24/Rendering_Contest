#!/usr/bin/env bash
# =============================================================================
#  monitor.sh — 학습 진행 상황 모니터링
# =============================================================================
#
#  Usage:
#    bash monitor.sh          # 1회 출력
#    bash monitor.sh -w       # 5초마다 갱신 (watch 모드)
#    bash monitor.sh -w -i 10 # 10초마다 갱신
#    bash monitor.sh -l       # 최신 학습 로그 tail
#
# =============================================================================

set -euo pipefail

WATCH_MODE=false
INTERVAL=5
LOG_MODE=false
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT_DIR="${ROOT}"

while getopts "wi:lh" opt; do
    case "$opt" in
        w) WATCH_MODE=true ;;
        i) INTERVAL="$OPTARG" ;;
        l) LOG_MODE=true ;;
        h)
            sed -n '3,15p' "$0"
            exit 0
            ;;
    esac
done

# ── 최신 학습 출력 디렉토리 찾기 ──────────────────────────────────────────────
find_latest_run() {
    find "${SCRIPT_DIR}/outputs" -name "config.yml" 2>/dev/null \
        | xargs ls -t 2>/dev/null \
        | head -1 \
        | xargs dirname 2>/dev/null || echo ""
}

# ── 체크포인트에서 step 읽기 ──────────────────────────────────────────────────
get_latest_step() {
    local run_dir="$1"
    local ckpt_dir="${run_dir}/sdfstudio_models"
    [[ -d "${run_dir}/nerfstudio_models" ]] && ckpt_dir="${run_dir}/nerfstudio_models"

    ls "${ckpt_dir}"/*.ckpt 2>/dev/null \
        | xargs ls -t 2>/dev/null \
        | head -1 \
        | grep -oP 'step-\K[0-9]+' || echo "0"
}

# ── 단일 출력 ─────────────────────────────────────────────────────────────────
print_status() {
    local LATEST_RUN
    LATEST_RUN=$(find_latest_run)

    echo ""
    echo "╔══════════════════════════════════════════════════════════╗"
    printf  "║  📊  Training Monitor   %-32s║\n" "$(date '+%H:%M:%S  %Y-%m-%d')"
    echo "╠══════════════════════════════════════════════════════════╣"

    # GPU 상태
    echo "║  🖥️  GPU                                                  ║"
    nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu \
        --format=csv,noheader,nounits 2>/dev/null \
    | while IFS=',' read -r idx name util mem_used mem_total temp; do
        printf "║    GPU%-2s │ util:%3s%% │ mem:%5sMiB/%5sMiB │ %s°C  ║\n" \
            "$idx" "$(echo $util | tr -d ' ')" "$(echo $mem_used | tr -d ' ')" \
            "$(echo $mem_total | tr -d ' ')" "$(echo $temp | tr -d ' ')"
    done

    echo "╠══════════════════════════════════════════════════════════╣"

    # 학습 진행 상황
    echo "║  🎯  Training Progress                                    ║"
    if [[ -n "$LATEST_RUN" ]]; then
        local exp_name model_name timestamp step config
        config="${LATEST_RUN}/config.yml"
        exp_name=$(grep "experiment_name" "$config" 2>/dev/null | head -1 | awk '{print $2}' | tr -d "'" || echo "unknown")
        model_name=$(basename "$(dirname "$LATEST_RUN")")
        timestamp=$(basename "$LATEST_RUN")

        printf "║    실험: %-47s║\n" "$exp_name"
        printf "║    모델: %-47s║\n" "$model_name"
        printf "║    시각: %-47s║\n" "$timestamp"

        # 최신 체크포인트 step
        step=$(get_latest_step "$LATEST_RUN")
        local max_iters
        max_iters=$(grep "max_num_iterations" "$config" 2>/dev/null | head -1 | awk '{print $2}' || echo "20000")

        if [[ "$step" -gt 0 && "$max_iters" -gt 0 ]]; then
            local pct=$(( step * 100 / max_iters ))
            local bar_len=30
            local filled=$(( pct * bar_len / 100 ))
            local bar=""
            for ((i=0; i<filled; i++)); do bar+="█"; done
            for ((i=filled; i<bar_len; i++)); do bar+="░"; done
            printf "║    Step: %6s / %-6s  [%s] %3s%%  ║\n" \
                "$step" "$max_iters" "$bar" "$pct"
        else
            printf "║    %-54s║\n" "Step: 체크포인트 대기 중..."
        fi

        # 출력 파일 목록
        local renders meshes
        renders=$(ls "${LATEST_RUN%/*/*/*}/renders" 2>/dev/null | wc -l || echo 0)
        meshes=$(ls "${LATEST_RUN%/*/*/*}/meshes" 2>/dev/null | wc -l || echo 0)
        printf "║    renders: %-3s개   meshes: %-3s개                        ║\n" "$renders" "$meshes"
    else
        printf "║    %-54s║\n" "아직 학습 출력이 없습니다."
    fi

    echo "╠══════════════════════════════════════════════════════════╣"

    # 디스크 사용량
    echo "║  💾  Disk                                                 ║"
    local total used avail pct_disk
    read total used avail pct_disk < <(df -h "${SCRIPT_DIR}" | tail -1 | awk '{print $2, $3, $4, $5}')
    printf "║    사용: %-6s / %-6s   여유: %-6s  (%s)          ║\n" \
        "$used" "$total" "$avail" "$pct_disk"

    if [[ -n "$LATEST_RUN" ]]; then
        local out_size
        out_size=$(du -sh "${SCRIPT_DIR}/outputs" 2>/dev/null | awk '{print $1}' || echo "0")
        printf "║    outputs/: %-44s║\n" "$out_size"
    fi

    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
}

# ── 로그 모드 ─────────────────────────────────────────────────────────────────
if $LOG_MODE; then
    LATEST_RUN=$(find_latest_run)
    if [[ -z "$LATEST_RUN" ]]; then
        echo "학습 출력을 찾을 수 없습니다."
        exit 1
    fi
    echo "최신 실행: $LATEST_RUN"
    echo "로그 추적 중... (Ctrl+C로 종료)"
    # nerfstudio는 stdout에 출력하므로 tmux에서 확인 권장
    # 대신 체크포인트 생성 이벤트를 감시
    watch -n 2 "ls -lht ${LATEST_RUN}/sdfstudio_models/*.ckpt ${LATEST_RUN}/nerfstudio_models/*.ckpt 2>/dev/null | head -5"
    exit 0
fi

# ── 실행 ──────────────────────────────────────────────────────────────────────
if $WATCH_MODE; then
    echo "Watch 모드 시작 (${INTERVAL}초마다 갱신, Ctrl+C로 종료)"
    while true; do
        clear
        print_status
        sleep "$INTERVAL"
    done
else
    print_status
fi
