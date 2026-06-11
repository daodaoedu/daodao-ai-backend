# DaoDao Agent vs Claude Agent 功能比較

## 比較表格

| 功能面向 | DaoDao Agent | Claude Agent (claude.ai) |
|---------|-------------|--------------------------|
| **對話管理** | Thread（in-memory，重啟後消失） | 持久化 Project / Conversation |
| **工具執行** | 固定 2 種：`query_db`、`send_email` | 動態工具：web search、code exec、file read/write、MCP 任意擴充 |
| **Skill 系統** | 靜態 SKILL.md 檔案，手動新增 | 無 skill 概念，直接理解意圖 |
| **資料來源** | 只能查自己的 PostgreSQL | 網路、上傳檔案、任意 API（透過 MCP） |
| **執行危險操作前** | ApprovalCard（Allow / Deny） | 工具執行前確認（視設定） |
| **Dry Run 模式** | 有，發信前預覽不真的送 | 無此概念 |
| **多步驟推理** | 單輪 LLM call，用 ```json tool_call``` 觸發 | 原生 multi-step agentic loop，自動迭代直到完成 |
| **LLM 選擇** | 可切換 provider（openrouter/gemini/groq 等） | 固定 Claude 系列 |
| **上下文記憶** | 同 thread history（無跨 thread 記憶） | Project Knowledge、Memory 跨對話持久 |
| **部署位置** | 自建，資料不離開自己的 infra | 雲端，資料經過 Anthropic |
| **使用者權限** | 只限 Admin（JWT 驗證） | 個人帳號，無 RBAC |
| **擴充方式** | 新增 SKILL.md + execute.py | MCP Server（任意語言） |
| **成本** | 依所選 provider 計費 | Claude Pro 訂閱或 API 計費 |

## 核心差距

DaoDao Agent 本質上是一個**有限狀態的指令分發器**：
LLM 判斷意圖 → 對應 skill → 執行固定流程。

Claude Agent 是真正的**自主推理迴圈**：
LLM 自己決定下一步要用什麼工具、執行後看結果再繼續，直到任務完成。

## DaoDao Agent 的優勢

- 資料不出內網，符合資安需求
- 有明確的 Approval 流程，防止誤操作
- 針對特定業務場景（查數據、發信、月報）準確率高
- 成本可控，可切換免費 provider（groq、openrouter 免費方案）

## 未來可改進方向

- Thread 持久化至 DB（目前 in-memory，重啟消失）
- 支援 multi-step agentic loop（目前單輪）
- 動態新增 skill（目前需手動加檔案）
- 跨 thread 記憶（目前每個 thread 獨立）
