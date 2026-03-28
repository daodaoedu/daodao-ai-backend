# Feature Pipeline & Service 架構

## API Endpoints

| Router | Endpoint | 功能 | 快取 TTL |
|--------|----------|------|---------|
| users | `GET /v1/users/practices` | 實踐貼文列表（搜尋/篩選/排序） | 120s |
| users | `GET /v1/users/practices/suggestions` | 搜尋關鍵字建議 | 600s |
| users | `GET /v1/users/practices/completions` | 文字補全 | 300s |
| users | `GET /v1/users/insights` | 精選洞察列表 | 300s |
| feed | `GET /v1/feed` | 統一 Feed（practice + checkin 混合） | 120s |
| recommendation | `GET /v1/recommendation/rank_feed` | 個人化推薦 Feed | 60s |
| feedback | `POST /v1/feedback/generate` | AI 回饋生成（非同步） | — |
| feedback | `GET /v1/feedback/status/{task_id}` | 查詢回饋生成狀態 | — |
| ping | `GET /v1/ping` / `GET /v1/health` | 健康檢查 | — |

---

## Services

| Service | 檔案 | 職責 |
|---------|------|------|
| **PracticeService** | `services/practice/practice.py` | 多維查詢/搜尋/推薦排序 |
| **FeedService** | `services/feed/feed_service.py` | UNION 混合 Feed + 批量 N+1 防護 |
| **FeedRankingService** | `services/feed/feed_ranking.py` | 社群圖 × 參與度 × 時間衰減 評分 |
| **RecommendationService** | `services/practice/recommendation.py` | 內容 + 行為 + 時間衰減 混合排名 |
| **InsightService** | `services/insight/insight_service.py` | 打卡統計分析 → Prompt 組合 → LLM 洞察生成 |
| **InsightScheduler** | `services/insight/insight_scheduler.py` | APScheduler 每日 01:00 UTC 觸發 |
| **FeedbackService** | `services/feedback.py` | Review/Project 上下文準備 → RAG Prompt → LLM |
| **LLMClient** | `services/llm/client.py` | OpenAI / Gemini / Anthropic / Ollama 統一介面 |
| **CacheClient** | `services/cache/client.py` | Redis TTL 快取管理 |

---

## Pipeline 詳解

### A. 實踐查詢

```
GET /v1/users/practices
  └─ PracticeService.get_practices()
      ├─ 查詢 User (external_id → internal id)
      ├─ 基礎查詢（keyword ILIKE、status 過濾）
      ├─ 套用篩選（tags, duration, privacy）
      ├─ 排序（newest / oldest / recommended）
      │   └─ recommended → RecommendationService
      │       └─ 評分 = Content + Behavior + TimeDecay
      ├─ 批量取 Reactions（GROUP BY）
      ├─ Cursor-based 分頁
      ├─ Redis 快取（120s）
      └─ Response
```

### B. 統一 Feed

```
GET /v1/feed
  └─ FeedService.get_feed()
      ├─ 解析遊標（cursor_time, cursor_id）
      ├─ UNION 查詢
      │   ├─ Practices（public, active/completed）
      │   └─ Checkins（JOIN practices）
      ├─ ORDER BY sort_time DESC, item_id DESC → 分頁取 limit+1
      ├─ 批量查詢（3 個並行）
      │   ├─ _batch_fetch_practices()
      │   ├─ _batch_fetch_checkins()
      │   ├─ _batch_fetch_reactions()
      │   └─ _batch_fetch_comments()
      ├─ [登入 + RECOMMENDED] FeedRankingService 重排
      │   └─ Score = 0.35×Social + 0.30×Engagement + 0.15×Content + 0.20×TimeDecay
      ├─ Redis 快取（120s，登入用戶）
      └─ Response（items + next_cursor）
```

**FeedRankingService 評分公式**：

```
SocialSignal    = Connected(1.0) | Following_Practice(0.8)
                  | Following_User(0.6) | Interaction_Count×0.1
EngagementSignal = (reactions + comments×2) / max(age_days, 1)
ContentSignal   = tag_match + description_quality
TimeDecay       = 1 / (1 + log(1 + days))
```

