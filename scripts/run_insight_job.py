"""
手動觸發精選洞察排程（等同排程器的 _run_job）

使用方式：
  python scripts/run_insight_job.py                  # 使用 .env 預設 backend
  python scripts/run_insight_job.py --backend gemini
  python scripts/run_insight_job.py --backend anthropic
  python scripts/run_insight_job.py --backend openai
  python scripts/run_insight_job.py --dry-run        # 只顯示待處理數量，不生成
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

# 確保專案 root 在 import path 中
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import get_settings  # noqa: E402
from src.db.factory import make_database  # noqa: E402
from src.logger import AppLogger  # noqa: E402
from src.services.insight import insight_service  # noqa: E402
from src.services.llm.client import LLMClient  # noqa: E402

logger = AppLogger(__name__).get_logger()

VALID_BACKENDS = ["gemini", "anthropic", "openai", "ollama"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="手動觸發精選洞察生成排程",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
範例：
  python scripts/run_insight_job.py
  python scripts/run_insight_job.py --backend anthropic
  python scripts/run_insight_job.py --dry-run
        """,
    )
    parser.add_argument(
        "--backend",
        choices=VALID_BACKENDS,
        default=None,
        help=f"指定 LLM backend（預設使用 .env INSIGHT__LLM_BACKEND 設定）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只顯示待處理 Practice 數量，不實際生成",
    )
    return parser.parse_args()


async def run_job(backend: str, dry_run: bool) -> None:
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

    # ── 查詢待處理 Practice ───────────────────────────────────
    with database.get_session() as db:
        practices = insight_service.get_pending_practices(db)

    pending_count = len(practices)
    print(f"📋 待處理 Practice 數量：{pending_count}")

    if pending_count == 0:
        print("\n✨ 沒有待處理的 Practice，任務結束。")
        _print_summary(total=0, failed=0, elapsed=time.time() - start)
        database.teardown()
        return

    # ── Dry run 模式：只顯示清單 ──────────────────────────────
    if dry_run:
        print("\n[Dry Run] 以下 Practice 將被生成洞察：")
        for p in practices:
            print(f"  - practice_id={p.id}  title={p.title}")
        print("\n[Dry Run] 未實際生成，請移除 --dry-run 後再執行。")
        database.teardown()
        return

    # ── 實際生成 ─────────────────────────────────────────────
    llm_client = LLMClient(settings, effective_backend)
    total = 0
    failed = 0

    print(f"\n🚀 開始生成（共 {pending_count} 筆）...\n")

    for i, practice in enumerate(practices, 1):
        print(f"  [{i}/{pending_count}] practice_id={practice.id}  {practice.title}")
        try:
            with database.get_session() as db:
                result = await insight_service.generate_for_practice(
                    db, llm_client, practice
                )
            if result:
                total += 1
                print(f"    ✅ 已生成 insight_id={result.id}  cost=${result.llm_cost:.6f}")
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
    asyncio.run(run_job(backend=args.backend, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
