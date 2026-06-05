#!/usr/bin/env python3
"""
viewer_render.py — GLFW 인터랙티브 뷰어 (Xvfb 필요)

실행:
  Xvfb :99 -screen 0 1280x1024x24 &
  DISPLAY=:99 python scripts/viewer_render.py

  좌클릭 드래그 : 회전   |   우클릭 드래그 : 이동   |   휠 : 줌
  [SPACE]        : 현재 시점으로 deformation.mp4 렌더링
  [Q]            : 종료

※ 브라우저 접근이 가능하면 web_viewer.py 를 권장합니다.
"""

import os
import sys
import subprocess
import threading

import numpy as np

# GLFW 창 뷰어 — EGL 강제 해제
os.environ.pop("PYOPENGL_PLATFORM", None)

import pyrender
import trimesh

from glb_utils import load_glb_base
from camera_utils import make_c2w

ROOT          = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GLB_PATH      = os.path.join(ROOT, "meshes", "deformation1.glb")
OUT_PATH      = os.path.join(ROOT, "renders", "deformation.mp4")
RENDER_SCRIPT = os.path.join(ROOT, "scripts", "render_deformation.py")
PYTHON        = sys.executable

VIEWPORT_W, VIEWPORT_H = 540, 963
INIT_EYE = np.array([1.179537, 0.486765, 0.260652])

_rendering = False


def on_space(viewer):
    global _rendering
    if _rendering:
        print("⏳ 이미 렌더링 중입니다.")
        return

    c2w      = viewer._trackball.pose.copy()
    eye      = c2w[:3, 3]
    c2w_flat = c2w.flatten().tolist()

    print(f"\n📸 eye=[{eye[0]:.6f}, {eye[1]:.6f}, {eye[2]:.6f}]  렌더링 시작")
    _rendering = True

    def _run():
        global _rendering
        result = subprocess.run(
            [PYTHON, RENDER_SCRIPT, "--c2w"] + [str(v) for v in c2w_flat] + ["-o", OUT_PATH],
            text=True,
        )
        print(f"\n{'✅ 완료' if result.returncode == 0 else '❌ 실패'}: {OUT_PATH}")
        _rendering = False

    threading.Thread(target=_run, daemon=True).start()


def main():
    print(f"메쉬 로딩: {GLB_PATH}")
    pos, norm, faces, colors = load_glb_base(GLB_PATH)
    center = (pos.min(0) + pos.max(0)) * 0.5
    diag   = np.linalg.norm(pos.max(0) - pos.min(0))
    print(f"  center={np.round(center, 3)}  diag={diag:.3f}")

    scene = pyrender.Scene(bg_color=[14, 14, 20, 255], ambient_light=[0.25] * 3)
    scene.add(pyrender.Mesh.from_trimesh(
        trimesh.Trimesh(vertices=pos, faces=faces,
                        vertex_normals=norm, vertex_colors=colors, process=False),
        smooth=True,
    ))
    scene.add(
        pyrender.PerspectiveCamera(yfov=np.radians(60.0), znear=0.001, zfar=100.0),
        pose=make_c2w(INIT_EYE, center),
    )

    print("\n조작법: 좌클릭드래그=회전 | 우클릭드래그=이동 | 휠=줌 | SPACE=렌더링 | Q=종료\n")

    pyrender.Viewer(
        scene,
        viewport_size=(VIEWPORT_W, VIEWPORT_H),
        use_raymond_lighting=True,
        show_world_axis=True,
        window_title="Deformation Viewer  [SPACE=render | Q=quit]",
        registered_keys={" ": on_space},
        run_in_thread=False,
    )


if __name__ == "__main__":
    main()