### C. 精選洞察（排程自動化）

```
App Startup → InsightScheduler.start() → APScheduler 初始化

每日 01:00 UTC
  └─ InsightScheduler._run_job()
      ├─ get_pending_practices()
      │   └─ SELECT WHERE status='completed' AND insight IS NULL
      └─ FOR EACH practice:
          ├─ get_checkins_for_practice()
          ├─ _analyze_checkins()
          │   ├─ total 打卡次數
          │   ├─ max_streak（最長連續天數）
          │   ├─ top_weekdays（最常打卡日）
          │   ├─ mood_summary（心情分布）
          │   └─ notable_notes（情緒強烈筆記，最多 2 條）
          ├─ _build_prompt() → system prompt + 統計摘要 + 用戶數據
          ├─ LLMClient.generate()（max_tokens=600）
          └─ practice.insight = output, db.commit()（冪等）

App Shutdown → InsightScheduler.stop()
```

> 手動觸發：`python scripts/run_insight_job.py --backend openai`

### D. AI 回饋生成

```
POST /v1/feedback/generate
  ├─ JWT 驗證（UserDep）
  └─ BackgroundTask（非同步）
      ├─ Redis 設 status=pending
      ├─ prepare_feedback_context()
      │   ├─ 查詢 Review → Post → Project
      │   ├─ get_project_data()（項目詳情）
      │   ├─ get_milestones_data()（里程碑）
      │   ├─ get_tasks_stats()（任務統計）
      │   ├─ get_review_trends()（歷史覆盤）
      │   ├─ 查詢 Outcomes（圖片/影片）
      │   └─ RAGPromptBuilder.create_rag_prompt()
      ├─ LLMClient.generate()
      ├─ AIReviewFeedback 寫入 DB
      └─ Redis 更新 status=done + content

GET /v1/feedback/status/{task_id}
  └─ 輪詢 Redis → 回傳 pending / done + content
```

### E. 推薦排名 Feed

```
GET /v1/recommendation/rank_feed
  └─ rank_feed.get_feed()
      ├─ UNION query（idea / practice / project）
      ├─ 評分
      │   └─ Score = base_score + 1/log(days+1) + resource_count + streak + progress
      ├─ 排序取前 limit 筆 → FeedInfo(id, type, score)
      └─ rank_feed.get_posts()
          ├─ 批量載入完整內容
          ├─ 聚合 Resources / User / Tags
          ├─ 轉換為 BasePost 格式
          ├─ Redis 快取（60s）
          └─ Response
```

---

## LLM 多後端

| Backend | SDK | 設定鍵 |
|---------|-----|--------|
| OpenAI | `openai` AsyncOpenAI | `LLM_BACKEND__OPENAI__*` |
| Gemini | `google-genai` | `LLM_BACKEND__GEMINI__*` |
| Anthropic | `anthropic` AsyncAnthropic | `LLM_BACKEND__ANTHROPIC__*` |
| Ollama | httpx（本地） | `LLM_BACKEND__OLLAMA__*` |

切換方式：`INSIGHT__LLM_BACKEND=openai` 或 `--backend openai`

---

## 快取策略

所有快取在 Router 層實作，失效時自動降級至 DB。

| 端點 | TTL | Key 組成 |
|------|-----|---------|
| `/practices` | 120s | `user_id:filters:cursor` |
| `/feed` | 120s | `user_id:filters:sort:cursor` |
| `/insights` | 300s | `user_id:limit:offset` |
| `/suggestions` | 600s | `user_id:keyword` |
| `/completions` | 300s | `user_id:prefix` |
| `/rank_feed` | 60s | `user_id:cursor` |

---

## 依賴注入

| Dependency | 說明 |
|-----------|------|
| `SessionDep` | SQLAlchemy ORM Session |
| `UserDep` | JWT 驗證（optional，支援匿名） |
| `CacheDep` | Redis CacheClient |
| `SettingsDep` | 全局設定 |
