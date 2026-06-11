---
name: monthly_insights
description: 查詢指定月份的用戶活躍與互動資料，透過 LLM 撰寫洞察摘要，輸出 Markdown 報告或寫入 Notion。觸發語句：月報、MAU、月度洞察。
---

# Skill: monthly_insights

## Trigger Phrases
- 月報
- MAU
- 月度洞察
- 每月報告
- monthly report
- monthly insights
- 上個月的數據

## Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| year_month | string | (last month) | Format: "YYYY-MM", e.g. "2024-01" |
| output_format | string | "markdown" | "markdown" or "notion" |
| notion_page_id | string | null | Target Notion page ID (only if output_format="notion") |

## Steps (Overview)

1. **Query MAU**: Count distinct active users (had checkins, reactions, or comments) in the month.
2. **Query DAU trend**: Daily active users for the month (sparkline data).
3. **Query Checkins**: Total checkin count, average mood score, and top mood distribution.
4. **Query New Users**: Count of new user registrations in the month.
5. **Query Practices**: New practices created, completed practices, active practices.
6. **Query Reactions & Comments**: Total reactions and comments to measure engagement.
7. **Query Cohort Retention**: For users who joined last month, how many were active this month.
8. **Query Top Practices**: Most-checkin-ed practices of the month (title, user, count).
9. **Query Top Users**: Most active users by checkin count.

10. **LLM Narrate**: Combine all metrics into a narrative monthly insights report in Markdown.
    - System: "你是 DaoDao 數據分析師，負責撰寫月度洞察報告。使用繁體中文，結構清晰，包含數據亮點、趨勢分析與行動建議。"
    - Output: Full Markdown report.

11. **Output**: Return as Markdown or push to Notion page if output_format="notion".

## Expected Output
- `type: agent_message` with Markdown report content
- `type: result` with summary of key metrics
