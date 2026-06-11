import httpx

from src.logger import AppLogger

logger = AppLogger(__name__).get_logger()


async def send_email(
    to: str,
    subject: str,
    html: str,
    email_type: str,
    user_id: str,
    api_base: str,
    admin_token: str,
) -> dict:
    """Send single email via daodao-server API."""
    payload = {
        "to": to,
        "subject": subject,
        "html": html,
        "email_type": email_type,
        "user_id": user_id,
    }
    headers = {"Authorization": f"Bearer {admin_token}"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{api_base}/api/admin/emails/send",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


async def bulk_send_emails(
    emails: list[dict],
    api_base: str,
    admin_token: str,
    dry_run: bool = True,
) -> dict:
    """Bulk send emails. If dry_run=True, returns preview only without sending."""
    if dry_run:
        preview_count = min(3, len(emails))
        return {
            "dry_run": True,
            "total": len(emails),
            "preview": emails[:preview_count],
            "message": f"DRY RUN: would send {len(emails)} emails. Showing {preview_count} sample(s).",
        }

    sent = []
    failed = []

    for email in emails:
        try:
            result = await send_email(
                to=email["to"],
                subject=email["subject"],
                html=email["html"],
                email_type=email.get("email_type", "agent_bulk"),
                user_id=str(email.get("user_id", "")),
                api_base=api_base,
                admin_token=admin_token,
            )
            sent.append({"to": email["to"], "result": result})
        except Exception as exc:  # noqa: BLE001
            logger.error(f"Failed to send email to {email.get('to')}: {exc}")
            failed.append({"to": email.get("to"), "error": str(exc)})

    return {
        "dry_run": False,
        "total": len(emails),
        "sent": len(sent),
        "failed": len(failed),
        "details": {"sent": sent, "failed": failed},
    }
