import os
# EGL(백그라운드 렌더링) 강제 설정 해제 (화면에 창을 띄우기 위함)
if "PYOPENGL_PLATFORM" in os.environ:
    del os.environ["PYOPENGL_PLATFORM"]

import trimesh
import pyrender
import numpy as np

# 1. 모델 로드 (경로를 본인 환경에 맞게 수정하세요)
glb_path = "/home/ubuntu/Rendering_Contest/Rendering_PJ/meshes/deformation1.glb" 
print(f"Loading {glb_path}...")

# 텍스처 베이킹 없이 단순 형태와 색상만 빠르게 로드합니다.
try:
    mesh = trimesh.load(glb_path, force='mesh')
except Exception as e:
    print(f"Error loading mesh: {e}")
    exit()

# 2. 씬(Scene) 구성
scene = pyrender.Scene(bg_color=[20, 20, 28, 255], ambient_light=[0.3, 0.3, 0.3])
scene.add(pyrender.Mesh.from_trimesh(mesh, smooth=True))

# 3. 키보드 콜백 함수: 스페이스바를 누르면 카메라 좌표(eye) 추출
def capture_camera_pose(viewer, event=None):
    # Viewer의 trackball(마우스 조작)에서 현재 4x4 변환 행렬(c2w)을 가져옴
    c2w = viewer._trackball.pose.copy()
    
    # 4x4 행렬의 평행이동(Translation) 부분이 바로 카메라의 위치(eye)
    eye = c2w[:3, 3]
    
    print("\n📸 [찰칵! 현재 시점의 카메라 좌표입니다]")
    print("-" * 50)
    print(f"eye = np.array([{eye[0]:.4f}, {eye[1]:.4f}, {eye[2]:.4f}])")
    print("-" * 50)
    print("이 코드를 render_transition.py의 fixed_c2w() 함수 안에 복사해 넣으세요.\n")

# 4. 인터랙티브 뷰어 실행
print("\n" + "="*50)
print("🎮 [3D 뷰어 조작법]")
print("- 좌클릭 + 드래그 : 카메라 회전")
print("- 우클릭 + 드래그 : 카메라 이동 (상하좌우)")
print("- 마우스 휠 : 줌 인/아웃")
print("- ★ 원하는 구도를 맞춘 후 [스페이스바]를 누르세요! ★")
print("="*50 + "\n")

# registered_keys를 통해 스페이스바(space) 이벤트 연결
viewer = pyrender.Viewer(
    scene, 
    use_raymond_lighting=True,
    viewport_size=(800, 600),
    registered_keys={'c': capture_camera_pose} # <--- 소문자 'c'로 변경!
)