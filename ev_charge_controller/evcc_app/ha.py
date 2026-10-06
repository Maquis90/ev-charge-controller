from __future__ import annotations

import aiohttp


class HAClient:
    def __init__(self, url: str, token: str) -> None:
        self._url = url.rstrip("/")
        self._h = {"Authorization": f"Bearer {token}"}
        self._s: aiohttp.ClientSession | None = None

    async def _session(self) -> aiohttp.ClientSession:
        if self._s is None or self._s.closed:
            self._s = aiohttp.ClientSession(headers=self._h, timeout=aiohttp.ClientTimeout(total=15))
        return self._s

    async def close(self) -> None:
        if self._s:
            await self._s.close()

    async def state(self, entity_id: str) -> dict:
        s = await self._session()
        async with s.get(f"{self._url}/api/states/{entity_id}") as r:
            r.raise_for_status()
            return await r.json()

    async def call(self, domain: str, service: str, data: dict) -> None:
        s = await self._session()
        async with s.post(f"{self._url}/api/services/{domain}/{service}", json=data) as r:
            r.raise_for_status()

    async def number(self, entity_id: str) -> float | None:
        """Numeric state in base units (kW->W) or None if unavailable."""
        st = await self.state(entity_id)
        try:
            val = float(st["state"])
        except (ValueError, TypeError):
            return None
        if st.get("attributes", {}).get("unit_of_measurement") == "kW":
            val *= 1000
        return val

    async def is_on(self, entity_id: str) -> bool | None:
        st = (await self.state(entity_id))["state"]
        if st in ("unavailable", "unknown"):
            return None
        return st in ("on", "home", "connected", "charging", "true", "True")
