"""Relative/absolute time expressions (VI with or without accents, EN) → [start, end) dates.

Input is `normalize()`d text. "Now" is `as_of`, the last day of data, so "tháng này" on
2026-08-31 means August 2026.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

NUM = {"mot": 1, "hai": 2, "ba": 3, "bon": 4, "tu": 4, "nam": 5, "sau": 6, "bay": 7, "tam": 8,
       "chin": 9, "muoi": 10, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
       "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12}  # fmt: skip
MONTHS_EN = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], 1
)}  # fmt: skip
MONTHS_EN |= {m[:3]: i for m, i in list(MONTHS_EN.items())}


@dataclass(frozen=True)
class TimeRange:
    start: date
    end: date  # exclusive
    label_vi: str
    label_en: str
    grain: str  # day | week | month | quarter | year | custom

    def previous(self) -> "TimeRange":
        """Same-length period right before (MoM for a month, QoQ for a quarter, …)."""
        if self.grain == "month":
            start = _add_months(self.start, -1)
            return TimeRange(start, self.start, f"tháng {start.month}/{start.year}",
                             f"{start:%b %Y}", "month")  # fmt: skip
        if self.grain == "quarter":
            start = _add_months(self.start, -3)
            q = (start.month - 1) // 3 + 1
            return TimeRange(start, self.start, f"quý {q}/{start.year}", f"Q{q} {start.year}",
                             "quarter")  # fmt: skip
        if self.grain == "year":
            start = date(self.start.year - 1, 1, 1)
            return TimeRange(start, self.start, f"năm {start.year}", str(start.year), "year")
        length = self.end - self.start
        return TimeRange(self.start - length, self.start, "kỳ trước", "previous period", "custom")


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def month_range(year: int, month: int) -> TimeRange:
    start = date(year, month, 1)
    return TimeRange(
        start, _add_months(start, 1), f"tháng {month}/{year}", f"{start:%b %Y}", "month"
    )


def quarter_range(year: int, quarter: int) -> TimeRange:
    start = date(year, 3 * (quarter - 1) + 1, 1)
    return TimeRange(start, _add_months(start, 3), f"quý {quarter}/{year}", f"Q{quarter} {year}",
                     "quarter")  # fmt: skip


def year_range(year: int) -> TimeRange:
    return TimeRange(date(year, 1, 1), date(year + 1, 1, 1), f"năm {year}", str(year), "year")


def _number(token: str) -> int | None:
    return int(token) if token.isdigit() else NUM.get(token)


def _year_after(text: str, default: int) -> int:
    """Year for "quý 3 năm nay", "Q2 2025", "tháng 7 năm ngoái"; `default` if unstated."""
    match = re.search(r"\b(20\d\d)\b", text)
    if match:
        return int(match.group(1))
    if re.search(r" (nam ngoai|nam truoc|nam roi|last year|previous year) ", text):
        return default - 1
    return default


def _not_future(
    found: TimeRange, text: str, today: date, make: Callable[[int, int], TimeRange], n: int
) -> TimeRange:
    """ "tháng 12" asked on 2026-08-31 means the last December, not a future one."""
    explicit_year = re.search(r"\b20\d\d\b", text) or re.search(r" nam (nay|ngoai|truoc) ", text)
    if found.start > today and not explicit_year:
        return make(found.start.year - 1, n)
    return found


def parse_time(text: str, as_of: date) -> TimeRange | None:
    t = f" {text} "
    today = as_of
    this_month = month_range(today.year, today.month)
    this_quarter = quarter_range(today.year, (today.month - 1) // 3 + 1)

    if re.search(r" (hom nay|today) ", t):
        return TimeRange(today, today + timedelta(1), "hôm nay", "today", "day")
    if re.search(r" (hom qua|yesterday) ", t):
        day = today - timedelta(1)
        return TimeRange(day, today, "hôm qua", "yesterday", "day")

    match = re.search(r" (\w+) (ngay|days?|tuan|weeks?|thang|months?) (qua|gan day|gan nhat|vua qua) ", t) \
        or re.search(r" (?:last|past|previous) (\w+) (days?|weeks?|months?) ", t)  # fmt: skip
    if match:
        count = _number(match.group(1))
        unit = match.group(2)
        if count:
            if unit.startswith(("ngay", "day")):
                start = today - timedelta(count - 1)
                return TimeRange(start, today + timedelta(1), f"{count} ngày qua",
                                 f"last {count} days", "custom")  # fmt: skip
            if unit.startswith(("tuan", "week")):
                start = today - timedelta(7 * count - 1)
                return TimeRange(start, today + timedelta(1), f"{count} tuần qua",
                                 f"last {count} weeks", "custom")  # fmt: skip
            start = _add_months(this_month.start, -(count - 1))
            return TimeRange(start, this_month.end, f"{count} tháng gần nhất",
                             f"last {count} months", "custom")  # fmt: skip

    if re.search(r" (tuan nay|this week) ", t):
        start = today - timedelta(today.weekday())
        return TimeRange(start, today + timedelta(1), "tuần này", "this week", "week")
    if re.search(r" (tuan truoc|last week|previous week) ", t):
        start = today - timedelta(today.weekday() + 7)
        return TimeRange(start, start + timedelta(7), "tuần trước", "last week", "week")

    match = re.search(r" (?:ngay )?([0-3]?\d) (1[0-2]|0?[1-9]) (20\d\d) ", t)
    if match:  # "ngày 11/11/2025", "12/12/2025"
        day = date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
        return TimeRange(day, day + timedelta(1), f"ngày {day:%d/%m/%Y}", f"{day:%d %b %Y}", "day")
    match = re.search(r" (?:quy|q|quarter) ([1-4]) ", t) or re.search(r" q([1-4]) ", t)
    if match:
        found = quarter_range(_year_after(t, today.year), int(match.group(1)))
        return _not_future(found, t, today, quarter_range, int(match.group(1)))
    match = re.search(r" thang (1[0-2]|[1-9]) ", t) or re.search(r" (1[0-2]|[1-9]) (20\d\d) ", t)
    if match:
        found = month_range(_year_after(t, today.year), int(match.group(1)))
        return _not_future(found, t, today, month_range, int(match.group(1)))
    for name, number in MONTHS_EN.items():
        if f" {name} " in t:
            found = month_range(_year_after(t, today.year), number)
            return _not_future(found, t, today, month_range, number)
    if re.search(r" (thang nay|this month|thang hien tai|current month) ", t):
        return this_month
    if re.search(r" (thang truoc|last month|previous month|thang vua roi) ", t):
        return this_month.previous()
    if re.search(r" (quy nay|this quarter|quy hien tai|current quarter) ", t):
        return this_quarter
    if re.search(r" (quy truoc|last quarter|previous quarter) ", t):
        return this_quarter.previous()
    if re.search(r" (nam nay|this year|current year) ", t):
        return year_range(today.year)
    if re.search(r" (nam ngoai|nam truoc|nam roi|last year|previous year) ", t):
        return year_range(today.year - 1)
    if re.search(r" (tet) ", t):
        year = _year_after(t, today.year)
        return TimeRange(date(year, 1, 1), date(year, 2, 16), f"mùa Tết {year}", f"Tet {year}",
                         "custom")  # fmt: skip
    if re.search(r" (11 11|ngay doc than|singles day) ", t):
        year = _year_after(t, today.year - (1 if today < date(today.year, 11, 12) else 0))
        return TimeRange(date(year, 11, 11), date(year, 11, 12), f"ngày 11/11/{year}",
                         f"11.11 {year}", "day")  # fmt: skip

    match = re.search(r" (?:nam |year |in )?(20\d\d) ", t)
    if match:
        return year_range(int(match.group(1)))
    return None
