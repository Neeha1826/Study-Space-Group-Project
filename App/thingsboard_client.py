from __future__ import annotations

import time
from typing import Any

import requests


class ThingsBoardError(Exception):
    pass


def _as_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _as_int(x: Any) -> int | None:
    f = _as_float(x)
    if f is None:
        return None
    return int(round(f))


class ThingsBoardClient:
    """
    ThingsBoard REST: login, then read device time-series / latest telemetry.
    Telemetry key names should match what the Pi sends to TB (e.g. CAPACITY, TEMPERATURE, …).
    """

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        *,
        verify_ssl: bool = True,
        timeout: int = 20,
    ) -> None:
        self.base = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.verify = verify_ssl
        self.timeout = timeout
        self._token: str | None = None

    def _login(self) -> str:
        url = f'{self.base}/api/auth/login'
        r = requests.post(
            url,
            json={'username': self.username, 'password': self.password},
            timeout=self.timeout,
            verify=self.verify,
        )
        if r.status_code != 200:
            raise ThingsBoardError(f'ThingsBoard login failed: HTTP {r.status_code} {r.text[:200]}')
        data = r.json()
        token = data.get('token')
        if not token:
            raise ThingsBoardError('ThingsBoard login: missing token in response')
        self._token = str(token)
        return self._token

    def _headers(self) -> dict[str, str]:
        if not self._token:
            self._login()
        return {'X-Authorization': f'Bearer {self._token}'}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f'{self.base}{path}' if path.startswith('/') else f'{self.base}/{path}'
        r = requests.get(
            url,
            headers=self._headers(),
            params=params or {},
            timeout=self.timeout,
            verify=self.verify,
        )
        if r.status_code == 401:
            self._token = None
            r = requests.get(
                url,
                headers=self._headers(),
                params=params or {},
                timeout=self.timeout,
                verify=self.verify,
            )
        if r.status_code != 200:
            raise ThingsBoardError(f'TB GET {path} -> HTTP {r.status_code} {r.text[:300]}')
        return r.json()

    def get_latest_telemetry(
        self,
        device_id: str,
        keys: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        if not device_id or not keys:
            return {}
        now = int(time.time() * 1000)
        start = now - 14 * 24 * 3600 * 1000
        keys_param = ','.join(keys)
        return self._get(
            f'/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries',
            {
                'keys': keys_param,
                'startTs': start,
                'endTs': now,
                'limit': 1,
                'agg': 'NONE',
                'orderBy': 'DESC',
                'useStrictDataTypes': 'false',
            },
        )

    def get_timeseries(
        self,
        device_id: str,
        keys: list[str],
        *,
        start_ts: int,
        end_ts: int,
        limit: int,
        order_by: str = 'ASC',
    ) -> dict[str, list[dict[str, Any]]]:
        if not device_id or not keys:
            return {}
        keys_param = ','.join(keys)
        return self._get(
            f'/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries',
            {
                'keys': keys_param,
                'startTs': start_ts,
                'endTs': end_ts,
                'limit': max(1, limit),
                'agg': 'NONE',
                'orderBy': order_by,
                'useStrictDataTypes': 'false',
            },
        )

    @staticmethod
    def pick_latest_ts(payload: dict[str, list[dict[str, Any]]], keys: list[str]) -> int | None:
        latest: int | None = None
        for k in keys:
            series = payload.get(k) or []
            if not series:
                continue
            ts = int(series[0].get('ts', 0))
            if latest is None or ts > latest:
                latest = ts
        return latest

    @staticmethod
    def first_value_at(series: list[dict[str, Any]], index: int = 0) -> Any:
        if not series or index >= len(series):
            return None
        return series[index].get('value')
