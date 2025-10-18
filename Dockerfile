# ====== 第一階段：建立依賴環境 ======
FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS base

WORKDIR /app

# 複製依賴宣告
# 如果你還沒改用 pyproject.toml，可以用 requirements.txt 直接安裝
COPY pyproject.toml uv.lock ./


# 設定 UV 環境變數
# UV_LINK_MODE=copy 避免跨檔案系統硬連結錯誤
# UV_COMPILE_BYTECODE=1 可預編譯 .pyc 加快啟動
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# 安裝正式依賴（這裡模擬 pip 安裝）
# 如果你已改用 pyproject.toml + uv.lock，則可改成 uv sync

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=/app/uv.lock \
    --mount=type=bind,source=pyproject.toml,target=/app/pyproject.toml \
    uv sync --frozen --no-dev

# 安裝測試依賴（可視情況移除）
RUN uv pip install --system pytest

# 複製應用程式原始碼
COPY src /app/src


# ====== 第二階段：最終可執行映像 ======
FROM python:3.12-slim AS final

WORKDIR /app

# 建議固定時區與環境設定
ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TZ=Asia/Taipei

# 複製整個應用程式與已安裝依賴
COPY --from=base /app /app

# 開放預設埠（若是 FastAPI / Flask 可開）
EXPOSE 8000

# Add virtual environment to PATH
ENV PATH="/app/.venv/bin:$PATH"


# 預設啟動命令
# CMD ["python", "-m", "src.app.main"]
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
