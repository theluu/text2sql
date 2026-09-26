from datetime import date

import pytest

from app.core.text import normalize
from app.llm.timeparse import parse_time

AS_OF = date(2026, 8, 31)


@pytest.mark.parametrize(
    ("text", "start", "end"),
    [
        ("doanh thu tháng này", "2026-08-01", "2026-09-01"),
        ("tháng trước", "2026-07-01", "2026-08-01"),
        ("last month", "2026-07-01", "2026-08-01"),
        ("quý này", "2026-07-01", "2026-10-01"),
        ("quy truoc", "2026-04-01", "2026-07-01"),
        ("quý 3 năm nay", "2026-07-01", "2026-10-01"),
        ("quý 2 năm ngoái", "2025-04-01", "2025-07-01"),
        ("Q4 last year", "2025-10-01", "2026-01-01"),
        ("Q2 2025", "2025-04-01", "2025-07-01"),
        ("năm 2025", "2025-01-01", "2026-01-01"),
        ("nam nay", "2026-01-01", "2027-01-01"),
        ("last year", "2025-01-01", "2026-01-01"),
        ("tháng 7/2025", "2025-07-01", "2025-08-01"),
        ("tháng 12", "2025-12-01", "2026-01-01"),  # not a future December
        ("in July 2025", "2025-07-01", "2025-08-01"),
        ("7 ngày qua", "2026-08-25", "2026-09-01"),
        ("last 3 months", "2026-06-01", "2026-09-01"),
        ("ba tháng gần đây", "2026-06-01", "2026-09-01"),
        ("mùa Tết 2026", "2026-01-01", "2026-02-16"),
        ("hôm qua", "2026-08-30", "2026-08-31"),
    ],
)
def test_parse_time(text: str, start: str, end: str) -> None:
    found = parse_time(normalize(text), AS_OF)
    assert found is not None
    assert (found.start.isoformat(), found.end.isoformat()) == (start, end)


def test_no_time_expression() -> None:
    assert parse_time(normalize("doanh thu theo khu vực"), AS_OF) is None


def test_previous_period() -> None:
    quarter = parse_time("quy nay", AS_OF)
    assert quarter is not None
    assert quarter.previous().start == date(2026, 4, 1)
