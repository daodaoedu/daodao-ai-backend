from enum import Enum
from typing import Literal, TypedDict


class FeedItemType(str, Enum):
    PRACTICE = "practice"
    CHECKIN = "checkin"


class FeedReasonType(str, Enum):
    new_practice = "new_practice"
    new_release = "new_release"
    checked_in = "checked_in"
    cheered = "cheered"


class SlotType(str, Enum):
    A = "A"
    B = "B"
    C = "C"


class FeedTypeFilter(str, Enum):
    ALL = "all"
    PRACTICE = "practice"
    CHECKIN = "checkin"


class FeedSortBy(str, Enum):
    NEWEST = "newest"
    RECOMMENDED = "recommended"


class ActivityType(str, Enum):
    COMMUNITY_EVENT = "community_event"
    FOLLOW_SUMMARY = "follow_summary"


class ActivityCardItem(TypedDict):
    item_type: Literal["activity"]
    activity_type: str
    event_text: str
    label: str
