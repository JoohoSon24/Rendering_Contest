#!/usr/bin/env python3
"""
render_deformation.py — deformation1.glb morph-target 애니메이션 렌더링

사용법:
  python scripts/render_deformation.py                          # orbit (기본)
  python scripts/render_deformation.py --traj fixed --eye X Y Z
  python scripts/render_deformation.py --c2w <16개 숫자>        # 웹 뷰어 캡처 행렬
  python scripts/render_deformation.py --preview                # 첫 프레임 PNG만
"""

import os
import argparse
import subprocess

import cv2
import numpy as np

os.environ["PYOPENGL_PLATFORM"] = "egl"
import pyrender
import trimesh

from glb_utils import load_glb_morph
from camera_utils import make_c2w

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLB_PATH = os.path.join(ROOT, "meshes", "deformation1.glb")


# ─────────────────────────────────────────────────────────────────────────────
# Morph 보간
# ─────────────────────────────────────────────────────────────────────────────

def sample_weight(times: np.ndarray, weights: np.ndarray, t: float) -> float:
    """시간 t에서 morph weight 선형 보간."""
    t   = float(np.clip(t, times[0], times[-1]))
    idx = int(np.clip(np.searchsorted(times, t, side="right") - 1, 0, len(times) - 2))
    t0, t1 = times[idx], times[idx + 1]
    alpha = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
    return float(weights[idx] * (1 - alpha) + weights[idx + 1] * alpha)


def make_mesh_at_t(base_pos, base_norm, delta_pos, delta_norm,
                   faces, times, weights, vertex_colors, t: float):
    """시간 t의 morph 상태 trimesh.Trimesh 반환."""
    w    = sample_weight(times, weights, t)
    pos  = base_pos  + w * delta_pos
    norm = base_norm + w * delta_norm
    norm = norm / (np.linalg.norm(norm, axis=1, keepdims=True) + 1e-8)
    return trimesh.Trimesh(vertices=pos, faces=faces,
                           vertex_normals=norm, vertex_colors=vertex_colors,
                           process=False)


# ─────────────────────────────────────────────────────────────────────────────
# 카메라 트라젝토리
# ─────────────────────────────────────────────────────────────────────────────

def orbit_trajectory(n_frames: int, center: np.ndarray, radius: float,
                     elevation: float = 20.0, full_rotations: float = 1.0):
    c2ws = []
    for i in range(n_frames):
        az  = np.radians(360 * full_rotations * i / n_frames)
        el  = np.radians(elevation)
        eye = center + radius * np.array([np.cos(el) * np.cos(az),
                                          np.sin(el),
                                          np.cos(el) * np.sin(az)])
        c2ws.append(make_c2w(eye, center))
    return c2ws


def fixed_trajectory(n_frames: int, eye: np.ndarray, center: np.ndarray):
    return [make_c2w(eye, center)] * n_frames


# ─────────────────────────────────────────────────────────────────────────────
# 렌더링
# ─────────────────────────────────────────────────────────────────────────────

def render_frames(glb_path: str, c2ws: list, fps: int,
                  width: int, height: int,
                  anim_start: float = 0.0, preview_path: str = None):
    """c2ws 각 프레임을 렌더링해 (H, W, 3) uint8 리스트 반환."""
    base_pos, base_norm, delta_pos, delta_norm, \
        faces, times, weights, vertex_colors = load_glb_morph(glb_path)

    center = (base_pos.min(0) + base_pos.max(0)) * 0.5
    diag   = np.linalg.norm(base_pos.max(0) - base_pos.min(0))
    print(f"  mesh center: {np.round(center, 3)}  diag: {diag:.3f}")

    fov_y = np.radians(60.0)
    fx    = (height / 2.0) / np.tan(fov_y / 2.0)
    camera = pyrender.IntrinsicsCamera(fx=fx, fy=fx,
                                       cx=width / 2, cy=height / 2,
                                       znear=0.01, zfar=1000.0)
    light_key  = pyrender.DirectionalLight(color=np.ones(3), intensity=4.0)
    light_fill = pyrender.DirectionalLight(color=np.ones(3) * 0.5, intensity=2.0)
    light_top  = pyrender.PointLight(color=np.ones(3), intensity=2.0)

    renderer = pyrender.OffscreenRenderer(width, height)
    frames, n = [], len(c2ws)

    for i, c2w in enumerate(c2ws):
        t_anim   = anim_start + i / fps
        mesh_tri = make_mesh_at_t(base_pos, base_norm, delta_pos, delta_norm,
                                  faces, times, weights, vertex_colors, t_anim)

        fill_pose        = np.eye(4)
        fill_pose[:3, 3] = c2w[:3, 3] + np.array([-diag * 0.8, diag * 0.4, 0])
        top_pose         = np.eye(4)
        top_pose[:3, 3]  = c2w[:3, 3] + np.array([0, diag, 0])

        scene = pyrender.Scene(bg_color=[0, 0, 0, 255], ambient_light=[0.15] * 3)
        scene.add(pyrender.Mesh.from_trimesh(mesh_tri, smooth=True))
        scene.add(camera,     pose=c2w)
        scene.add(light_key,  pose=c2w)
        scene.add(light_fill, pose=fill_pose)
        scene.add(light_top,  pose=top_pose)

        color, _ = renderer.render(scene)
        frames.append(color)

        if i == 0 and preview_path:
            cv2.imwrite(preview_path, cv2.cvtColor(color, cv2.COLOR_RGB2BGR))
            print(f"  preview → {preview_path}")

        if (i + 1) % 24 == 0 or i == n - 1:
            print(f"  [{i+1}/{n}] t={t_anim:.2f}s  w={sample_weight(times, weights, t_anim):.3f}")

    renderer.delete()
    return frames


