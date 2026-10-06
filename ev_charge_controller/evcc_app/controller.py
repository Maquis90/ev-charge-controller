from __future__ import annotations

from datetime import datetime, timedelta

from .models import Decision, Mode, Settings, State, VehicleConfig


def deadline_dt(deadline: str, now: datetime) -> datetime:
    h, m = (int(x) for x in deadline.split(":"))
    d = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return d if d > now else d + timedelta(days=1)


def watts_per_amp(v: VehicleConfig) -> float:
    return v.voltage * v.phases


def deadline_critical(s: Settings, st: State, v: VehicleConfig, now: datetime) -> bool:
    """True if the min-SoC target can only be reached by charging at full speed from now on."""
    if st.ev_soc is None or s.min_soc_tomorrow <= st.ev_soc:
        return False
    target = min(s.min_soc_tomorrow, s.max_soc)
    energy_kwh = (target - st.ev_soc) / 100 * v.capacity_kwh / v.efficiency
    max_kw = watts_per_amp(v) * min(s.max_amps, v.hard_max_amps) / 1000
    hours_needed = energy_kwh / max_kw
    hours_left = (deadline_dt(s.deadline, now) - now).total_seconds() / 3600
    return hours_left <= hours_needed * 1.1 + 0.25


def decide(s: Settings, st: State, v: VehicleConfig, now: datetime) -> Decision:
    """Pure, stateless target decision (no hysteresis)."""
    if s.mode == Mode.OFF:
        return Decision(charge=False, reason="Modus aus")
    if not st.plugged:
        return Decision(charge=False, reason="Fahrzeug nicht verbunden")
    if st.ev_soc is not None and st.ev_soc >= s.max_soc:
        return Decision(charge=False, reason="Max-SoC erreicht")

    lo = max(v.hard_min_amps, s.min_amps)
    hi = min(v.hard_max_amps, s.max_amps)

    if s.mode == Mode.EXPRESS:
        a = max(v.hard_min_amps, min(v.hard_max_amps, s.express_amps))
        return Decision(charge=True, amps=a, reason="Express")

    # SMART: car may use what the grid would otherwise receive plus its own draw
    avail = st.ev_w - st.grid_w - s.grid_offset_w
    if st.battery_soc is None or st.battery_soc >= s.battery_min_soc:
        avail += max(st.battery_w, 0) + s.battery_max_discharge_w
    amps = int(avail // watts_per_amp(v))

    if deadline_critical(s, st, v, now):
        return Decision(charge=True, amps=hi, reason="Deadline: Mindest-SoC sonst nicht erreichbar")
    if amps >= lo:
        return Decision(charge=True, amps=min(amps, hi), reason="PV-Überschuss")
    if s.pause_below_min:
        return Decision(charge=False, reason="Zu wenig Überschuss (Pause)")
    return Decision(charge=True, amps=lo, reason="Min-Strom (Netzbezug)")


class Controller:
    """Adds smoothing, start/stop delays and ramp limiting around decide()."""

    def __init__(self) -> None:
        self._want_since: datetime | None = None
        self._want: bool | None = None
        self._avg: list[tuple[datetime, float]] = []

    def step(self, s: Settings, st: State, v: VehicleConfig, now: datetime) -> Decision:
        raw = decide(s, st, v, now)
        if s.mode != Mode.SMART:
            self._want = None
            return raw

        # smooth amps over ~60 s to avoid flapping with cloud edges
        if raw.charge:
            self._avg = [(t, a) for t, a in self._avg if (now - t).total_seconds() <= 60]
            self._avg.append((now, raw.amps))
            raw.amps = round(sum(a for _, a in self._avg) / len(self._avg))
        else:
            self._avg = []

        # delays only for transitions caused by surplus (not for hard stops like max SoC)
        hard = raw.reason in ("Max-SoC erreicht", "Fahrzeug nicht verbunden", "Modus aus")
        if hard or raw.charge == st.charging:
            self._want = None
            return raw
        if self._want != raw.charge:
            self._want, self._want_since = raw.charge, now
        delay = s.start_delay_s if raw.charge else s.stop_delay_s
        if (now - self._want_since).total_seconds() >= delay:
            return raw
        keep = st.charging
        return Decision(charge=keep, amps=st.amps_now if keep else 0, reason=f"Warte ({raw.reason})")
