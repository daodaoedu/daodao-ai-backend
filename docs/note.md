**每個服務對應到的資料庫**，以及這樣設計的原因。

---

### **1. Recommendation API → PostgreSQL + Redis**

* **PostgreSQL**

  * 儲存使用者、資源、推薦紀錄等結構化資料。
  * 推薦系統需要追蹤使用者行為（點擊`click`、收藏`favorite`、分享`share`）和資源特徵（類別`resources.major_category_id, resources.sub_category_id, resources.type`、標籤`entity_tag`、難度`resources.level`等），這些是典型的關聯式資料。
    * `click`, `favorite`, `share` 目前沒這表
* **Redis**
  * 做熱門推薦快取、使用者推薦列表快取，減少每次都重新計算的開銷。
  * 也可以儲存用戶最近行為，用於即時個人化推薦。


---

### **2. Vector Search API → Qdrant + Redis**

* **Qdrant (Vector DB)**

  * 儲存資源或內容的向量化嵌入（embeddings），支援相似度搜尋（例如找相似資源、專案、找內容相關的教學文章）。
    * `resources.name` + `resources.description`
    * `review.mood_description` + `review.learning_feedback`
    * `post.type` + `post.title` +
      * `outcome.content`
      * `review.mood_description` + `review.learning_feedback`
      *  `note.content`
  * 特別適合語義搜尋與內容推薦。
* **Redis**

  * 快取向量查詢結果或熱門關鍵字的搜尋結果，降低 Qdrant 查詢延遲。
  * 也可做短期 session-based 向量查詢緩存。

---

### **3. Analytics API → ClickHouse + PostgreSQL**

* **ClickHouse**

  * 高效能的列式數據庫，適合儲存大量事件日誌（例如觀看次數、互動行為、流量統計）。
  * 分析 API 會做即時/批次的數據聚合（如每日活躍用戶 DAU、資源熱門榜）。
* **PostgreSQL**

  * 用來對應分析結果到實體資料（例如用戶 ID → 用戶資料、資源 ID → 資源詳細內容）。
  * 也可儲存非大量但需要事務處理的分析配置（例如報表配置、儀表板設定）。

---

### **4. Chatbot Service → LLM + PostgreSQL + Redis**

* **LLM (OpenAI 或自建模型)**

  * 負責自然語言生成、對話理解、知識問答。
  * 可能連接到雲端 API 或本地部署模型。
* **PostgreSQL**

  * 儲存聊天記錄、對話上下文、使用者偏好設定。
  * 方便做日後的回溯分析、個人化回覆。
* **Redis**

  * 快取近期對話上下文（session context），避免每次都從資料庫取完整歷史對話。
  * 減少 LLM API 調用延遲。

---

### **為什麼會一個服務對應多個 DB？**

1. **不同類型資料有不同最佳儲存技術**

   * 關聯資料 → PostgreSQL
   * 大規模事件數據 → ClickHouse
   * 高維向量 → Qdrant
   * 即時快取/Session → Redis
2. **提升效能與可擴展性**

   * 把不同負載分開，避免單一資料庫成為瓶頸。
3. **服務自治（Service Autonomy）**

   * 每個服務有自己專屬的資料存取層，能獨立擴展與維護，不必所有服務都依賴同一個 DB。




=====

最活躍用戶：
- 用戶 comments 數量
- 用戶 entity_tags 數量 ？
- 用戶創建 group 數量
- 用戶完成 project + milestone 數量
