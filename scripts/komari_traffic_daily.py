#!/usr/bin/env python3
"""只读汇总 Komari 全部公开可见节点近 24 小时流量。"""

from __future__ import annotations

import json
import math
import sys
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hermes_constants import get_hermes_home


MAX_RESPONSE_BYTES = 4 * 1024 * 1024
METRICS = ("traffic.up", "traffic.down")


class ReportError(Exception):
    """仅携带可公开的固定错误码。"""


def _base_url() -> str:
    try:
        with (get_hermes_home() / "komari_traffic.toml").open("rb") as stream:
            base = tomllib.load(stream)["base_url"].rstrip("/")
        parsed = urlsplit(base)
        valid = (
            parsed.scheme == "https" and parsed.hostname
            and not (parsed.username or parsed.password or parsed.query or parsed.fragment)
            and parsed.path in ("", "/")
        )
        if not valid:
            raise ValueError
        return base
    except (OSError, ValueError, TypeError, KeyError):
        raise ReportError("invalid_komari_config") from None


def _request(client: httpx.Client, method: str, url: str, **kwargs):
    try:
        with client.stream(method, url, **kwargs) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ReportError("response_too_large")
            return json.loads(body)
    except httpx.TimeoutException:
        raise ReportError("komari_timeout") from None
    except httpx.HTTPError:
        raise ReportError("komari_unavailable") from None
    except (ValueError, UnicodeDecodeError):
        raise ReportError("invalid_komari_response") from None


def _bytes(value: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB", "PiB"):
        if value < 1024 or unit == "PiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError


def build_report(nodes, metrics, start: datetime, end: datetime) -> dict:
    if not isinstance(nodes, list) or not nodes:
        raise ReportError("no_visible_nodes")
    if not isinstance(metrics, dict) or not isinstance(metrics.get("series"), list):
        raise ReportError("invalid_komari_response")
    totals = {}
    for series in metrics["series"]:
        if not isinstance(series, dict) or series.get("metric_key") not in METRICS:
            raise ReportError("invalid_komari_response")
        entity = series.get("entity_id")
        points = series.get("points") or []
        if not isinstance(entity, str) or not isinstance(points, list):
            raise ReportError("invalid_komari_response")
        if series.get("downsampled") and series.get("downsample_algorithm") != "sum":
            raise ReportError("unexpected_aggregation")
        values = []
        for point in points:
            if not isinstance(point, dict):
                raise ReportError("invalid_komari_response")
            value = point.get("value")
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ReportError("invalid_traffic_value")
            values.append(value)
        if values:
            key = (entity, series["metric_key"])
            totals[key] = totals.get(key, 0) + sum(values)
    rows = []
    seen = set()
    for node in nodes:
        if not isinstance(node, dict) or not isinstance(node.get("uuid"), str):
            raise ReportError("invalid_komari_response")
        uuid = node["uuid"]
        if uuid in seen:
            raise ReportError("duplicate_node")
        seen.add(uuid)
        up, down = (totals.get((uuid, key)) for key in METRICS)
        name = str(node.get("name") or uuid).replace("\r", " ").replace("\n", " ")
        rows.append({"name": name, "up_bytes": up, "down_bytes": down})
    rows.sort(key=lambda row: row["name"])
    lines = [
        "流量日报（近 24 小时，Komari 公开可见节点）",
        f"{start:%Y-%m-%d %H:%M} 至 {end:%Y-%m-%d %H:%M} UTC",
    ]
    complete = []
    for row in rows:
        up, down = row["up_bytes"], row["down_bytes"]
        if up is None or down is None:
            lines.append(f"{row['name']}：数据不足，不记为零")
        else:
            complete.append(row)
            lines.append(f"{row['name']}：↑{_bytes(up)} ↓{_bytes(down)} 合计 {_bytes(up + down)}")
    total = sum(row["up_bytes"] + row["down_bytes"] for row in complete)
    lines.append(f"有效数据 {len(complete)}/{len(rows)} 台，已知合计 {_bytes(total)}")
    return {
        "ok": True, "source": "Komari public API", "scope": "public_visible_nodes",
        "start": start.isoformat(), "end": end.isoformat(),
        "nodes": rows, "report": "\n".join(lines),
    }


def fetch_report(base_url: str, *, transport=None, now=None) -> dict:
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(hours=24)
    with httpx.Client(timeout=20, follow_redirects=False, transport=transport) as client:
        listing = _request(client, "GET", base_url + "/api/nodes")
        if not isinstance(listing, dict) or listing.get("status") != "success":
            raise ReportError("invalid_komari_response")
        result = _request(client, "POST", base_url + "/api/rpc2", json={
            "jsonrpc": "2.0", "method": "public:queryMetrics", "id": 1,
            "params": {
                "metric_keys": list(METRICS),
                "start": start.isoformat(), "end": end.isoformat(),
                "aggregation_by_metric": {key: "sum" for key in METRICS},
                "max_points": 1000,
            },
        })
    if not isinstance(result, dict) or result.get("error") or "result" not in result:
        raise ReportError("komari_metrics_failed")
    return build_report(listing.get("data"), result["result"], start, end)


def main() -> int:
    try:
        if len(sys.argv) != 1:
            raise ReportError("unexpected_arguments")
        result = fetch_report(_base_url())
    except ReportError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
