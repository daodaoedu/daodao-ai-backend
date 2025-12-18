# ====== 第一階段：建構依賴環境 ======
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# 複製依賴宣告
COPY pyproject.toml uv.lock ./

# 環境變數優化
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1

# ⭐ 關鍵步驟：先安裝 CPU-only PyTorch
# 這會強制 sentence-transformers 使用 CPU 版本
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install \
    torch==2.9.1+cpu \
    torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# 然後安裝其他生產依賴
# uv 會尊重已安裝的 torch 版本
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    uv sync --frozen --no-dev --no-install-project

# ====== 第二階段：最終執行鏡像 ======
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# 環境變數設定
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    TZ=Asia/Taipei \
    PATH="/app/.venv/bin:$PATH"

# 建立非 root 使用者（安全最佳實踐）
RUN groupadd -r appuser && \
    useradd -r -g appuser -u 1000 appuser && \
    mkdir -p /app && \
    chown -R appuser:appuser /app

# 只複製虛擬環境和原始碼
COPY --from=builder --chown=appuser:appuser /app/.venv /app/.venv
COPY --chown=appuser:appuser src /app/src

# 切換到非特權使用者
USER appuser

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/ping/health', timeout=5)" || exit 1

# 開放連接埠
EXPOSE 8000

# 啟動命令
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
