```
app/
├── api/                       # API 路由相關，依功能子目錄拆分
│   ├── __init__.py
│   ├── recommendation/        # 推薦系統相關路由
│   │   ├── __init__.py
│   │   ├── endpoints.py       # 推薦 API endpoints
│   │   └── schemas.py         # 推薦相關的 Pydantic schema
│   ├── analytics/             # 分析系統相關路由
│   │   ├── __init__.py
│   │   ├── endpoints.py       # 分析 API endpoints
│   │   └── schemas.py
│   ├── chatbot/               # 聊天機器人相關路由
│   │   ├── __init__.py
│   │   ├── endpoints.py
│   │   └── schemas.py
│   └── common/                # 公共路由或共用 API
│       ├── __init__.py
│       ├── endpoints.py
│       └── schemas.py
│
├── core/                      # 核心設定與配置
│   ├── __init__.py
│   ├── config.py              # 環境設定（讀取 .env）
│   ├── security.py            # 認證、授權相關
│   └── logger.py              # 日誌設定
│
├── models/                    # 資料庫 ORM 模型（SQLAlchemy）
│   ├── __init__.py
│   ├── base.py                # Base ORM class
│   ├── user.py
│   ├── resource.py
│   ├── recommendation.py
│   ├── analytics.py
│   └── chatbot.py
│
├── services/                  # 業務邏輯與 AI 服務實作
│   ├── __init__.py
│   ├── recommendation_service.py
│   ├── analytics_service.py
│   ├── chatbot_service.py
│   ├── embedding_service.py   # 向量化模型
│   └── etl_service.py         # 資料同步與 ETL 流程
│
├── utils/                     # 工具函式與共用模組
│   ├── __init__.py
│   ├── db.py                  # 資料庫連線與 session 管理
│   ├── redis_utils.py         # Redis 相關工具
│   ├── qdrant_utils.py        # Qdrant 向量庫操作
│   └── llm_utils.py           # LLM 輔助函式
│
├── workers/                   # 非同步任務工作者 (Celery task 等)
│   ├── __init__.py
│   ├── tasks.py
│   └── celery_app.py
│
├── tests/                     # 測試程式碼
│   ├── __init__.py
│   ├── test_recommendation.py
│   ├── test_analytics.py
│   └── test_chatbot.py
│
├── main.py                    # FastAPI 入口，註冊各路由
├── Dockerfile                 # 建置映像檔
├── docker-compose.yml         # 多服務容器定義
├── requirements.txt
├── .env.example
└── README.md
```

```mermaid
flowchart TB
    %% API Gateway
    A[API Gateway / Proxy]

    %% 後端服務
    subgraph Backends[後端服務]
        direction TB
        B[Recommendation API]
        D[Vector Search API]
        F[Analytics API]
        H[Chatbot Service]
    end

    %% 資料庫
    subgraph Databases[資料層]
        direction TB
        C[(PostgreSQL)]
        E[(Qdrant Vector DB)]
        G[(ClickHouse 分析DB)]
        K[(Redis Cache)]
        I[(LLM - OpenAI 或自建模型)]
    end

    %% 背景任務
    subgraph Workers[背景任務系統]
        J[Celery + Redis]
    end

    %% API Gateway 路由
    A -->|/api/recommendation/*| B
    A -->|/api/search/*| D
    A -->|/api/analytics/*| F
    A -->|/api/chatbot/*| H

    %% 服務與資料庫連接
    B <--> C
    B <--> K
    D <--> E
    D <--> K
    F <--> G
    F <--> C
    H <--> I
    H <--> C
    H <--> K

    %% 背景任務與服務連接
    J -.-> B
    J -.-> D
    J -.-> F
    J -.-> H

```
```mermaid
flowchart LR
  %% 顏色定義
  classDef user fill:#dbeafe,stroke:#3b82f6,color:#1e3a8a
  classDef app fill:#e0f2fe,stroke:#0284c7,color:#0369a1
  classDef auth fill:#fde68a,stroke:#f59e0b,color:#78350f
  classDef data fill:#dcfce7,stroke:#16a34a,color:#065f46
  classDef worker fill:#fcd5ce,stroke:#ef4444,color:#7f1d1d
  classDef obs fill:#f3e8ff,stroke:#8b5cf6,color:#4c1d95
  classDef cicd fill:#fee2e2,stroke:#ef4444,color:#7f1d1d
  classDef event fill:#fef3c7,stroke:#f59e0b,color:#7c2d12

  %% 使用者層
  U[使用者 / 前端<br/>Web / Mobile]:::user -->|HTTPS + Token| AUTH_AUTH[Auth 模組<br/>JWT / OAuth2]:::auth
  AUTH_AUTH -->|驗證成功| LB[Nginx<br/>API Gateway / Load Balancer]:::app

  %% 應用層
  subgraph APP[應用層]
    API[Backend API<br/>FastAPI]:::app
    WORKER[Background Worker<br/>Celery]:::worker
  end
  LB -->|路由請求到 API| API

  %% 資料層
  subgraph DATA[資料層]
    PG[(PostgreSQL)]
    REDIS[(Redis)]
    MINIO[(MinIO)]
    KAFKA[(Kafka)]
  end

  %% API 與資料層連線
  API -->|查詢 / 寫入資料| PG
  API -->|快取 / Session| REDIS
  API -->|檔案存取| MINIO
  API -->|發送事件 Event Publish| KAFKA

  %% Worker 消費事件
  WORKER -->|讀取事件 Event Consumer| KAFKA
  WORKER -->|寫結果 / 更新狀態| PG
  WORKER -->|快取更新| REDIS
  WORKER -->|檔案存取| MINIO

  %% 觀測性
  subgraph OBS[觀測性]
    LOG[Loki<br/>集中日誌]
    MET[Prometheus<br/>Metrics]
    TRACE[Tempo<br/>Tracing]
    GRAF[Grafana + Alertmanager<br/>Dashboard & Alerts]
  end
  API -.->|收集 Logs / Metrics / Trace| LOG
  API -.->|收集 Metrics| MET
  API -.->|收集 Trace| TRACE
  WORKER -.->|收集 Logs / Metrics / Trace| LOG
  WORKER -.->|收集 Metrics| MET
  WORKER -.->|收集 Trace| TRACE
  LOG --> GRAF
  MET --> GRAF
  TRACE --> GRAF

  %% CI/CD + 基礎設施
  subgraph CICD[CI/CD + Infra]
    GIT[Git Repo] --> CI[CI Pipeline<br/>GitHub Actions / GitLab CI]
    CI --> REG[Container Registry]
    REG --> DEPLOY[Deploy: Docker / K8s]
    DEPLOY --> APP
    DEPLOY --> DATA
    DEPLOY --> OBS
    TERRAFORM[Terraform]<-->|管理基礎設施<br/>VM / Network / DB / Redis / Kafka / MinIO| DEPLOY
  end

  %% Kafka 消費者標註
  class KAFKA event

```