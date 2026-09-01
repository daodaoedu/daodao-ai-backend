# Spec: 靈感頁後端測試（12.1–12.8）

Issue: daodaoedu/daodao-ai-backend#42  
Change: showcase-and-search  
Subprojects: daodao-ai-backend（12.1–12.2、12.5–12.8）、daodao-server（12.3–12.4）

---

## 背景

`practices` 資料表新增 `privacy_status` 欄位（`private` / `public` / `delayed`）。  
「Brewing Card」分流邏輯：`privacy_status = 'delayed' AND status = 'active'` 時，`is_brewing = true`，打卡心得不公開，也不納入搜尋索引。  
搜尋使用 PostgreSQL ILIKE（Phase 1）。

---

## 12.1 單元測試：`get_practices()` — delayed+active 不回傳打卡內容（Brewing Card）

**Target**: `PracticeService._build_base_query()` (`src/services/practice/practice.py` 行 405–418)  
**Test type**: pytest + MagicMock（與 `tests/services/test_practice_service.py` 相同模式）

### 測試設計

```
前置條件
  Practice P1: privacy_status='delayed', status='active'
  CheckIn C1: practice_id=P1.id, note='我的秘密學習計畫'
  P1 的其他欄位（title / practice_action）均不含關鍵字

操作
  PracticeService.get_practices(db, user_external_id=None, keyword='秘密學習計畫')

預期結果
  回傳列表不含 P1
  （checkin_exists subquery 的 ~(delayed AND active) 條件排除此筆打卡）
```

### 關鍵程式碼

```python
# src/services/practice/practice.py
checkin_exists = (
    select(PracticeCheckIn.id)
    .where(
        PracticeCheckIn.practice_id == Practice.id,
        PracticeCheckIn.note.ilike(pattern),
        ~(
            (Practice.privacy_status == PracticePrivacyStatus.DELAYED.value)
            & (Practice.status == PracticeStatus.ACTIVE.value)
        ),
    )
    .correlate(Practice)
    .exists()
)
```

### 測試文件路徑
`tests/services/test_practice_service_brewing.py`

---

## 12.2 單元測試：`get_practices()` — delayed+completed 回傳完整打卡內容（Full Access Card）

**Target**: 同 12.1（`_build_base_query()` 的 `checkin_exists`）

### 測試設計

```
前置條件
  Practice P2: privacy_status='delayed', status='completed'
  CheckIn C2: practice_id=P2.id, note='完成後的完整心得'
  P2 的 title / practice_action 均不含關鍵字

操作
  PracticeService.get_practices(db, user_external_id=None, keyword='完整心得')

預期結果
  回傳列表包含 P2
  （completed 不屬於 brewing，~(delayed AND active) 不排除，checkin note 可被搜尋）
  P2 的 is_brewing 欄位在 feed 層應為 false（by _batch_fetch_practices 邏輯）
```

### 測試文件路徑
`tests/services/test_practice_service_brewing.py`（與 12.1 同檔）

---

## 12.3 單元測試：`toggleLike` — 同 (target_type, target_id, user_id) 重複呼叫為 toggle（daodao-server）

**Backend**: daodao-server  
**Target**: `PracticeInteractionService.toggleLike()` (`practice-interaction.service.ts`)  
**Test type**: Jest / Vitest + mock Prisma / TypeORM

### 測試設計

```
前置條件
  user_id=U1, target_type='practice', target_id=P1
  reactions 表無任何資料

操作序列
  1. toggleLike(target_type, target_id, U1, reactionType='encourage')
  2. toggleLike(target_type, target_id, U1, reactionType='encourage')
  3. toggleLike(target_type, target_id, U1, reactionType='encourage')

預期結果
  呼叫 1：reaction 建立（count=1）
  呼叫 2：reaction 刪除（count=0）—— toggle 效果，不重複計數
  呼叫 3：reaction 再建立（count=1）

驗證
  資料庫中 (target_type, target_id, U1) 最多只存在一筆 reaction
  IReactionCount.count 與 DB 一致
```

### 迴歸測試

```
不同使用者對同一 target 反應互不影響：
  U1 toggleLike → 建立
  U2 toggleLike → 建立（兩筆獨立，count=2）
  U1 toggleLike → 刪除（count=1，只影響 U1 那筆）
```

---

## 12.4 單元測試：reaction notification worker — 擁有者對自己的練習反應時不發通知（daodao-server）

**Backend**: daodao-server  
**Target**: `reaction-notification.worker.ts`  
**Test type**: Jest / Vitest + mock job queue

### 測試設計

```
前置條件
  Practice P1: owner_user_id = U1
  Reactor: U1（同一人）

操作
  Worker 處理 reaction event { practice_id: P1.id, reactor_user_id: U1 }

預期結果
  通知 job 未被加入 queue
  （條件：reactor_user_id === practice.owner_user_id → skip）

迴歸：他人反應正常發送
  Reactor: U2（不同人）
  Worker 處理 { practice_id: P1.id, reactor_user_id: U2 }
  → 通知 job 加入 queue，延遲 1 小時，job ID = practice_id（合併）
```

