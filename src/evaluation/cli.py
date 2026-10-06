"""conclave-eval — run scenarios, print a Rich summary (spec §4.6).

Rich lives only here (spec §6); the runner and metrics stay presentation-free.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.table import Table

from evaluation.errors import EvaluationError
from evaluation.model import ScenarioResult
from evaluation.report import write_report
from evaluation.runner import run_scenario
from evaluation.scenarios import SCENARIOS, get_scenario
from session.factory import PROVIDER_API_KEY_ENV


def _table(results: list[ScenarioResult]) -> Table:
    table = Table(title="Evaluation results")
    for column in (
        "scenario",
        "model",
        "runs",
        "checks",
        "legal %",
        "rejections",
        "retries",
        "tokens/game",
        "cost/game",
        "p50 ms",
        "p95 ms",
        "status",
    ):
        table.add_column(column)
    for result in results:
        metrics = result.metrics
        legal = metrics.get("legal_action_rate")
        cost = metrics.get("cost_per_game_usd")
        table.add_row(
            result.scenario.name,
            result.model,
            str(len(result.runs)),
            f"{sum(1 for check in result.checks if check.passed)}/{len(result.checks)}",
            "—" if legal is None else f"{legal:.0%}",
            str(metrics.get("rejection_count")),
            str(metrics.get("retry_count")),
            str(metrics.get("tokens_per_game")),
            "—" if cost is None else f"${cost:.6f}",
            str(metrics.get("latency_ms_p50")),
            str(metrics.get("latency_ms_p95")),
            result.status,
        )
    return table


def main(argv: list[str] | None = None, console: Console | None = None) -> int:
    parser = argparse.ArgumentParser(prog="conclave-eval")
    parser.add_argument("--scenario", default="all", help="all | <scenario name>")
    parser.add_argument(
        "--provider", choices=("fake", "openrouter", "opencode-go"), default="fake"
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--repeat", type=int, default=None, help="override the scenario's repeat_runs"
    )
    parser.add_argument("--db", choices=("memory", "postgres"), default="memory")
    parser.add_argument("--out-dir", type=Path, default=Path("eval-results"))
    # argv=None means "read the process arguments" so the console-script entry
    # point (`conclave-eval = "evaluation.cli:main"`) honors its flags; callers
    # pass an explicit list (often []) to stay isolated from sys.argv.
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    console = console or Console()
    env_var = PROVIDER_API_KEY_ENV.get(args.provider) if args.provider != "fake" else None
    if env_var and not os.environ.get(env_var):
        console.print(
            f"[red]{env_var} is not set; export it to run live evaluation[/red]"
        )
        return 2
    try:
        scenarios = (
            [get_scenario(name) for name in sorted(SCENARIOS)]
            if args.scenario == "all"
            else [get_scenario(args.scenario)]
        )
    except EvaluationError as error:
        console.print(f"[red]{error}[/red]")
        return 2

    exit_code = 0
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        result = run_scenario(
            scenario,
            seed=args.seed,
            repeat=args.repeat if args.repeat is not None else scenario.repeat_runs,
            provider=args.provider,
            db=args.db,
        )
        path = write_report(result, args.out_dir)
        console.print(f"[dim]wrote {path}[/dim]")
        results.append(result)
        if result.status != "ok" or not all(check.passed for check in result.checks):
            exit_code = 1
    console.print(_table(results))
    return exit_code