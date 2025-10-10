
如果你要做 統一 feed（ideas + practices + projects 混排），可以考慮一個簡單公式：

`score = base_score + freshness_score + activity_score`
- base_score (依類型預設，例如 idea=1, practice=2, project=3) +
- freshness_score (1 / log(1 + age_in_days)) +
- activity_score (like_count*2 + resource_count*1 + streak*0.5 + progress_ratio*2)

## base_score
- Idea（想法） → base_score = 1
  - 表示一般想法，推薦權重較低。
- Practice（實踐） → base_score = 2
  - 表示有實際行動或學習計畫，權重較高。
- Project（專案） → base_score = 3
  - 表示完整專案或大型計畫，權重最高。


## 新鮮度加分（freshness_score）
- 計算公式：1 / log(1 + 發布天數)
- 想法：越新的內容分數越高，鼓勵使用者看到最新的 post。
- 避免 LOG(0) 的問題，保護計算安全。
- 這個部分確保 feed 不會只顯示老舊內容，保持新鮮感。

## 活躍度加分（activity_score）
- 活躍度計算（目前用 placeholder）：
  - 綁定資源數量（resource_count）×1
  - 實踐的連續天數（streak）×0.5
  - 進度比例（progress_ratio）×2
- 對不同類型：
  - Idea / Project 沒有 streak 與 progress_ratio → 這兩項為 0
  - Practice 才有完整活躍度指標
- 這部分可以未來擴充，加入「讚 / 收藏 / 分享數」，更真實反映使用者互動。

```sql
WITH idea_feed AS (
    SELECT
        i.id::text AS id,
        'idea'::text AS type,
        i.content::text AS title,
        i.created_at,
        i.updated_at,
        COALESCE(er_count.count,0)::float8 AS resource_count,
        0::float8 AS streak,
        0::float8 AS progress_ratio,
        1::float8 AS base_score
    FROM ideas i
    LEFT JOIN (
        SELECT entity_id, entity_type, COUNT(*) AS count
        FROM entity_resources
        WHERE entity_type = 'idea'
        GROUP BY entity_id, entity_type
    ) er_count
    ON er_count.entity_id = i.id::text
),
practice_feed AS (
    SELECT
        p.id::text AS id,
        'practice'::text AS type,
        p.title::text AS title,
        p.created_at,
        p.updated_at,
        COALESCE(er_count.count,0)::float8 AS resource_count,
        COALESCE(p.streak,0)::float8 AS streak,
        COALESCE(p.current_progress / NULLIF(p.total_amount,0),0)::float8 AS progress_ratio,
        2::float8 AS base_score
    FROM practices p
    LEFT JOIN (
        SELECT entity_id, entity_type, COUNT(*) AS count
        FROM entity_resources
        WHERE entity_type = 'practice'
        GROUP BY entity_id, entity_type
    ) er_count
    ON er_count.entity_id = p.id::text
),
project_feed AS (
    SELECT
        pr.id::text AS id,
        'project'::text AS type,
        pr.title::text AS title,
        pr.created_at,
        pr.updated_at,
        COALESCE(er_count.count,0)::float8 AS resource_count,
        0::float8 AS streak,
        0::float8 AS progress_ratio,
        3::float8 AS base_score
    FROM project pr
    LEFT JOIN (
        SELECT entity_id, entity_type, COUNT(*) AS count
        FROM entity_resources
        WHERE entity_type = 'project'
        GROUP BY entity_id, entity_type
    ) er_count
    ON er_count.entity_id = pr.id::text
)
SELECT *,
       base_score,
       1 / NULLIF(LOG(1 + EXTRACT(DAY FROM (NOW() - created_at))),0) AS freshness_score,
       (resource_count*1 + streak*0.5 + progress_ratio*2) AS activity_score,
       (base_score
        + 1 / NULLIF(LOG(1 + EXTRACT(DAY FROM (NOW() - created_at))),0)
        + (resource_count*1 + streak*0.5 + progress_ratio*2)
       ) AS score
FROM (
    SELECT * FROM idea_feed
    UNION ALL
    SELECT * FROM practice_feed
    UNION ALL
    SELECT * FROM project_feed
) combined
ORDER BY score DESC, freshness_score DESC, activity_score DESC
LIMIT 50;

```
