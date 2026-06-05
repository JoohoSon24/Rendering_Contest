#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  convert_ply.sh — PLY → GLB / OBJ 변환 (VSCode 뷰어용)
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행
#  2. ~/Rendering_Contest 에서 실행
#  3. NeuS-facto 폴리곤 메시에 적합
#     GS splat.ply (sh_coeffs)는 점군으로만 표시됨 — SuperSplat 사용 권장
# ╠══════════════════════════════════════════════════════════════╣
#  사용법:
#    bash convert_ply.sh meshes/nerf-IMG_1217.ply
#    bash convert_ply.sh meshes/nerf-IMG_1217.ply -f obj   # OBJ로 변환
#    bash convert_ply.sh meshes/nerf-IMG_1217.ply -o out/model.glb
# ╚══════════════════════════════════════════════════════════════╝

# 결과 파일은 https://superspl.at/editor/ 여기에서 가공하기

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate nerfstudio
set -u

# ── 인수 파싱 ─────────────────────────────────────────────────────────────────
INPUT=""
FORMAT="glb"    # glb | obj | stl
OUTPUT=""

usage() {
    echo "사용법: bash convert_ply.sh <input.ply> [-f glb|obj|stl] [-o output경로]"
    echo "  -f FMT   출력 형식 (default: glb)"
    echo "  -o PATH  출력 파일 경로 (미지정 시 입력 파일과 같은 위치)"
    exit 0
}

# positional 첫 번째 인수를 INPUT으로 처리
[[ $# -gt 0 && "$1" != -* ]] && INPUT="$1" && shift

while getopts "f:o:h" opt; do
    case "$opt" in
        f) FORMAT="$OPTARG" ;;
        o) OUTPUT="$OPTARG" ;;
        h) usage ;;
    esac
done

[[ -z "$INPUT" ]] && echo "❌ 입력 PLY 파일을 지정하세요" && usage
[[ "$INPUT" != /* ]] && INPUT="${ROOT}/${INPUT}"
[[ ! -f "$INPUT" ]] && echo "❌ 파일 없음: $INPUT" && exit 1

[[ -z "$OUTPUT" ]] && OUTPUT="${INPUT%.ply}.${FORMAT}"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  PLY → ${FORMAT^^} 변환"
echo "  입력 : $INPUT"
echo "  출력 : $OUTPUT"
echo "════════════════════════════════════════════════════════"
echo ""

python3 - <<PYEOF
import trimesh, numpy as np, os

input_path  = "$INPUT"
output_path = "$OUTPUT"
fmt         = "$FORMAT"

def is_gs_ply(path):
    """GS splat.ply 여부 확인 (f_dc_0 필드 존재)"""
    from plyfile import PlyData
    try:
        names = [p.name for p in PlyData.read(path)['vertex'].properties]
        return 'f_dc_0' in names
    except Exception:
        return False

def load_gs_as_pointcloud(path, opacity_thresh=0.05):
    """GS splat.ply → 컬러 점군 (SH DC 성분으로 색상 추출)"""
    from plyfile import PlyData
    v = PlyData.read(path)['vertex']
    xyz = np.column_stack([v['x'], v['y'], v['z']]).astype(np.float32)
    C0  = 0.28209479177387814
    rgb = np.clip(C0 * np.column_stack([v['f_dc_0'], v['f_dc_1'], v['f_dc_2']]) + 0.5, 0, 1)
    opacity = 1 / (1 + np.exp(-np.array(v['opacity'], dtype=np.float32)))
    mask = opacity > opacity_thresh
    rgba = np.ones((mask.sum(), 4), dtype=np.uint8)
    rgba[:, :3] = (rgb[mask] * 255).astype(np.uint8)
    print(f"  점군 크기: {mask.sum():,} / {len(xyz):,}  (opacity>{opacity_thresh})")
    return trimesh.PointCloud(vertices=xyz[mask], colors=rgba)

print(f"  로딩: {input_path}")

if is_gs_ply(input_path):
    print("  GS splat.ply 감지 → 점군으로 변환 (색상 포함)")
    pc = load_gs_as_pointcloud(input_path)
    data = pc.export(file_type=fmt)
    print(f"  💡 메시+텍스처가 필요하면: bash convert_gs_mesh.sh {input_path}")
else:
    loaded = trimesh.load(input_path, force="mesh", process=False)
    if isinstance(loaded, trimesh.Scene):
        mesh = trimesh.util.concatenate(
            [g for g in loaded.geometry.values() if isinstance(g, trimesh.Trimesh)]
        )
    else:
        mesh = loaded
    print(f"  정점: {len(mesh.vertices):,}  면: {len(mesh.faces):,}")
    data = mesh.export(file_type=fmt)

with open(output_path, "wb" if isinstance(data, bytes) else "w") as f:
    f.write(data)

size_mb = os.path.getsize(output_path) / 1024 / 1024
print(f"  ✅ 저장 완료: {output_path}  ({size_mb:.1f} MB)")
PYEOF

echo ""
echo "  VSCode에서 열기: File → Open → $(basename "$OUTPUT")"
echo "  (확장: 'glTF Tools' 또는 '3D Viewer' 설치 필요)"
echo "════════════════════════════════════════════════════════"
