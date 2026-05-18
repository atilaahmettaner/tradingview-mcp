"""Tests for the structured error envelope and exception types."""
from __future__ import annotations

import pytest

from tradingview_mcp.core.errors import (
    BatchExecutionError,
    ErrorCode,
    is_error,
    make_error,
)


class TestErrorCode:
    def test_codes_are_strings(self):
        # Stable string values survive JSON serialization without extra encoding.
        for code in ErrorCode:
            assert isinstance(code.value, str)
            assert code.value == code.value.upper()
            assert " " not in code.value

    def test_all_batches_failed_value_is_stable(self):
        # Other code (skills, clients) string-compares against this literal.
        assert ErrorCode.ALL_BATCHES_FAILED.value == "ALL_BATCHES_FAILED"


class TestMakeError:
    def test_basic_envelope_shape(self):
        env = make_error(ErrorCode.NO_DATA, "nothing returned")
        assert env == {"error": {"code": "NO_DATA", "message": "nothing returned"}}

    def test_accepts_raw_string_code(self):
        # Forward-compat: external callers don't have to import the enum.
        env = make_error("CUSTOM_CODE", "details")
        assert env["error"]["code"] == "CUSTOM_CODE"

    def test_extra_kwargs_merge_into_error_dict(self):
        env = make_error(
            ErrorCode.ALL_BATCHES_FAILED,
            "all 5 batches failed",
            batches_attempted=5,
            batches_failed=5,
            first_error="JSONDecodeError",
        )
        err = env["error"]
        assert err["code"] == "ALL_BATCHES_FAILED"
        assert err["message"] == "all 5 batches failed"
        assert err["batches_attempted"] == 5
        assert err["batches_failed"] == 5
        assert err["first_error"] == "JSONDecodeError"

    def test_no_extra_kwargs_omits_extras(self):
        env = make_error(ErrorCode.NO_DATA, "msg")
        assert set(env["error"].keys()) == {"code", "message"}


class TestIsError:
    def test_new_envelope_detected(self):
        assert is_error(make_error(ErrorCode.NO_DATA, "x")) is True

    def test_envelope_with_extras_detected(self):
        env = make_error(ErrorCode.UPSTREAM_RATE_LIMIT, "rate limited", retry_after_s=30)
        assert is_error(env) is True

    def test_legacy_string_error_is_not_an_envelope(self):
        # The point of the new shape is to be distinguishable from the prior
        # ad-hoc ``{"error": "Analysis failed: ..."}`` strings.
        assert is_error({"error": "Analysis failed: something"}) is False

    def test_non_dict_payload_not_envelope(self):
        assert is_error("error") is False
        assert is_error(None) is False
        assert is_error([{"error": {"code": "X", "message": "y"}}]) is False
        assert is_error(42) is False

    def test_dict_without_error_key_not_envelope(self):
        assert is_error({"result": [], "ok": True}) is False

    def test_dict_with_error_but_missing_code_not_envelope(self):
        # Catches partially-constructed envelopes; clients should still treat
        # the response as malformed rather than as a known error type.
        assert is_error({"error": {"message": "msg"}}) is False


class TestBatchExecutionError:
    def test_stores_batch_metadata(self):
        exc = BatchExecutionError(
            batches_attempted=4,
            batches_failed=4,
            first_error="JSONDecodeError('Expecting value', '', 0)",
        )
        assert exc.batches_attempted == 4
        assert exc.batches_failed == 4
        assert exc.first_error == "JSONDecodeError('Expecting value', '', 0)"

    def test_string_message_includes_first_error(self):
        exc = BatchExecutionError(batches_attempted=3, batches_failed=3, first_error="boom")
        msg = str(exc)
        assert "3" in msg
        assert "boom" in msg

    def test_is_a_real_exception(self):
        with pytest.raises(BatchExecutionError):
            raise BatchExecutionError(1, 1, "x")
