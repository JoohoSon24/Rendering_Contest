#!/usr/bin/env python3
"""
make_camera_path.py — 커스텀 카메라 경로 생성 → camera_path.json

COLMAP transforms.json의 카메라 포즈를 키프레임으로 선택하거나,
직접 위치(look-at)를 지정해 보간된 카메라 경로를 만듭니다.
출력된 camera_path.json은 ns-render camera-path 에 바로 사용합니다.

────────────────────────────────────────────────────────────────
[모드 1] 기존 카메라 인덱스만 사용
  python3 scripts/make_camera_path.py -k 0,50,150,300,351

[모드 2] look-at만 사용
  python3 scripts/make_camera_path.py \\
    --lookat "eye=1.0,-2.0,0.5 at=0,0,0 up=0,0,1" \\
    --lookat "eye=-1.0,2.0,0.5 at=0,0,0 up=0,0,1"

[모드 3] 혼합: --waypoint 로 순서 지정 (기존 카메라 + look-at 섞기)
  python3 scripts/make_camera_path.py \\
    --waypoint 0:88 \\
    --waypoint "eye=0.5,-0.8,0.2 at=0,0,0" \\
    --waypoint "eye=-0.5,0.8,0.3 at=0,0,0" \\
    --seconds 10

  → 카메라 0→88까지 실제 촬영 경로 따라가다가
    이후 커스텀 위치로 자유롭게 이동

  --waypoint 값 형식:
    숫자          예) 0, 88, 175     → 카메라 인덱스 단일 지정
    start:end     예) 0:88           → 0번부터 88번까지 모두 (끝 포함)
    start:end:step예) 0:88:5         → 0, 5, 10, ..., 85 (5프레임 간격)
    역방향        예) 88:0:-1        → 88, 87, ..., 0 (역순)
    'eye=...'     예) 'eye=0.5,-0.8,0.2 at=0,0,0'  → look-at 커스텀 포즈

[렌더링]
  ns-render camera-path \\
    --load-config outputs/background/splatfacto/.../config.yml \\
    --camera-path-filename camera_path.json \\
    --output-path renders/custom.mp4
────────────────────────────────────────────────────────────────
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import List

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# 좌표계 변환
# ─────────────────────────────────────────────────────────────────────────────

def apply_dataparser_transform(c2ws: np.ndarray, dp_path: str) -> np.ndarray:
    """
    transforms.json 공간 → nerfstudio 훈련 공간으로 변환.
    dataparser_transforms.json의 transform + scale 적용.

    c2ws: (N,4,4) float64
    반환: (N,4,4) 훈련 공간 c2w
    """
    with open(dp_path) as f:
        dp = json.load(f)

    T3x4 = np.array(dp["transform"], dtype=np.float64)   # (3,4)
    T = np.vstack([T3x4, [0, 0, 0, 1]])                  # (4,4)
    scale = float(dp["scale"])

    out = []
    for c2w in c2ws:
        c2w_new = T @ c2w                          # 회전+평행이동 적용
        c2w_new[:3, 3] *= scale                    # 번역 스케일 적용
        out.append(c2w_new)
    return np.array(out)


# ─────────────────────────────────────────────────────────────────────────────
# 회전 보간 (Slerp)
# ─────────────────────────────────────────────────────────────────────────────

def mat_to_quat(R: np.ndarray) -> np.ndarray:
    """3x3 회전행렬 → 쿼터니언 (w,x,y,z)"""
    tr = R[0, 0] + R[1, 1] + R[2, 2]
    if tr > 0:
        s = 0.5 / math.sqrt(tr + 1.0)
        w = 0.25 / s
        x = (R[2, 1] - R[1, 2]) * s
        y = (R[0, 2] - R[2, 0]) * s
        z = (R[1, 0] - R[0, 1]) * s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = 2.0 * math.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = 2.0 * math.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z], dtype=np.float64)
    return q / np.linalg.norm(q)


def quat_to_mat(q: np.ndarray) -> np.ndarray:
    """쿼터니언 (w,x,y,z) → 3x3 회전행렬"""
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([
        [1 - 2*(y*y + z*z),     2*(x*y - z*w),     2*(x*z + y*w)],
        [    2*(x*y + z*w), 1 - 2*(x*x + z*z),     2*(y*z - x*w)],
        [    2*(x*z - y*w),     2*(y*z + x*w), 1 - 2*(x*x + y*y)],
    ], dtype=np.float64)


def slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
    """쿼터니언 Slerp: q0에서 q1까지 t(0~1) 보간"""
    q0 = q0 / np.linalg.norm(q0)
    q1 = q1 / np.linalg.norm(q1)
    dot = np.clip(np.dot(q0, q1), -1.0, 1.0)
    if dot < 0:            # 최단 경로 선택
        q1 = -q1
        dot = -dot
    if dot > 0.9995:       # 거의 같으면 선형 보간
        return (q0 + t * (q1 - q0)) / np.linalg.norm(q0 + t * (q1 - q0))
    theta0 = math.acos(dot)
    theta = theta0 * t
    sin_t  = math.sin(theta)
    sin_t0 = math.sin(theta0)
    s0 = math.cos(theta) - dot * sin_t / sin_t0
    s1 = sin_t / sin_t0
    return s0 * q0 + s1 * q1


def catmull_rom(p0, p1, p2, p3, t: float):
    """Catmull-Rom 스플라인 (위치 보간용)"""
    t2, t3 = t * t, t * t * t
    return 0.5 * (
        2 * p1
        + (-p0 + p2) * t
        + (2*p0 - 5*p1 + 4*p2 - p3) * t2
        + (-p0 + 3*p1 - 3*p2 + p3) * t3
    )


# ─────────────────────────────────────────────────────────────────────────────
# 카메라 경로 생성
# ─────────────────────────────────────────────────────────────────────────────

def interpolate_path(keyframe_c2ws: np.ndarray, total_frames: int) -> np.ndarray:
    """
    키프레임 c2w 배열을 total_frames 개로 부드럽게 보간.
    위치: Catmull-Rom 스플라인
    회전: Slerp
    반환: (total_frames, 4, 4)
    """
    K = len(keyframe_c2ws)
    if K < 2:
        return np.tile(keyframe_c2ws[0:1], (total_frames, 1, 1))

    positions = keyframe_c2ws[:, :3, 3]
    quats = np.array([mat_to_quat(c2w[:3, :3]) for c2w in keyframe_c2ws])

    # 부드러운 q 연속성: 인접 쿼터니언 부호 정렬
    for i in range(1, K):
        if np.dot(quats[i - 1], quats[i]) < 0:
            quats[i] = -quats[i]

    result = []
    # 각 세그먼트에 균등 프레임 배분
    frames_per_seg = total_frames / max(K - 1, 1)

    for seg in range(K - 1):
        seg_frames = round(frames_per_seg * (seg + 1)) - round(frames_per_seg * seg)
        seg_frames = max(1, seg_frames)

        # Catmull-Rom 제어점 (경계 클램프)
        i0 = max(seg - 1, 0)
        i1 = seg
        i2 = min(seg + 1, K - 1)
        i3 = min(seg + 2, K - 1)

        for f in range(seg_frames):
            t = f / seg_frames
            # 위치
            pos = catmull_rom(positions[i0], positions[i1], positions[i2], positions[i3], t)
            # 회전 (직접 인접 키프레임 Slerp)
            rot_mat = quat_to_mat(slerp(quats[i1], quats[i2], t))

            c2w = np.eye(4)
            c2w[:3, :3] = rot_mat
            c2w[:3, 3] = pos
            result.append(c2w)

    # 마지막 키프레임
    result.append(keyframe_c2ws[-1].copy())
    return np.array(result[:total_frames])


def lookat_c2w(eye: np.ndarray, at: np.ndarray, up: np.ndarray) -> np.ndarray:
    """look-at 파라미터 → c2w 4x4 행렬 (nerfstudio 좌표계: X우, Y위, Z뒤)"""
    forward = eye - at
    norm = np.linalg.norm(forward)
    if norm < 1e-8:
        raise ValueError("eye와 at이 너무 가깝습니다")
    forward = forward / norm

    right = np.cross(up, forward)
    right_norm = np.linalg.norm(right)
    if right_norm < 1e-8:
        raise ValueError("up 벡터와 시선 방향이 평행합니다")
    right = right / right_norm

    true_up = np.cross(forward, right)

    c2w = np.eye(4)
    c2w[:3, 0] = right
    c2w[:3, 1] = true_up
    c2w[:3, 2] = forward
    c2w[:3, 3] = eye
    return c2w


def parse_lookat(s: str) -> np.ndarray:
    """
    "eye=x,y,z at=x,y,z up=x,y,z" 파싱 → c2w (4x4)
    up 생략 가능 (기본값: 0,0,1)
    """
    parts = {}
    for tok in s.split():
        k, v = tok.split("=")
        parts[k.strip()] = np.array([float(x) for x in v.split(",")])
    eye = parts["eye"]
    at  = parts["at"]
    up  = parts.get("up", np.array([0.0, 0.0, 1.0]))
    return lookat_c2w(eye, at, up)


# ─────────────────────────────────────────────────────────────────────────────
# camera_path.json 직렬화
# ─────────────────────────────────────────────────────────────────────────────

def fov_from_focal(focal: float, sensor_size: float) -> float:
    """focal length → field of view (degrees)"""
    return 2 * math.degrees(math.atan(sensor_size / (2 * focal)))


def make_camera_path_json(
    c2ws_train: np.ndarray,   # (N,4,4) 훈련 공간 c2w
    fov_deg: float,
    render_w: int,
    render_h: int,
    fps: int,
) -> dict:
    """nerfstudio camera_path.json 딕셔너리 생성"""
    seconds = len(c2ws_train) / fps
    camera_path = []
    for c2w in c2ws_train:
        # 4x4 행렬을 row-major flat list로 직렬화
        flat = c2w.flatten().tolist()
        camera_path.append({
            "camera_to_world": flat,
            "fov": fov_deg,
            "aspect": render_w / render_h,
        })
    return {
        "camera_path": camera_path,
        "render_height": render_h,
        "render_width": render_w,
        "camera_type": "perspective",
        "fps": fps,
        "seconds": seconds,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 범위 파싱 유틸
# ─────────────────────────────────────────────────────────────────────────────

def _is_range(s: str) -> bool:
    """'0:88' 또는 '0:88:5' 형태인지 확인"""
    parts = s.split(":")
    return 2 <= len(parts) <= 3 and all(p.lstrip("-").isdigit() for p in parts)


def _parse_range(s: str, n_cameras: int) -> List[int]:
    """
    '0:88'   → range(0, 89)        (끝 포함)
    '0:88:5' → range(0, 89, 5)     (끝 포함, step=5)
    '88:0:-1'→ range(88, -1, -1)   (역방향, 끝 포함)
    """
    parts = [int(p) for p in s.split(":")]
    start, end = parts[0], parts[1]
    step = parts[2] if len(parts) == 3 else (1 if end >= start else -1)

    # 끝 인덱스를 포함(inclusive)하도록 조정
    end_inclusive = end + (1 if step > 0 else -1)
    indices = list(range(start, end_inclusive, step))

    # 범위 체크
    for idx in indices:
        if not (0 <= idx < n_cameras):
            raise ValueError(f"인덱스 {idx} 범위 초과 (0 ~ {n_cameras - 1})")
    return indices


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="커스텀 카메라 경로 생성 → camera_path.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # 입력
    ap.add_argument("-t", "--transforms",
                    default=str(ROOT / "data/processed/background/transforms.json"),
                    help="transforms.json 경로")
    ap.add_argument("-d", "--dataparser-transforms",
                    default=str(ROOT / "outputs/background/splatfacto/2026-06-01_063932/dataparser_transforms.json"),
                    help="dataparser_transforms.json 경로 (학습 폴더 안에 있음)")

    # 키프레임 지정 방법
    ap.add_argument("-k", "--keyframes",
                    help="기존 카메라 인덱스 (쉼표 구분, 예: 0,50,150,300,351)")
    ap.add_argument("--lookat", action="append", default=[],
                    metavar="'eye=x,y,z at=x,y,z up=x,y,z'",
                    help="look-at 포즈 직접 지정 (여러 번 사용 가능). 훈련 공간 좌표 사용")
    ap.add_argument("--waypoint", "-w", action="append", default=[],
                    metavar="INDEX_or_RANGE_or_LOOKAT",
                    help=("키프레임을 순서대로 지정 (여러 번 사용, -k/--lookat 보다 우선).\n"
                          "  숫자           → 카메라 인덱스 단일 지정\n"
                          "  start:end      → 범위 (끝 포함), 예) 0:88\n"
                          "  start:end:step → 간격 지정, 예) 0:88:5  역순) 88:0:-1\n"
                          "  'eye=x,y,z at=x,y,z [up=x,y,z]'  → look-at 커스텀 포즈\n"
                          "예) 기존 경로 0~88 따라가다 커스텀 포즈로 전환:\n"
                          "  --waypoint 0:88 --waypoint 'eye=0.5,-0.8,0.2 at=0,0,0'"))

    # 렌더링 파라미터
    ap.add_argument("--fps", type=int, default=24, help="FPS (default: 24)")
    ap.add_argument("--seconds", type=float, default=None,
                    help="총 영상 길이 (초). 미지정 시 키프레임 수 × 1초")
    ap.add_argument("--fov", type=float, default=None,
                    help="Field of view (도). 미지정 시 transforms.json의 fl_x에서 계산")
    ap.add_argument("--width",  type=int, default=None, help="렌더링 가로 해상도")
    ap.add_argument("--height", type=int, default=None, help="렌더링 세로 해상도")

    # 출력
    ap.add_argument("-o", "--output", default="camera_path.json",
                    help="출력 camera_path.json 경로 (default: camera_path.json)")

    # 유틸
    ap.add_argument("--list-cameras", action="store_true",
                    help="transforms.json의 카메라 목록만 출력 후 종료")
    args = ap.parse_args()

    # ── transforms.json 로드 ─────────────────────────────────────────────
    with open(args.transforms) as f:
        tf_data = json.load(f)
    frames = tf_data["frames"]
    all_c2ws = np.array([f["transform_matrix"] for f in frames], dtype=np.float64)
    N = len(all_c2ws)

    # ── --list-cameras ───────────────────────────────────────────────────
    if args.list_cameras:
        print(f"  총 {N}개 카메라")
        for i, f in enumerate(frames):
            pos = np.array(f["transform_matrix"])[:3, 3]
            print(f"  [{i:4d}] {Path(f['file_path']).name:40s}  pos=({pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f})")
        return

    # ── 카메라 파라미터 ──────────────────────────────────────────────────
    render_w = args.width  or tf_data["w"]
    render_h = args.height or tf_data["h"]
    if args.fov is not None:
        fov_deg = args.fov
    else:
        fl_x = tf_data["fl_x"]
        fov_deg = fov_from_focal(fl_x, tf_data["w"])
    print(f"  렌더링 해상도: {render_w}×{render_h}  FoV: {fov_deg:.1f}°")

    # ── dataparser_transforms.json ───────────────────────────────────────
    dp_path = args.dataparser_transforms
    if not Path(dp_path).exists():
        # 최신 학습 폴더 자동 탐색
        outputs = sorted((ROOT / "outputs").glob("**/dataparser_transforms.json"))
        if outputs:
            dp_path = str(outputs[-1])
            print(f"  dataparser_transforms 자동 감지: {dp_path}")
        else:
            print("  ❌ dataparser_transforms.json 을 찾을 수 없습니다. -d 옵션으로 경로 지정")
            sys.exit(1)

    print(f"  dataparser_transforms: {dp_path}")

    # ── 키프레임 c2w 수집 (훈련 좌표계) ─────────────────────────────────
    keyframe_c2ws_train: List[np.ndarray] = []

    def _add_index(idx: int) -> None:
        """카메라 인덱스 → 훈련 공간 c2w 추가"""
        if not (0 <= idx < N):
            print(f"  ❌ 인덱스 {idx}는 범위 초과 (0 ~ {N-1})")
            sys.exit(1)
        c2w = apply_dataparser_transform(all_c2ws[idx:idx+1], dp_path)[0]
        keyframe_c2ws_train.append(c2w)
        print(f"  키프레임 #{len(keyframe_c2ws_train):2d}: 카메라 인덱스 {idx}")

    def _add_lookat(spec: str) -> None:
        """look-at 문자열 → c2w 추가 (훈련 좌표계 직접 입력)"""
        try:
            c2w = parse_lookat(spec)
            keyframe_c2ws_train.append(c2w)
            short = spec[:50] + "..." if len(spec) > 50 else spec
            print(f"  키프레임 #{len(keyframe_c2ws_train):2d}: look-at  {short}")
        except Exception as e:
            print(f"  ❌ look-at 파싱 실패: '{spec}'\n     {e}")
            sys.exit(1)

    if args.waypoint:
        # ── --waypoint 혼합 모드: 순서 보존, -k / --lookat 무시 ──────────
        if args.keyframes or args.lookat:
            print("  ⚠️  --waypoint 가 지정되어 -k / --lookat 은 무시됩니다.")
        for wp in args.waypoint:
            wp = wp.strip()
            if wp.lstrip("-").isdigit():        # 정수 → 카메라 인덱스
                _add_index(int(wp))
            elif _is_range(wp):                 # 0:88 또는 0:88:5 → 범위
                for idx in _parse_range(wp, N):
                    _add_index(idx)
            else:                               # 'eye=...' 형태 → look-at
                _add_lookat(wp)
    else:
        # ── 레거시 모드: -k (인덱스 일괄) + --lookat (look-at 일괄) ──────
        if args.keyframes:
            for idx in [int(x.strip()) for x in args.keyframes.split(",")]:
                _add_index(idx)
        for spec in args.lookat:
            _add_lookat(spec)

    if not keyframe_c2ws_train:
        print("  ❌ 키프레임을 지정하세요.")
        print("     기존 카메라 순서대로:  -k 0,88,175,263,351")
        print("     혼합 (권장):           --waypoint 0 --waypoint 88 --waypoint 'eye=0.5,-0.8,0.2 at=0,0,0'")
        ap.print_help()
        sys.exit(1)

    keyframe_c2ws_train_arr = np.array(keyframe_c2ws_train)   # (K,4,4)
    K = len(keyframe_c2ws_train_arr)
    print(f"  키프레임 수: {K}")

    # ── 총 프레임 수 계산 ────────────────────────────────────────────────
    if args.seconds is not None:
        total_frames = max(1, round(args.seconds * args.fps))
    else:
        total_frames = max(1, K * args.fps)   # 키프레임당 1초
    total_seconds = total_frames / args.fps
    print(f"  총 프레임: {total_frames}  ({total_seconds:.1f}초 @ {args.fps}fps)")

    # ── 보간 ─────────────────────────────────────────────────────────────
    print("  카메라 경로 보간 중...")
    c2ws_interp = interpolate_path(keyframe_c2ws_train_arr, total_frames)

    # ── camera_path.json 생성 ────────────────────────────────────────────
    cam_path_dict = make_camera_path_json(c2ws_interp, fov_deg, render_w, render_h, args.fps)

    out_path = Path(args.output)
    with open(out_path, "w") as f:
        json.dump(cam_path_dict, f, indent=2)

    print(f"\n  ✅ 저장 완료: {out_path}")
    print(f"     {total_frames} 프레임  {total_seconds:.1f}초  {render_w}×{render_h}")
    print()
    print("  [렌더링 명령어]")

    # config.yml 자동 탐색
    configs = sorted((ROOT / "outputs").glob("background/**/config.yml"))
    cfg = configs[-1] if configs else "outputs/background/splatfacto/.../config.yml"
    print(f"  conda activate nerfstudio")
    print(f"  ns-render camera-path \\")
    print(f"    --load-config {cfg} \\")
    print(f"    --camera-path-filename {out_path.resolve()} \\")
    print(f"    --output-path renders/custom.mp4")


if __name__ == "__main__":
    main()
