from datetime import date, timedelta
from typing import AsyncIterator

from src.logger import AppLogger
from src.services.agent.state import AppState
from src.services.agent.tools.db import query_prod_db
from src.services.agent.tools.email import bulk_send_emails
from src.services.llm.client import LLMClient

logger = AppLogger(__name__).get_logger()


def _resolve_time_range(time_range: str) -> tuple[str, str]:
    """Resolve time_range param to (start_date, end_date) ISO strings."""
    today = date.today()
    if time_range == "last_7_days":
        return (today - timedelta(days=7)).isoformat(), today.isoformat()
    if time_range == "last_30_days":
        return (today - timedelta(days=30)).isoformat(), today.isoformat()
    if time_range == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if ":" in time_range:
        parts = time_range.split(":", 1)
        return parts[0], parts[1]
    # default fallback
    return (today - timedelta(days=7)).isoformat(), today.isoformat()


async def execute(
    params: dict,
    state: AppState,
    settings,
    db_session,
) -> AsyncIterator[dict]:
    """
    Execute practice_completion_email skill.
    Steps: query DB -> get user context -> LLM generate email content -> preview -> send
    params: {time_range, dry_run, preview_count, email_template, extra_data_fields}
    """
    time_range = params.get("time_range", "last_7_days")
    dry_run = params.get("dry_run", state.dry_run)
    preview_count = int(params.get("preview_count", 3))

    start_date, end_date = _resolve_time_range(time_range)

    yield {
        "type": "agent_message",
        "content": f"查詢 {start_date} 至 {end_date} 完成實踐的用戶...",
    }

    # Step 1: Query completed practices and users
    sql = f"""
        SELECT
            p.id AS practice_id,
            p.title AS practice_title,
            p.updated_at AS completed_at,
            u.id AS user_id,
            u.nickname,
            u.email,
            u.personal_slogan,
            u.professional_field
        FROM practices p
        JOIN users u ON u.id = p.user_id
        WHERE p.status = 'completed'
          AND p.deleted_at IS NULL
          AND u.email IS NOT NULL
          AND u.email != ''
          AND p.updated_at >= '{start_date}'
          AND p.updated_at <= '{end_date} 23:59:59'
        ORDER BY p.updated_at DESC
    """

    try:
        rows = await query_prod_db(sql, db_session)
    except Exception as exc:  # noqa: BLE001
        yield {"type": "agent_message", "content": f"查詢失敗：{exc}"}
        yield {"type": "result", "summary": f"Error: {exc}"}
        return

    if not rows:
        yield {
            "type": "agent_message",
            "content": f"在 {start_date} 至 {end_date} 期間沒有找到完成實踐的用戶。",
        }
        yield {"type": "result", "summary": "No completed practices found in the given range."}
        return

    yield {
        "type": "agent_message",
        "content": f"找到 {len(rows)} 位用戶完成實踐，正在生成個人化慶賀信...",
    }

    # Step 2 & 3: For each user, fetch checkin context and generate email
    llm = LLMClient(settings, state.provider, enable_guardrail=False)
    if state.model_override:
        llm._backend.config["model"] = state.model_override

    emails = []
    for row in rows:
        practice_id = row["practice_id"]

        # Fetch checkin summary
        checkin_sql = f"""
            SELECT COUNT(*) AS total_checkins,
                   MAX(mood) AS best_mood,
                   MIN(created_at) AS first_checkin,
                   MAX(created_at) AS last_checkin
            FROM practice_checkins
            WHERE practice_id = {practice_id}
              AND deleted_at IS NULL
        """
        try:
            checkin_rows = await query_prod_db(checkin_sql, db_session)
            checkin_summary = checkin_rows[0] if checkin_rows else {}
        except Exception:  # noqa: BLE001
            checkin_summary = {}

        # Build LLM prompt for personalized email
        system_prompt = (
            "你是 DaoDao 的溫暖夥伴，負責撰寫個人化慶賀信。"
            "信件要簡短有力、真誠感人，使用繁體中文，約 200-300 字。"
            "輸出格式：\n"
            "SUBJECT: <email subject>\n"
            "---\n"
            "<email HTML body>"
        )

        user_context = f"""用戶資訊：
- 暱稱：{row.get('nickname', '用戶')}
- 個人slogan：{row.get('personal_slogan') or '(未填)'}
- 專業領域：{row.get('professional_field') or '(未填)'}

實踐資訊：
- 實踐名稱：{row.get('practice_title', '你的實踐')}
- 完成日期：{str(row.get('completed_at', ''))[:10]}
- 總打卡次數：{checkin_summary.get('total_checkins', 0)}
- 第一次打卡：{str(checkin_summary.get('first_checkin', ''))[:10]}
- 最後打卡：{str(checkin_summary.get('last_checkin', ''))[:10]}

請為這位用戶寫一封個人化的慶賀信，慶祝他們完成「{row.get('practice_title', '實踐')}」。"""

        full_prompt = f"<system>\n{system_prompt}\n</system>\n<user>\n{user_context}\n</user>\n<assistant>"

        try:
            output, _cost, _usage, _backend = await llm.generate(full_prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"LLM generation failed for user {row.get('user_id')}: {exc}")
            continue

        # Parse subject and body from LLM output
        subject = f"恭喜你完成「{row.get('practice_title', '你的實踐')}」！"
        html_body = output

        if "SUBJECT:" in output:
            lines = output.split("\n")
            for i, line in enumerate(lines):
                if line.startswith("SUBJECT:"):
                    subject = line.replace("SUBJECT:", "").strip()
                    remaining = "\n".join(lines[i + 1:])
                    html_body = remaining.replace("---", "", 1).strip()
                    break

        emails.append({
            "to": row["email"],
            "subject": subject,
            "html": html_body,
            "email_type": "practice_completion",
            "user_id": str(row["user_id"]),
            "nickname": row.get("nickname", ""),
            "practice_title": row.get("practice_title", ""),
        })

    if not emails:
        yield {
            "type": "agent_message",
            "content": "無法生成任何慶賀信（LLM 生成失敗）。",
        }
        yield {"type": "result", "summary": "No emails generated."}
        return

    # Step 4: Preview
    preview_samples = emails[:preview_count]
    preview_text = "\n\n".join(
        f"**收件人**: {e['to']} ({e['nickname']})\n"
        f"**主旨**: {e['subject']}\n"
        f"**內容預覽**: {e['html'][:200]}..."
        for e in preview_samples
    )

    yield {
        "type": "agent_message",
        "content": (
            f"共生成 {len(emails)} 封慶賀信。以下是前 {len(preview_samples)} 封預覽：\n\n{preview_text}"
        ),
    }

    if dry_run:
        yield {
            "type": "approval_request",
            "id": f"bulk_email_{practice_id}",
            "action": "bulk_send_emails",
            "description": f"發送 {len(emails)} 封實踐完成慶賀信",
            "payload": {"emails": emails, "dry_run": False},
            "preview": preview_samples,
        }
        yield {
            "type": "result",
            "summary": f"DRY RUN: Preview generated for {len(emails)} emails. Waiting for approval to send.",
        }
        return

    # Step 5: Send emails (live mode)
    api_base = getattr(settings, "daodao_server_url", "")
    admin_token = getattr(settings, "api_secret_key", "")

    result = await bulk_send_emails(
        emails=emails,
        api_base=api_base,
        admin_token=admin_token,
        dry_run=False,
    )

    yield {
        "type": "agent_message",
        "content": f"已發送 {result.get('sent', 0)} 封，失敗 {result.get('failed', 0)} 封。",
    }
    yield {
        "type": "result",
        "summary": f"Sent {result.get('sent', 0)}/{len(emails)} emails successfully.",
    }
