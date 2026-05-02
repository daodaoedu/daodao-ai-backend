from enum import Enum


class FeedItemType(str, Enum):
    PRACTICE = "practice"
    CHECKIN = "checkin"


class FeedReasonType(str, Enum):
    new_practice = "new_practice"
    new_release = "new_release"
    checked_in = "checked_in"
    cheered = "cheered"


class FeedTypeFilter(str, Enum):
    ALL = "all"
    PRACTICE = "practice"
    CHECKIN = "checkin"


class FeedSortBy(str, Enum):
    NEWEST = "newest"
    RECOMMENDED = "recommended"
