#!/usr/bin/env python3
"""
camera_preview.py — elevation × azimuth 시점 그리드 PNG 생성

마음에 드는 칸의 eye 좌표를 render_deformation.py --eye 에 사용.

사용법:
  python scripts/camera_preview.py
  python scripts/camera_preview.py --dist 0.8
  python scripts/camera_preview.py --elevs "-30,0,30,60,90"
  python scripts/camera_preview.py --n_az 36    # 10° 간격
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

os.environ["PYOPENGL_PLATFORM"] = "egl"
import pyrender
import trimesh

from glb_utils import load_glb_base
from camera_utils import make_c2w, spherical_to_eye

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H  = 180, 320
FOV_Y = np.radians(60.0)
DEFAULT_ELEVS = [-15, -5, 5, 15, 25, 35, 45, 55, 65, 75]


def render_view(pos, norm, faces, colors, c2w, renderer, camera, diag):
    fill_pose       = np.eye(4)
    fill_pose[:3, 3] = c2w[:3, 3] + np.array([-diag * 0.8, diag * 0.4, 0])

    scene = pyrender.Scene(bg_color=[20, 20, 28, 255], ambient_light=[0.25] * 3)
    scene.add(pyrender.Mesh.from_trimesh(
        trimesh.Trimesh(vertices=pos, faces=faces,
                        vertex_normals=norm, vertex_colors=colors, process=False),
        smooth=True,
    ))
    scene.add(camera, pose=c2w)
    scene.add(pyrender.DirectionalLight(color=np.ones(3),       intensity=4.0), pose=c2w)
    scene.add(pyrender.DirectionalLight(color=np.ones(3) * 0.5, intensity=2.0), pose=fill_pose)

    color, _ = renderer.render(scene)
    return color


def render_elev_grid(pos, norm, faces, colors, center, diag, dist,
                     elev_deg, azimuths, renderer, camera, out_path):
    ncols = 6
    nrows = int(np.ceil(len(azimuths) / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(ncols * 2.5, nrows * 4.2))
    fig.patch.set_facecolor("#0e0e18")
    sign = "+" if elev_deg >= 0 else ""
    fig.suptitle(f"elevation = {sign}{elev_deg:.0f}°   dist = {dist:.3f}  (diag×{dist/diag:.2f})",
                 color="white", fontsize=11, y=0.995)

    flat = axes.flatten() if hasattr(axes, "flatten") else [axes]
    for i, az in enumerate(azimuths):
        eye = spherical_to_eye(center, az, elev_deg, dist)
        img = render_view(pos, norm, faces, colors, make_c2w(eye, center),
                          renderer, camera, diag)
        flat[i].imshow(img)
        flat[i].set_title(f"az={az:.0f}°\n{list(np.round(eye, 3))}",
                          fontsize=5.8, color="white", pad=2)
        flat[i].axis("off")

    for j in range(i + 1, len(flat)):
        flat[j].set_visible(False)

    fig.text(0.01, 0.002,
             "eye=[x,y,z]  →  python scripts/render_deformation.py --traj fixed --eye x y z",
             color="#8888aa", fontsize=7)
    plt.tight_layout(rect=[0, 0.012, 1, 0.993])
    plt.savefig(out_path, dpi=110, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="시점 그리드 PNG 생성")
    ap.add_argument("--glb",   default=os.path.join(ROOT, "meshes", "deformation1.glb"))
    ap.add_argument("--dist",  type=float, default=1.1,
                    help="diag 기준 거리 배율 (기본 1.1)")
    ap.add_argument("--elevs", default=",".join(map(str, DEFAULT_ELEVS)),
                    help="쉼표 구분 앙각 목록 (기본: -15~75)")
    ap.add_argument("--n_az",  type=int, default=24,
                    help="방위각 분할 수 (기본 24 = 15° 간격)")
    ap.add_argument("--out",   default=os.path.join(ROOT, "renders"))
    args = ap.parse_args()

    elevations = [float(e) for e in args.elevs.split(",")]
    azimuths   = list(np.linspace(0, 360, args.n_az, endpoint=False))

    print(f"GLB: {args.glb}")
    pos, norm, faces, colors = load_glb_base(args.glb)
    center = (pos.min(0) + pos.max(0)) * 0.5
    diag   = np.linalg.norm(pos.max(0) - pos.min(0))
    dist   = diag * args.dist
    print(f"center={np.round(center, 3)}  diag={diag:.3f}  dist={dist:.3f}")
    print(f"앙각: {elevations}  방위각: {len(azimuths)}방향  총: {len(elevations)*len(azimuths)}뷰\n")

    fx = (H / 2.0) / np.tan(FOV_Y / 2.0)
    camera   = pyrender.IntrinsicsCamera(fx=fx, fy=fx, cx=W/2, cy=H/2,
                                          znear=0.001, zfar=100.0)
    renderer = pyrender.OffscreenRenderer(W, H)
    os.makedirs(args.out, exist_ok=True)

    for elev in elevations:
        tag = f"p{int(elev):02d}" if elev >= 0 else f"m{int(-elev):02d}"
        out = os.path.join(args.out, f"preview_elev_{tag}.png")
        sign = "+" if elev >= 0 else ""
        print(f"  [{sign}{elev:.0f}°] {len(azimuths)}뷰 … ", end="", flush=True)
        render_elev_grid(pos, norm, faces, colors, center, diag, dist,
                         elev, azimuths, renderer, camera, out)
        print(f"→ {out}")

    renderer.delete()
    print(f"\n완료. renders/ 폴더의 PNG를 확인 후 원하는 eye 좌표를 사용하세요.")


if __name__ == "__main__":
    main()
