from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime
from pathlib import Path

import yaml

from .controller import Controller
from .ha import HAClient
from .models import AppConfig, Decision, Settings, State

log = logging.getLogger("evcc")
MIN_CMD_INTERVAL_S = 20  # Tesla BLE is slow / rate limited


def load_config() -> AppConfig:
    sup_token = os.getenv("SUPERVISOR_TOKEN")
    if sup_token:  # running as Home Assistant add-on
        raw = json.loads(Path("/data/options.json").read_text())
        raw["ha"] = {"url": "http://supervisor/core", "token": sup_token, "interval_s": raw.pop("interval_s", 10)}
        raw["entities"] = {k: v for k, v in raw["entities"].items() if v not in (None, "")}
        raw.pop("log_level", None)
        cfg = AppConfig.model_validate(raw)
    else:
        path = Path(os.getenv("EVCC_CONFIG", "config.yaml"))
        cfg = AppConfig.model_validate(yaml.safe_load(path.read_text()))
    sf = Path(os.getenv("EVCC_DATA", ".")) / "settings.json"
    if sf.exists():
        cfg.settings = Settings.model_validate_json(sf.read_text())
    return cfg


class Runner:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.ha = HAClient(cfg.ha.url, cfg.ha.token)
        self.ctrl = Controller()
        self.state = State()
        self.decision = Decision(charge=False, reason="Start")
        self.error: str | None = None
        self._last_cmd = 0.0
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        await self.ha.close()

    def save_settings(self, s: Settings) -> None:
        self.cfg.settings = s
        p = Path(os.getenv("EVCC_DATA", ".")) / "settings.json"
        p.write_text(s.model_dump_json(indent=2))

    async def read_state(self) -> State:
        e, v, ha = self.cfg.entities, self.cfg.vehicle, self.ha
        st = State()
        st.pv_w = await ha.number(e.pv_power) or 0
        st.grid_w = await ha.number(e.grid_power) or 0
        if e.invert_grid:
            st.grid_w = -st.grid_w
        if e.battery_power:
            st.battery_w = await ha.number(e.battery_power) or 0
            if e.invert_battery:
                st.battery_w = -st.battery_w
        if e.battery_soc:
            st.battery_soc = await ha.number(e.battery_soc)
        if e.house_power:
            st.house_w = await ha.number(e.house_power)
        st.ev_soc = await ha.number(e.ev_soc)
        if e.ev_plugged:
            st.plugged = bool(await ha.is_on(e.ev_plugged))
        st.charging = bool(await ha.is_on(e.ev_charging_switch))
        st.amps_now = int(await ha.number(e.ev_amps_number) or 0)
        if e.ev_power:
            st.ev_w = await ha.number(e.ev_power) or 0
        elif st.charging:
            st.ev_w = st.amps_now * v.voltage * v.phases
        return st

    async def apply(self, d: Decision) -> None:
        e, st = self.cfg.entities, self.state
        if time.monotonic() - self._last_cmd < MIN_CMD_INTERVAL_S:
            return
        acts: list[tuple[str, str, dict]] = []
        if d.charge and d.amps != st.amps_now:
            acts.append(("number", "set_value", {"entity_id": e.ev_amps_number, "value": d.amps}))
        if d.charge != st.charging:
            acts.append(("switch", "turn_on" if d.charge else "turn_off", {"entity_id": e.ev_charging_switch}))
        if not acts:
            return
        for dom, svc, data in acts:
            log.info("%s.%s %s", dom, svc, data)
            if not self.cfg.dry_run:
                await self.ha.call(dom, svc, data)
        self._last_cmd = time.monotonic()

    async def _loop(self) -> None:
        while True:
            try:
                self.state = await self.read_state()
                self.decision = self.ctrl.step(self.cfg.settings, self.state, self.cfg.vehicle, datetime.now())
                await self.apply(self.decision)
                self.error = None
            except asyncio.CancelledError:
                raise
            except Exception as ex:  # keep running on transient HA/BLE errors
                self.error = str(ex)
                log.exception("loop error")
            await asyncio.sleep(self.cfg.ha.interval_s)

    def snapshot(self) -> dict:
        return {
            "state": self.state.model_dump(),
            "decision": self.decision.model_dump(),
            "settings": self.cfg.settings.model_dump(mode="json"),
            "kw_per_amp": self.cfg.vehicle.voltage * self.cfg.vehicle.phases / 1000,
            "error": self.error,
            "dry_run": self.cfg.dry_run,
        }
