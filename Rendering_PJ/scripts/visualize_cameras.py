#!/usr/bin/env python3
"""
visualize_cameras.py — COLMAP 카메라 포지션 인터랙티브 시각화

사용법:
  python3 scripts/visualize_cameras.py
  python3 scripts/visualize_cameras.py -t data/processed/background/transforms.json
  python3 scripts/visualize_cameras.py -t data/processed/background/transforms.json -o renders/cam_vis.html
  python3 scripts/visualize_cameras.py --no-pointcloud   # 스파스 포인트클라우드 생략 (빠름)

출력:
  renders/camera_vis.html  ← 브라우저에서 열어서 인터랙티브하게 확인
  (마우스: 회전, 스크롤: 줌, 더블클릭: 리셋)
"""

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent


def load_transforms(path: str):
    with open(path) as f:
        d = json.load(f)
    frames = d["frames"]
    c2ws = np.array([f["transform_matrix"] for f in frames], dtype=np.float64)   # (N,4,4)
    names = [f["file_path"] for f in frames]
    intrinsics = {
        "w": d["w"], "h": d["h"],
        "fl_x": d["fl_x"], "fl_y": d.get("fl_y", d["fl_x"]),
        "cx": d.get("cx", d["w"] / 2), "cy": d.get("cy", d["h"] / 2),
    }
    return c2ws, names, intrinsics


def load_pointcloud(ply_path: str, max_points: int = 80_000):
    """스파스 포인트클라우드 로드 (최대 max_points 샘플링)"""
    try:
        from plyfile import PlyData
    except ImportError:
        print("  plyfile 없음 — 포인트클라우드 생략")
        return None, None
    data = PlyData.read(ply_path)
    v = data["vertex"]
    xyz = np.column_stack([v["x"], v["y"], v["z"]]).astype(np.float32)
    prop_names = v.data.dtype.names
    if "red" in prop_names:
        rgb = np.column_stack([v["red"], v["green"], v["blue"]]).astype(np.uint8)
    else:
        rgb = np.full((len(xyz), 3), 128, dtype=np.uint8)
    if len(xyz) > max_points:
        idx = np.random.choice(len(xyz), max_points, replace=False)
        xyz, rgb = xyz[idx], rgb[idx]
    return xyz, rgb


def frustum_lines(c2w: np.ndarray, size: float = 0.08):
    """
    카메라 프러스텀 선분 반환 (월드 좌표)
    c2w: (4,4) camera-to-world
    size: 프러스텀 크기 (장면 스케일에 맞게 조정)
    """
    # 카메라 좌표계: X-right, Y-up, Z-back (nerfstudio/OpenCV 스타일)
    corners_cam = np.array([
        [0, 0, 0],           # 카메라 원점
        [ size,  size, -size],  # 프러스텀 모서리 4개
        [-size,  size, -size],
        [-size, -size, -size],
        [ size, -size, -size],
    ], dtype=np.float64)
    R = c2w[:3, :3]
    t = c2w[:3, 3]
    corners_world = (R @ corners_cam.T).T + t   # (5,3)

    o = corners_world[0]
    a, b, c, d = corners_world[1], corners_world[2], corners_world[3], corners_world[4]
    # 8개 선분 (원점→모서리 4개 + 모서리 사각형 4개)
    segs = [
        (o, a), (o, b), (o, c), (o, d),
        (a, b), (b, c), (c, d), (d, a),
    ]
    return segs