def frames_to_video(frames: list, output_path: str, fps: int):
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    h, w   = frames[0].shape[:2]
    tmp    = output_path + ".tmp.mp4"
    writer = cv2.VideoWriter(tmp, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    for f in frames:
        writer.write(cv2.cvtColor(f, cv2.COLOR_RGB2BGR))
    writer.release()

    # mp4v → h264 재인코딩
    subprocess.run(
        ["ffmpeg", "-y", "-i", tmp,
         "-c:v", "libx264", "-crf", "18", "-preset", "fast",
         "-pix_fmt", "yuv420p", output_path],
        check=True, capture_output=True,
    )
    os.remove(tmp)


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="GLB morph 애니메이션 렌더링")
    ap.add_argument("-o", "--output",  default=os.path.join(ROOT, "renders", "deformation.mp4"))
    ap.add_argument("--fps",           type=int,   default=24)
    ap.add_argument("--width",         type=int,   default=540)
    ap.add_argument("--height",        type=int,   default=963)
    ap.add_argument("--seconds",       type=float, default=10.0)
    ap.add_argument("--traj",          default="orbit", choices=["orbit", "fixed"])
    ap.add_argument("--eye",           type=float, nargs=3, metavar=("X", "Y", "Z"),
                    help="fixed 트라젝토리 eye 위치")
    ap.add_argument("--c2w",           type=float, nargs=16, metavar="M",
                    help="웹 뷰어 캡처 c2w 행렬 (row-major 16개)")
    ap.add_argument("--anim-start",    type=float, default=0.0)
    ap.add_argument("--preview",       action="store_true", help="첫 프레임 PNG만 저장")
    args = ap.parse_args()

    # 메쉬 로드 (center/diag 계산용)
    base_pos, *_ = load_glb_morph(GLB_PATH)
    center = (base_pos.min(0) + base_pos.max(0)) * 0.5
    diag   = np.linalg.norm(base_pos.max(0) - base_pos.min(0))

    n_frames = round(args.seconds * args.fps)
    print(f"GLB: {GLB_PATH}")

    if args.c2w is not None:
        c2w_mat = np.array(args.c2w).reshape(4, 4)
        print(f"  c2w 사용  eye={np.round(c2w_mat[:3, 3], 4)}")
        c2ws = [c2w_mat] * n_frames
    elif args.traj == "orbit":
        print(f"  orbit  {n_frames}프레임 @ {args.fps}fps")
        c2ws = orbit_trajectory(n_frames, center, diag * 0.75)
    else:
        eye  = np.array(args.eye) if args.eye is not None else center + np.array([0, 0, diag * 0.9])
        print(f"  fixed  eye={np.round(eye, 4)}  {n_frames}프레임 @ {args.fps}fps")
        c2ws = fixed_trajectory(n_frames, eye, center)

    preview_path = args.output.replace(".mp4", "_preview.png") if args.preview else None

    print("렌더링 시작...")
    frames = render_frames(GLB_PATH, c2ws, args.fps, args.width, args.height,
                           anim_start=args.anim_start, preview_path=preview_path)

    if args.preview:
        print(f"\n✅ 프리뷰: {preview_path}")
    else:
        frames_to_video(frames, args.output, args.fps)
        print(f"\n✅ {args.output}  ({len(frames)}프레임, {len(frames)/args.fps:.1f}초)")


if __name__ == "__main__":
    main()
