#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  config.sh — 파이프라인 설정 파일
#  여기만 수정하고 bash pipeline.sh 실행
# ╚══════════════════════════════════════════════════════════════╝

# ── ① 입력 (필수) ────────────────────────────────────────────────────────────
DATA="data/processed/object"  # 영상 파일 (.mp4/.mov 등) 또는 전처리된 폴더 경로
EXP="object2"                          # 실험 이름 (비워두면 파일명에서 자동 생성)

# ── ② 학습 ───────────────────────────────────────────────────────────────────
MODEL="splatfacto"              # splatfacto | splatfacto-big
MAX_ITERS=30000                 # 학습 반복 횟수 (15000 이상이어야 stop_split_at이 작동함)
GPU_ID="0"                      # GPU 번호
NUM_FRAMES=300                  # COLMAP 프레임 추출 수

# ── ③ 메시 변환 (gs_to_mesh) ─────────────────────────────────────────────────
OPACITY_THRESH=0.1              # Gaussian 필터 임계값 (낮을수록 더 많이 포함)
SCALE_THRESH=0.3                # 플로터 제거 최대 scale (0=비활성화)
POISSON_DEPTH=9                 # Poisson 재구성 깊이 (클수록 세밀·느림)
TEXTURE_SIZE=2048               # UV 텍스처 해상도 px (2048 | 4096)

# ── ④ 파이프라인 제어 (true = 해당 단계 건너뜀) ───────────────────────────────
SKIP_TRAIN=false                # GS 학습 건너뜀 (이미 학습된 경우)
SKIP_EXTRACT_PLY=false          # Gaussian PLY 추출 건너뜀
SKIP_GS_TO_MESH=true           # GS → OBJ+텍스처 변환 건너뜀
SKIP_GLB=true                  # OBJ → GLB 변환 건너뜀
SKIP_RENDER=true               # 렌더링 영상 생성 건너뜀
