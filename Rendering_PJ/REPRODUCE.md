# Reproducibility Guide

이 문서는 제출된 코드와 데이터로 **3D 콘텐츠 및 최종 영상을 재현**하는 절차를 단계별로 기술합니다.

---

## 제출 파일 목록

| 파일 | 설명 | 크기 |
|------|------|------|
| `meshes/deformation1.glb` | **제출 3D 콘텐츠** — morph 애니메이션 포함 GLB | 22 MB |
| `renders/final_transition_output_ver2.mp4` | **제출 최종 영상** | 2.9 MB |
| `renders/background_flyin_final.mp4` | 배경 fly-in 렌더링 (중간 결과) | 2.8 MB |
| `renders/deformation.mp4` | GLB 애니메이션 렌더링 (중간 결과) | 1.8 MB |
| `meshes/splat_wo_background_2.ply` | SuperSplat 편집 후 PLY (중간 결과) | 4.6 MB |
| `meshes/object-resumed_gaussians/splat.ply` | GS 학습 원본 PLY (중간 결과) | 12 MB |
| `outputs/object-resumed/` | GS 학습 체크포인트 | 53 MB |
| `data/object.MOV` | 오브젝트 촬영 원본 영상 | — |
| `data/background.MOV` | 배경 촬영 원본 영상 | — |

---

## 재현 경로 선택

```
경로 A — 빠른 검증 (권장, ~15분)
  제공된 deformation1.glb + background_flyin_final.mp4
  → generate_final.sh
  → final_transition_output_ver2.mp4  ✔ 재현 완료

경로 B — GLB 이전 단계 검증 (~1시간 + 수동 2단계)
  data/object.MOV
  → GS 학습 (outputs/object-resumed/ 체크포인트 재사용 가능)
  → PLY 추출 → SuperSplat 편집(수동) → 메시 변환
  → Blender 애니메이션(수동) → deformation1.glb
```

> **수동 단계**: SuperSplat(브라우저 배경 제거)과 Blender(morph 애니메이션 제작)는  
> 자동화 불가한 크리에이티브 과정입니다. 중간 산출물(`splat_wo_background_2.ply`,  
> `splat_wo_background_2_mesh/`, `deformation1.glb`)이 모두 포함되어 있어 검증 가능합니다.

---

## 사전 요구사항

### 하드웨어
- CUDA 지원 GPU (A100 또는 동급 이상 권장)
- RAM 32 GB 이상

### 시스템 패키지
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg xvfb
```

### Python 환경 (nerfstudio conda)

> 서버에 이미 `/home/ubuntu/miniconda3/envs/nerfstudio` 환경이 구성되어 있습니다.  
> 새 환경이 필요한 경우 아래 절차를 따르세요.

```bash
# 새 환경 구성 (이미 있으면 건너뜀)
conda create -n nerfstudio python=3.10 -y
conda activate nerfstudio

pip install nerfstudio==1.1.5
pip install gsplat==1.4.0
pip install pyrender==0.1.45 trimesh==4.6.0
pip install flask opencv-python-headless pillow scipy

# CUDA arch 영구 등록 (gsplat JIT 빌드 필수)
bash scripts/setup_nerfstudio_env.sh
```

---

## 경로 A — 최종 영상 재현 (권장)

`deformation1.glb`와 `background_flyin_final.mp4`가 이미 제공됩니다.  
아래 명령 한 줄로 `final_transition_output_ver2.mp4`를 재현합니다.

```bash
cd Rendering_PJ
conda activate nerfstudio
export PYOPENGL_PLATFORM=egl

bash generate_final.sh
```

완료 후 `renders/final_transition_output_ver2.mp4` 생성을 확인합니다.

### 예상 출력

```
══ [1/4] 환경 확인 ══
  Python : /home/ubuntu/miniconda3/envs/nerfstudio/bin/python
  GLB    : .../meshes/deformation1.glb  (22M)
  BG     : .../renders/background_flyin_final.mp4

══ [2/4] Deformation 렌더링 ══
  [240/240] t=9.96s  w=0.997          ← 약 10분 소요

══ [3/4] Crossfade 합성 ══
  bg=14.583s  offset=13.083s  xfade=1.5s

══ [4/4] 앞뒤 트림 ══
  원본: 23.1s  →  남은 길이: 9.5s

  ✅ 완료!
  final_transition_output_ver2.mp4     2.9M
```

### 중간 결과물 재사용 (렌더링 생략)

deformation.mp4가 이미 있는 경우 렌더링 단계를 건너뛸 수 있습니다.

```bash
bash generate_final.sh --skip-deform
```

---

## 3D 콘텐츠 확인 — deformation1.glb

### 방법 1: 브라우저 (권장)

[https://gltf-viewer.donmccurdy.com](https://gltf-viewer.donmccurdy.com) 접속 →  
`meshes/deformation1.glb` 드래그앤드롭 → 우측 "Animation" 패널에서 재생

### 방법 2: MeshLab

```bash
MeshLab meshes/deformation1.glb
```

> MeshLab은 정적 프레임만 표시합니다 (애니메이션 미지원).

### 방법 3: 인터랙티브 뷰어 (렌더 연동)

```bash
conda activate nerfstudio
cd Rendering_PJ
python scripts/web_viewer.py
# VS Code PORTS 탭 → 7860 포워딩 → http://localhost:7860
```

마우스 드래그로 시점 조정 → 스페이스바로 `deformation.mp4` 렌더링 트리거.

---

## 경로 B — GLB 이전 단계 전체 재현

### B-1. GS 학습

원본 영상으로부터 Gaussian Splatting 모델을 학습합니다.

```bash
conda activate nerfstudio
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"
export CUDA_VISIBLE_DEVICES=0

