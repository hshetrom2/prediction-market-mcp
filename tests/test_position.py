import pytest

from pm_mcp.position import Fill, Position, second_leg_cap


def close(a, b, tol=1e-9):
    return abs(a - b) <= tol


def test_partial_fills_average_cost_with_fee():
    p = Position([Fill("YES", 60, 0.40), Fill("YES", 40, 0.45, fee=1.0)])
    assert close(p.qty("YES"), 100)
    assert close(p.avg_cost("YES"), 0.43)      # (24 + 18 + 1) / 100


def test_one_sided_is_a_bet_not_a_lock():
    p = Position([Fill("YES", 100, 0.42)])
    assert close(p.pnl_if("YES"), 58.0)
    assert close(p.pnl_if("NO"), -42.0)
    assert p.locked_pnl() < 0


def test_locked_only_when_combined_cost_under_one():
    assert close(Position([Fill("YES", 100, 0.42), Fill("NO", 100, 0.53)]).locked_pnl(), 5.0)
    assert close(Position([Fill("YES", 100, 0.55), Fill("NO", 100, 0.50)]).locked_pnl(), -5.0)


def test_cap_full_hedge_and_fee():
    p = Position([Fill("YES", 100, 0.42)])
    assert close(second_leg_cap(p, 0.02), 0.56)            # 1 - 0.42 - 0.02
    assert close(second_leg_cap(p, 0.02, 0.01), 0.55)


def test_cap_after_partial_second_leg_hits_target_exactly():
    p = Position([Fill("YES", 100, 0.42), Fill("NO", 40, 0.50)])
    cap = second_leg_cap(p, 0.02)
    assert close(cap, 0.60)                                # (98 - 62) / 60
    p.fills.append(Fill("NO", 60, cap))
    assert close(p.locked_pnl(), 2.0)


def test_cap_none_when_balanced_empty_or_impossible():
    assert second_leg_cap(Position()) is None
    assert second_leg_cap(Position([Fill("YES", 10, 0.4), Fill("NO", 10, 0.5)])) is None
    assert second_leg_cap(Position([Fill("YES", 100, 0.99)]), 0.02) is None


def test_empty_position_has_no_average_cost():
    p = Position()
    assert p.avg_cost("YES") is None and p.total_cost() == 0 and p.leading_side() is None


@pytest.mark.parametrize("bad", [
    dict(side="YES", qty=10, price=42), dict(side="YES", qty=0, price=0.4),
    dict(side="UP", qty=10, price=0.4), dict(side="NO", qty=1, price=0.4, fee=-1),
    dict(side="NO", qty=1, price=1.0), dict(side="NO", qty=1, price=0.0),
])
def test_bad_fills_rejected(bad):
    with pytest.raises(ValueError):
        Fill(**bad)
