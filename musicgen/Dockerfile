# ACE-Step 1.5 for an older NVIDIA card (our GTX 1050 Ti, Pascal, sm_61).
#
# ACE-Step's own image uses PyTorch built for CUDA 12.8, and since PyTorch
# 2.8 those builds no longer contain kernels for Pascal ("no kernel image is
# available for execution on the device"). The CUDA 12.6 builds of the same
# PyTorch version still do, so we install ACE-Step from its lockfile and then
# swap torch, torchvision and torchaudio for the cu126 builds. We start the
# server with the venv's python directly: `uv run` would re-sync the lockfile
# and put the cu128 build back.
#
# Python comes from uv (a download of a few seconds) instead of the deadsnakes
# PPA, which pulled in ~300 apt packages and took over 20 minutes on our server.

FROM nvidia/cuda:12.6.3-runtime-ubuntu22.04

ARG ACESTEP_REF=v0.1.8
ARG TORCH_VERSION=2.10.0
ARG TORCHVISION_VERSION=0.25.0
ARG TORCH_INDEX=https://download.pytorch.org/whl/cu126

ENV DEBIAN_FRONTEND=noninteractive LANG=C.UTF-8 LC_ALL=C.UTF-8 \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git curl ca-certificates libsndfile1 ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7 /uv /uvx /bin/

WORKDIR /app
RUN git clone --depth 1 --branch ${ACESTEP_REF} https://github.com/ace-step/ACE-Step-1.5.git /app

# get_arch_list() is empty during `docker build` (no GPU attached), so check
# the architectures compiled into the wheel instead. An sm_60 kernel also runs
# on our sm_61 card.
RUN uv python install 3.11 \
    && uv sync --frozen --no-dev --python 3.11 \
    && uv pip install --python /app/.venv/bin/python --reinstall \
        "torch==${TORCH_VERSION}" "torchvision==${TORCHVISION_VERSION}" "torchaudio==${TORCH_VERSION}" \
        --index-url ${TORCH_INDEX} \
    && /app/.venv/bin/python -c "import torch; flags = torch._C._cuda_getArchFlags(); print(torch.__version__, flags); assert 'sm_61' in flags or 'sm_60' in flags, 'this torch build has no Pascal kernels'"

RUN mkdir -p /app/checkpoints /app/output

ENV ACESTEP_API_HOST=0.0.0.0 ACESTEP_API_PORT=8001 ACESTEP_LM_BACKEND=pt TOKENIZERS_PARALLELISM=false

EXPOSE 8001
HEALTHCHECK --interval=60s --timeout=10s --start-period=600s --retries=5 \
    CMD curl -sf http://localhost:8001/health > /dev/null || exit 1

# Print what the GPU can do at start, then serve the REST API.
CMD ["sh", "-c", "/app/.venv/bin/python -c \"import torch; print('torch', torch.__version__, 'cuda ok:', torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '', torch.cuda.get_arch_list())\" ; exec /app/.venv/bin/python -m acestep.api_server --host 0.0.0.0 --port 8001"]
