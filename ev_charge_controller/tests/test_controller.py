from datetime import datetime, timedelta

from evcc_app.controller import Controller, decide
from evcc_app.models import Mode, Settings, State, VehicleConfig

V = VehicleConfig()
NOW = datetime(2026, 6, 1, 12, 0)


def st(**k):
    return State(**{"ev_soc": 40, "charging": True, "amps_now": 6, "ev_w": 4140, **k})


def test_express():
    d = decide(Settings(mode=Mode.EXPRESS, express_amps=10), st(), V, NOW)
    assert d.charge and d.amps == 10


def test_max_soc_stops():
    assert not decide(Settings(max_soc=40), st(), V, NOW).charge


def test_not_plugged():
    assert not decide(Settings(), st(plugged=False), V, NOW).charge


def test_smart_follows_surplus_capped():
    # exporting 2000 W while car draws 4140 W -> 6140 W / 690 = 8 A
    d = decide(Settings(max_amps=16), st(grid_w=-2000), V, NOW)
    assert d.amps == 8
    d = decide(Settings(max_amps=10), st(grid_w=-9000), V, NOW)
    assert d.amps == 10


def test_smart_min_amps_when_no_sun():
    d = decide(Settings(min_amps=6), st(grid_w=3000, ev_w=0), V, NOW)
    assert d.charge and d.amps == 6


def test_smart_pause_below_min():
    d = decide(Settings(pause_below_min=True), st(grid_w=3000, ev_w=0), V, NOW)
    assert not d.charge


def test_battery_discharge_and_priority():
    s = Settings(battery_max_discharge_w=2000, battery_min_soc=30)
    assert decide(s, st(grid_w=0, ev_w=0, battery_soc=50), V, NOW).amps == 6  # 2000/690=2 -> min
    s = Settings(battery_max_discharge_w=5000, battery_min_soc=30)
    assert decide(s, st(grid_w=0, ev_w=0, battery_soc=50), V, NOW).amps == 7
    assert decide(s, st(grid_w=0, ev_w=0, battery_soc=10, battery_w=3000), V, NOW).amps == 6


def test_smart_does_not_double_count_battery_discharge():
    s = Settings(min_amps=4, max_amps=16, battery_min_soc=50, battery_max_discharge_w=4000)
    state = st(amps_now=16, ev_w=11040, grid_w=3737, battery_w=-5874, battery_soc=98)

    d = decide(s, state, V, NOW)

    assert d.charge and d.amps == 7


def test_smart_applies_downward_amp_changes_without_smoothing_delay():
    c = Controller()
    s = Settings(min_amps=4, max_amps=16, battery_min_soc=50, battery_max_discharge_w=4000)
    c.step(s, st(amps_now=16, ev_w=11040, grid_w=-2000), V, NOW)

    d = c.step(s, st(amps_now=6, ev_w=11040, grid_w=3737, battery_w=-5874, battery_soc=98), V, NOW)

    assert d.charge and d.amps == 7


def test_deadline_forces_max():
    s = Settings(min_soc_tomorrow=80, max_soc=90, max_amps=16, deadline="13:00")
    d = decide(s, st(grid_w=3000, ev_w=0, ev_soc=30), V, NOW)
    assert d.amps == 16 and "Deadline" in d.reason
    s.deadline = "07:00"  # plenty of time -> no force
    assert "Deadline" not in decide(s, st(grid_w=3000, ev_w=0, ev_soc=30), V, NOW).reason


def test_stop_delay_with_pause():
    c = Controller()
    s = Settings(pause_below_min=True, stop_delay_s=300)
    s0 = st(grid_w=3000, ev_w=0)
    assert c.step(s, s0, V, NOW).charge  # still waiting
    assert not c.step(s, s0, V, NOW + timedelta(seconds=301)).charge
