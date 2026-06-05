#!/usr/bin/env python3
"""
gs_to_mesh.py — Gaussian Splatting PLY → OBJ + UV 텍스처

SuGaR 스타일 간이 구현:
1. GS PLY 로드  (위치, SH DC 색상, opacity, scale)
2. Gaussian 필터링  (opacity & scale 임계값)
3. Poisson 재구성  → 삼각형 메시
4. KNN 색상 전이  → 꼭짓점 색상
5. xatlas UV 언래핑
6. 삼각형 래스터라이즈로 UV 텍스처 베이킹
7. 텍스처 경계 딜레이션  (UV 심 아티팩트 방지)
8. OBJ + MTL + texture.png 출력  → Blender/Unity/Unreal 바로 사용 가능

※ 이 구현의 한계:
   - SH DC 성분(view-independent diffuse)만 텍스처에 반영
   - Specular / 구면조화 고차 항은 생략 (완전한 SuGaR는 재학습 필요)
   - 결과물은 조명-독립 Albedo 텍스처
"""

import argparse
import sys
import time
import numpy as np
from pathlib import Path


# ── SH / 수학 유틸 ───────────────────────────────────────────────────────────

def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -88, 88)))


def sh_dc_to_rgb(f_dc):
    """SH degree-0 DC 성분 → 선형 RGB (view-independent diffuse)"""
    C0 = 0.28209479177387814
    return np.clip(C0 * f_dc + 0.5, 0.0, 1.0)


# ── 1. GS PLY 로드 ────────────────────────────────────────────────────────────

def load_gs_ply(path: str):
    from plyfile import PlyData
    print(f"  📂 GS PLY 로딩: {path}")
    plydata = PlyData.read(path)
    v = plydata['vertex']

    xyz     = np.column_stack([v['x'], v['y'], v['z']]).astype(np.float32)
    opacity = sigmoid(np.array(v['opacity'], dtype=np.float32))
    f_dc    = np.column_stack([v['f_dc_0'], v['f_dc_1'], v['f_dc_2']]).astype(np.float32)
    rgb     = sh_dc_to_rgb(f_dc)
    scale   = np.exp(np.column_stack([v['scale_0'], v['scale_1'], v['scale_2']]).astype(np.float32))
    max_scale = scale.max(axis=1)

    print(f"     Gaussian 총 수: {len(xyz):,}")
    return xyz, rgb, opacity, max_scale


# ── 2. 필터링 ─────────────────────────────────────────────────────────────────

def filter_gaussians(xyz, rgb, opacity, max_scale, opacity_thresh, scale_thresh):
    mask = opacity > opacity_thresh
    if scale_thresh > 0:
        mask &= max_scale < scale_thresh
    n = mask.sum()
    print(f"  🔍 필터 후: {n:,}개  (opacity>{opacity_thresh:.2f}, scale<{scale_thresh})")
    if n < 1000:
        print("  ⚠️  Gaussian이 너무 적습니다. --opacity-threshold 를 낮춰 보세요.")
    return xyz[mask], rgb[mask], opacity[mask]


# ── 3. Poisson 재구성 ─────────────────────────────────────────────────────────

def reconstruct_mesh(xyz, rgb, opacity, poisson_depth, density_quantile):
    import open3d as o3d
    print(f"  🔺 Poisson 재구성 (depth={poisson_depth}) ...")

    pcd = o3d.geometry.PointCloud()
    pcd.points  = o3d.utility.Vector3dVector(xyz)
    pcd.colors  = o3d.utility.Vector3dVector(rgb)

    pcd.estimate_normals(
        search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.05, max_nn=30)
    )
    pcd.orient_normals_consistent_tangent_plane(100)

    mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        pcd, depth=poisson_depth, scale=1.1, linear_fit=False
    )
    densities = np.asarray(densities)

    # 저밀도(플로터) 꼭짓점 제거
    thresh = np.quantile(densities, density_quantile)
    mesh.remove_vertices_by_mask(densities < thresh)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.compute_vertex_normals()

    verts = np.asarray(mesh.vertices, dtype=np.float32)
    faces = np.asarray(mesh.triangles, dtype=np.int32)
    print(f"     꼭짓점: {len(verts):,}  삼각형: {len(faces):,}")
    return verts, faces


# ── 4. KNN 색상 전이 ──────────────────────────────────────────────────────────

def transfer_colors(mesh_verts, src_xyz, src_rgb, src_opacity, k=5):
    from sklearn.neighbors import KDTree
    print("  🎨 꼭짓점 색상 전이 (KNN) ...")

    tree = KDTree(src_xyz)
    distances, indices = tree.query(mesh_verts, k=k)

    # 거리 · opacity 가중 평균
    weights = (1.0 / (distances + 1e-8)) * src_opacity[indices]
    weights /= weights.sum(axis=1, keepdims=True)

    colors = (weights[:, :, None] * src_rgb[indices]).sum(axis=1)
    return np.clip(colors, 0, 1).astype(np.float32)


