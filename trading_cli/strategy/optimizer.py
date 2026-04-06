"""Strategy parameter optimizer — grid search and genetic algorithm."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable

import pandas as pd

from trading_cli.backtest.engine import BacktestEngine
from trading_cli.strategy.models import Strategy, StrategyConfig, StrategyResult


@dataclass
class OptimizationResult:
    """Result of an optimization run."""

    best_params: dict[str, Any]
    best_score: float
    best_result: StrategyResult
    all_results: list[dict] = field(default_factory=list)
    total_combinations: int = 0
    method: str = "grid_search"


def _score_result(result: StrategyResult, metric: str = "sharpe_ratio") -> float:
    """Extract a scalar score from a backtest result."""
    scores = {
        "sharpe_ratio": result.sharpe_ratio,
        "total_pnl": result.total_pnl,
        "total_pnl_pct": result.total_pnl_pct,
        "win_rate": result.win_rate,
        "max_drawdown": -abs(result.max_drawdown),  # less drawdown = better
    }
    return scores.get(metric, result.sharpe_ratio)


def grid_search(
    strategy_cls: type[Strategy],
    data: pd.DataFrame,
    symbol: str,
    param_grid: dict[str, list],
    metric: str = "sharpe_ratio",
    initial_capital: float = 100000.0,
    commission_rate: float = 0.0003,
) -> OptimizationResult:
    """Exhaustive grid search over parameter combinations.

    Args:
        strategy_cls: Strategy class to instantiate for each combo.
        data: Historical OHLCV DataFrame.
        symbol: Stock symbol.
        param_grid: e.g. {"fast_period": [5,10,15], "slow_period": [20,30,40]}
        metric: Optimisation target (sharpe_ratio|total_pnl|win_rate|max_drawdown).
        initial_capital: Starting capital.
        commission_rate: Commission rate per trade.

    Returns:
        OptimizationResult with best params and full sweep.
    """
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combos = list(product(*values))

    engine = BacktestEngine(
        initial_capital=initial_capital,
        commission_rate=commission_rate,
    )

    best_score = float("-inf")
    best_params: dict[str, Any] = {}
    best_result: StrategyResult | None = None
    all_results: list[dict] = []

    for combo in combos:
        params = dict(zip(keys, combo))
        strategy = strategy_cls(**params)
        result = engine.run(strategy, data, symbol)
        score = _score_result(result, metric)

        entry = {
            **params,
            "score": score,
            "sharpe": result.sharpe_ratio,
            "pnl_pct": result.total_pnl_pct,
            "win_rate": result.win_rate,
            "trades": result.total_trades,
            "drawdown": result.max_drawdown,
        }
        all_results.append(entry)

        if score > best_score:
            best_score = score
            best_params = params
            best_result = result

    return OptimizationResult(
        best_params=best_params,
        best_score=best_score,
        best_result=best_result
        or StrategyResult(strategy_name=strategy_cls.__name__, symbol=symbol),
        all_results=sorted(all_results, key=lambda x: x["score"], reverse=True),
        total_combinations=len(combos),
        method="grid_search",
    )


# ---------------------------------------------------------------------------
# Genetic algorithm
# ---------------------------------------------------------------------------


@dataclass
class _Individual:
    params: dict[str, Any]
    score: float = 0.0
    result: StrategyResult | None = None


def genetic_optimize(
    strategy_cls: type[Strategy],
    data: pd.DataFrame,
    symbol: str,
    param_ranges: dict[str, tuple[float, float, float]],
    metric: str = "sharpe_ratio",
    population_size: int = 20,
    generations: int = 10,
    mutation_rate: float = 0.2,
    crossover_rate: float = 0.7,
    initial_capital: float = 100000.0,
    commission_rate: float = 0.0003,
    seed: int | None = None,
) -> OptimizationResult:
    """Genetic algorithm parameter optimisation.

    Args:
        strategy_cls: Strategy class.
        data: Historical OHLCV DataFrame.
        symbol: Stock symbol.
        param_ranges: {name: (min, max, step)}  e.g. {"fast_period": (5, 30, 1)}
        metric: Optimisation target.
        population_size: Individuals per generation.
        generations: Number of generations.
        mutation_rate: Probability of mutating a gene.
        crossover_rate: Probability of crossover vs cloning.
        initial_capital: Starting capital.
        commission_rate: Commission per trade.
        seed: Random seed for reproducibility.

    Returns:
        OptimizationResult with best params found.
    """
    rng = random.Random(seed)
    engine = BacktestEngine(
        initial_capital=initial_capital, commission_rate=commission_rate
    )

    def _random_params() -> dict[str, Any]:
        params: dict[str, Any] = {}
        for name, (lo, hi, step) in param_ranges.items():
            steps = int((hi - lo) / step) + 1
            val = lo + rng.randint(0, steps - 1) * step
            # Keep int if step is integral
            params[name] = int(val) if step == int(step) else round(val, 4)
        return params

    def _evaluate(ind: _Individual) -> None:
        strategy = strategy_cls(**ind.params)
        ind.result = engine.run(strategy, data, symbol)
        ind.score = _score_result(ind.result, metric)

    def _crossover(a: _Individual, b: _Individual) -> _Individual:
        child_params: dict[str, Any] = {}
        for key in param_ranges:
            child_params[key] = a.params[key] if rng.random() < 0.5 else b.params[key]
        return _Individual(params=child_params)

    def _mutate(ind: _Individual) -> None:
        for name, (lo, hi, step) in param_ranges.items():
            if rng.random() < mutation_rate:
                steps = int((hi - lo) / step) + 1
                val = lo + rng.randint(0, steps - 1) * step
                ind.params[name] = int(val) if step == int(step) else round(val, 4)

    # --- initialise population ---
    population = [_Individual(params=_random_params()) for _ in range(population_size)]
    all_results: list[dict] = []

    for gen in range(generations):
        # evaluate
        for ind in population:
            _evaluate(ind)
            entry = {**ind.params, "score": ind.score, "generation": gen}
            if ind.result:
                entry.update(
                    sharpe=ind.result.sharpe_ratio,
                    pnl_pct=ind.result.total_pnl_pct,
                    win_rate=ind.result.win_rate,
                    trades=ind.result.total_trades,
                    drawdown=ind.result.max_drawdown,
                )
            all_results.append(entry)

        # sort by fitness
        population.sort(key=lambda x: x.score, reverse=True)

        # elitism: top 2 survive unchanged
        next_gen = population[:2]

        # breed
        while len(next_gen) < population_size:
            if rng.random() < crossover_rate:
                # tournament selection (pick best of 3)
                parents = [
                    max(
                        rng.sample(population, min(3, len(population))),
                        key=lambda x: x.score,
                    )
                    for _ in range(2)
                ]
                child = _crossover(parents[0], parents[1])
            else:
                child = _Individual(params=dict(rng.choice(population[:5]).params))
            _mutate(child)
            next_gen.append(child)

        population = next_gen

    # final evaluation
    for ind in population:
        _evaluate(ind)

    best = max(population, key=lambda x: x.score)
    return OptimizationResult(
        best_params=best.params,
        best_score=best.score,
        best_result=best.result
        or StrategyResult(strategy_name=strategy_cls.__name__, symbol=symbol),
        all_results=sorted(all_results, key=lambda x: x["score"], reverse=True),
        total_combinations=len(all_results),
        method="genetic",
    )
