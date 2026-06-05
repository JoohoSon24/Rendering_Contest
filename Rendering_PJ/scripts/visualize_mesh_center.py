#!/usr/bin/env python3
"""
메쉬 좌표 시각화 + 진단
- Raw vertex 위치 (GLTF node 변환 미적용)
- Node transform 적용 후 실제 위치
- Eye 좌표와의 관계
"""
import struct, json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from scipy.spatial.transform import Rotation

GLB_PATH = "/home/ubuntu/Rendering_Contest/Rendering_PJ/meshes/deformation1.glb"
EYE      = np.array([1.179537, 0.486765, 0.260652])

# ── GLB 파싱 ──────────────────────────────────────────────────────────────────
raw = open(GLB_PATH, "rb").read()
chunk0_len = struct.unpack("<I", raw[12:16])[0]
gltf = json.loads(raw[20:20 + chunk0_len])
bin_data = raw[20 + chunk0_len + 8:]

def get_arr(acc_idx, dtype=np.float32):
    acc = gltf["accessors"][acc_idx]
    bv  = gltf["bufferViews"][acc["bufferView"]]
    off = bv.get("byteOffset", 0)
    buf = np.frombuffer(bin_data[off:off + bv["byteLength"]], dtype=dtype)
    n   = acc["count"]
    type_map = {"SCALAR":1,"VEC2":2,"VEC3":3,"VEC4":4,"MAT4":16}
    return buf[:n*type_map[acc["type"]]].reshape(n,-1).squeeze()

prim     = gltf["meshes"][0]["primitives"][0]
base_pos = get_arr(prim["attributes"]["POSITION"])   # (N,3) raw

# ── Node transform 파싱 ───────────────────────────────────────────────────────
node = gltf["nodes"][0]
q_xyzw = np.array(node["rotation"])       # GLTF: [x, y, z, w]
t_node = np.array(node["translation"])

rot = Rotation.from_quat(q_xyzw)          # scipy: [x, y, z, w]
transformed_pos = rot.apply(base_pos) + t_node

# ── 중심 계산 ─────────────────────────────────────────────────────────────────
raw_center  = (base_pos.min(0) + base_pos.max(0)) * 0.5
real_center = (transformed_pos.min(0) + transformed_pos.max(0)) * 0.5

print("=== 진단 결과 ===")
print(f"  Raw vertex 중심  (node transform 미적용): {np.round(raw_center,4)}")
print(f"  실제 메쉬 중심   (node transform 적용):   {np.round(real_center,4)}")
print(f"  Eye 좌표:                                  {EYE}")
print()
print(f"  Eye → raw_center  거리: {np.linalg.norm(EYE - raw_center):.4f}")
print(f"  Eye → real_center 거리: {np.linalg.norm(EYE - real_center):.4f}")
print()
print(f"  Node rotation (xyzw): {np.round(q_xyzw,4)}")
print(f"  Node translation:     {np.round(t_node,4)}")
print()
print(f"  Raw BBox  min={np.round(base_pos.min(0),4)}  max={np.round(base_pos.max(0),4)}")
print(f"  Real BBox min={np.round(transformed_pos.min(0),4)}  max={np.round(transformed_pos.max(0),4)}")

# ── 서브샘플링 (시각화용) ─────────────────────────────────────────────────────
rng  = np.random.default_rng(0)
idx  = rng.choice(len(base_pos), min(3000, len(base_pos)), replace=False)
raw_s  = base_pos[idx]
real_s = transformed_pos[idx]

# ── 3D 시각화 ─────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(18, 7))

for col, (pts, center, title) in enumerate([
    (raw_s,  raw_center,  "Raw vertices\n(node transform 미적용)"),
    (real_s, real_center, "Transformed vertices\n(node transform 적용)"),
]):
    ax = fig.add_subplot(1, 3, col+1, projection="3d")
    ax.scatter(pts[:,0], pts[:,1], pts[:,2],
               c=pts[:,1], cmap="viridis", s=0.5, alpha=0.4)

    # 중심
    ax.scatter(*center, color="red", s=120, zorder=5, label=f"center {np.round(center,3)}")
    # eye
    ax.scatter(*EYE, color="cyan", s=120, marker="^", zorder=5, label=f"eye {EYE}")
    # eye → center 선
    ax.plot([EYE[0], center[0]], [EYE[1], center[1]], [EYE[2], center[2]],
            "cyan", lw=1.5, alpha=0.7)

    ax.set_xlabel("X"); ax.set_ylabel("Y"); ax.set_zlabel("Z")
    ax.set_title(title, fontsize=10)
    ax.legend(fontsize=7)

# ── XY 평면 투영 (overlap 확인) ───────────────────────────────────────────────
ax3 = fig.add_subplot(1, 3, 3)
ax3.scatter(raw_s[:,0], raw_s[:,1], s=0.3, alpha=0.3, label="raw", color="orange")
ax3.scatter(real_s[:,0], real_s[:,1], s=0.3, alpha=0.3, label="transformed", color="blue")
ax3.scatter(*raw_center[:2],  color="red",  s=80, zorder=5, label=f"raw_center {np.round(raw_center[:2],3)}")
ax3.scatter(*real_center[:2], color="navy", s=80, marker="D", zorder=5, label=f"real_center {np.round(real_center[:2],3)}")
ax3.scatter(EYE[0], EYE[1], color="cyan", s=100, marker="^", zorder=5, label=f"eye XY {EYE[:2]}")
ax3.set_xlabel("X"); ax3.set_ylabel("Y")
ax3.set_title("XY 투영 (raw vs transformed)", fontsize=10)
ax3.legend(fontsize=7); ax3.set_aspect("equal"); ax3.grid(True)

plt.tight_layout()
out = "/home/ubuntu/Rendering_Contest/Rendering_PJ/renders/mesh_center_debug.png"
plt.savefig(out, dpi=150)
print(f"\n시각화 저장: {out}")
