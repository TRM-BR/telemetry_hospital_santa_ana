"""Unit tests for shift-based consumption accumulation logic in dashboard.py."""
from __future__ import annotations

import zoneinfo
from datetime import datetime, timezone

import pytest

from app.api.v1.dashboard import _parse_hhmm, _fmt_hhmm
from app.processing.derivations import flow_from_level

_TZ = zoneinfo.ZoneInfo("America/Sao_Paulo")
_CAP_L = 40_000.0


# ---------------------------------------------------------------------------
# _parse_hhmm
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
# Consumption accumulation logic (mirrors dashboard.py device loop)
# ---------------------------------------------------------------------------

def _accumulate(pts, shift_start="07:00", shift_end="19:00"):
    """Replicate the shift accumulation logic from get_dashboard."""
    shift_start_min = _parse_hhmm(shift_start, 7 * 60)
    shift_end_min = _parse_hhmm(shift_end, 19 * 60)
    p1 = 0.0
    p2 = 0.0
    for bucket_end_ms, delta_l in flow_from_level.net_flow_hourly(pts, _CAP_L, "America/Sao_Paulo"):
        consumed = max(0.0, -delta_l)
        if consumed <= 0.0:
            continue
        bucket_start_ms = bucket_end_ms - 3_600_000
        local_dt = datetime.fromtimestamp(bucket_start_ms / 1000, tz=_TZ)
        minute_of_day = local_dt.hour * 60 + local_dt.minute
        if shift_start_min < shift_end_min:
            in_p1 = shift_start_min <= minute_of_day < shift_end_min
        else:
            in_p1 = minute_of_day >= shift_start_min or minute_of_day < shift_end_min
        if in_p1:
            p1 += consumed
        else:
            p2 += consumed
    return p1, p2


def _ms(hour_local: int, day_offset: int = 0) -> int:
    """Return epoch ms for a given local hour (America/Sao_Paulo) at 2024-01-15 + offset days."""
    dt = datetime(2024, 1, 15 + day_offset, hour_local, 0, 0, tzinfo=_TZ)
    return int(dt.timestamp() * 1000)


def test_consumption_daytime_drop():
    """Tank drops 800 L during daytime (10h) → counted in period 1 (07-19)."""
    cap = _CAP_L
    # 80% at 10h, 78% at 11h → drop = 800 L
    pts = [
        (_ms(10), 80.0),
        (_ms(11), 78.0),
    ]
    p1, p2 = _accumulate(pts)
    assert p1 > 0
    assert p2 == 0.0
    # 800 L expected (2% of 40000)
    assert abs(p1 - 800.0) < 1.0


def test_reabastecimento_ignored():
    """Tank fills 9600 L at 11h → not counted as consumption."""
    pts = [
        (_ms(10), 80.0),
        (_ms(11), 104.0),  # unrealistic fill but tests sign
    ]
    p1, p2 = _accumulate(pts)
    assert p1 == 0.0
    assert p2 == 0.0


def test_nighttime_drop_counted_in_period2():
    """Tank drops at 22h → counted in period 2 (19-07)."""
    pts = [
        (_ms(22), 90.0),
        (_ms(23), 88.0),
    ]
    p1, p2 = _accumulate(pts)
    assert p1 == 0.0
    assert p2 > 0
    assert abs(p2 - 800.0) < 1.0


def test_total_m3():
    """1600 L total → 1.6 m³."""
    pts = [
        (_ms(10), 80.0),
        (_ms(11), 78.0),
        (_ms(22), 90.0),
        (_ms(23), 88.0),
    ]
    p1, p2 = _accumulate(pts)
    total_m3 = round((p1 + p2) / 1000, 2)
    assert total_m3 == 1.6
