# Rendering Contest — 3D 재구성 + 변형 애니메이션 합성 파이프라인

비디오 한 편에서 시작해 **Gaussian Splatting 학습 → PLY 추출 → 브라우저 편집 → GLB 변환 → Blender 애니메이션 → 렌더링 합성** 까지 전 과정을 기록한 파이프라인입니다.

---

## 목차

1. [전체 파이프라인 개요](#1-전체-파이프라인-개요)
2. [폴더 구조](#2-폴더-구조)
3. [환경 설정](#3-환경-설정)
4. [Phase A — Object: GS 학습 → PLY → 브라우저 편집 → GLB](#4-phase-a--object-gs-학습--ply--브라우저-편집--glb)
5. [Phase B — GLB 애니메이션 (Blender)](#5-phase-b--glb-애니메이션-blender)
6. [Phase C — Deformation 렌더링](#6-phase-c--deformation-렌더링)
7. [Phase D — 배경 GS 학습 + 카메라 경로 → 배경 렌더링](#7-phase-d--배경-gs-학습--카메라-경로--배경-렌더링)
8. [Phase E — 두 영상 합성 + 후처리](#8-phase-e--두-영상-합성--후처리)
9. [One-Stop 스크립트](#9-one-stop-스크립트)
10. [인터랙티브 뷰어](#10-인터랙티브-뷰어)
11. [시행착오 기록](#11-시행착오-기록)

---

## 1. 전체 파이프라인 개요

```
[Object 영상]                         [Background 영상]
      │                                       │
      ▼                                       ▼
  GS 학습 (splatfacto)               GS 학습 (splatfacto)
      │                                       │
      ▼                                       ▼
  PLY 추출                           ns-render interpolate
  (Gaussian splat)                   (eval 카메라 경로 렌더링)
      │                                       │
      ▼                                       ▼
  SuperSplat 브라우저 편집         마지막 트라젝토리 방향 추출
  (배경 제거, 오브젝트 분리)         + fly-in 카메라 경로 연장
      │                                       │
      ▼                                       ▼
  PLY → OBJ + 텍스처               통합 camera_path.json 생성
  (convert_gs_mesh.sh)                        │
      │                                       ▼
      ▼                             ns-render camera-path
  OBJ → GLB (trimesh)               → background_flyin_final.mp4
      │
      ▼
  Blender 애니메이션 제작
  (morph target / shape key)
      │
      ▼
  render_deformation.py             ← 웹 뷰어로 시점 선택 가능
  (pyrender EGL 렌더링)
      │
      ▼
  deformation.mp4
      │
      └──────────── ffmpeg xfade ─────────────┘
                          │
                          ▼
               final_transition_output.mp4
                          │
                          ▼ (앞뒤 트림)
               final_transition_output_ver2.mp4  ← 최종 결과
```

---

## 2. 폴더 구조

```
Rendering_PJ/
│
├── config.sh                    # GS 파이프라인 전역 설정
├── pipeline.sh                  # GS 전체 오케스트레이터 (학습→PLY→GLB→렌더)
├── generate_final.sh            # ★ GLB + 배경 → 최종 영상 one-stop 스크립트
│
├── gs/                          # Gaussian Splatting 학습 래퍼
│   ├── train.sh                 #   영상 → COLMAP → splatfacto 학습
│   ├── run.sh                   #   전처리 완료 데이터 → 학습
│   ├── resume.sh                #   체크포인트에서 이어 학습
│   └── extract_mesh.sh          #   Gaussian PLY 추출
│
├── nerf/                        # NeuS-facto (SDF) 학습 래퍼 (선택)
│   └── train.sh / run.sh / resume.sh / extract_mesh.sh
│
├── scripts/
│   ├── render_deformation.py    # ★ GLB morph 애니메이션 렌더링 (pyrender EGL)
│   ├── web_viewer.py            # ★ 브라우저 인터랙티브 뷰어 (Flask, 포트 7860)
│   ├── viewer_render.py         #   pyrender GLFW 뷰어 (Xvfb 필요)
│   ├── camera_preview.py        #   elevation×azimuth 시점 미리보기 PNG 생성
│   ├── make_camera_path.py      #   fly-in 카메라 경로 JSON 생성
│   ├── make_flyin_render.sh     #   Part1+Part2 영상 xfade 합성 (레거시)
│   ├── gs_to_mesh.py            #   GS PLY → OBJ + UV 텍스처 (SuGaR 스타일)
│   ├── convert_gs_mesh.sh       #   gs_to_mesh.py 래퍼
│   ├── convert_ply.sh           #   폴리곤 PLY → GLB/OBJ/STL
│   ├── convert_to_glb.sh        #   OBJ/PLY → GLB (텍스처 자동 임베드)
│   ├── visualize_cameras.py     #   COLMAP 카메라 인터랙티브 시각화 (HTML)
│   ├── visualize_mesh_center.py #   메시 좌표계 진단 시각화
│   ├── background_flyin_pipeline.md  # 배경 렌더링 파이프라인 상세 기록
│   ├── setup_nerfstudio_env.sh  #   nerfstudio conda 환경 설치
│   └── setup_sdfstudio_env.sh   #   sdfstudio conda 환경 설치
│
├── data/
│   └── processed/
│       ├── object/              # COLMAP 처리된 object 데이터
│       ├── background/          # COLMAP 처리된 background 데이터
│       └── IMG_1217/            # 기타 영상 데이터
│
├── outputs/                     # nerfstudio 학습 결과 (자동 생성)
│   ├── object/splatfacto/...    # object GS 체크포인트·config
│   ├── object2/splatfacto/...   # object GS 재학습 버전
│   ├── object-resumed/...       # 이어 학습 버전
│   └── background/splatfacto/...# background GS 체크포인트·config
│
├── meshes/                      # 메시·GLB 파일
│   ├── deformation1.glb         # ★ Blender 제작 morph 애니메이션 GLB
│   ├── splat_wo_background_2.ply# SuperSplat 편집 PLY (배경 제거됨)
│   ├── object_gaussians/        # GS → OBJ+텍스처 변환 결과
│   ├── object2_gaussians/       # object2 GS → OBJ+텍스처
│   └── splat_wo_background_2_mesh/ # 편집 PLY → OBJ+텍스처
│
├── renders/                     # 렌더링 결과물
│   ├── deformation.mp4                      # GLB 애니메이션 렌더링
│   ├── background_flyin_final.mp4           # 배경 fly-in 렌더링
│   ├── final_transition_output.mp4          # 합성 결과 (트림 전)
│   └── final_transition_output_ver2.mp4     # ★ 최종 결과
│
└── camera_path.json             # fly-in 카메라 경로
```

---

## 3. 환경 설정

### 사전 요구사항
- CUDA 지원 GPU (A100 권장)
- conda / miniconda

### nerfstudio 환경 (GS 학습 + 렌더링)

```bash
bash scripts/setup_nerfstudio_env.sh
conda activate nerfstudio

# 추가 패키지 (렌더링·웹 뷰어용)
pip install pyrender trimesh flask flask-socketio scipy glfw pillow
```

주요 패키지: `nerfstudio`, `gsplat`, `pyrender`, `trimesh`, `flask`, `opencv-python-headless`

### ffmpeg

```bash
sudo apt-get install -y ffmpeg xvfb
```

### CUDA 설정 (학습·렌더링 전 필수)

```bash
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"
export CUDA_VISIBLE_DEVICES=0
```

---

## 4. Phase A — Object: GS 학습 → PLY → 브라우저 편집 → GLB

### A-1. GS 학습

```bash
conda activate nerfstudio
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"

bash gs/train.sh -d data/raw/object.mp4 -e object -m splatfacto -i 30000
# 결과: outputs/object/splatfacto/<timestamp>/
```

### A-2. Gaussian PLY 추출

```bash
bash gs/extract_mesh.sh \
  -c outputs/object/splatfacto/<timestamp>/config.yml \
  -e object
# 결과: meshes/object_gaussians/splat.ply
```

### A-3. SuperSplat 브라우저 편집

1. [https://superspl.at/editor](https://superspl.at/editor) 접속
2. `splat.ply` 드래그앤드롭
3. Selection 툴로 배경·잡음 Gaussian 선택 → Delete
4. 편집된 PLY 다운로드 → `meshes/splat_wo_background_2.ply`

> 편집 후 PLY는 Gaussian 수가 줄어 이후 변환·렌더링이 빠릅니다.

### A-4. PLY → OBJ + UV 텍스처

```bash
bash scripts/convert_gs_mesh.sh meshes/splat_wo_background_2.ply \
  -o meshes/splat_wo_background_2_mesh
# 결과: mesh.obj + texture.png
```

### A-5. OBJ → GLB

```bash
bash scripts/convert_to_glb.sh meshes/splat_wo_background_2_mesh/mesh.obj
# 결과: meshes/splat_wo_background_2_mesh/mesh.glb
```

---

## 5. Phase B — GLB 애니메이션 (Blender)

Blender에서 morph target (Shape Key) 애니메이션을 제작하여 GLB로 내보냅니다.

### 작업 흐름

1. **Import**: File → Import → glTF 2.0 → `mesh.glb`
2. **Shape Key 추가**:
   - Properties → Object Data → Shape Keys → `+` (Basis 자동 생성)
   - `+` 한 번 더 → Key 1 추가
   - Edit Mode에서 Key 1 선택 후 버텍스를 원하는 형태로 변형
3. **키프레임 애니메이션**:
   - Frame 0: Key 1 Value = 0.0 → `I` (Insert Keyframe)
   - Frame N: Key 1 Value = 1.0 → `I`
4. **Export**: File → Export → glTF 2.0
   - Format: **GLB**
   - Data → Mesh → **Shape Keys** ✓
   - Animation → **NLA Tracks** or **Active Actions** ✓

```
결과 파일: meshes/deformation1.glb
  구조: base mesh + morph target delta + animation (times, weights)
```

---

## 6. Phase C — Deformation 렌더링

### C-1. 시점 선택 — 웹 뷰어 (권장)

```bash
conda activate nerfstudio
cd Rendering_PJ
python scripts/web_viewer.py
# VS Code PORTS 탭 → 7860 포워딩 → http://localhost:7860 접속
# 마우스 드래그로 시점 조정 → 스페이스바로 렌더링 트리거
```

### C-2. 시점 그리드 미리보기

```bash
python scripts/camera_preview.py --elevs "25,35,45" --n_az 12
# renders/preview_elev_p*.png 생성 — eye 좌표 확인 후 아래 명령에 사용
```

### C-3. CLI 직접 렌더링

```bash
# 고정 시점
python scripts/render_deformation.py \
  --traj fixed \
  --eye 1.179537 0.486765 0.260652 \
  --seconds 10 --fps 24 \
  -o renders/deformation.mp4

# orbit
python scripts/render_deformation.py --traj orbit -o renders/deformation.mp4

# 웹 뷰어 캡처 c2w 행렬 사용
python scripts/render_deformation.py \
  --c2w <16개 숫자> -o renders/deformation.mp4
```

**⚠️ 카메라 행렬 필수 사항 (det=+1)**

```python
# 올바른 방법
right = np.cross(fwd, world_up);  right /= np.linalg.norm(right)
up    = np.cross(right, fwd)

# 잘못된 방법 → 특정 각도에서 완전 검은 화면
right = np.cross(world_up, fwd)  # ← 이 순서 금지
```

---

## 7. Phase D — 배경 GS 학습 + 카메라 경로 → 배경 렌더링

### D-1. 배경 GS 학습

```bash
bash gs/train.sh -d data/raw/background.mp4 -e background -m splatfacto -i 30000
```

### D-2. eval 카메라 경로 렌더링

```bash
ns-render interpolate \
  --load-config outputs/background/splatfacto/<timestamp>/config.yml \
  --output-path renders/background_part1.mp4
```

### D-3. fly-in 카메라 경로 생성 및 렌더링

Part 1 마지막 트라젝토리 방향을 평균 내어 fly-in 구간으로 연장합니다.
상세 절차는 [`scripts/background_flyin_pipeline.md`](scripts/background_flyin_pipeline.md) 참조.

```bash
# 통합 camera_path.json 생성 → 단일 렌더링 (권장)
python /tmp/gen_unified_fixed.py        # 590프레임 JSON 생성
# 앞 96프레임 + 뒤 144프레임 트림 → 350프레임
ns-render camera-path \
  --load-config outputs/background/splatfacto/<timestamp>/config.yml \
  --camera-path-filename /tmp/camera_final.json \
  --output-path renders/background_flyin_final.mp4
```

> **단일 렌더링을 권장하는 이유**: GS는 렌더 세션마다 미묘한 색감 차이 발생. xfade보다 하나의 JSON으로 연속 렌더링하면 경계가 완벽히 연속됩니다.

---

## 8. Phase E — 두 영상 합성 + 후처리

### E-1. crossfade 합성

```bash
BG=renders/background_flyin_final.mp4   # 14.58s
DEF=renders/deformation.mp4             # 10.0s

BG_DUR=$(ffprobe -v quiet -select_streams v:0 \
  -show_entries stream=duration -of csv=p=0 "$BG")
XFADE=1.5
OFFSET=$(python3 -c "print(max(0, $BG_DUR - $XFADE))")

ffmpeg -y -i "$BG" -i "$DEF" \
  -filter_complex "
    [0:v]fps=24,scale=540:963,setsar=1,format=yuv420p[v0];
    [1:v]fps=24,scale=540:963,setsar=1,format=yuv420p[v1];
    [v0][v1]xfade=transition=fade:duration=${XFADE}:offset=${OFFSET}[outv]
  " \
  -map "[outv]" -c:v libx264 -crf 18 -preset fast \
  renders/final_transition_output.mp4
# 결과: 23.1초
```

### E-2. 앞뒤 트림

```bash
# 앞 6.58s + 뒤 7s 제거 → 약 9.5초
ffmpeg -y -ss 6.58 -i renders/final_transition_output.mp4 -t 9.503333 \
  -vf "scale=540:962" \
  -c:v libx264 -crf 18 -preset fast -pix_fmt yuv420p \
  renders/final_transition_output_ver2.mp4
```

> **⚠️ yuv420p 홀수 해상도 주의**: 원본 높이 963이 홀수 → libx264 오류. `-vf scale=540:962` 로 짝수로 맞춰야 합니다.

---

## 9. One-Stop 스크립트

GLB 애니메이션과 배경 영상이 준비된 상태에서 최종 영상까지 자동 생성합니다.

```bash
# 기본 실행
bash generate_final.sh

# 커스텀 옵션
bash generate_final.sh \
  --glb meshes/deformation1.glb \
  --bg  renders/background_flyin_final.mp4 \
  --eye "1.179537 0.486765 0.260652" \
  --trim-start 6.58 \
  --trim-end   7.0 \
  --out renders/final_transition_output_ver2.mp4
```

전체 옵션: `bash generate_final.sh --help`

---

## 10. 인터랙티브 뷰어

### 웹 뷰어 (권장 — 브라우저 기반)

```bash
python scripts/web_viewer.py
# VS Code PORTS 탭 → 7860 포워딩 → http://localhost:7860
```

| 조작 | 기능 |
|------|------|
| 좌클릭 + 드래그 | 카메라 회전 (orbit) |
| 마우스 휠 | 줌 인/아웃 |
| **스페이스바** | 현재 시점으로 `deformation.mp4` 렌더링 시작 |

렌더링 완료 후 브라우저에서 `deformation.mp4` 다운로드 링크 자동 표시.

### 시점 그리드 미리보기

```bash
python scripts/camera_preview.py --elevs "25,35,45" --n_az 12 --dist 1.2
# → renders/preview_elev_p*.png: eye 좌표 포함 썸네일
```

### GLFW 뷰어 (Xvfb 가상 디스플레이 방식)

```bash
Xvfb :99 -screen 0 1280x1024x24 &
DISPLAY=:99 python scripts/viewer_render.py
# 스페이스바 → 현재 c2w로 render_deformation.py 실행
```

---

## 11. 시행착오 기록

### pyrender 특정 각도 검은 화면

**원인**: 카메라 c2w 행렬 `det=-1` (좌수 좌표계). OpenGL은 det=+1 우수좌표계를 가정.  
같은 스크립트에서 일부 각도만 검은 화면이 되는 비결정적 패턴이 특징.

```python
# 잘못된 방법 (det=-1)
right = np.cross(world_up, fwd)
up    = np.cross(fwd, right)

# 올바른 방법 (det=+1)
right = np.cross(fwd, world_up);  right /= np.linalg.norm(right)
up    = np.cross(right, fwd)
```

### trimesh vertex_colors 검은 화면

```python
# 잘못된 방법 — pyrender가 무시함
mesh.visual = trimesh.visual.ColorVisuals(mesh=mesh, vertex_colors=...)

# 올바른 방법 — 생성자에 직접 전달
trimesh.Trimesh(..., vertex_colors=colors, process=False)
```

### GLB node transform

- `deformation1.glb` GLTF node에 rotation+translation 변환 존재
- **eye 좌표는 raw vertex 기준** (node transform 미적용 좌표계)
- `camera_preview.py` 도 동일하게 raw vertex 기준으로 좌표 계산 → 일관성 유지
- node transform을 렌더링에 적용하면 eye 좌표계가 달라져 카메라가 엉뚱한 곳을 향함

### 배경 xfade vs 단일 렌더링

- 초기: Part1(interpolate) + Part2(camera-path) → xfade 합산
- 문제: GS는 렌더 세션이 달라지면 같은 위치도 색감 미묘히 달라져 경계에서 이중 노출 느낌
- 해결: 하나의 `camera_path.json`으로 **단일 ns-render** → 경계 완전히 연속

### 홀수 해상도 인코딩 오류

- `yuv420p`는 짝수 해상도만 지원 → 높이 963(홀수) → libx264 오류
- 해결: `ffmpeg -vf "scale=540:962"` (1px 손실 무시) 또는 `scale=iw:trunc(ih/2)*2`

### EGL 스레드 분리

- pyrender EGL 컨텍스트는 생성한 스레드에서만 사용 가능
- Flask/SocketIO 핸들러가 다른 스레드에서 렌더러를 호출하면 `eglMakeCurrent` 오류
- 해결: `threading.local()`로 스레드별 독립 렌더러 생성
