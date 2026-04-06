"""Tests for the reporting system."""

from datetime import date

import pytest

from trading_cli.core.reporter import (
    PortfolioPosition,
    PortfolioSummary,
    PerformanceMetrics,
    ReportGenerator,
)


class TestPortfolioPosition:
    def test_pnl_positive(self):
        p = PortfolioPosition(symbol="000001.SZ", quantity=1000, avg_cost=10.0, current_price=11.0)
        assert p.market_value == 11000.0
        assert p.cost_basis == 10000.0
        assert p.pnl == 1000.0
        assert p.pnl_pct == pytest.approx(10.0)

    def test_pnl_negative(self):
        p = PortfolioPosition(symbol="000001.SZ", quantity=500, avg_cost=20.0, current_price=18.0)
        assert p.pnl == -1000.0
        assert p.pnl_pct == pytest.approx(-10.0)

    def test_zero_cost(self):
        p = PortfolioPosition(symbol="TEST", quantity=0, avg_cost=0, current_price=10.0)
        assert p.pnl_pct == 0.0


class TestPortfolioSummary:
    def test_aggregation(self):
        summary = PortfolioSummary(
            cash=50000,
            positions=[
                PortfolioPosition(symbol="A", quantity=100, avg_cost=10, current_price=12),
                PortfolioPosition(symbol="B", quantity=200, avg_cost=5, current_price=4),
            ],
        )
        assert summary.position_count == 2
        assert summary.total_market_value == 100 * 12 + 200 * 4  # 2000
        assert summary.total_cost == 100 * 10 + 200 * 5  # 2000
        assert summary.total_pnl == 200 + (-200)  # 0
        assert summary.total_equity == 2000 + 50000

    def test_empty_portfolio(self):
        summary = PortfolioSummary(cash=100000)
        assert summary.position_count == 0
        assert summary.total_equity == 100000
        assert summary.total_pnl_pct == 0.0


class TestPerformanceMetrics:
    def test_return_pct(self):
        m = PerformanceMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            starting_equity=100000,
            ending_equity=110000,
        )
        assert m.return_pct == pytest.approx(10.0)

    def test_negative_return(self):
        m = PerformanceMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            starting_equity=100000,
            ending_equity=90000,
        )
        assert m.return_pct == pytest.approx(-10.0)


class TestReportGenerator:
    def test_generate_portfolio_report(self):
        gen = ReportGenerator()
        summary = PortfolioSummary(
            cash=10000,
            positions=[PortfolioPosition(symbol="A", quantity=100, avg_cost=10, current_price=12)],
        )
        report = gen.generate_portfolio_report(summary)
        assert report["type"] == "portfolio"
        assert report["cash"] == 10000
        assert len(report["positions"]) == 1

    def test_generate_performance_report(self):
        gen = ReportGenerator()
        metrics = PerformanceMetrics(
            period_start=date(2026, 1, 1),
            period_end=date(2026, 3, 31),
            starting_equity=100000,
            ending_equity=108500,
            total_trades=42,
            win_rate=59.5,
        )
        report = gen.generate_performance_report(metrics)
        assert report["type"] == "performance"
        assert report["total_trades"] == 42

    def test_export_json(self, tmp_path, monkeypatch):
        gen = ReportGenerator()
        monkeypatch.setattr(gen, "REPORTS_DIR", tmp_path)
        report = {"type": "test", "value": 42}
        path = gen.export_json(report, "test_report.json")
        assert path.exists()
        import json
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["value"] == 42

    def test_export_csv(self, tmp_path, monkeypatch):
        gen = ReportGenerator()
        monkeypatch.setattr(gen, "REPORTS_DIR", tmp_path)
        rows = [{"symbol": "A", "pnl": 100}, {"symbol": "B", "pnl": -50}]
        path = gen.export_csv(rows, "test.csv")
        assert path.exists()
