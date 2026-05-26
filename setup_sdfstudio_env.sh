#!/usr/bin/env bash

# How to use:
# cd ~/JW/rend/sdfstudio
# bash setup_sdfstudio_env.sh

set -eo pipefail

ENV_NAME="${1:-sdfstudio}"
PYTHON_VER="${PYTHON_VER:-3.8}"
CUDA_RUNFILE_URL="https://developer.download.nvidia.com/compute/cuda/11.3.1/local_installers/cuda_11.3.1_465.19.01_linux.run"
CUDA_RUNFILE_NAME="cuda_11.3.1_465.19.01_linux.run"
CUDA_CACHE_DIR="${HOME}/.cache/sdfstudio"

echo "========================================"
echo " [1/6] Create conda env: ${ENV_NAME}"
echo "========================================"
eval "$(conda shell.bash hook)"
CONDA_BASE="$(conda info --base)"

if conda env list | awk '{print $1}' | grep -qx "${ENV_NAME}"; then
    echo "Removing existing env ${ENV_NAME}"
    conda remove -n "${ENV_NAME}" --all -y
fi

conda create -n "${ENV_NAME}" "python=${PYTHON_VER}" -y
conda activate "${ENV_NAME}"

echo "========================================"
echo " [2/6] Base Python packaging tools"
echo "========================================"
python -m pip install --upgrade pip setuptools wheel

echo "========================================"
echo " [3/6] Install CUDA 11.3 toolkit inside env"
echo "========================================"
# SDFStudio pins torch 1.12.1 and was tested with CUDA 11.3.
# Install the 11.3 runtime from conda-forge, then place the matching compiler
# toolchain into the env manually. This avoids two failures we hit repeatedly:
# 1) NVIDIA's modern cuda-toolkit metapackage resolves to 12.x subpackages.
# 2) conda-forge cudatoolkit-dev's post-link script is brittle and rolls back.
unset CUDA_HOME CUDA_PATH CUDAHOSTCXX
conda install -n "${ENV_NAME}" -c conda-forge cudatoolkit=11.3 -y

mkdir -p "${CUDA_CACHE_DIR}"
CUDA_RUNFILE="${CUDA_CACHE_DIR}/${CUDA_RUNFILE_NAME}"
CUDA_RUNFILE_FALLBACK="${CONDA_BASE}/pkgs/cudatoolkit-dev/${CUDA_RUNFILE_NAME}"
CUDA_RUNFILE_SIZE=0
CUDA_RUNFILE_FALLBACK_SIZE=0
if [[ -f "${CUDA_RUNFILE}" ]]; then
    CUDA_RUNFILE_SIZE="$(stat -c%s "${CUDA_RUNFILE}")"
fi
if [[ -f "${CUDA_RUNFILE_FALLBACK}" ]]; then
    CUDA_RUNFILE_FALLBACK_SIZE="$(stat -c%s "${CUDA_RUNFILE_FALLBACK}")"
fi
if [[ "${CUDA_RUNFILE_FALLBACK_SIZE}" -gt 0 ]] && [[ "${CUDA_RUNFILE_SIZE}" -lt "${CUDA_RUNFILE_FALLBACK_SIZE}" ]]; then
    cp -f "${CUDA_RUNFILE_FALLBACK}" "${CUDA_RUNFILE}"
fi
if [[ ! -f "${CUDA_RUNFILE}" ]]; then
    wget "${CUDA_RUNFILE_URL}" -O "${CUDA_RUNFILE}"
fi
chmod +x "${CUDA_RUNFILE}"

CUDA_HOME="${CONDA_PREFIX}/pkgs/cuda-toolkit"
EXTRACT_DIR="$(mktemp -d "${PWD}/.cuda-extract.XXXXXX")"
trap 'rm -rf "${EXTRACT_DIR}"' EXIT

rm -rf "${CUDA_HOME}"
mkdir -p "${CUDA_HOME}"
"${CUDA_RUNFILE}" --silent --toolkit --toolkitpath="${EXTRACT_DIR}" --override
cp -a "${EXTRACT_DIR}/." "${CUDA_HOME}/"

