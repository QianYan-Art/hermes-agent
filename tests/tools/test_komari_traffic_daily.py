"""只读日报的 HTTP 契约、汇总与失败边界。"""

from datetime import datetime, timezone

import httpx
import pytest

from scripts import komari_traffic_daily as daily


NOW = datetime(2026, 10, 15, 8, tzinfo=timezone.utc)


def _series(metric, value, uuid="one"):
    return {
        "metric_key": metric, "entity_id": uuid,
        "downsampled": True, "downsample_algorithm": "sum",
        "points": [{"value": value}],
    }


def _transport(*, metrics=None, nodes=None):
    calls = []

    def respond(request):
        calls.append(request)
        if request.url.path == "/api/nodes":
            assert request.method == "GET"
            return httpx.Response(200, json={
                "status": "success",
                "data": nodes if nodes is not None else [{"uuid": "one", "name": "VPS"}],
            })
        import json
        body = json.loads(request.content)
        assert request.method == "POST"
        assert request.url.path == "/api/rpc2"
        assert body["method"] == "public:queryMetrics"
        assert body["params"]["aggregation_by_metric"] == {
            "traffic.up": "sum", "traffic.down": "sum",
        }
        assert set(body["params"]) == {
            "metric_keys", "start", "end", "aggregation_by_metric", "max_points",
        }
        return httpx.Response(200, json={"result": {"series": metrics if metrics is not None else [
            _series("traffic.up", 1024), _series("traffic.down", 2048),
        ]}})

    return httpx.MockTransport(respond), calls


def test_readonly_http_pipeline_and_full_visible_node_list():
    transport, calls = _transport(nodes=[
        {"uuid": "one", "name": "VPS"}, {"uuid": "missing", "name": "无数据"},
    ])
    result = daily.fetch_report("https://komari.test", transport=transport, now=NOW)
    assert result["ok"] is True
    assert len(result["nodes"]) == 2
    assert result["nodes"][0]["up_bytes"] == 1024
    assert "↑1.00 KiB ↓2.00 KiB" in result["report"]
    assert "数据不足，不记为零" in result["report"]
    assert "有效数据 1/2 台" in result["report"]
    assert len(calls) == 2
    assert result["start"] == "2026-10-14T08:00:00+00:00"


@pytest.mark.parametrize("value", [-1, True, "1024", float("inf")])
def test_rejects_invalid_traffic_values(value):
    with pytest.raises(daily.ReportError, match="invalid_traffic_value"):
        daily.build_report(
            [{"uuid": "one"}], {"series": [_series("traffic.up", value)]}, NOW, NOW,
        )


def test_rejects_wrong_aggregation():
    series = _series("traffic.up", 100)
    series["downsample_algorithm"] = "avg"
    with pytest.raises(daily.ReportError, match="unexpected_aggregation"):
        daily.build_report([{"uuid": "one"}], {"series": [series]}, NOW, NOW)


@pytest.mark.parametrize(
    "response,error",
    [
        (httpx.Response(401, text="secret-token"), "komari_unavailable"),
        (httpx.Response(302, headers={"Location": "https://unexpected.test"}), "komari_unavailable"),
        (httpx.Response(200, text="secret-token"), "invalid_komari_response"),
        (httpx.Response(200, json=[]), "invalid_komari_response"),
        (httpx.Response(200, content=b"x" * (daily.MAX_RESPONSE_BYTES + 1)), "response_too_large"),
    ],
)
def test_http_failures_do_not_echo_response_body(response, error):
    transport = httpx.MockTransport(lambda _: response)
    with pytest.raises(daily.ReportError, match=error) as exc:
        daily.fetch_report("https://komari.test", transport=transport, now=NOW)
    assert "secret-token" not in str(exc.value)


@pytest.mark.parametrize("exception,error", [
    (httpx.ReadTimeout("secret-token"), "komari_timeout"),
    (httpx.ConnectError("secret-token"), "komari_unavailable"),
])
def test_transport_failure_is_sanitized(exception, error):
    def fail(_):
        raise exception
    with pytest.raises(daily.ReportError, match=error):
        daily.fetch_report("https://komari.test", transport=httpx.MockTransport(fail), now=NOW)


def test_rpc_error_does_not_echo_private_details():
    count = 0

    def respond(_):
        nonlocal count
        count += 1
        if count == 1:
            return httpx.Response(200, json={"status": "success", "data": [{"uuid": "one"}]})
        return httpx.Response(200, json={"error": {"message": "secret-token"}})

    with pytest.raises(daily.ReportError, match="komari_metrics_failed"):
        daily.fetch_report("https://komari.test", transport=httpx.MockTransport(respond), now=NOW)
