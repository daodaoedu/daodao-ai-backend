# DaoDao AI Backend

DaoDao AI Backend 是島島教育平台的後端服務，提供 AI 增強的教育功能，包含推薦系統、實踐追蹤與 LLM 整合。

## 專案結構

```
src/
├── routers/        # FastAPI 路由層（users, recommendation, ping）
├── middleware/     # 中介層（JWT 驗證、速率限制）
├── models/         # SQLAlchemy ORM 模型（對應 daodao-storage schema）
├── schemas/        # Pydantic request / response 資料結構
├── services/       # 業務邏輯
│   ├── practice/   # 實踐查詢、推薦邏輯
│   ├── cache/      # Redis 快取
│   ├── llm/        # LLM 整合
│   ├── qdrant/     # 向量搜尋
│   └── clickhouse/ # 分析資料庫
├── db/             # 資料庫連線
├── utils/          # 共用工具函數
└── config.py       # 設定（pydantic-settings）
```

## 🧩 系統架構

```mermaid
flowchart TD
    U[👩‍💻 使用者 / 前端應用] -->|HTTP / JSON| API[🌐 FastAPI API 層]
    API --> SVC[⚙️ Service 層]
    API --> MID[🧱 Middleware / 驗證 / 限流]
    SVC --> Repo[💾 Repository 層]
    SVC --> LLM[🧠 LLM / 推薦引擎]
    SVC --> Cache[🚀 Redis 快取]
    Repo --> DB[(🗄️ PostgreSQL)]
    Repo --> VecDB[📚 Qdrant 向量庫]
    SVC --> CH[📈 ClickHouse 分析]
```

## 環境要求

- Python 3.10+（推薦 3.12）
- [uv](https://docs.astral.sh/uv/) — 套件管理
- Docker / Docker Compose
- PostgreSQL（主資料庫）
- Redis（快取 / 限流）
- Qdrant（向量搜尋）

## 快速開始

1. 克隆專案
```bash
git clone https://github.com/daodaoedu/daodao-ai-backend.git
cd daodao-ai-backend
```

2. 安裝依賴
```bash
uv sync
```

3. 配置環境變數
```bash
cp .env.dev .env
# 編輯 .env，設定資料庫、Redis、API key 等參數
```

4. 安裝 pre-commit hooks（確保 commit 前自動格式化）
```bash
uvx pre-commit install
```

5. 使用 Docker 啟動服務
```bash
# 開發環境
make up-dev

# 正式環境
make up-prod
```

## 開發指南

### 常用指令

| 指令 | 說明 |
|------|------|
| `make up-dev` | 啟動開發環境 |
| `make down-dev` | 停止開發環境 |
| `make rebuild-dev` | 重建開發環境 |
| `make format` | 格式化程式碼（black + ruff） |
| `make check` | 檢查格式（不修改） |
| `make lint` | 靜態分析（pylint + bandit） |
| `make quality_checks` | format + lint 一鍵執行 |

### 程式碼規範

- 格式化工具：`black 25.9.0`、`ruff`
- commit 前 pre-commit hook 會自動執行 black，確保格式一致
- CI 會執行 `make check` 驗證格式，格式錯誤會擋住 merge

### 資料模型說明

- `src/models/` 下的資料模型需要與 [daodao-storage](https://github.com/daodaoedu/daodao-storage) 倉庫的 schema 保持一致
- 新增或修改模型時，請確保同步更新兩個倉庫

## API 文件

服務啟動後可訪問：
- Swagger UI：http://localhost:8002/docs
- ReDoc：http://localhost:8002/redoc

## 授權條款

本專案採用 MIT 授權條款 - 查看 [LICENSE](LICENSE) 檔案瞭解詳情