mkdir -p "${CONDA_PREFIX}/bin" "${CONDA_PREFIX}/lib" "${CONDA_PREFIX}/include"
find "${CUDA_HOME}/bin" -maxdepth 1 -type f -exec ln -sf {} "${CONDA_PREFIX}/bin/" \;
find "${CUDA_HOME}/lib64" -maxdepth 1 -type f -exec ln -sf {} "${CONDA_PREFIX}/lib/" \;
find "${CUDA_HOME}/nvvm/bin" -maxdepth 1 -type f -exec ln -sf {} "${CONDA_PREFIX}/bin/" \;
find "${CUDA_HOME}/nvvm/lib64" -maxdepth 1 -type f -exec ln -sf {} "${CONDA_PREFIX}/lib/" \;
find "${CUDA_HOME}/nvvm/libdevice" -maxdepth 1 -type f -exec ln -sf {} "${CONDA_PREFIX}/lib/" \;
find "${CUDA_HOME}/include" -maxdepth 1 -type f -exec ln -sf {} "${CONDA_PREFIX}/include/" \;
ln -sfn "${CUDA_HOME}/nvvm" "${CONDA_PREFIX}/nvvm"
ln -sfn "${CONDA_PREFIX}/lib" "${CONDA_PREFIX}/lib64"

export CUDA_HOME
export PATH="${CUDA_HOME}/bin:${PATH}"
export LD_LIBRARY_PATH="${CUDA_HOME}/lib:${CUDA_HOME}/lib64:${LD_LIBRARY_PATH:-}"

echo "CUDA_HOME=${CUDA_HOME}"
which nvcc
nvcc --version

echo "========================================"
echo " [4/6] Install host compiler + PyTorch/cu113"
echo "========================================"
if ! command -v gcc-10 >/dev/null 2>&1 || ! command -v g++-10 >/dev/null 2>&1 || ! pkg-config --exists libavformat; then
    sudo DEBIAN_FRONTEND=noninteractive apt-get update
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
        gcc-10 g++-10 ffmpeg pkg-config \
        libavformat-dev libavcodec-dev libavdevice-dev libavutil-dev \
        libavfilter-dev libswscale-dev libswresample-dev
fi

pip install torch==1.12.1+cu113 torchvision==0.13.1+cu113 \
    -f https://download.pytorch.org/whl/torch_stable.html
pip install "pillow<10"

echo "========================================"
echo " [5/6] Install tiny-cuda-nn"
echo "========================================"
export CC="/usr/bin/gcc-10"
export CXX="/usr/bin/g++-10"
export CUDAHOSTCXX="${CXX}"
export NVCC_PREPEND_FLAGS="--allow-unsupported-compiler"
export TORCH_DONT_CHECK_COMPILER_ABI=1
pip install ninja
# This machine has an A100 (SM 80). Setting the arch trims build time and
# avoids accidental compilation for every architecture.
export TCNN_CUDA_ARCHITECTURES="${TCNN_CUDA_ARCHITECTURES:-80}"
unset CUDA_PATH BUILD HOST CONDA_BUILD_SYSROOT CONDA_TOOLCHAIN_BUILD \
    CONDA_TOOLCHAIN_HOST CMAKE_PREFIX_PATH CMAKE_ARGS MESON_ARGS \
    CPPFLAGS CFLAGS DEBUG_CFLAGS DEBUG_CPPFLAGS LDFLAGS \
    _CONDA_PYTHON_SYSCONFIGDATA_NAME
pip install git+https://github.com/NVlabs/tiny-cuda-nn/#subdirectory=bindings/torch

echo "========================================"
echo " [6/6] Install SDFStudio"
echo "========================================"
pip install -e .
ns-install-cli

echo "========================================"
echo " Verification"
echo "========================================"
python - <<'PY'
import os
import shutil
import torch

print("CUDA_HOME:", os.environ.get("CUDA_HOME"))
print("nvcc:", shutil.which("nvcc"))
print("torch:", torch.__version__)
print("torch.cuda.is_available():", torch.cuda.is_available())
if torch.cuda.is_available():
    print("torch.cuda.get_device_name(0):", torch.cuda.get_device_name(0))
PY

echo
echo "Environment '${ENV_NAME}' is ready."
echo "Activate it with: conda activate ${ENV_NAME}"
