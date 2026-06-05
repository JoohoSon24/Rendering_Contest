#!/usr/bin/env bash
# ╔══════════════════════════════════════════════════════════════╗
#  setup_nerfstudio_env.sh — nerfstudio conda 환경 설정
#
#  수행 내용:
#    [1] conda 환경 변수 영구 등록 (TORCH_CUDA_ARCH_LIST 등)
#    [2] gsplat CUDA 확장 사전 컴파일 (JIT 빌드 캐시 생성)
#    [3] 설치 검증
#
#  RULES
#  1. conda activate nerfstudio 먼저 실행
#  2. ~/Rendering_Contest 에서 실행: bash setup_nerfstudio_env.sh
#  3. 환경이 새로 구성되거나 JIT 캐시가 초기화된 경우 재실행
#
#  [이 스크립트가 필요한 상황]
#  - ValueError: Unknown CUDA arch (10.0) or GPU not supported 에러 발생 시
#    → gsplat JIT 빌드 중 TORCH_CUDA_ARCH_LIST 미설정으로 발생
#    → 이 스크립트가 conda 환경 변수로 영구 등록하여 방지
#  - 새 서버/컨테이너에서 nerfstudio 환경 구성 후
# ╚══════════════════════════════════════════════════════════════╝

set -euo pipefail

ENV_NAME="${1:-nerfstudio}"

set +u
source ~/miniconda3/etc/profile.d/conda.sh
conda activate "${ENV_NAME}"
set -u

[[ "${CONDA_DEFAULT_ENV:-}" != "${ENV_NAME}" ]] && echo "❌ conda activate ${ENV_NAME} 먼저" && exit 1

echo "========================================"
echo " [1/3] conda 환경 변수 영구 등록"
echo "========================================"
# TORCH_CUDA_ARCH_LIST:
#   8.0       → A100 (SM 8.0) 네이티브 컴파일
#   9.0+PTX   → Hopper (SM 9.0) PTX 포함 → Blackwell(SM 10.0) 등 향후 GPU에서
#               런타임 PTX JIT 컴파일로 동작 (Unknown CUDA arch 에러 방지)
conda env config vars set TORCH_CUDA_ARCH_LIST="8.0;9.0+PTX" -n "${ENV_NAME}"

# 재활성화해서 환경 변수 적용 (set -u와 충돌하므로 일시 해제)
set +euo pipefail
# shellcheck disable=SC1091
conda deactivate 2>/dev/null || true
conda activate "${ENV_NAME}"
set -euo pipefail

echo "  TORCH_CUDA_ARCH_LIST = ${TORCH_CUDA_ARCH_LIST:-<재활성화 필요>}"

echo "========================================"
echo " [2/3] gsplat CUDA 확장 사전 컴파일"
echo "========================================"
# JIT 캐시를 지금 강제 생성 → 런타임에 긴 빌드 대기 없애고 arch 에러 방지
echo "  (최초 실행 시 수 분 소요됩니다)"

# 기존 캐시 제거 후 재빌드 (아키텍처 불일치 캐시 제거)
GSPLAT_CACHE=$(python3 -c "
from torch.utils.cpp_extension import _get_build_directory
print(_get_build_directory('gsplat_cuda', verbose=False))
")
echo "  캐시 경로: ${GSPLAT_CACHE}"

if [[ -d "${GSPLAT_CACHE}" ]]; then
    echo "  기존 캐시 제거: ${GSPLAT_CACHE}"
    rm -rf "${GSPLAT_CACHE}"
fi

python3 - <<'PYEOF'
import os
print(f"  TORCH_CUDA_ARCH_LIST = {os.environ.get('TORCH_CUDA_ARCH_LIST', '<unset>')}")
print("  gsplat CUDA 확장 컴파일 시작...")
import gsplat
from gsplat.cuda._backend import _C
if _C is not None:
    print("  ✅ gsplat CUDA 확장 로드 성공")
else:
    print("  ⚠️  gsplat CUDA 확장 로드 실패 (_C is None)")
PYEOF

echo "========================================"
echo " [3/3] 설치 검증"
echo "========================================"
python3 - <<'PYEOF'
import torch
import gsplat

print(f"  torch      : {torch.__version__}")
print(f"  CUDA       : {torch.version.cuda}")
print(f"  gsplat     : {gsplat.__version__}")
print(f"  GPU        : {torch.cuda.get_device_name(0)}")
cap = torch.cuda.get_device_capability()
print(f"  SM         : {cap[0]}.{cap[1]}")
print(f"  ARCH_LIST  : {__import__('os').environ.get('TORCH_CUDA_ARCH_LIST', '<unset>')}")
PYEOF

echo ""
echo "  ✅ nerfstudio 환경 설정 완료"
echo "  conda activate ${ENV_NAME} 로 활성화 후 사용하세요"
