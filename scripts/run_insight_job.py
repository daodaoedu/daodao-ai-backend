"""
手動觸發精選洞察排程（等同排程器的 _run_job）

使用方式：
  python scripts/run_insight_job.py                         # 使用 .env
  python scripts/run_insight_job.py --env-file .env.dev    # 指定 env 檔
  python scripts/run_insight_job.py --backend gemini
  python scripts/run_insight_job.py --backend anthropic
  python scripts/run_insight_job.py --dry-run               # 只顯示待處理數量，不生成
"""

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# 確保專案 root 在 import path 中
_PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="手動觸發精選洞察生成排程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python scripts/run_insight_job.py --env-file .env.dev
  python scripts/run_insight_job.py --env-file .env.dev --backend anthropic
  python scripts/run_insight_job.py --env-file .env.dev --dry-run
        """,
    )
    parser.add_argument(
        "--env-file",
        default=None,
        help="指定要載入的 .env 檔路徑（例如 .env.dev）",
    )
    parser.add_argument(
        "--backend",
        choices=["gemini", "anthropic", "openai", "ollama", "groq"],
        default=None,
        help="指定 LLM backend（預設使用 env 的 INSIGHT__LLM_BACKEND 設定）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示待處理 Practice 數量，不實際生成",
    )
    parser.add_argument(
        "--setup-db",
        action="store_true",
        help="建立 AI 後端自有的資料表（practice_insights），首次使用時執行",
    )
    return parser.parse_args()


def _load_env(env_file: str | None) -> None:
    """
    在 Settings 初始化前載入指定的 .env 檔，
    讓 os.environ 先有值，pydantic-settings 才讀得到正確的設定。
    """
    # 優先用指定檔，沒指定就找 .env.dev → .env
    candidates = [env_file] if env_file else [".env.dev", ".env"]

    for candidate in candidates:
        path = _PROJECT_ROOT / candidate
        if path.exists():
            print(f"  env 檔案    : {candidate}")
            # 手動讀取並注入 os.environ（不覆蓋已存在的環境變數）
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    os.environ.setdefault(key, value)
            return

    print("  env 檔案    : （未找到，使用系統環境變數）")


async def run_job(backend: str, dry_run: bool, setup_db: bool) -> None:
    # env 載入後才 import（讓 pydantic-settings 讀到正確值）
    from src.config import get_settings  # noqa: E402
    from src.db.factory import make_database  # noqa: E402
    from src.services.insight import insight_service  # noqa: E402
    from src.services.llm.client import LLMClient  # noqa: E402

    start = time.time()

    print("=" * 55)
    print("  精選洞察手動觸發")
    print("=" * 55)

    # ── 初始化設定與 DB ───────────────────────────────────────
    settings = get_settings()
    effective_backend = backend or settings.insight.llm_backend

    print(f"  LLM backend : {effective_backend}")
    print(f"  Dry run     : {'是' if dry_run else '否'}")
    print("-" * 55)

    print("⏳ 連線資料庫...")
    database = make_database()
    print("✅ 資料庫連線成功\n")

    # ── 查詢待處理 Practice IDs ───────────────────────────────
    # 只存 id + title，避免 session 關閉後物件 detached
    with database.get_session() as db:
        practices = insight_service.get_pending_practices(db)
        pending = [(p.id, p.title) for p in practices]

    pending_count = len(pending)
    print(f"📋 待處理 Practice 數量：{pending_count}")

    if pending_count == 0:
        print("\n✨ 沒有待處理的 Practice，任務結束。")
        _print_summary(total=0, failed=0, elapsed=time.time() - start)
        database.teardown()
        return

    # ── Dry run 模式：只顯示清單 ──────────────────────────────
    if dry_run:
        print("\n[Dry Run] 以下 Practice 將被生成洞察：")
        for pid, title in pending:
            print(f"  - practice_id={pid}  title={title}")
        print("\n[Dry Run] 未實際生成，請移除 --dry-run 後再執行。")
        database.teardown()
        return

    # ── 實際生成 ─────────────────────────────────────────────
    llm_client = LLMClient(settings, effective_backend)
    total = 0
    failed = 0

    print(f"\n🚀 開始生成（共 {pending_count} 筆）...\n")

    for i, (practice_id, title) in enumerate(pending, 1):
        print(f"  [{i}/{pending_count}] practice_id={practice_id}  {title}")
        try:
            with database.get_session() as db:
                result = await insight_service.generate_for_practice_by_id(
                    db, llm_client, practice_id
                )
            if result:
                total += 1
                print(f"    ✅ 洞察已寫入 practice_id={result}")
            else:
                print("    ⚠️  跳過（已存在或 LLM 回傳空值）")
        except Exception as exc:  # pylint: disable=broad-exception-caught
            failed += 1
            print(f"    ❌ 失敗：{exc}")

    database.teardown()
    _print_summary(total=total, failed=failed, elapsed=time.time() - start)


def _print_summary(total: int, failed: int, elapsed: float) -> None:
    print("\n" + "=" * 55)
    print(f"  完成：成功 {total} 筆 | 失敗 {failed} 筆 | 耗時 {elapsed:.1f}s")
    print("=" * 55)


def main() -> None:
    args = _parse_args()
    _load_env(args.env_file)
    asyncio.run(run_job(backend=args.backend, dry_run=args.dry_run, setup_db=args.setup_db))


if __name__ == "__main__":
    main()