# ── 5. xatlas UV 언래핑 ───────────────────────────────────────────────────────

def uv_unwrap(verts, faces):
    import xatlas
    print("  🗺️  UV 언래핑 (xatlas) ...")
    vmapping, new_faces, uvs = xatlas.parametrize(verts, faces)
    print(f"     UV 꼭짓점: {len(uvs):,}  UV 면: {len(new_faces):,}")
    return vmapping, new_faces.astype(np.int32), uvs.astype(np.float32)


# ── 6. UV 텍스처 베이킹 ───────────────────────────────────────────────────────

def bake_texture(uvs, faces, colors, texture_size):
    """삼각형 단위 래스터라이즈 + 무게중심 보간으로 UV 텍스처 생성"""
    print(f"  🖼️  텍스처 베이킹 ({texture_size}×{texture_size}) ...")

    texture = np.zeros((texture_size, texture_size, 3), dtype=np.float32)
    px_all  = uvs * texture_size          # UV → 픽셀 (Y flip은 저장 시)
    N       = len(faces)
    step    = max(1, N // 20)

    for fi, f in enumerate(faces):
        if fi % step == 0:
            print(f"    {fi * 100 // N:3d}%", end="\r", flush=True)

        p0, p1, p2 = px_all[f[0]], px_all[f[1]], px_all[f[2]]
        c0, c1, c2 = colors[f[0]], colors[f[1]], colors[f[2]]

        # AABB 클리핑
        min_x = max(0, int(min(p0[0], p1[0], p2[0])))
        max_x = min(texture_size - 1, int(max(p0[0], p1[0], p2[0])) + 1)
        min_y = max(0, int(min(p0[1], p1[1], p2[1])))
        max_y = min(texture_size - 1, int(max(p0[1], p1[1], p2[1])) + 1)
        if min_x >= max_x or min_y >= max_y:
            continue

        yy, xx = np.mgrid[min_y:max_y + 1, min_x:max_x + 1]
        pts = np.column_stack([xx.ravel(), yy.ravel()]).astype(np.float32) + 0.5

        # 무게중심 좌표 계산
        v0 = p2 - p0;  v1 = p1 - p0;  v2 = pts - p0
        d00 = v0 @ v0;  d01 = v0 @ v1;  d11 = v1 @ v1
        d02 = v2 @ v0;  d12 = v2 @ v1
        denom = d00 * d11 - d01 * d01
        if abs(denom) < 1e-10:
            continue
        inv   = 1.0 / denom
        u_b   = (d11 * d02 - d01 * d12) * inv
        v_b   = (d00 * d12 - d01 * d02) * inv
        inside = (u_b >= 0) & (v_b >= 0) & (u_b + v_b <= 1)
        if not inside.any():
            continue

        w0 = (1 - u_b[inside] - v_b[inside])[:, None]
        w1 = v_b[inside][:, None]
        w2 = u_b[inside][:, None]
        color = w0 * c0 + w1 * c1 + w2 * c2

        ys = yy.ravel()[inside]
        xs = xx.ravel()[inside]
        texture[texture_size - 1 - ys, xs] = color   # Y flip

    print("    100%")
    return texture


# ── 7. 텍스처 딜레이션 ────────────────────────────────────────────────────────

def dilate_texture(texture, iters=6):
    """UV 경계를 바깥으로 확장해 필터링 / 밉맵 아티팩트 방지"""
    import cv2
    mask = (texture.sum(axis=2) > 0).astype(np.uint8)
    filled = (texture * 255).astype(np.uint8)
    kernel = np.ones((3, 3), np.uint8)
    for _ in range(iters):
        dilated  = cv2.dilate(filled, kernel)
        new_mask = cv2.dilate(mask, kernel)
        expand   = (new_mask > 0) & (mask == 0)
        filled[expand] = dilated[expand]
        mask = new_mask
    return filled.astype(np.float32) / 255.0


# ── 8. OBJ + MTL 출력 ────────────────────────────────────────────────────────

def export_obj(out_dir: Path, orig_verts, vmapping, uv_faces, uvs, texture_name):
    """
    xatlas 이후 레이아웃:
      - UV 꼭짓점 위치  = orig_verts[vmapping]
      - UV 좌표         = uvs
      - 면              = uv_faces  (UV 꼭짓점 인덱스 기준)
    """
    uv_verts = orig_verts[vmapping]           # [N_uv, 3]

    mtl_path = out_dir / "mesh.mtl"
    obj_path = out_dir / "mesh.obj"

    with open(mtl_path, "w") as f:
        f.write("newmtl material0\n")
        f.write("Ka 1.0 1.0 1.0\n")
        f.write("Kd 1.0 1.0 1.0\n")
        f.write("Ks 0.0 0.0 0.0\n")
        f.write("illum 1\n")
        f.write(f"map_Kd {texture_name}\n")

    with open(obj_path, "w") as f:
        f.write("# GS → Mesh (gs_to_mesh.py)\n")
        f.write("mtllib mesh.mtl\n")
        f.write("usemtl material0\n\n")
        for vx, vy, vz in uv_verts:
            f.write(f"v {vx:.6f} {vy:.6f} {vz:.6f}\n")
        f.write("\n")
        for u, v in uvs:
            f.write(f"vt {u:.6f} {v:.6f}\n")
        f.write("\n")
        # OBJ는 1-indexed, v와 vt 인덱스가 동일
        for i0, i1, i2 in uv_faces:
            a, b, c = i0 + 1, i1 + 1, i2 + 1
            f.write(f"f {a}/{a} {b}/{b} {c}/{c}\n")

    print(f"     mesh.obj  / mesh.mtl  / {texture_name}")


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="GS PLY → OBJ + UV 텍스처 (SuGaR 스타일 간이 구현)"
    )
    parser.add_argument("input",
                        help="입력 GS splat.ply 경로")
    parser.add_argument("-o", "--output-dir", default=None,
                        help="출력 폴더 (기본: 입력 파일 옆에 *_mesh/)")
    parser.add_argument("--opacity-threshold", type=float, default=0.1,
                        help="Gaussian 필터 opacity 임계값 (default: 0.1)")
    parser.add_argument("--scale-threshold",   type=float, default=0.3,
                        help="Gaussian 최대 scale (플로터 제거, 0=비활성화, default: 0.3)")
    parser.add_argument("--poisson-depth",     type=int,   default=9,
                        help="Poisson 재구성 깊이 (default: 9, 클수록 세밀)")
    parser.add_argument("--density-quantile",  type=float, default=0.1,
                        help="저밀도 꼭짓점 제거 분위수 (default: 0.1)")
    parser.add_argument("--texture-size",      type=int,   default=2048,
                        help="UV 텍스처 해상도 px (default: 2048)")
    parser.add_argument("--knn",               type=int,   default=5,
                        help="색상 전이 KNN 이웃 수 (default: 5)")
    args = parser.parse_args()

    t0 = time.time()
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ 파일 없음: {input_path}"); sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else \
              input_path.parent / (input_path.stem + "_mesh")
    out_dir.mkdir(parents=True, exist_ok=True)

    TEXTURE_NAME = "texture.png"

    print("\n════════════════════════════════════════════════════════")
    print("  GS PLY → OBJ + UV 텍스처 변환")
    print(f"  입력  : {input_path}")
    print(f"  출력  : {out_dir}/")
    print("════════════════════════════════════════════════════════\n")

    xyz, rgb, opacity, max_scale = load_gs_ply(str(input_path))
    xyz, rgb, opacity = filter_gaussians(
        xyz, rgb, opacity, max_scale,
        args.opacity_threshold, args.scale_threshold
    )
    verts, faces = reconstruct_mesh(
        xyz, rgb, opacity,
        args.poisson_depth, args.density_quantile
    )
    vertex_colors        = transfer_colors(verts, xyz, rgb, opacity, k=args.knn)
    vmapping, uv_faces, uvs = uv_unwrap(verts, faces)
    uv_colors            = vertex_colors[vmapping]

    texture = bake_texture(uvs, uv_faces, uv_colors, args.texture_size)
    texture = dilate_texture(texture)

    from PIL import Image
    img = (np.clip(texture, 0, 1) * 255).astype(np.uint8)
    Image.fromarray(img).save(out_dir / TEXTURE_NAME)

    print(f"  💾 저장 중...")
    export_obj(out_dir, verts, vmapping, uv_faces, uvs, TEXTURE_NAME)

    elapsed = time.time() - t0
    print(f"\n  ✅ 완료!  ({elapsed:.1f}초)\n")
    print(f"  📁 {out_dir}/")
    print(f"      mesh.obj      ← 메시 (꼭짓점 + UV)")
    print(f"      mesh.mtl      ← 재질 정의")
    print(f"      texture.png   ← Albedo 텍스처 ({args.texture_size}px)")
    print("\n  Blender: File → Import → Wavefront OBJ")
    print("  Unity  : Assets 폴더에 세 파일 모두 드롭")
    print("  Unreal : Content 브라우저로 OBJ Import")
    print("════════════════════════════════════════════════════════\n")


if __name__ == "__main__":
    main()
