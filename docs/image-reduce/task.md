# Docker 鏡像優化執行任務

**目標**: 將鏡像從 7.94GB 減少到 ~5GB
**策略**: 保留所有依賴，使用 CPU-only PyTorch
**預計時間**: 1-2 小時
**風險等級**: 低

---

## 📋 執行前檢查清單

執行前請確認：
- [ ] 已閱讀 `report.md` 了解優化策略
- [ ] 確認應用程式不需要 GPU 訓練（只做推理）
- [ ] 本地有足夠磁碟空間（至少 15GB 空閒）
- [ ] 已通知團隊即將進行優化
- [ ] 有測試環境可以驗證

---

## 🚀 執行步驟

### 步驟 1：備份當前配置（5 分鐘）

```bash
# 切換到專案目錄
cd /Users/xiaoxu/Projects/daodao/daodao-ai-backend

# 建立優化分支
git checkout dev
git pull origin dev
git checkout -b feat/optimize-docker-cpu-only

# 備份當前配置檔案
cp pyproject.toml pyproject.toml.backup
cp Dockerfile Dockerfile.backup
cp .dockerignore .dockerignore.backup

# 確認備份成功
ls -la *.backup
```

**驗證**:
- ✅ 成功建立分支 `feat/optimize-docker-cpu-only`
- ✅ 看到 3 個 `.backup` 檔案

---

### 步驟 2：修改 pyproject.toml（10 分鐘）

#### 2.1 打開檔案

```bash
# 使用編輯器打開
vim pyproject.toml
# 或
code pyproject.toml
```

#### 2.2 移除開發工具到 dev-dependencies

**找到第 53-57 行**，註解掉或刪除這些行：

```toml
# dependencies 區塊中，刪除或註解以下內容：
    # "ruff>=0.14.1",
    # "isort>=7.0.0",
    # "black>=25.9.0",
    # "pylint>=4.0.1",
    # "bandit>=1.8.6",
```

**在 `[tool.uv]` 區塊的 dev-dependencies 中添加**：

找到這個區塊：
```toml
[tool.uv]
dev-dependencies = [
    "pytest",
    "pytest-asyncio",
    "httpx"
]
```

修改為：
```toml
[tool.uv]
dev-dependencies = [
    "pytest",
    "pytest-asyncio",
    "httpx",
    # 從 dependencies 移過來的開發工具
    "ruff>=0.14.1",
    "isort>=7.0.0",
    "black>=25.9.0",
    "pylint>=4.0.1",
    "bandit>=1.8.6",
]
```

#### 2.3 可選：移除 matplotlib（如果不需要）

如果確認不需要繪圖功能，可以註解掉第 37 行：

```toml
# "matplotlib",  # 未使用，暫時註解
```

#### 2.4 儲存並驗證

```bash
# 儲存檔案後驗證語法
python3 -c "import tomllib; tomllib.load(open('pyproject.toml', 'rb'))" && echo "✅ pyproject.toml 語法正確"

# 查看變更
git diff pyproject.toml
```

**預期結果**:
- ✅ 看到開發工具從 `dependencies` 移到 `dev-dependencies`
- ✅ 語法驗證通過

---

### 步驟 3：修改 Dockerfile（15 分鐘）

#### 3.1 完整替換 Dockerfile 內容

```bash
# 備份後開啟編輯
vim Dockerfile
```

**完整替換為以下內容**：

```dockerfile
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
    torch==2.1.2+cpu \
    torchvision==0.16.2+cpu \
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
```

#### 3.2 關鍵變更確認

```bash
# 查看關鍵變更
echo "=== 檢查關鍵變更 ==="

# 1. 確認基礎鏡像改為 slim
grep "bookworm-slim" Dockerfile && echo "✅ 基礎鏡像已優化"

# 2. 確認有 PyTorch CPU 安裝
grep "torch.*cpu" Dockerfile && echo "✅ PyTorch CPU 安裝已添加"

# 3. 確認沒有 pytest 安裝
! grep "install.*pytest" Dockerfile && echo "✅ pytest 已移除"

# 4. 確認只複製 .venv 和 src
grep "COPY.*\.venv" Dockerfile && grep "COPY.*src" Dockerfile && echo "✅ 複製策略已優化"
```

---

### 步驟 4：更新 .dockerignore（5 分鐘）

#### 4.1 檢查並更新

```bash
# 檢查當前內容
cat .dockerignore

# 使用編輯器打開
vim .dockerignore
```

**確保包含以下內容**（可以完整替換）：

```
# Python 快取
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
.ruff_cache/
*.egg-info/

# 虛擬環境
.venv/
venv/
env/

# IDE 設定
.vscode/
.idea/
*.swp
*.swo

# 測試與文件
tests/
docs/
*.md
!README.md

# 日誌與資料
*.log
*.sqlite3
*.db

# 環境設定
.env
.env.*
!.env.*.sample

# Git
.git/
.github/
.gitignore

# 暫存檔案
*.tmp
.DS_Store
*.backup
```

