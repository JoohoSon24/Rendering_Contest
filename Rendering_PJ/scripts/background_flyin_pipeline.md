# background_flyin_final.mp4 제작 파이프라인

## 결과물

| 파일 | 설명 |
|------|------|
| `renders/background_flyin_final.mp4` | **최종 렌더링** (350프레임, 14.58초 @ 24fps, 540×963) |
| `renders/trajectory_vis.html` | 카메라 경로 인터랙티브 시각화 |

---

## 구성

```
0s ──────────── 10.4s ─────────── 14.58s
│                  │                  │
│  Part 1          │  Part 2          │
│  eval 카메라 경로 │  fly-in (avg 방향)│
│  (244프레임)     │  (106프레임)      │
│                  │                  │
│              전환점 (gap=0, 각도=0°) │
```

- **전체 경로**: 590프레임(24.58s) 중 앞 4s(96f) + 뒤 6s(144f) 제거 → **350프레임(14.58s)**
- **전환점**: Part1 마지막 위치에서 Part2가 정확히 시작 (위치 gap=0, 시선 각도=0°)
- **단일 렌더링**: xfade 없음, 하나의 camera_path.json으로 연속 렌더

---

## 재현 방법

### Step 1 — 통합 카메라 경로 생성

```python
# /tmp/gen_unified_fixed.py 실행
conda run -n nerfstudio python3 /tmp/gen_unified_fixed.py
# 출력: /tmp/camera_unified2.json  (590프레임)
```

**핵심 파라미터:**
- `render_h = 963` — `ns-render interpolate` 출력 해상도에 맞춤
- `FoV = 98.11°` — `fl_y_full=1665.75, full_h=3840` 기준 정확 계산
  (`fov = 2 * atan(render_h/2 / (fl_y_full * render_h/full_h))`)
- `transition_frames = 24` — Part2 첫 1초 동안 시선 방향 선형 보간
  (Part1 마지막 forward → avg_dir, 각도 차이 부드럽게 해소)

### Step 2 — 앞뒤 트림

```python
# 앞 4초(96프레임) + 뒤 6초(144프레임) 제거
with open("/tmp/camera_unified2.json") as f:
    d = json.load(f)
d["camera_path"] = d["camera_path"][96 : 590 - 144]   # [96:446]
d["seconds"] = 350 / 24
with open("/tmp/camera_final.json", "w") as f:
    json.dump(d, f)
```

### Step 3 — 렌더링

```bash
export TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX"
conda activate nerfstudio

ns-render camera-path \
  --load-config outputs/background/splatfacto/2026-06-01_063932/config.yml \
  --camera-path-filename /tmp/camera_final.json \
  --output-path renders/background_flyin_final.mp4
```

---

## 설계 결정

### 왜 단일 렌더링인가?

초기에는 Part1(`ns-render interpolate`) + Part2(`ns-render camera-path`)를 ffmpeg xfade로 합산했으나:
- GS 렌더링 특성상 같은 위치라도 렌더 세션이 다르면 미묘한 색감·Gaussian 차이 발생
- xfade가 픽셀 합성이라 경계에서 이중 노출 느낌

→ 모든 프레임을 **하나의 camera_path.json**으로 단일 렌더링

### 왜 FoV = 98.11°인가?

`ns-render interpolate`는 eval 카메라의 실제 focal length를 그대로 사용.
`camera-path` 모드는 FoV를 직접 지정 → 잘못된 FoV(32.15°)를 쓰면 화각이 완전히 달라짐.

```
fl_y_render = fl_y_full × (render_h / full_h)
            = 1665.75 × (963 / 3840) = 417.74
FoV = 2 × atan(render_h/2 / fl_y_render)
    = 2 × atan(481.5 / 417.74) = 98.11°
```

### fly-in 방향은 어떻게 결정했나?

Part1 마지막 1초(24프레임)의 프레임 간 이동 벡터를 평균:
```python
last_n = 24
deltas = np.diff(interp_pos[-last_n-1:], axis=0)   # 24개 이동 벡터
avg_dir = deltas.mean(axis=0)
avg_dir /= np.linalg.norm(avg_dir)
# 결과: [-0.252, 0.954, -0.165]
```

### 전환점 연속성

| 항목 | 값 |
|------|-----|
| 위치 gap | 0.000000 units |
| 시선 각도 gap | 0.00° |
| 전환점 좌표 | `(-0.1409, 0.9999, 0.0440)` |

Part2 첫 24프레임 동안 시선 방향을 선형 보간:
```python
t = min(frame_idx / 24, 1.0)
fwd = (1 - t) * last_fwd_n + t * avg_dir
fwd /= np.linalg.norm(fwd)
```
