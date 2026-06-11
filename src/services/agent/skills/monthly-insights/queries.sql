-- Monthly Insights Queries
-- Replace :year_month with 'YYYY-MM' and :start_date/:end_date with month boundaries

-- ============================================================
-- MAU (Monthly Active Users)
-- Active = had at least one checkin, reaction, or comment in the month
-- ============================================================
SELECT COUNT(DISTINCT user_id) AS mau
FROM (
    SELECT user_id FROM practice_checkins
    WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CAST(:year_month || '-01' AS DATE))
      AND deleted_at IS NULL
    UNION
    SELECT user_id FROM reactions
    WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CAST(:year_month || '-01' AS DATE))
    UNION
    SELECT user_id FROM comments
    WHERE DATE_TRUNC('month', created_at) = DATE_TRUNC('month', CAST(:year_month || '-01' AS DATE))
      AND deleted_at IS NULL
) AS active_users;


-- ============================================================
-- DAU trend (Daily Active Users for the month)
-- ============================================================
SELECT
    DATE(created_at) AS day,
    COUNT(DISTINCT user_id) AS dau
FROM practice_checkins
WHERE created_at >= :start_date
  AND created_at < :end_date
  AND deleted_at IS NULL
GROUP BY DATE(created_at)
ORDER BY day;


-- ============================================================
-- Checkin stats: total, avg mood, mood distribution
-- ============================================================
SELECT
    COUNT(*) AS total_checkins,
    ROUND(AVG(mood), 2) AS avg_mood,
    SUM(CASE WHEN mood = 5 THEN 1 ELSE 0 END) AS mood_5,
    SUM(CASE WHEN mood = 4 THEN 1 ELSE 0 END) AS mood_4,
    SUM(CASE WHEN mood = 3 THEN 1 ELSE 0 END) AS mood_3,
    SUM(CASE WHEN mood = 2 THEN 1 ELSE 0 END) AS mood_2,
    SUM(CASE WHEN mood = 1 THEN 1 ELSE 0 END) AS mood_1
FROM practice_checkins
WHERE created_at >= :start_date
  AND created_at < :end_date
  AND deleted_at IS NULL;


-- ============================================================
-- New user registrations in the month
-- ============================================================
SELECT COUNT(*) AS new_users
FROM users
WHERE created_at >= :start_date
  AND created_at < :end_date;


-- ============================================================
-- Practice stats: new, completed, active
-- ============================================================
SELECT
    COUNT(*) FILTER (WHERE created_at >= :start_date AND created_at < :end_date) AS new_practices,
    COUNT(*) FILTER (WHERE status = 'completed' AND updated_at >= :start_date AND updated_at < :end_date) AS completed_practices,
    COUNT(*) FILTER (WHERE status = 'active' AND deleted_at IS NULL) AS total_active_practices
FROM practices
WHERE deleted_at IS NULL;


-- ============================================================
-- Reactions in the month
-- ============================================================
SELECT
    COUNT(*) AS total_reactions,
    reaction_type,
    COUNT(*) AS count_per_type
FROM reactions
WHERE created_at >= :start_date
  AND created_at < :end_date
GROUP BY reaction_type
ORDER BY count_per_type DESC;


-- ============================================================
-- Comments in the month
-- ============================================================
SELECT COUNT(*) AS total_comments
FROM comments
WHERE created_at >= :start_date
  AND created_at < :end_date
  AND deleted_at IS NULL;


-- ============================================================
-- Cohort retention: users who joined last month and were active this month
-- ============================================================
WITH last_month_users AS (
    SELECT id AS user_id
    FROM users
    WHERE created_at >= :last_month_start
      AND created_at < :start_date
),
active_this_month AS (
    SELECT DISTINCT user_id
    FROM practice_checkins
    WHERE created_at >= :start_date
      AND created_at < :end_date
      AND deleted_at IS NULL
)
SELECT
    COUNT(lmu.user_id) AS cohort_size,
    COUNT(atm.user_id) AS retained_users,
    ROUND(
        100.0 * COUNT(atm.user_id) / NULLIF(COUNT(lmu.user_id), 0),
        1
    ) AS retention_rate_pct
FROM last_month_users lmu
LEFT JOIN active_this_month atm ON atm.user_id = lmu.user_id;


-- ============================================================
-- Top 10 practices by checkin count this month
-- ============================================================
SELECT
    p.id AS practice_id,
    p.title AS practice_title,
    u.nickname AS user_nickname,
    COUNT(pc.id) AS checkin_count
FROM practice_checkins pc
JOIN practices p ON p.id = pc.practice_id
JOIN users u ON u.id = p.user_id
WHERE pc.created_at >= :start_date
  AND pc.created_at < :end_date
  AND pc.deleted_at IS NULL
  AND p.deleted_at IS NULL
GROUP BY p.id, p.title, u.nickname
ORDER BY checkin_count DESC
LIMIT 10;


-- ============================================================
-- Top 10 users by checkin count this month
-- ============================================================
SELECT
    u.id AS user_id,
    u.nickname,
    COUNT(pc.id) AS checkin_count,
    COUNT(DISTINCT pc.practice_id) AS active_practices
FROM practice_checkins pc
JOIN users u ON u.id = pc.user_id
WHERE pc.created_at >= :start_date
  AND pc.created_at < :end_date
  AND pc.deleted_at IS NULL
GROUP BY u.id, u.nickname
ORDER BY checkin_count DESC
LIMIT 10;