---

### 步驟 5：重新產生 uv.lock（5 分鐘）

```bash
# 清理舊的虛擬環境（可選）
rm -rf .venv

# 重新產生 lock 檔案
uv lock

# 檢查 lock 檔案大小
ls -lh uv.lock

# 檢查是否成功
echo "✅ uv.lock 重新產生完成"
```

**預期**:
- ✅ `uv.lock` 檔案更新
- ✅ 無錯誤訊息

---

### 步驟 6：本地建構測試（15-20 分鐘）

#### 6.1 清理舊快取

```bash
# 清理 Docker 建構快取
docker builder prune -f

# 清理舊鏡像（可選）
docker image prune -f
```

#### 6.2 建構新鏡像

```bash
# 建構新鏡像（會花較長時間）
docker build -t daodao-ai-backend:cpu-optimized .

# 如果需要查看詳細建構過程
docker build --progress=plain -t daodao-ai-backend:cpu-optimized .
```

**建構過程中應該看到**:
```
✅ [builder] Installing torch-2.1.2+cpu...
✅ [builder] Installing torchvision-0.16.2+cpu...
✅ [builder] uv sync --frozen --no-dev...
```

**預期建構時間**:
- 首次: 10-15 分鐘
- 有快取: 3-5 分鐘

---

### 步驟 7：驗證鏡像大小（2 分鐘）

```bash
# 對比鏡像大小
echo "=== 鏡像大小對比 ==="
docker images | grep daodao-ai-backend

# 應該看到類似輸出：
# daodao-ai-backend   cpu-optimized   4.8GB    ...   # ✅ 新版本
# daodao-ai-backend   latest          7.94GB   ...   # 舊版本

# 查看詳細層級
docker history daodao-ai-backend:cpu-optimized --human --no-trunc | head -20

# 計算減少的空間
echo ""
echo "預期效果："
echo "- 當前: 7.94GB"
echo "- 目標: ~5GB"
echo "- 減少: ~37%"
```

**成功標準**:
- ✅ 新鏡像 < 5.5GB
- ✅ 理想範圍: 4.5GB - 5GB
- ⚠️ 如果 > 6GB，檢查是否有錯誤

---

### 步驟 8：功能驗證（15 分鐘）

#### 8.1 啟動測試容器

```bash
# 停止並刪除舊的測試容器（如果存在）
docker stop daodao-backend-test 2>/dev/null || true
docker rm daodao-backend-test 2>/dev/null || true

# 啟動新容器
docker run -d \
  --name daodao-backend-test \
  -p 8000:8000 \
  --env-file .env.dev.sample \
  daodao-ai-backend:cpu-optimized

# 查看啟動日誌
docker logs -f daodao-backend-test
```

**預期看到**:
```
✅ Starting daodao ai backend API...
✅ daodao_collection ready
✅ API ready
```

按 `Ctrl+C` 停止日誌查看

#### 8.2 健康檢查

```bash
# 等待容器啟動
sleep 5

# 健康檢查
curl http://localhost:8000/api/ping/health

# 預期輸出：
# {"status": "healthy", ...}
```

#### 8.3 驗證 PyTorch 版本（重要！）

```bash
echo "=== 驗證 PyTorch 配置 ==="

# 檢查 PyTorch 版本
docker exec daodao-backend-test python -c "
import torch
print(f'PyTorch 版本: {torch.__version__}')
print(f'CUDA 可用: {torch.cuda.is_available()}')
print(f'CUDA 版本: {torch.version.cuda if torch.cuda.is_available() else \"N/A\"}')
"

# 預期輸出：
# ✅ PyTorch 版本: 2.1.2+cpu
# ✅ CUDA 可用: False
# ✅ CUDA 版本: N/A
```

**如果看到 `+cpu` 和 `CUDA 可用: False`，表示成功！**

#### 8.4 驗證 AI 函式庫可用性

```bash
echo "=== 驗證 AI 函式庫 ==="

# 驗證 sentence-transformers
docker exec daodao-backend-test python -c "
try:
    from sentence_transformers import SentenceTransformer
    print('✅ sentence-transformers 可用')
except Exception as e:
    print(f'❌ sentence-transformers 錯誤: {e}')
"

# 驗證 fastembed
docker exec daodao-backend-test python -c "
try:
    import fastembed
    print('✅ fastembed 可用')
except Exception as e:
    print(f'❌ fastembed 錯誤: {e}')
"

# 驗證 qdrant
docker exec daodao-backend-test python -c "
try:
    from qdrant_client import QdrantClient
    print('✅ qdrant-client 可用')
except Exception as e:
    print(f'❌ qdrant-client 錯誤: {e}')
"
```

