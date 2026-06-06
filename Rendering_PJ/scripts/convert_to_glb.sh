#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  convert_to_glb.sh — OBJ / PLY → GLB 변환 (VSCode 뷰어용)
#  텍스처(texture.png)가 있으면 GLB에 자동 임베드
# ╠══════════════════════════════════════════════════════════════╣
#  RULES
#  1. conda activate nerfstudio 먼저 실행
#  2. ~/Rendering_Contest 에서 실행
#  3. OBJ 변환 시 mesh.mtl / texture.png 가 같은 폴더에 있어야 함
# ╠══════════════════════════════════════════════════════════════╣
#  사용법:
#    bash convert_to_glb.sh meshes/splat_mesh/mesh.obj
#    bash convert_to_glb.sh meshes/nerf-IMG_1217.ply
#    bash convert_to_glb.sh meshes/splat_mesh/mesh.obj -o out/model.glb
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set +u
eval "$(conda shell.bash hook)"
conda activate nerfstudio
set -u

INPUT=""
OUTPUT=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -o|--output) OUTPUT="$2"; shift 2 ;;
        -h|--help)
            sed -n '2,15p' "$0"; exit 0 ;;
        *) INPUT="$1"; shift ;;
    esac
done

[[ "${CONDA_DEFAULT_ENV:-}" != "nerfstudio" ]] && echo "❌ conda activate nerfstudio 먼저" && exit 1
[[ -z "$INPUT" ]] && echo "❌ 입력 파일을 지정하세요" && exit 1
[[ "$INPUT" != /* ]] && INPUT="${ROOT}/${INPUT}"
[[ ! -f "$INPUT" ]] && echo "❌ 파일 없음: $INPUT" && exit 1

[[ -z "$OUTPUT" ]] && OUTPUT="${INPUT%.*}.glb"

echo ""
echo "════════════════════════════════════════════════════════"
echo "  → GLB 변환"
echo "  입력 : $INPUT"
echo "  출력 : $OUTPUT"
echo "════════════════════════════════════════════════════════"

python3 - <<PYEOF
import trimesh
import numpy as np
import os, sys

input_path  = "$INPUT"
output_path = "$OUTPUT"

print(f"  로딩...")
scene = trimesh.load(input_path, process=False)

# Scene vs 단일 Mesh 처리
if isinstance(scene, trimesh.Scene):
    vcount = sum(len(g.vertices) for g in scene.geometry.values() if hasattr(g, 'vertices'))
    fcount = sum(len(g.faces)    for g in scene.geometry.values() if hasattr(g, 'faces'))
else:
    vcount = len(scene.vertices)
    fcount = len(scene.faces) if hasattr(scene, 'faces') else 0

print(f"  꼭짓점: {vcount:,}  면: {fcount:,}")

# GLB 변환 (텍스처 자동 임베드)
glb_data = scene.export(file_type="glb")
with open(output_path, "wb") as f:
    f.write(glb_data)

size_mb = os.path.getsize(output_path) / 1024 / 1024
print(f"  ✅ GLB 저장 완료: {output_path}  ({size_mb:.1f} MB)")
PYEOF

echo ""
echo "  VSCode에서 열기:"
echo "    Extensions → '3D Viewer' 또는 'glTF Tools' 설치 후"
echo "    $(basename "$OUTPUT") 파일 클릭"
echo "════════════════════════════════════════════════════════"
