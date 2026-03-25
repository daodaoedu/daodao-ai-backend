from enum import Enum


class FeedItemType(str, Enum):
    PRACTICE = "practice"
    CHECKIN = "checkin"


class FeedTypeFilter(str, Enum):
    ALL = "all"
    PRACTICE = "practice"
    CHECKIN = "checkin"
