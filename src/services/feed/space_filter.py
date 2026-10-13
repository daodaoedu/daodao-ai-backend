"""
Feed 空間篩選（daodao#213 FR-D3）

主頁動態牆以「空間」篩選：個人實踐、共同挑戰、使用者參與的活動課程。
空間由 practices.cohort_id 判定：
- personal：不屬任何 cohort 的實踐
- challenge：所屬 cohort 的 program.kind = 'challenge'
- cohort:<id>：屬指定 cohort 的實踐
多選時取聯集。只縮小結果，不改變 feed 既有的隱私條件。
"""

import re
from dataclasses import dataclass
from typing import Optional

PERSONAL = "personal"
CHALLENGE = "challenge"
# Router 以此做 query 驗證（不合法回 422）
SPACE_VALUE_PATTERN = r"^(personal|challenge|cohort:[1-9][0-9]{0,18})$"
_COHORT_PATTERN = re.compile(r"^cohort:([1-9][0-9]{0,18})$")
_CHALLENGE_KIND = "challenge"


@dataclass(frozen=True)
class SpaceFilter:
    personal: bool = False
    challenge: bool = False
    cohort_ids: tuple[int, ...] = ()


def parse_space_filter(values: Optional[list[str]]) -> Optional[SpaceFilter]:
    """解析 query 參數；沒給值回 None（不篩選），值不合法 raise ValueError。"""
    if not values:
        return None

    personal = False
    challenge = False
    cohort_ids: set[int] = set()
    for value in values:
        if value == PERSONAL:
            personal = True
        elif value == CHALLENGE:
            challenge = True
        else:
            match = _COHORT_PATTERN.match(value)
            if not match:
                raise ValueError(f"invalid space filter: {value!r}")
            cohort_ids.add(int(match.group(1)))

    return SpaceFilter(
        personal=personal, challenge=challenge, cohort_ids=tuple(sorted(cohort_ids))
    )


def restrict_to_joined_cohorts(
    space_filter: Optional[SpaceFilter], joined_cohort_ids: set[int]
) -> Optional[SpaceFilter]:
    """活動課程只能篩使用者已參加（joined）的 cohort，其餘 cohort id 移除；未登入時集合為空。"""
    if space_filter is None:
        return None
    return SpaceFilter(
        personal=space_filter.personal,
        challenge=space_filter.challenge,
        cohort_ids=tuple(c for c in space_filter.cohort_ids if c in joined_cohort_ids),
    )


def matches_nothing(space_filter: Optional[SpaceFilter]) -> bool:
    """有篩選但沒有任何空間（例如只選了未參加的活動課程）。"""
    return space_filter is not None and space_filter == SpaceFilter()


def build_space_clause(
    space_filter: Optional[SpaceFilter], practice_alias: str
) -> tuple[str, dict]:
    """回傳 (WHERE 子句, bind params)；None 代表不篩選回 ("", {})，空的篩選不符合任何資料。"""
    if space_filter is None:
        return "", {}

    p = practice_alias
    conditions: list[str] = []
    params: dict = {}

    if space_filter.personal:
        conditions.append(f"{p}.cohort_id IS NULL")
    if space_filter.challenge:
        conditions.append(
            "EXISTS (SELECT 1 FROM cohorts sco"
            " JOIN programs spr ON spr.id = sco.program_id"
            f" WHERE sco.id = {p}.cohort_id AND spr.kind = :space_challenge_kind)"
        )
        params["space_challenge_kind"] = _CHALLENGE_KIND
    if space_filter.cohort_ids:
        conditions.append(f"{p}.cohort_id = ANY(:space_cohort_ids)")
        params["space_cohort_ids"] = list(space_filter.cohort_ids)

    if not conditions:
        return "FALSE", {}
    return "(" + " OR ".join(conditions) + ")", params


def space_cache_token(space_filter: Optional[SpaceFilter]) -> str:
    """cache key 用的穩定字串，與參數順序無關。"""
    if space_filter is None:
        return "__all__"
    parts: list[str] = []
    if space_filter.personal:
        parts.append(PERSONAL)
    if space_filter.challenge:
        parts.append(CHALLENGE)
    parts.extend(f"cohort:{cohort_id}" for cohort_id in space_filter.cohort_ids)
    return ",".join(parts)
