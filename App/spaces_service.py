from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

from thingsboard_client import ThingsBoardClient, ThingsBoardError, _as_float, _as_int

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'

_TB_KEYS = ['CAPACITY', 'TEMPERATURE', 'HUMIDITY', 'LIGHT', 'NOISE']


def _load_json(name: str) -> Any:
    p = DATA_DIR / name
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def _map_noise(
    raw_val: Any,
    cfg: dict[str, Any],
) -> float:
    nm = cfg.get('noiseMapping') or {}
    if not nm.get('useRawAnalog', True):
        f = _as_float(raw_val)
        return float(f) if f is not None else 0.0
    f = _as_float(raw_val)
    if f is None:
        return 0.0
    r0 = float(nm.get('rawMin', 0))
    r1 = float(nm.get('rawMax', 1023))
    d0 = float(nm.get('dbMin', 28))
    d1 = float(nm.get('dbMax', 70))
    if r1 <= r0:
        return d0
    t = (f - r0) / (r1 - r0)
    t = max(0.0, min(1.0, t))
    return d0 + t * (d1 - d0)


def _dict_by_id(demo_list: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {s['id']: s for s in demo_list if 'id' in s}


def build_spaces_payload(
    tb: ThingsBoardClient | None,
    *,
    map_path: Path | None = None,
) -> tuple[list[dict[str, Any]], str, str | None]:
    """
    Returns (spaces, source, error_message).
    source is 'thingsboard' | 'hybrid' | 'demo'.
    """
    map_path = map_path or (DATA_DIR / 'spaces_map.json')
    with open(map_path, encoding='utf-8') as f:
        sm = json.load(f)

    cfg_noise = {
        'noiseMapping': sm.get('noiseMapping', {}),
    }
    stale_sec = int(sm.get('staleAfterSeconds', 120))
    hist_n = int(sm.get('historyPoints', 12))

    demo_list = _load_json('demo_spaces.json')
    demo_by_id = _dict_by_id(demo_list)

    out: list[dict[str, Any]] = []
    any_tb = False
    any_demo = False
    last_err: str | None = None

    for spec in sm.get('spaces', []):
        sid = spec['id']
        base = copy.deepcopy(demo_by_id.get(sid))
        if not base:
            base = {
                'id': sid,
                'name': spec.get('name', sid),
                'address': spec.get('address', ''),
                'postcode': spec.get('postcode', ''),
                'capacity': int(spec.get('capacity', 0)),
                'occupied': 0,
                'noiseDb': 0,
                'tempC': 20.0,
                'humidity': 50.0,
                'lightRaw': None,
                'camera': {'online': False, 'model': str(spec.get('camera', {}).get('model', '')), 'confidence': 0.0, 'lastSeenSec': 9999},
                'history': [0] * hist_n,
            }

        dev_id = spec.get('thingsboardDeviceId') or spec.get('thingsboard_device_id')
        if not dev_id or not str(dev_id).strip():
            out.append(_ensure_light_key(base))
            any_demo = True
            continue

        dev_id = str(dev_id).strip()
        if not tb:
            out.append(_ensure_light_key(base))
            any_demo = True
            continue

        try:
            latest = tb.get_latest_telemetry(dev_id, _TB_KEYS)
        except (ThingsBoardError, OSError) as e:
            last_err = str(e)
            out.append(_ensure_light_key(base))
            any_demo = True
            continue

        latest_ts = ThingsBoardClient.pick_latest_ts(latest, _TB_KEYS) if latest else None
        now_ms = int(time.time() * 1000)
        is_stale = latest_ts is None or (now_ms - latest_ts) > stale_sec * 1000

        merged = copy.deepcopy(base)
        merged['name'] = spec.get('name', merged['name'])
        merged['address'] = spec.get('address', merged['address'])
        merged['postcode'] = spec.get('postcode', merged['postcode'])
        cap_max = int(spec.get('capacity', merged['capacity']))

        cap_ser = latest.get('CAPACITY') or []
        occ = _as_int(ThingsBoardClient.first_value_at(cap_ser, 0))
        if occ is not None:
            occ = max(0, min(cap_max, occ))
            merged['occupied'] = occ

        t_ser = latest.get('TEMPERATURE') or []
        t_val = _as_float(ThingsBoardClient.first_value_at(t_ser, 0))
        if t_val is not None:
            merged['tempC'] = float(t_val)

        h_ser = latest.get('HUMIDITY') or []
        h_val = _as_float(ThingsBoardClient.first_value_at(h_ser, 0))
        if h_val is not None:
            merged['humidity'] = float(h_val)

        n_ser = latest.get('NOISE') or []
        n_raw = ThingsBoardClient.first_value_at(n_ser, 0)
        merged['noiseDb'] = round(_map_noise(n_raw, cfg_noise), 1)

        l_ser = latest.get('LIGHT') or []
        l_val = _as_float(ThingsBoardClient.first_value_at(l_ser, 0))
        if l_val is not None:
            merged['lightRaw'] = l_val
        else:
            merged['lightRaw'] = _as_int(ThingsBoardClient.first_value_at(l_ser, 0))

        cam = dict(merged.get('camera') or {})
        cam['model'] = (spec.get('camera') or {}).get('model', cam.get('model', ''))
        if 'confidence' in (spec.get('camera') or {}):
            cam['confidence'] = float((spec.get('camera') or {})['confidence'])

        if is_stale or latest_ts is None:
            cam['online'] = False
            if latest_ts is not None:
                cam['lastSeenSec'] = int((now_ms - latest_ts) / 1000)
            else:
                cam['lastSeenSec'] = 9999
        else:
            cam['online'] = True
            cam['lastSeenSec'] = max(0, int((now_ms - latest_ts) / 1000))
        merged['camera'] = cam

        # Occupancy history: pull CAPACITY time series from ThingsBoard
        try:
            end_ms = int(time.time() * 1000)
            start_ms = end_ms - 3 * 3600 * 1000
            hist = tb.get_timeseries(
                dev_id,
                ['CAPACITY'],
                start_ts=start_ms,
                end_ts=end_ms,
                limit=hist_n,
                order_by='ASC',
            )
            cap_hist = hist.get('CAPACITY') or []
            pts: list[int] = []
            for item in cap_hist:
                v = _as_float(item.get('value'))
                if v is None:
                    continue
                p = int(round(100.0 * float(v) / cap_max)) if cap_max > 0 else 0
                p = max(0, min(100, p))
                pts.append(p)
            if len(pts) >= hist_n:
                merged['history'] = pts[-hist_n:]
            elif pts:
                pad = [pts[0]] * (hist_n - len(pts)) + pts
                merged['history'] = pad[-hist_n:]
            else:
                h0 = list(merged.get('history') or [0] * hist_n)
                if len(h0) < hist_n:
                    h0 = h0 + [h0[-1] if h0 else 0] * (hist_n - len(h0))
                merged['history'] = h0[-hist_n:]
        except (ThingsBoardError, OSError, ZeroDivisionError):
            h0 = list(merged.get('history') or [0] * hist_n)
            if len(h0) < hist_n:
                h0 = h0 + [h0[-1] if h0 else 0] * (hist_n - len(h0))
            merged['history'] = h0[-hist_n:]

        out.append(_ensure_light_key(merged))
        any_tb = True

    if any_tb and any_demo:
        src = 'hybrid'
    elif any_tb:
        src = 'thingsboard'
    else:
        src = 'demo'

    return out, src, last_err


def _ensure_light_key(s: dict[str, Any]) -> dict[str, Any]:
    if 'lightRaw' not in s:
        s['lightRaw'] = None
    return s
