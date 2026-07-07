"""结构化发送失败分类测试。"""

import pytest

from gateway.platforms.base import (
    SEND_ERROR_KINDS,
    SendResult,
    classify_send_error,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Message_too_long", "too_long"),
        ("Bad Request: message is too long", "too_long"),
        ("Bad Request: can't parse entities: unsupported start tag", "bad_format"),
        ("Bad Request: not enough rights to send text messages", "forbidden"),
        ("Forbidden: bot was blocked by the user", "forbidden"),
        ("Bad Request: chat not found", "not_found"),
        ("Too Many Requests: retry after 12", "rate_limited"),
        ("QQ daily upload limit exceeded for 'a.png'", "rate_limited"),
        ("ConnectError: connection refused", "transient"),
        ("Not connected", "transient"),
        ("some entirely novel provider message", "unknown"),
        ("", "unknown"),
    ],
)
def test_classify_send_error_text(text, expected):
    assert classify_send_error(None, text) == expected


def test_classify_uses_exception_class_name():
    exc = type("Forbidden", (Exception,), {})()
    assert classify_send_error(exc) == "forbidden"


def test_every_classification_is_in_the_vocabulary():
    for text in (
        "message_too_long",
        "can't parse entities",
        "forbidden",
        "chat not found",
        "flood",
        "connecterror",
        "mystery",
        "",
    ):
        assert classify_send_error(None, text) in SEND_ERROR_KINDS


def test_unknown_never_masquerades_as_benign():
    assert classify_send_error(None, "kaboom 500 internal") == "unknown"


def test_sendresult_error_kind_defaults_none_and_is_backward_compatible():
    ok = SendResult(success=True, message_id="42")
    assert ok.error_kind is None
    legacy_fail = SendResult(success=False, error="boom")
    assert legacy_fail.error_kind is None
