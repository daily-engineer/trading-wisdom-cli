"""Tests for trading-cli review command (Issue #13).

Covers:
 1. parse_sina_response — parse hardcoded Sina response string → verify dict fields
 2. format_change — positive=green tag, negative=red tag, zero=neutral
 3. render_markdown with mock data → verify key sections present
 4. render_json → valid JSON, has "indices" key
 5. fetch_indices — mock requests.get → verify 7 indices parsed
 6. fetch_sector_board success — mock push2 response → verify list returned
 7. fetch_sector_board failure — mock timeout → verify returns [] (not crash)
 8. CLI review daily — mock both fetch functions → exit_code==0, "上证" in output
 9. CLI review daily --json — exit_code==0, output is valid JSON
10. CLI review daily --mode intraday — exit_code==0
11. CLI review daily --mode close — exit_code==0
12. auto mode logic — hour=12 → intraday, hour=17 → close
13. fetch_indices network error → returns list with error dicts (no exception)
14. format_change with exactly 0.0 → no color tag
15. render_markdown with all-error indices → still renders without crashing
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from trading_cli.core.market_review import (
    fetch_indices,
    fetch_market_breadth,
    fetch_sector_board,
    format_change,
    parse_sina_response,
    render_json,
    render_markdown,
)
from trading_cli.commands.review_cmd import review

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_SINA_RESPONSE = (
    'var hq_str_sh000001="上证指数,3280.00,3300.00,3250.00,3310.00,3240.00,'
    "0,0,500000000,5000000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
    '2026-04-07,15:00:00,00,";'
)

SAMPLE_MULTI_SINA_RESPONSE = "\n".join(
    [
        'var hq_str_sh000001="上证指数,3280.00,3300.00,3250.00,3310.00,3240.00,'
        "0,0,500000000,5000000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
        '2026-04-07,15:00:00,00,";',
        'var hq_str_sh000300="沪深300,3850.00,3900.00,3820.00,3920.00,3810.00,'
        "0,0,300000000,4000000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
        '2026-04-07,15:00:00,00,";',
        'var hq_str_sz399001="深证成指,10500.00,10600.00,10450.00,10650.00,10430.00,'
        "0,0,400000000,3500000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
        '2026-04-07,15:00:00,00,";',
        'var hq_str_sz399006="创业板指,2100.00,2120.00,2080.00,2130.00,2070.00,'
        "0,0,200000000,2000000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
        '2026-04-07,15:00:00,00,";',
        'var hq_str_sh000688="科创50,980.00,1000.00,970.00,1010.00,960.00,'
        "0,0,100000000,1500000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
        '2026-04-07,15:00:00,00,";',
        'var hq_str_sh000905="中证500,6100.00,6200.00,6050.00,6250.00,6030.00,'
        "0,0,150000000,1800000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
        '2026-04-07,15:00:00,00,";',
        'var hq_str_sh000016="上证50,2700.00,2750.00,2680.00,2760.00,2670.00,'
        "0,0,80000000,1200000000,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,"
        '2026-04-07,15:00:00,00,";',
    ]
)

SAMPLE_EASTMONEY_RESPONSE = {
    "data": {
        "diff": [
            {"f12": "BK0001", "f14": "食品饮料", "f2": 123.45, "f3": 2.34},
            {"f12": "BK0002", "f14": "医药生物", "f2": 456.78, "f3": 1.56},
            {"f12": "BK0003", "f14": "电子", "f2": 789.01, "f3": -0.78},
        ]
    }
}

MOCK_INDICES = [
    {
        "code": "sh000001",
        "name": "上证指数",
        "current": 3250.00,
        "prev_close": 3300.00,
        "open": 3280.00,
        "change": -50.0,
        "change_pct": -1.52,
        "amount_yi": 500.0,
        "error": False,
    }
]

MOCK_SECTORS = [
    {"code": "BK0001", "name": "食品饮料", "latest": 123.45, "change_pct": 2.34},
    {"code": "BK0002", "name": "医药生物", "latest": 456.78, "change_pct": 1.56},
]

MOCK_BREADTH = {
    "advancing": 0,
    "declining": 0,
    "flat": 0,
    "limit_up": 0,
    "limit_down": 0,
    "northbound": 0.0,
    "note": "实时数据需要 Tushare Token",
}


# ---------------------------------------------------------------------------
# 1. parse_sina_response
# ---------------------------------------------------------------------------


class TestParseSinaResponse:
    def test_parses_basic_response(self) -> None:
        result = parse_sina_response(SAMPLE_SINA_RESPONSE)
        assert len(result) == 1
        idx = result[0]
        assert idx["code"] == "sh000001"
        assert idx["name"] == "上证指数"
        assert idx["current"] == pytest.approx(3250.00)
        assert idx["prev_close"] == pytest.approx(3300.00)
        assert not idx["error"]

    def test_change_calculated(self) -> None:
        result = parse_sina_response(SAMPLE_SINA_RESPONSE)
        idx = result[0]
        expected_change = 3250.00 - 3300.00
        assert idx["change"] == pytest.approx(expected_change)

    def test_change_pct_calculated(self) -> None:
        result = parse_sina_response(SAMPLE_SINA_RESPONSE)
        idx = result[0]
        expected_pct = (3250.00 - 3300.00) / 3300.00 * 100
        assert idx["change_pct"] == pytest.approx(expected_pct, rel=1e-4)

    def test_amount_yi_converted(self) -> None:
        result = parse_sina_response(SAMPLE_SINA_RESPONSE)
        idx = result[0]
        # 5000000000 yuan → 50 亿
        assert idx["amount_yi"] == pytest.approx(50.0)

    def test_parses_multiple_indices(self) -> None:
        result = parse_sina_response(SAMPLE_MULTI_SINA_RESPONSE)
        assert len(result) == 7

    def test_empty_string_returns_empty(self) -> None:
        result = parse_sina_response("")
        assert result == []

    def test_garbled_line_returns_error_dict(self) -> None:
        garbled = 'var hq_str_sh000001="";'
        result = parse_sina_response(garbled)
        assert len(result) == 1
        assert result[0]["error"] is True


# ---------------------------------------------------------------------------
# 2. format_change
# ---------------------------------------------------------------------------


class TestFormatChange:
    def test_positive_returns_green(self) -> None:
        result = format_change(1.23)
        assert "<font color='green'>" in result
        assert "+1.23%" in result

    def test_negative_returns_red(self) -> None:
        result = format_change(-0.45)
        assert "<font color='red'>" in result
        assert "-0.45%" in result

    def test_zero_no_color_tag(self) -> None:
        result = format_change(0.0)
        assert "<font" not in result
        assert "0.00%" in result

    def test_small_positive(self) -> None:
        result = format_change(0.01)
        assert "green" in result

    def test_small_negative(self) -> None:
        result = format_change(-0.01)
        assert "red" in result


# ---------------------------------------------------------------------------
# 3. render_markdown
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_contains_upper_index_name(self) -> None:
        md = render_markdown(MOCK_INDICES, MOCK_SECTORS, [], MOCK_BREADTH, "close")
        assert "上证指数" in md

    def test_contains_industry_section(self) -> None:
        md = render_markdown(MOCK_INDICES, MOCK_SECTORS, [], MOCK_BREADTH, "close")
        assert "行业板块" in md

    def test_mode_label_intraday(self) -> None:
        md = render_markdown(MOCK_INDICES, [], [], MOCK_BREADTH, "intraday")
        assert "盘中" in md

    def test_mode_label_close(self) -> None:
        md = render_markdown(MOCK_INDICES, [], [], MOCK_BREADTH, "close")
        assert "收盘" in md

    def test_empty_sectors_graceful(self) -> None:
        md = render_markdown(MOCK_INDICES, [], [], MOCK_BREADTH, "close")
        assert "数据暂不可用" in md

    def test_sector_names_present(self) -> None:
        md = render_markdown(MOCK_INDICES, MOCK_SECTORS, [], MOCK_BREADTH, "close")
        assert "食品饮料" in md


# ---------------------------------------------------------------------------
# 4. render_json
# ---------------------------------------------------------------------------


class TestRenderJson:
    def test_valid_json(self) -> None:
        result = render_json(MOCK_INDICES, MOCK_SECTORS, [], MOCK_BREADTH, "close")
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_has_indices_key(self) -> None:
        result = render_json(MOCK_INDICES, MOCK_SECTORS, [], MOCK_BREADTH, "close")
        parsed = json.loads(result)
        assert "indices" in parsed

    def test_has_mode_key(self) -> None:
        result = render_json(MOCK_INDICES, MOCK_SECTORS, [], MOCK_BREADTH, "close")
        parsed = json.loads(result)
        assert parsed["mode"] == "close"

    def test_sectors_in_output(self) -> None:
        result = render_json(MOCK_INDICES, MOCK_SECTORS, [], MOCK_BREADTH, "intraday")
        parsed = json.loads(result)
        assert len(parsed["sectors_industry"]) == 2


# ---------------------------------------------------------------------------
# 5. fetch_indices with mock
# ---------------------------------------------------------------------------


class TestFetchIndices:
    def test_returns_7_indices_on_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = SAMPLE_MULTI_SINA_RESPONSE.encode("gb2312")
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "trading_cli.core.market_review.requests.get", return_value=mock_resp
        ):
            result = fetch_indices()

        assert len(result) == 7

    def test_parsed_index_has_correct_fields(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = SAMPLE_SINA_RESPONSE.encode("gb2312")
        mock_resp.raise_for_status = MagicMock()

        with patch(
            "trading_cli.core.market_review.requests.get", return_value=mock_resp
        ):
            result = fetch_indices()

        assert len(result) >= 1
        idx = result[0]
        assert "code" in idx
        assert "name" in idx
        assert "current" in idx

    def test_network_error_returns_error_dicts(self) -> None:
        with patch(
            "trading_cli.core.market_review.requests.get",
            side_effect=Exception("network error"),
        ):
            result = fetch_indices()

        assert len(result) == 7
        for item in result:
            assert item.get("error") is True

    def test_network_error_does_not_raise(self) -> None:
        with patch(
            "trading_cli.core.market_review.requests.get",
            side_effect=ConnectionError("timeout"),
        ):
            # Should not raise
            result = fetch_indices()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 6. fetch_sector_board success
# ---------------------------------------------------------------------------


class TestFetchSectorBoardSuccess:
    def test_returns_list_on_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_EASTMONEY_RESPONSE

        with patch(
            "trading_cli.core.market_review.requests.get", return_value=mock_resp
        ):
            result = fetch_sector_board("industry")

        assert isinstance(result, list)
        assert len(result) == 3

    def test_list_item_has_correct_keys(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_EASTMONEY_RESPONSE

        with patch(
            "trading_cli.core.market_review.requests.get", return_value=mock_resp
        ):
            result = fetch_sector_board("industry")

        item = result[0]
        assert "code" in item
        assert "name" in item
        assert "change_pct" in item

    def test_concept_board_uses_different_id(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = SAMPLE_EASTMONEY_RESPONSE

        with patch(
            "trading_cli.core.market_review.requests.get", return_value=mock_resp
        ) as mock_get:
            fetch_sector_board("concept")

        call_url = mock_get.call_args[0][0]
        assert "t:3" in call_url


# ---------------------------------------------------------------------------
# 7. fetch_sector_board failure
# ---------------------------------------------------------------------------


class TestFetchSectorBoardFailure:
    def test_timeout_returns_empty_list(self) -> None:
        import requests as req

        with patch(
            "trading_cli.core.market_review.requests.get",
            side_effect=req.exceptions.Timeout("timeout"),
        ):
            result = fetch_sector_board("industry")

        assert result == []

    def test_connection_error_returns_empty_list(self) -> None:
        with patch(
            "trading_cli.core.market_review.requests.get",
            side_effect=ConnectionError("refused"),
        ):
            result = fetch_sector_board("industry")

        assert result == []

    def test_non_200_status_returns_empty_list(self) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 403

        with patch(
            "trading_cli.core.market_review.requests.get", return_value=mock_resp
        ):
            result = fetch_sector_board("industry")

        assert result == []


# ---------------------------------------------------------------------------
# 8-11. CLI tests
# ---------------------------------------------------------------------------


def _make_mock_fetch_indices():
    """Return mock fetch_indices that returns MOCK_INDICES."""
    return MOCK_INDICES


def _make_mock_fetch_sector_board(board_type="industry", top_n=5):
    return MOCK_SECTORS


class TestReviewCLI:
    def setup_method(self) -> None:
        self.runner = CliRunner()

    def _invoke_daily(self, args: list[str]) -> any:
        with patch(
            "trading_cli.commands.review_cmd.fetch_indices",
            return_value=MOCK_INDICES,
        ), patch(
            "trading_cli.commands.review_cmd.fetch_sector_board",
            return_value=MOCK_SECTORS,
        ), patch(
            "trading_cli.commands.review_cmd.fetch_market_breadth",
            return_value=MOCK_BREADTH,
        ):
            return self.runner.invoke(review, ["daily"] + args)

    def test_daily_exit_code_zero(self) -> None:
        result = self._invoke_daily([])
        assert result.exit_code == 0, result.output

    def test_daily_output_contains_shangzheng(self) -> None:
        result = self._invoke_daily([])
        assert "上证" in result.output

    def test_daily_json_exit_code_zero(self) -> None:
        result = self._invoke_daily(["--json"])
        assert result.exit_code == 0, result.output

    def test_daily_json_output_is_valid_json(self) -> None:
        result = self._invoke_daily(["--json"])
        # Extract JSON from output (may have leading text from click)
        output = result.output.strip()
        parsed = json.loads(output)
        assert "indices" in parsed

    def test_daily_mode_intraday_exit_code_zero(self) -> None:
        result = self._invoke_daily(["--mode", "intraday"])
        assert result.exit_code == 0, result.output

    def test_daily_mode_close_exit_code_zero(self) -> None:
        result = self._invoke_daily(["--mode", "close"])
        assert result.exit_code == 0, result.output

    def test_review_help(self) -> None:
        result = self.runner.invoke(review, ["--help"])
        assert result.exit_code == 0
        assert "daily" in result.output.lower() or "market" in result.output.lower()


# ---------------------------------------------------------------------------
# 12. Auto mode logic
# ---------------------------------------------------------------------------


class TestAutoModeLogic:
    def test_hour_12_gives_intraday(self) -> None:
        from unittest.mock import patch
        from trading_cli.commands.review_cmd import _resolve_mode

        with patch("trading_cli.commands.review_cmd.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 12
            mock_dt.now.return_value.minute = 0
            result = _resolve_mode("auto")

        assert result == "intraday"

    def test_hour_17_gives_close(self) -> None:
        from trading_cli.commands.review_cmd import _resolve_mode

        with patch("trading_cli.commands.review_cmd.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 17
            mock_dt.now.return_value.minute = 0
            result = _resolve_mode("auto")

        assert result == "close"

    def test_hour_15_minute_29_gives_intraday(self) -> None:
        from trading_cli.commands.review_cmd import _resolve_mode

        with patch("trading_cli.commands.review_cmd.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 15
            mock_dt.now.return_value.minute = 29
            result = _resolve_mode("auto")

        assert result == "intraday"

    def test_hour_15_minute_30_gives_close(self) -> None:
        from trading_cli.commands.review_cmd import _resolve_mode

        with patch("trading_cli.commands.review_cmd.datetime") as mock_dt:
            mock_dt.now.return_value.hour = 15
            mock_dt.now.return_value.minute = 30
            result = _resolve_mode("auto")

        assert result == "close"

    def test_explicit_intraday_returned_as_is(self) -> None:
        from trading_cli.commands.review_cmd import _resolve_mode

        assert _resolve_mode("intraday") == "intraday"

    def test_explicit_close_returned_as_is(self) -> None:
        from trading_cli.commands.review_cmd import _resolve_mode

        assert _resolve_mode("close") == "close"


# ---------------------------------------------------------------------------
# 14. format_change zero → no color tag (already covered in 2, explicit here)
# ---------------------------------------------------------------------------


class TestFormatChangeZero:
    def test_exactly_zero_no_color(self) -> None:
        result = format_change(0.0)
        assert "font" not in result

    def test_exactly_zero_shows_percent(self) -> None:
        result = format_change(0.0)
        assert "%" in result


# ---------------------------------------------------------------------------
# 15. render_markdown with all-error indices
# ---------------------------------------------------------------------------


class TestRenderMarkdownAllErrors:
    def test_all_error_indices_does_not_crash(self) -> None:
        error_indices = [{"code": c, "error": True} for c in ["sh000001", "sh000300"]]
        md = render_markdown(error_indices, [], [], MOCK_BREADTH, "close")
        assert isinstance(md, str)
        assert len(md) > 0

    def test_all_error_indices_shows_placeholder(self) -> None:
        error_indices = [{"code": "sh000001", "error": True}]
        md = render_markdown(error_indices, [], [], MOCK_BREADTH, "close")
        # Should show '-' for missing values
        assert "-" in md
