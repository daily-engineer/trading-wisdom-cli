"""Workflow orchestration — run multi-step pipelines from YAML definitions."""

from __future__ import annotations

from pathlib import Path

import click
import yaml
from rich.console import Console

console = Console()

EXAMPLE_PIPELINE = """\
# Example pipeline: fetch → analyze → report
name: daily_analysis
description: Daily stock analysis pipeline

steps:
  - name: fetch_data
    command: data fetch {symbol} --days {days}

  - name: analyze
    command: analyze signal {symbol}

  - name: monitor
    command: monitor dashboard {symbol}
"""

WORKFLOWS_DIR = Path.home() / ".trading-wisdom" / "workflows"


@click.group()
def workflow():
    """🔄 Workflow Orchestration — run multi-step pipelines."""
    pass


@workflow.command()
@click.argument("pipeline_file", type=click.Path(exists=True))
@click.option("--var", "-v", multiple=True, help="Variable substitution: key=value")
@click.option("--dry-run", is_flag=True, help="Show steps without executing.")
def run(pipeline_file: str, var: tuple[str, ...], dry_run: bool):
    """Run a workflow pipeline from a YAML file.

    Variables are substituted into command templates using {key} syntax.

    Examples:

        trading-cli workflow run pipeline.yaml -v symbol=000001.SZ -v days=30

        trading-cli workflow run pipeline.yaml -v symbol=600519 --dry-run
    """
    with open(pipeline_file, "r", encoding="utf-8") as f:
        pipeline = yaml.safe_load(f)

    if not pipeline or "steps" not in pipeline:
        console.print("[red]Invalid pipeline: missing 'steps' key.[/red]")
        return

    # Parse variables
    variables = {}
    for v in var:
        if "=" in v:
            k, val = v.split("=", 1)
            variables[k.strip()] = val.strip()

    name = pipeline.get("name", "unnamed")
    steps = pipeline["steps"]
    console.print(f"\n[cyan]🔄 Pipeline:[/cyan] {name} ({len(steps)} steps)\n")

    for i, step in enumerate(steps, 1):
        step_name = step.get("name", f"step-{i}")
        cmd_template = step.get("command", "")

        # Substitute variables
        try:
            cmd = cmd_template.format(**variables)
        except KeyError as e:
            console.print(f"[red]Step {i} ({step_name}): missing variable {e}[/red]")
            return

        if dry_run:
            console.print(f"  [dim]{i}.[/dim] [yellow]DRY[/yellow] trading-cli {cmd}")
            continue

        console.print(f"  [dim]{i}.[/dim] [cyan]{step_name}[/cyan]: trading-cli {cmd}")

        # Execute by invoking the CLI programmatically
        from trading_cli.main import cli

        try:
            cli.main(cmd.split(), standalone_mode=False)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"     [red]Error: {e}[/red]")
            if not step.get("continue_on_error", False):
                console.print("[red]Pipeline halted.[/red]")
                return

        console.print(f"     [green]✓[/green]")

    console.print(f"\n[green]✓ Pipeline '{name}' completed.[/green]\n")


@workflow.command()
def init():
    """Create an example pipeline YAML file."""
    WORKFLOWS_DIR.mkdir(parents=True, exist_ok=True)
    path = WORKFLOWS_DIR / "example_pipeline.yaml"
    path.write_text(EXAMPLE_PIPELINE, encoding="utf-8")
    console.print(f"[green]✓[/green] Example pipeline created at [cyan]{path}[/cyan]")
    console.print(
        "[dim]Edit it, then run: trading-cli workflow run <path> -v symbol=000001.SZ[/dim]"
    )


@workflow.command("list")
def workflow_list():
    """List saved workflow files."""
    if not WORKFLOWS_DIR.exists():
        console.print("[yellow]No workflows found. Run 'workflow init' first.[/yellow]")
        return

    files = sorted(WORKFLOWS_DIR.glob("*.yaml")) + sorted(WORKFLOWS_DIR.glob("*.yml"))
    if not files:
        console.print("[yellow]No workflow files found.[/yellow]")
        return

    for f in files:
        with open(f, "r") as fh:
            data = yaml.safe_load(fh) or {}
        name = data.get("name", f.stem)
        steps = len(data.get("steps", []))
        console.print(f"  [cyan]{f.name}[/cyan] — {name} ({steps} steps)")