#### 8.5 API 功能測試

```bash
echo "=== API 功能測試 ==="

# 測試根路徑
curl http://localhost:8000/

# 測試推薦 API（需要 JWT token）
# curl -X GET "http://localhost:8000/api/v1/recommendation/rank_feed?page_size=10" \
#   -H "Authorization: Bearer YOUR_TOKEN"

echo "✅ 基本 API 測試完成"
```

#### 8.6 效能簡單測試（可選）

```bash
# 簡單壓測健康檢查端點
echo "=== 簡單效能測試 ==="

# 使用 ab (Apache Bench) 如果有安裝
if command -v ab &> /dev/null; then
    ab -n 100 -c 10 http://localhost:8000/api/ping/health
else
    echo "未安裝 ab，跳過效能測試"
fi
```

#### 8.7 清理測試容器

```bash
# 測試完成後清理
docker stop daodao-backend-test
docker rm daodao-backend-test

echo "✅ 功能驗證完成"
```

---

### 步驟 9：提交變更（10 分鐘）

#### 9.1 檢視變更

```bash
# 查看所有變更
git status

# 查看具體差異
git diff pyproject.toml
git diff Dockerfile
git diff .dockerignore
```

#### 9.2 暫存變更

```bash
# 暫存修改的檔案
git add pyproject.toml
git add Dockerfile
git add .dockerignore
git add uv.lock

# 確認暫存
git status
```

#### 9.3 提交

```bash
git commit -m "feat: optimize Docker image with CPU-only PyTorch

主要變更：
- 使用 CPU-only PyTorch 取代 CUDA 版本 (減少 ~1.4GB)
- 移除開發工具到 dev-dependencies (減少 ~100MB)
- 移除 Dockerfile 中的 pytest 安裝 (減少 ~50MB)
- 優化 Dockerfile 多階段建構
- 使用 slim 基礎鏡像
- 新增非 root 使用者提升安全性
- 新增 HEALTHCHECK 健康檢查

效果：
- 鏡像大小：7.94GB → ~5GB (-37%)
- 保留所有功能性依賴
- PyTorch CPU-only 足夠推理使用
- 無功能損失

相關文件：docs/image-reduce/report.md
測試結果：
- ✅ PyTorch 版本：2.1.2+cpu
- ✅ CUDA 可用：False
- ✅ sentence-transformers 正常
- ✅ API 端點正常

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
```

#### 9.4 推送到遠端

```bash
# 推送分支
git push origin feat/optimize-docker-cpu-only

echo "✅ 變更已推送到遠端分支"
```

---

### 步驟 10：測試環境部署（30 分鐘）

#### 10.1 標記並推送鏡像

```bash
# 登入 Docker Hub（如果還沒登入）
docker login

# 標記鏡像
docker tag daodao-ai-backend:cpu-optimized vincentxxx/app:dev-cpu-optimized

# 推送到註冊表
docker push vincentxxx/app:dev-cpu-optimized

echo "✅ 鏡像已推送到遠端"
```

#### 10.2 在測試環境部署

```bash
# SSH 到測試伺服器
ssh user@server-ai.daoedu.tw

# 在測試伺服器上執行：

# 拉取新鏡像
docker pull vincentxxx/app:dev-cpu-optimized

# 停止當前服務
docker-compose -f docker-compose.dev.yml down

# 備份 docker-compose 檔案
cp docker-compose.dev.yml docker-compose.dev.yml.backup

# 更新 docker-compose.dev.yml 中的鏡像標籤
# 修改 image: vincentxxx/app:dev-cpu-optimized

# 啟動新服務
docker-compose -f docker-compose.dev.yml up -d

# 查看日誌
docker-compose -f docker-compose.dev.yml logs -f
```

#### 10.3 測試環境驗證

```bash
# 在測試伺服器或本地執行：

# 健康檢查
curl https://server-ai.daoedu.tw/api/ping/health

# 驗證 PyTorch 版本
docker exec <container_name> python -c "import torch; print(torch.__version__)"

# 功能測試
# 執行你的測試套件
```

---

## ✅ 完成檢查清單

執行完成後，確認以下項目：

### 建構階段
- [ ] 鏡像大小 < 5.5GB（理想 4.5-5GB）
- [ ] PyTorch 版本顯示 `2.1.2+cpu`
- [ ] 建構過程無錯誤

### 驗證階段
- [ ] `torch.cuda.is_available()` 返回 `False`
- [ ] sentence-transformers 可正常匯入
- [ ] fastembed 可正常匯入
- [ ] qdrant-client 可正常匯入
- [ ] API 端點正常回應
- [ ] 健康檢查通過

