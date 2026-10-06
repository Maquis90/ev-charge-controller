from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Mode(str, Enum):
    OFF = "off"
    EXPRESS = "express"
    SMART = "smart"


class Settings(BaseModel):
    """Runtime-editable settings (persisted, changed via UI)."""

    mode: Mode = Mode.SMART
    # Express
    express_amps: int = Field(16, ge=1, le=32)
    # Smart
    min_amps: int = Field(6, ge=1, le=32)
    max_amps: int = Field(16, ge=1, le=32)
    pause_below_min: bool = False  # True: pause instead of drawing grid power at min_amps
    grid_offset_w: int = 0  # tolerated grid import (+) / required export (-) in smart mode
    battery_min_soc: int = Field(30, ge=0, le=100)  # below: house battery has priority
    battery_max_discharge_w: int = Field(0, ge=0)  # house battery power the car may use
    start_delay_s: int = 60
    stop_delay_s: int = 300
    # Targets
    max_soc: int = Field(80, ge=1, le=100)
    min_soc_tomorrow: int = Field(0, ge=0, le=100)  # must be reached by deadline
    deadline: str = "07:00"  # HH:MM local time, next occurrence


class VehicleConfig(BaseModel):
    capacity_kwh: float = 60.0
    efficiency: float = 0.9
    voltage: int = 230
    phases: int = 3
    hard_min_amps: int = 5  # Tesla minimum
    hard_max_amps: int = 32


class Entities(BaseModel):
    pv_power: str
    grid_power: str  # positive = import
    battery_power: str | None = None  # positive = charging
    battery_soc: str | None = None
    house_power: str | None = None  # info only
    ev_soc: str
    ev_plugged: str | None = None  # binary_sensor / sensor
    ev_charging_switch: str
    ev_amps_number: str
    ev_power: str | None = None  # optional measured EV power
    invert_grid: bool = False
    invert_battery: bool = False


class HAConfig(BaseModel):
    url: str = "http://homeassistant.local:8123"
    token: str = ""
    interval_s: int = 10


class AppConfig(BaseModel):
    ha: HAConfig = HAConfig()
    entities: Entities
    vehicle: VehicleConfig = VehicleConfig()
    settings: Settings = Settings()
    dry_run: bool = False


class State(BaseModel):
    pv_w: float = 0
    grid_w: float = 0  # + import
    battery_w: float = 0  # + charging
    battery_soc: float | None = None
    house_w: float | None = None
    ev_soc: float | None = None
    plugged: bool = True
    ev_w: float = 0
    charging: bool = False
    amps_now: int = 0


class Decision(BaseModel):
    charge: bool
    amps: int = 0
    reason: str = ""