def build_figure(c2ws, names, pc_xyz, pc_rgb,
                 show_frustums: bool = True,
                 frustum_step: int = 1,
                 frustum_size: float = 0.08,
                 point_size: float = 1.0):
    import plotly.graph_objects as go

    fig = go.Figure()
    N = len(c2ws)

    # ── 스파스 포인트클라우드 ──────────────────────────────────────────────
    if pc_xyz is not None:
        colors = [f"rgb({r},{g},{b})" for r, g, b in pc_rgb]
        fig.add_trace(go.Scatter3d(
            x=pc_xyz[:, 0], y=pc_xyz[:, 1], z=pc_xyz[:, 2],
            mode="markers",
            marker=dict(size=point_size, color=colors, opacity=0.4),
            name="Sparse Point Cloud",
            hoverinfo="skip",
        ))

    # ── 카메라 위치 (점) ─────────────────────────────────────────────────
    positions = c2ws[:, :3, 3]
    cam_colors = np.linspace(0, 1, N)   # 프레임 순서로 색상
    hover_texts = [f"#{i}<br>{Path(names[i]).name}" for i in range(N)]

    fig.add_trace(go.Scatter3d(
        x=positions[:, 0], y=positions[:, 1], z=positions[:, 2],
        mode="markers",
        marker=dict(
            size=3,
            color=cam_colors,
            colorscale="Viridis",
            colorbar=dict(title="Frame #", thickness=12, len=0.5),
            opacity=0.9,
        ),
        text=hover_texts,
        hovertemplate="%{text}<extra></extra>",
        name="Camera Positions",
    ))

    # ── 카메라 프러스텀 ─────────────────────────────────────────────────
    if show_frustums:
        xs, ys, zs = [], [], []
        for i in range(0, N, frustum_step):
            for p0, p1 in frustum_lines(c2ws[i], size=frustum_size):
                xs += [p0[0], p1[0], None]
                ys += [p0[1], p1[1], None]
                zs += [p0[2], p1[2], None]
        fig.add_trace(go.Scatter3d(
            x=xs, y=ys, z=zs,
            mode="lines",
            line=dict(color="rgba(255,120,0,0.5)", width=1),
            name="Camera Frustums",
            hoverinfo="skip",
        ))

    # ── 카메라 경로 선 ────────────────────────────────────────────────────
    fig.add_trace(go.Scatter3d(
        x=positions[:, 0], y=positions[:, 1], z=positions[:, 2],
        mode="lines",
        line=dict(color="rgba(100,180,255,0.4)", width=2),
        name="Camera Path",
        hoverinfo="skip",
    ))

    # ── 레이아웃 ─────────────────────────────────────────────────────────
    fig.update_layout(
        title=dict(text=f"COLMAP Camera Positions ({N} frames)", font=dict(size=16)),
        scene=dict(
            xaxis_title="X",
            yaxis_title="Y",
            zaxis_title="Z",
            aspectmode="data",
            bgcolor="rgb(15,15,20)",
            xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
            yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
            zaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.1)"),
        ),
        paper_bgcolor="rgb(20,20,30)",
        plot_bgcolor="rgb(20,20,30)",
        font=dict(color="white"),
        legend=dict(bgcolor="rgba(0,0,0,0.5)", bordercolor="gray", borderwidth=1),
        margin=dict(l=0, r=0, t=40, b=0),
    )

    # 카메라 번호 주석 (50프레임마다)
    annotations = []
    for i in range(0, N, max(1, N // 20)):
        p = positions[i]
        annotations.append(dict(
            x=p[0], y=p[1], z=p[2],
            text=str(i),
            showarrow=False,
            font=dict(color="yellow", size=9),
            xanchor="center",
        ))
    fig.update_layout(scene=dict(annotations=annotations))

    return fig


def main():
    ap = argparse.ArgumentParser(description="COLMAP 카메라 시각화")
    ap.add_argument("-t", "--transforms", default=str(ROOT / "data/processed/background/transforms.json"),
                    help="transforms.json 경로")
    ap.add_argument("-p", "--pointcloud",
                    help="스파스 포인트클라우드 .ply 경로 (미지정 시 transforms.json 옆의 sparse_pc.ply 자동 탐색)")
    ap.add_argument("-o", "--output", default=str(ROOT / "renders/camera_vis.html"),
                    help="출력 HTML 경로 (default: renders/camera_vis.html)")
    ap.add_argument("--no-frustums", action="store_true", help="카메라 프러스텀 표시 안 함")
    ap.add_argument("--frustum-step", type=int, default=3,
                    help="몇 프레임마다 프러스텀 표시 (default: 3)")
    ap.add_argument("--frustum-size", type=float, default=0.08,
                    help="프러스텀 크기 (default: 0.08)")
    ap.add_argument("--no-pointcloud", action="store_true", help="스파스 포인트클라우드 생략")
    ap.add_argument("--max-points", type=int, default=80_000,
                    help="포인트클라우드 최대 표시 개수 (default: 80000)")
    args = ap.parse_args()

    # ── 데이터 로드 ───────────────────────────────────────────────────────
    print(f"  transforms.json 로드: {args.transforms}")
    c2ws, names, intr = load_transforms(args.transforms)
    print(f"  카메라 수: {len(c2ws)}")

    pc_xyz, pc_rgb = None, None
    if not args.no_pointcloud:
        ply_path = args.pointcloud
        if not ply_path:
            candidate = Path(args.transforms).parent / "sparse_pc.ply"
            if candidate.exists():
                ply_path = str(candidate)
        if ply_path and Path(ply_path).exists():
            print(f"  포인트클라우드 로드: {ply_path}  (max {args.max_points:,})")
            pc_xyz, pc_rgb = load_pointcloud(ply_path, args.max_points)
            if pc_xyz is not None:
                print(f"  → {len(pc_xyz):,} 포인트")
        else:
            print("  포인트클라우드: 없음 (--no-pointcloud 또는 경로 지정)")

    # ── 장면 스케일에 따라 프러스텀 크기 자동 조정 ───────────────────────
    positions = c2ws[:, :3, 3]
    scene_radius = np.linalg.norm(positions - positions.mean(axis=0), axis=1).max()
    frustum_size = args.frustum_size if args.frustum_size != 0.08 else max(0.03, scene_radius * 0.04)
    print(f"  장면 반경: {scene_radius:.2f}  프러스텀 크기: {frustum_size:.3f}")

    # ── 그래프 생성 ───────────────────────────────────────────────────────
    print("  그래프 생성 중...")
    fig = build_figure(
        c2ws, names, pc_xyz, pc_rgb,
        show_frustums=not args.no_frustums,
        frustum_step=args.frustum_step,
        frustum_size=frustum_size,
    )

    # ── 저장 ─────────────────────────────────────────────────────────────
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(out), include_plotlyjs="cdn")
    print(f"\n  ✅ 저장 완료: {out}")
    print(f"  → 브라우저에서 열기: file://{out.resolve()}")
    print(f"  → 카메라 인덱스 확인 후  make_camera_path.py -k 0,50,100,...  로 경로 생성")


if __name__ == "__main__":
    main()