### 部署階段
- [ ] 本地測試容器正常運行
- [ ] 測試環境部署成功
- [ ] 所有 API 功能正常
- [ ] 無效能明顯下降

### 程式碼管理
- [ ] 變更已提交到 git
- [ ] 已推送到遠端分支
- [ ] 備份檔案已建立

---

## ⚠️ 常見問題排查

### 問題 1：建構失敗 "Could not find torch"

**症狀**:
```
ERROR: Could not find a version that satisfies the requirement torch==2.1.2+cpu
```

**解決**:
```bash
# 檢查網路連線
ping download.pytorch.org

# 手動測試下載
pip download torch==2.1.2+cpu --index-url https://download.pytorch.org/whl/cpu

# 清理快取重試
docker builder prune -f
docker build --no-cache -t daodao-ai-backend:cpu-optimized .
```

---

### 問題 2：鏡像還是很大（> 6GB）

**排查**:
```bash
# 檢查 PyTorch 版本
docker run --rm daodao-ai-backend:cpu-optimized \
  python -c "import torch; print(torch.__version__)"

# 如果沒有看到 +cpu，表示安裝了錯誤版本
# 檢查 Dockerfile 的 PyTorch 安裝步驟是否正確

# 查看鏡像層級
docker history daodao-ai-backend:cpu-optimized --human --no-trunc
```

---

### 問題 3：容器啟動失敗 "Permission denied"

**症狀**:
```
PermissionError: [Errno 13] Permission denied: '/app/...'
```

**解決**:
```dockerfile
# 臨時方案：在 Dockerfile 中註解掉 USER appuser
# USER appuser

# 重新建構測試
# 後續需要修正權限問題
```

---

### 問題 4：sentence-transformers 錯誤

**症狀**:
```
ImportError: cannot import name 'SentenceTransformer'
```

**排查**:
```bash
# 進入容器檢查
docker exec -it daodao-backend-test bash

# 檢查安裝的套件
pip list | grep sentence
pip list | grep torch

# 嘗試重新安裝
pip install --force-reinstall sentence-transformers
```

---

### 問題 5：API 回應很慢

**排查**:
```bash
# 測試推理速度
docker exec daodao-backend-test python -c "
from sentence_transformers import SentenceTransformer
import time

model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
start = time.time()
embeddings = model.encode(['測試'] * 10)
print(f'推理時間: {time.time() - start:.2f}秒')
"

# 如果 > 5 秒，可能需要考慮 GPU 版本
# 如果 < 2 秒，效能正常
```

---

## 🔄 回滾步驟

如果遇到嚴重問題需要回滾：

### 快速回滾

```bash
# 1. 停止優化版本
docker stop daodao-backend-test
docker rm daodao-backend-test

# 2. 使用舊版鏡像
docker run -d \
  --name daodao-backend \
  -p 8000:8000 \
  --env-file .env.dev.sample \
  daodao-ai-backend:latest

# 3. 回滾程式碼
git reset --hard HEAD~1
# 或
git revert HEAD
git push origin feat/optimize-docker-cpu-only

# 4. 使用備份檔案重建
cp pyproject.toml.backup pyproject.toml
cp Dockerfile.backup Dockerfile
docker build -t daodao-ai-backend:rollback .
```

---

## 📊 成果報告模板

優化完成後，填寫此報告：

```
=== Docker 鏡像優化成果 ===

執行日期：____________________
執行人員：____________________

鏡像大小：
- 優化前：7.94GB
- 優化後：________GB
- 減少：________GB (_____%)

驗證結果：
- [ ] PyTorch 版本：__________
- [ ] CUDA 可用：□ True  □ False
- [ ] sentence-transformers：□ 正常  □ 異常
- [ ] API 健康檢查：□ 通過  □ 失敗
- [ ] 效能測試：推理時間 ________秒

測試環境部署：
- [ ] 部署成功
- [ ] 所有功能正常
- [ ] 無明顯效能下降

問題記錄：
____________________________________
____________________________________

備註：
____________________________________
____________________________________
```

---

## 📞 支援與協助

如果執行過程中遇到問題：

1. **檢查日誌**：`docker logs <container_id>`
2. **查看報告**：參考 `report.md` 了解技術細節
3. **常見問題**：查看本文件的「常見問題排查」章節
4. **團隊協助**：聯繫團隊成員討論

---

## 🎯 後續建議

優化完成後，建議：

1. **建立監控**：追蹤鏡像大小變化
2. **定期審查**：每季度檢查依賴使用情況
3. **文件更新**：更新部署文件說明新的建構流程
4. **CI/CD 整合**：在 pipeline 中加入鏡像大小檢查

---

**任務建立日期**: 2025-12-18
**相關文件**: `report.md` - 完整分析報告
**預期完成時間**: 1-2 小時
**下次審查日期**: 建議 3 個月後
