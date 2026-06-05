#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  loss_monitor.sh — 학습 Loss 실시간 모니터링
#  TensorBoard 이벤트 파일을 읽어 터미널에 출력
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행
#  2. ~/Rendering_Contest 에서 실행
#  3. ns-train --vis viewer+tensorboard 로 실행한 경우에만 동작
# ╠══════════════════════════════════════════════════════════════╣
#  사용법:
#    bash loss_monitor.sh                   # 최신 실험 자동 감지
#    bash loss_monitor.sh -e whitedog-resumed  # 실험 이름 지정
#    bash loss_monitor.sh -i 10             # 10초마다 갱신 (default: 5)
#    bash loss_monitor.sh -n 20             # 최근 20개 값 표시 (default: 10)
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate nerfstudio
set -u

EXP=""
INTERVAL=5
TAIL_N=10

while getopts "e:i:n:h" opt; do
    case "$opt" in
        e) EXP="$OPTARG" ;;
        i) INTERVAL="$OPTARG" ;;
        n) TAIL_N="$OPTARG" ;;
        h) sed -n '2,15p' "$0"; exit 0 ;;
    esac
done

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1

echo ""
echo "  🔍 TensorBoard 이벤트 파일 탐색 중..."

python3 - <<PYEOF
import os, sys, time, glob, subprocess
from pathlib import Path

root      = "$ROOT"
exp_name  = "$EXP"
interval  = int("$INTERVAL")
tail_n    = int("$TAIL_N")

def find_event_files(root, exp_name=""):
    pattern = os.path.join(root, "outputs", "**", "events.out.tfevents.*")
    files = glob.glob(pattern, recursive=True)
    if exp_name:
        files = [f for f in files if exp_name in f]
    return sorted(files, key=os.path.getmtime)

def read_events(event_file, max_steps=500):
    """TensorBoard 이벤트 파일에서 scalar 값 읽기"""
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    ea = EventAccumulator(event_file, size_guidance={"scalars": max_steps})
    ea.Reload()
    tags = ea.Tags().get("scalars", [])
    data = {}
    for tag in tags:
        try:
            events = ea.Scalars(tag)
            data[tag] = [(e.step, e.value) for e in events]
        except Exception:
            pass
    return data

def format_loss_table(data, tail_n):
    # 주요 loss 키 우선순위
    priority = ["train_loss", "loss", "rgb_loss", "num_gaussians"]
    keys = sorted(data.keys(), key=lambda k: (
        0 if any(p in k.lower() for p in priority[:2]) else
        1 if any(p in k.lower() for p in priority[2:]) else 2,
        k
    ))

    if not keys:
        return "  (아직 데이터 없음 — 학습 시작 후 잠시 기다리세요)"

    lines = []
    # 공통 step 범위 파악
    all_steps = [sv[-1][0] for sv in data.values() if sv]
    latest_step = max(all_steps) if all_steps else 0

    lines.append(f"  {'Metric':<35} {'Step':>8}  {'Value':>12}  {'Recent':>10}")
    lines.append("  " + "─" * 70)

    for key in keys:
        if key not in data or not data[key]:
            continue
        recent = data[key][-tail_n:]
        latest_step_k, latest_val = recent[-1]
        # 최근 trend (평균)
        if len(recent) >= 2:
            avg = sum(v for _, v in recent) / len(recent)
            trend = "↓" if recent[-1][1] < recent[0][1] else "↑"
        else:
            avg = latest_val
            trend = " "

        short_key = key.replace("Train/", "").replace("train/", "")[:34]
        lines.append(f"  {short_key:<35} {latest_step_k:>8,}  {latest_val:>12.6f}  {trend} avg={avg:.5f}")

    lines.append("  " + "─" * 70)
    lines.append(f"  최신 step: {latest_step:,}")
    return "\n".join(lines)

# 메인 루프
print(f"  갱신 주기: {interval}초  |  표시 개수: 최근 {tail_n}개\n")

while True:
    files = find_event_files(root, exp_name)

    if not files:
        hint = f"-e {exp_name}" if exp_name else ""
        print(f"  ⚠️  이벤트 파일 없음. --vis viewer+tensorboard 로 학습이 실행 중인지 확인하세요.")
        print(f"      재탐색 중... ({interval}초 후)")
        time.sleep(interval)
        continue

    latest_file = files[-1]
    exp_path = str(Path(latest_file).parent)

    # 화면 지우기
    print("\033[2J\033[H", end="")
    print("════════════════════════════════════════════════════════")
    print("  📊 Loss 실시간 모니터  (종료: Ctrl+C)")
    print(f"  실험: {exp_path.replace(root + '/outputs/', '')}")
    print(f"  파일: {os.path.basename(latest_file)}")
    print("════════════════════════════════════════════════════════")

    try:
        data = read_events(latest_file, max_steps=tail_n * 2 + 10)
        print(format_loss_table(data, tail_n))
    except Exception as e:
        print(f"  ⚠️  읽기 오류: {e}")

    print(f"\n  🔄 {interval}초 후 갱신... (Ctrl+C 로 종료)")
    time.sleep(interval)
PYEOF