# 영상 전처리(COLMAP) + splatfacto 학습 (약 40분)
bash gs/train.sh \
  -d data/object.MOV \
  -e object-reproduced \
  -m splatfacto \
  -i 30000

# 결과: outputs/object-reproduced/splatfacto/<timestamp>/
```

> **체크포인트 재사용**: 기존 학습 결과(`outputs/object-resumed/`)가 있으면  
> 이 단계를 건너뛰고 아래 PLY 추출 단계로 바로 이동할 수 있습니다.
>
> ```bash
> # 기존 체크포인트 경로
> CONFIG=outputs/object-resumed/splatfacto/2026-06-01_160906/config.yml
> ```

### B-2. Gaussian PLY 추출

```bash
# 새로 학습한 경우
CONFIG=outputs/object-reproduced/splatfacto/<timestamp>/config.yml

# 제공된 체크포인트 사용 시
CONFIG=outputs/object-resumed/splatfacto/2026-06-01_160906/config.yml

bash gs/extract_mesh.sh -c "$CONFIG" -e object-reproduced
# 결과: meshes/object-reproduced_gaussians/splat.ply
```

### B-3. SuperSplat 브라우저 편집 (수동)

> 이 단계의 결과물(`meshes/splat_wo_background_2.ply`)이 이미 제공됩니다.  
> 재현하려면 아래 절차를 따르세요.

1. [https://superspl.at/editor](https://superspl.at/editor) 접속
2. `splat.ply` 드래그앤드롭
3. 배경·잡음 Gaussian을 Selection 툴로 선택 → Delete
4. 편집된 PLY 다운로드 → `meshes/splat_wo_background_2.ply`로 저장

### B-4. PLY → OBJ + UV 텍스처

```bash
bash scripts/convert_gs_mesh.sh meshes/splat_wo_background_2.ply \
  -o meshes/splat_wo_background_2_mesh
# 결과: mesh.obj + mesh.mtl + texture.png
```

### B-5. OBJ → GLB

```bash
bash scripts/convert_to_glb.sh \
  meshes/splat_wo_background_2_mesh/mesh.obj
# 결과: meshes/splat_wo_background_2_mesh/mesh.glb
```

### B-6. Blender — morph 애니메이션 제작 (수동)

> 이 단계의 결과물(`meshes/deformation1.glb`)이 이미 제공됩니다.

Blender에서 morph target(Shape Key) 애니메이션을 제작한 뒤 GLB로 내보냅니다.

1. **Import**: File → Import → glTF 2.0 → `mesh.glb`
2. **Shape Key 추가**: Properties → Object Data → Shape Keys
   - `+` → Basis (기준 형태 자동 생성)
   - `+` → Key 1 (변형 형태)
   - Edit Mode에서 Key 1 선택 → 버텍스 변형
3. **키프레임**:
   - Frame 0: Key 1 Value = `0.0` → `I` (Insert Keyframe)
   - Frame N: Key 1 Value = `1.0` → `I`
4. **Export**: File → Export → glTF 2.0
   - Format: **GLB**
   - Mesh → **Shape Keys** ✓ 체크
   - Animation → **NLA Tracks** ✓ 체크
   - 저장 경로: `meshes/deformation1.glb`

### B-7. 최종 영상 생성

B-6 이후 경로 A와 동일합니다.

```bash
bash generate_final.sh
```

---

## 문제 해결

### pyrender 검은 화면

EGL 플랫폼 설정이 누락된 경우 발생합니다.

```bash
export PYOPENGL_PLATFORM=egl
python scripts/render_deformation.py --traj fixed --eye 1.179537 0.486765 0.260652
```

### gsplat JIT 빌드 실패 (Unknown CUDA arch)

```bash
bash scripts/setup_nerfstudio_env.sh
conda activate nerfstudio   # 재활성화 필수
```

### ffmpeg 홀수 해상도 오류

`scale=540:963`(홀수 높이) → libx264 오류가 발생하는 경우,  
`generate_final.sh`는 자동으로 `scale=540:962`로 보정합니다.

### 렌더링 중 EGL 컨텍스트 오류

GPU 드라이버 또는 EGL 라이브러리 문제입니다.

```bash
# EGL 라이브러리 확인
find /usr -name "libEGL.so*" 2>/dev/null

# nvidia EGL 확인
ls /usr/share/glvnd/egl_vendor.d/
```

---

## 소프트웨어 출처

| 소프트웨어 | 용도 | 라이선스 |
|---|---|---|
| [NerfStudio](https://github.com/nerfstudio-project/nerfstudio) (v1.1.5) | GS 학습, 렌더링 | Apache 2.0 |
| [gsplat](https://github.com/nerfstudio-project/gsplat) (v1.4.0) | Gaussian Splatting CUDA 커널 | Apache 2.0 |
| [SuperSplat](https://superspl.at) | PLY 브라우저 편집 | Free |
| [Blender](https://www.blender.org) | GLB morph 애니메이션 | GPL |
| [pyrender](https://github.com/mmatl/pyrender) (v0.1.45) | EGL 오프스크린 렌더링 | MIT |
| [trimesh](https://github.com/mikedh/trimesh) (v4.12.2) | 메시 처리 | MIT |
| [FFmpeg](https://ffmpeg.org) | 영상 합성·트림 | LGPL |