---

## 12.5 整合測試：搜尋隱私安全 — delayed+active 打卡心得不出現在搜尋結果

**Target**: `GET /api/v1/users/practices?keyword=...`  
**Test type**: pytest + TestClient + 測試用 DB（或 factory fixtures）

### 測試設計

```
前置條件
  建立 Practice P: privacy_status='delayed', status='active', title='日常練習', practice_action='持續中'
  建立 CheckIn C: practice_id=P.id, note='KEYWORD_12_5_UNIQUE_私密心得'
  （P 的 title / practice_action 均不含此關鍵字）

操作
  GET /api/v1/users/practices?keyword=KEYWORD_12_5_UNIQUE_私密心得

預期結果
  HTTP 200
  data 陣列為空（[]）或不含 P

迴歸（Task 12.2 對應）
  將 P 的 status 更新為 'completed'
  再次呼叫相同 keyword 搜尋
  → data 包含 P（full access）
```

---

## 12.6 整合測試：組合篩選 — tags + status + duration 精確性

**Target**: `GET /api/v1/users/practices?tags=ai&status=active&duration_min=7&duration_max=7`  
**Test type**: pytest + TestClient + 測試用 DB

### 測試設計

```
前置條件（4 筆練習，均為 privacy_status='public'）
  P1: tags=['ai'], status='active',    duration_days=7   → 應出現
  P2: tags=['ai'], status='active',    duration_days=14  → 不出現（duration 不符）
  P3: tags=['ai'], status='completed', duration_days=7   → 不出現（status 不符）
  P4: tags=['ml'],  status='active',   duration_days=7   → 不出現（tag 不符）

操作
  GET /api/v1/users/practices?tags=ai&status=active&duration_min=7&duration_max=7

預期結果
  data 長度 = 1
  data[0].id 等於 P1 的 external_id（slug 查詢驗證）
  P2 / P3 / P4 均不出現
```

---

## 12.7 整合測試：`/api/v1/users/practices` 不含 `private` 或 `draft` 練習

**Target**: `GET /api/v1/users/practices`  
**Test type**: pytest + TestClient + 測試用 DB

### 測試設計

```
前置條件（4 筆練習）
  A: privacy_status='private', status='active'    → 不回傳
  B: privacy_status='public',  status='draft'     → 不回傳
  C: privacy_status='public',  status='active'    → 回傳（一般公開）
  D: privacy_status='delayed', status='active'    → 回傳（Brewing Card，is_brewing=true）

操作
  GET /api/v1/users/practices（不帶任何過濾參數）

預期結果
  data 中的 id 集合 == { C.external_id, D.external_id }
  A / B 均不出現
  D 出現時 is_brewing = true

驗證點
  `_remove_unwanted_status()` 的 privacy_status != 'private' 過濾
  status NOT IN ('draft', 'archived', 'not_started') 過濾
```

---

## 12.8 整合測試：`privacy_status` private → public 後練習立即出現在廣場 Feed

**Target**: Practice 更新 API + `GET /api/v1/feed`（或 `GET /api/v1/users/practices`）  
**Test type**: pytest + TestClient + 測試用 DB

### 測試設計

```
前置條件
  Practice P: privacy_status='private', status='active'

步驟 1
  GET /api/v1/users/practices
  → data 不含 P

步驟 2
  呼叫 practice 更新 API（PATCH/PUT）：{ privacy_status: 'public' }
  → HTTP 200 / 2xx

步驟 3
  GET /api/v1/users/practices（不含 cache 攔截，或 bypass cache key）
  → data 包含 P

預期結果
  步驟 1：P 不在列表
  步驟 3：P 立即出現（無延遲、無快取問題）

注意
  測試環境須 bypass Redis cache（或在快取 TTL 內使用不同 user 繞過 per-user cache key）
  驗證的是資料庫層的即時性，而非快取行為
```

---

## 測試基礎設施需求

| 項目 | 規格 |
|------|------|
| AI backend 單元測試框架 | pytest 9.x + MagicMock（已有 `tests/services/` 範例） |
| AI backend 整合測試框架 | pytest + `fastapi.testclient.TestClient` + SQLite / 測試 PostgreSQL |
| daodao-server 單元測試框架 | Jest / Vitest + Prisma mock 或 TypeORM in-memory |
| CI 觸發 | PR 建立 / push 時自動執行（參考 `.github/workflows/`） |

## 接受條件

- [ ] 12.1–12.2：新增 `tests/services/test_practice_service_brewing.py`，4 個 test case 全過
- [ ] 12.5–12.8：新增 `tests/integration/test_practice_api.py`（或分檔），所有 test case 全過
- [ ] 12.3–12.4：新增 daodao-server 測試（路徑由 Node.js team 決定），CI 全綠
- [ ] 所有新測試不影響既有測試（`pytest` 全套通過）
- [ ] 每個 task 均有對應的迴歸 test case
