---
name: practice_completion_email
description: 當用戶完成實踐，查詢相關資料，透過 LLM 生成個人化慶賀信並寄出。觸發語句：對完成實踐的用戶寄信、寄慶賀信。
---

# Skill: practice_completion_email

## Trigger Phrases
- 對完成實踐的用戶寄信
- 寄慶賀信
- 發送實踐完成通知
- send completion email
- congratulate users who completed practice

## Parameters
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| time_range | string | "last_7_days" | Time range for completed practices: "last_7_days", "last_30_days", "this_month", or ISO date range "YYYY-MM-DD:YYYY-MM-DD" |
| dry_run | bool | true | If true, preview only; if false, actually send emails |
| preview_count | int | 3 | Number of sample emails to show in preview |
| email_template | string | "default" | Email template name |
| extra_data_fields | list | [] | Additional user fields to include in personalization |

## Steps (Overview)

1. **Query DB**: Find users who completed a practice in the given time range.
   - Join `practices` with `users` to get nickname, email, practice title, completion date.
   - Filter: `practices.status = 'completed'`, `practices.deleted_at IS NULL`, `users.deleted_at IS NULL`.
   - Apply `time_range` filter on `practices.updated_at`.

2. **Get User Context**: For each user, fetch their checkin history for the completed practice to personalize the email (total checkins, best streak, notable notes).

3. **LLM Generate Email**: Call LLMClient with:
   - System prompt: "你是 DaoDao 的溫暖夥伴，負責撰寫個人化慶賀信。信件要簡短有力、真誠感人，使用繁體中文，約 200-300 字。"
   - User prompt: User profile + practice data + checkin highlights → generate subject and HTML body.

4. **Preview**: Show `preview_count` sample emails with subject and first 200 chars of body.

5. **Send** (if `dry_run=False` and admin approves): Call `bulk_send_emails` tool for all recipients.

## Expected Output
- `type: approval_request` with preview before sending
- Final summary: total sent, failed, dry_run status
