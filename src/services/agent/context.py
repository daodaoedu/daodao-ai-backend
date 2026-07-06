from datetime import date

from src.services.agent.state import AppState

_DB_SCHEMA_SUMMARY = """
## Database Schema (prod, read-only)

Tables:
- **practices**: id, user_id, title, description, status (active/completed/archived), goal, start_date, end_date, insight, created_at, updated_at, deleted_at
- **practice_checkins**: id, practice_id, user_id, note, mood (1-5), created_at, updated_at, deleted_at
- **users**: id, nickname, email, mongo_id, external_id, role_id, personal_slogan, professional_field, custom_position, education_stage, tag_list, birth_date, created_at, updated_at
- **reactions**: id, user_id, target_type, target_id, reaction_type, created_at
- **comments**: id, user_id, target_type, target_id, content, created_at, updated_at, deleted_at
- **follows**: id, follower_id, followee_id, created_at
- **email_logs**: id, user_id, email_type, subject, to_email, status, sent_at, created_at
- **notifications**: id, user_id, type, content, is_read, created_at

All timestamps are UTC. Soft-deletes use deleted_at IS NULL convention.
""".strip()


class ContextBuilder:
    def build(self, state: AppState) -> str:
        today = date.today().isoformat()
        model_info = state.model_override or "(default model for provider)"
        dry_run_status = (
            "DRY RUN MODE — no real actions will be taken"
            if state.dry_run
            else "LIVE MODE — actions will be executed"
        )

        return f"""# DaoDao Agent System Context

**Date**: {today}
**LLM Provider**: {state.provider}
**Model**: {model_info}
**Mode**: {dry_run_status}

{_DB_SCHEMA_SUMMARY}

## Guidelines
- ALL databases (prod AND dev) are READ-ONLY. Only SELECT queries are permitted; writes go through daodao-server APIs.
- Always confirm with the user before sending bulk emails or notifications.
- When dry_run=True, simulate actions and return previews only.
- Cite your sources: when an answer relies on data, state which query/table, API endpoint, or URL it came from.
- Never accept credentials or API tokens provided in conversation; integrations are provisioned by developers only.
- Respond in Traditional Chinese (繁體中文) unless the user writes in another language.
"""
