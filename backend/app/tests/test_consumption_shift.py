"""Unit tests for group-based consumption accumulation logic in dashboard.py."""
from __future__ import annotations

import zoneinfo
from datetime import datetime, timezone

import pytest

from app.api.v1.dashboard import _parse_hhmm, _fmt_hhmm
from app.processing.derivations import flow_from_level

_TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
_CAP_L = 40_000.0


# ---------------------------------------------------------------------------
# _parse_hhmm / _fmt_hhmm
# ---------------------------------------------------------------------------

def test_parse_hhmm_valid():
    assert _parse_hhmm("07:00", 0) == 7 * 60
    assert _parse_hhmm("19:30", 0) == 19 * 60 + 30
    assert _parse_hhmm("00:00", 0) == 0
    assert _parse_hhmm("23:59", 0) == 23 * 60 + 59


def test_parse_hhmm_invalid_returns_default():
    assert _parse_hhmm("", 99) == 99
    assert _parse_hhmm("25:00", 99) == 99
    assert _parse_hhmm("07:60", 99) == 99
    assert _parse_hhmm("abc", 99) == 99
    assert _parse_hhmm("7:0:0", 99) == 99


def test_fmt_hhmm():
    assert _fmt_hhmm(7 * 60) == "07:00"
    assert _fmt_hhmm(19 * 60 + 30) == "19:30"


# ---------------------------------------------------------------------------
# Group consumption accumulation logic (mirrors dashboard.py device loop)
# ---------------------------------------------------------------------------

def _accumulate_groups(
    groups_pts: list[list[tuple[int, float]]],
    win_start: str = "07:00",
    win_end: str = "19:00",
) -> dict[int, float]:
    """Replicate the group accumulation logic from get_dashboard.

    groups_pts: list of point-series, one per group (device index).
    Returns dict[group_index, consumed_l].
    """
    win_start_min = _parse_hhmm(win_start, 7 * 60)
    win_end_min = _parse_hhmm(win_end, 19 * 60)
    cons_by_group: dict[int, float] = {i: 0.0 for i in range(len(groups_pts))}

    for i, pts in enumerate(groups_pts):
        for bucket_end_ms, delta_l in flow_from_level.net_flow_hourly(pts, _CAP_L, "America/Sao_Paulo"):
            consumed = max(0.0, -delta_l)
            if consumed <= 0.0:
                continue
            bucket_start_ms = bucket_end_ms - 3_600_000
            local_dt = datetime.fromtimestamp(bucket_start_ms / 1000, tz=_TZ)
            minute_of_day = local_dt.hour * 60 + local_dt.minute
            if win_start_min == win_end_min:
                in_window = True
            elif win_start_min < win_end_min:
                in_window = win_start_min <= minute_of_day < win_end_min
            else:
                in_window = minute_of_day >= win_start_min or minute_of_day < win_end_min
            if in_window:
                cons_by_group[i] += consumed

    return cons_by_group


def _ms(hour_local: int, day_offset: int = 0) -> int:
    """Return epoch ms for a given local hour (America/Sao_Paulo) at 2024-01-15 + offset days."""
    dt = datetime(2024, 1, 15 + day_offset, hour_local, 0, 0, tzinfo=_TZ)
    return int(dt.timestamp() * 1000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_daytime_drop_counts_for_group():
    """Tank drops 800 L during daytime (10h) → counted in group 0 with 07–19 window."""
    pts = [(_ms(10), 80.0), (_ms(11), 78.0)]
    result = _accumulate_groups([pts])
    assert result[0] > 0
    assert abs(result[0] - 800.0) < 1.0


def test_nighttime_drop_outside_window():
    """Tank drops at 22h → outside 07–19 window → group 0 = 0."""
    pts = [(_ms(22), 90.0), (_ms(23), 88.0)]
    result = _accumulate_groups([pts], win_start="07:00", win_end="19:00")
    assert result[0] == 0.0


def test_nighttime_drop_inside_window_with_wrap():
    """Night window 19–07 includes 22h → counted."""
    pts = [(_ms(22), 90.0), (_ms(23), 88.0)]
    result = _accumulate_groups([pts], win_start="19:00", win_end="07:00")
    assert result[0] > 0
    assert abs(result[0] - 800.0) < 1.0


def test_dia_inteiro_counts_all():
    """win_start == win_end ('00:00'–'00:00') = dia inteiro → both day and night counted."""
    pts_day = [(_ms(10), 80.0), (_ms(11), 78.0)]
    pts_night = [(_ms(22), 90.0), (_ms(23), 88.0)]
    # Group 0: day drop; group 1: night drop
    result = _accumulate_groups([pts_day, pts_night], win_start="00:00", win_end="00:00")
    assert result[0] > 0
    assert result[1] > 0


def test_two_groups_isolated():
    """Each group accumulates its own series independently."""
    pts_g0 = [(_ms(10), 80.0), (_ms(11), 78.0)]  # 800 L day
    pts_g1 = [(_ms(10), 60.0), (_ms(11), 57.0)]  # 1200 L day
    result = _accumulate_groups([pts_g0, pts_g1])
    assert abs(result[0] - 800.0) < 1.0
    assert abs(result[1] - 1200.0) < 1.0


def test_share_sums_to_one():
    """share of each group sums to 1.0 when both have consumption."""
    pts_g0 = [(_ms(10), 80.0), (_ms(11), 78.0)]
    pts_g1 = [(_ms(10), 60.0), (_ms(11), 57.0)]
    cons = _accumulate_groups([pts_g0, pts_g1])
    total_l = sum(cons.values())
    assert total_l > 0
    shares = [round(cons[i] / total_l, 4) for i in range(2)]
    assert abs(sum(shares) - 1.0) < 0.001


def test_reabastecimento_ignored():
    """Tank fills → not counted as consumption for any group."""
    pts = [(_ms(10), 80.0), (_ms(11), 104.0)]
    result = _accumulate_groups([pts])
    assert result[0] == 0.0


def test_group_zero_consumption_present():
    """Group with no drops still appears in result with 0."""
    pts_g0 = [(_ms(10), 80.0), (_ms(11), 78.0)]
    pts_g1 = [(_ms(10), 50.0), (_ms(11), 50.0)]  # flat, no drop
    result = _accumulate_groups([pts_g0, pts_g1])
    assert result[0] > 0
    assert result[1] == 0.0


def test_total_m3():
    """Total across groups = sum of individual groups / 1000."""
    pts_g0 = [(_ms(10), 80.0), (_ms(11), 78.0)]   # 800 L
    pts_g1 = [(_ms(10), 60.0), (_ms(11), 57.0)]   # 1200 L
    cons = _accumulate_groups([pts_g0, pts_g1])
    total_m3 = round(sum(cons.values()) / 1000, 2)
    assert total_m3 == 2.0
