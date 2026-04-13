"""Intellapi CLI — the main user-facing interface.

Commands:
  intellapi init               Interactive setup
  intellapi generate           Generate documentation
  intellapi doctor             Validate setup
  intellapi config show        Show resolved config
  intellapi config set K V     Update a config value
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import typer
from rich.prompt import Prompt, Confirm
from rich.table import Table

from intellapi import __version__
from intellapi.config import (
    IntellapiConfig,
    OutputFormat,
    Provider,
    SECRET_CONFIG_KEYS,
    read_user_config,
    resolve_config,
    store_api_key,
    update_user_config,
    write_user_config,
    USER_CONFIG_FILE,
    find_project_config,
)
from intellapi.utils import console, print_error, print_info, print_success, print_warning

# ─── App ────────────────────────────────────────────────────────────────────

app = typer.Typer(
    name="intellapi",
    help="AI-powered API documentation generator.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

config_app = typer.Typer(help="Manage configuration.")
app.add_typer(config_app, name="config")


# ─── Version callback ──────────────────────────────────────────────────────


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"intellapi {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Intellapi — AI-powered API documentation generator."""
    pass


# ─── init ───────────────────────────────────────────────────────────────────


@app.command()
def init() -> None:
    """Interactive setup — choose provider, configure credentials, save config."""
    console.print("\n[bold]Intellapi Setup[/bold]\n")

    # ── Provider selection ───────────────────────────────────────────────
    console.print("Choose your LLM provider:\n")
    console.print("  [cyan]1[/cyan]  AWS Bedrock (Claude on AWS)")
    console.print("  [cyan]2[/cyan]  Anthropic (direct API)")
    console.print("  [cyan]3[/cyan]  OpenAI-compatible (OpenAI, OpenRouter, Ollama, custom)\n")

    choice = Prompt.ask(
        "Provider",
        choices=["1", "2", "3"],
    )

    provider_map = {
        "1": Provider.BEDROCK,
        "2": Provider.ANTHROPIC,
        "3": Provider.OPENAI_COMPATIBLE,
    }
    provider = provider_map[choice]

    config_data: dict = {"provider": provider.value}

    # ── Provider-specific setup ──────────────────────────────────────────
    if provider == Provider.BEDROCK:
        _setup_bedrock(config_data)
    elif provider == Provider.ANTHROPIC:
        _setup_anthropic(config_data)
    elif provider == Provider.OPENAI_COMPATIBLE:
        _setup_openai_compatible(config_data)

    # ── Write user config ────────────────────────────────────────────────
    write_user_config(config_data)
    print_success(f"Config written to {USER_CONFIG_FILE}")

    console.print("\n[dim]You can now run 'intellapi generate' in any project directory.[/dim]\n")


def _setup_bedrock(config_data: dict) -> None:
    """Configure AWS Bedrock provider."""
    console.print("\n[dim]Bedrock uses your existing AWS credentials (env vars, ~/.aws/credentials, SSO, IAM role).[/dim]\n")

    region = Prompt.ask("AWS region", default="us-east-1")
    config_data["aws_region"] = region

    profile = Prompt.ask("AWS profile (leave blank for default chain)", default="")
    if profile:
        config_data["aws_profile"] = profile

    model = Prompt.ask(
        "Model ID",
        default="anthropic.claude-3-haiku-20240307-v1:0",
    )
    config_data["model"] = model

    console.print("\n[dim]AWS credentials are resolved via your existing AWS config -- nothing stored by Intellapi.[/dim]")


def _setup_anthropic(config_data: dict) -> None:
    """Configure Anthropic direct API provider."""
    api_key = Prompt.ask("\nAnthropic API key", password=True)

    if store_api_key(Provider.ANTHROPIC, api_key):
        print_success("API key saved to OS keyring")
    else:
        print_warning(
            "Could not save to keyring. Set INTELLAPI_API_KEY env var instead."
        )

    model = Prompt.ask(
        "Model",
        default="claude-3-5-sonnet-20241022",
    )
    config_data["model"] = model


def _setup_openai_compatible(config_data: dict) -> None:
    """Configure OpenAI-compatible provider."""
    console.print("\n[dim]Common base URLs:[/dim]")
    console.print("  [dim]OpenAI:     https://api.openai.com/v1[/dim]")
    console.print("  [dim]OpenRouter: https://openrouter.ai/api/v1[/dim]")
    console.print("  [dim]Ollama:     http://localhost:11434/v1[/dim]\n")

    base_url = Prompt.ask("Base URL", default="https://api.openai.com/v1")
    config_data["base_url"] = base_url

    api_key = Prompt.ask("API key", password=True)

    if store_api_key(Provider.OPENAI_COMPATIBLE, api_key):
        print_success("API key saved to OS keyring")
    else:
        print_warning(
            "Could not save to keyring. Set INTELLAPI_API_KEY env var instead."
        )

    model = Prompt.ask("Model", default="gpt-4o-mini")
    config_data["model"] = model


def _resolve_generation_target(path: Optional[Path], non_interactive: bool) -> Path:
    """Resolve the backend directory to analyze."""
    if path is not None:
        return path.resolve()

    from intellapi.scanner.framework_detector import discover_backend_candidates

    cwd = Path.cwd().resolve()
    candidates = discover_backend_candidates(cwd)
    if not candidates:
        return cwd
    if len(candidates) == 1:
        return candidates[0].path
    if non_interactive:
        choices = ", ".join(str(candidate.path.relative_to(cwd)) for candidate in candidates)
        raise ValueError(
            "Multiple backend directories detected in non-interactive mode. "
            f"Pass --path explicitly. Candidates: {choices}"
        )

    console.print("\n[bold]Multiple backend directories detected:[/bold]\n")
    for index, candidate in enumerate(candidates, 1):
        label = "."
        if candidate.path != cwd:
            label = str(candidate.path.relative_to(cwd))
        console.print(
            f"  [cyan]{index}[/cyan]  {label} "
            f"({candidate.detection.framework} / {candidate.detection.language}, "
            f"{candidate.detection.confidence:.0%} confidence)"
        )
    console.print()

    choice = Prompt.ask(
        "Choose backend directory",
        choices=[str(i) for i in range(1, len(candidates) + 1)],
        default="1",
    )
    return candidates[int(choice) - 1].path


# ─── generate ───────────────────────────────────────────────────────────────


@app.command()
def generate(
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to the backend directory to analyze. Defaults to current directory.",
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        "-m",
        help="Override the LLM model for this run.",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="Override the provider (openai_compatible, anthropic, bedrock).",
    ),
    format: Optional[str] = typer.Option(
        None,
        "--format",
        "-f",
        help="Output format: md, txt, or both.",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="Output file path.",
    ),
    openapi_file: Optional[str] = typer.Option(
        None,
        "--openapi-file",
        help="Path to an OpenAPI spec file to merge with static analysis.",
    ),
    openapi_url: Optional[str] = typer.Option(
        None,
        "--openapi-url",
        help="URL of an OpenAPI spec to merge with static analysis.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Preview what would happen without calling the LLM.",
    ),
    non_interactive: bool = typer.Option(
        False,
        "--non-interactive",
        help="CI mode -- no interactive prompts, fail on ambiguity.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Debug output including privacy audit log.",
    ),
) -> None:
    """Generate API documentation for a backend project."""
    try:
        target_path = _resolve_generation_target(path, non_interactive)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)

    # Build CLI overrides
    overrides: dict = {}
    if model:
        overrides["model"] = model
    if provider:
        overrides["provider"] = provider
    if format:
        overrides["output_format"] = format
    if output:
        overrides["output_path"] = output
    if openapi_file:
        overrides["openapi_file"] = openapi_file
    if openapi_url:
        overrides["openapi_url"] = openapi_url

    # Resolve config
    try:
        config = resolve_config(cli_overrides=overrides, project_dir=target_path)
    except Exception as e:
        print_error(f"Configuration error: {e}")
        raise typer.Exit(1)

    if not config.provider and not dry_run:
        print_error("No provider configured. Run 'intellapi init' first.")
        raise typer.Exit(1)

    # Run pipeline
    from intellapi.generator.pipeline import run_pipeline

    console.print(f"\n[bold]Generating documentation for:[/bold] {target_path}\n")

    try:
        result = run_pipeline(
            target_path=target_path,
            config=config,
            dry_run=dry_run,
            verbose=verbose,
        )
        if result:
            console.print()
    except KeyboardInterrupt:
        print_warning("\nGeneration cancelled.")
        raise typer.Exit(130)
    except Exception as e:
        print_error(f"Generation failed: {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


# ─── doctor ─────────────────────────────────────────────────────────────────


@app.command()
def doctor(
    path: Optional[Path] = typer.Option(
        None,
        "--path",
        "-p",
        help="Path to check. Defaults to current directory.",
    ),
) -> None:
    """Validate your Intellapi setup — config, credentials, provider connectivity."""
    console.print("\n[bold]Intellapi Doctor[/bold]\n")

    target_path = (path or Path.cwd()).resolve()
    all_ok = True

    # ── Check 1: User config ────────────────────────────────────────────
    if USER_CONFIG_FILE.exists():
        print_success(f"User config: {USER_CONFIG_FILE}")
    else:
        print_warning(f"User config not found: {USER_CONFIG_FILE}")
        print_info("  This is optional if you use project config or environment variables.")

    # ── Check 2: Project config ─────────────────────────────────────────
    project_config_path = find_project_config(target_path)
    if project_config_path:
        print_success(f"Project config: {project_config_path}")
    else:
        print_info("  No .intellapi.yml found (optional)")

    # ── Check 3: Resolve config ─────────────────────────────────────────
    try:
        config = resolve_config(project_dir=target_path)
    except Exception as e:
        print_error(f"Config resolution failed: {e}")
        raise typer.Exit(1)

    if config.provider:
        print_success(f"Provider: {config.provider.value}")
    else:
        print_error("No provider configured")
        all_ok = False

    if config.model:
        print_success(f"Model: {config.model}")
    else:
        print_warning("No model configured (will use provider default)")

    # ── Check 4: Credentials ────────────────────────────────────────────
    if config.provider == Provider.BEDROCK:
        print_info("  Bedrock credentials: using AWS credential chain")
    elif config.provider and config.api_key:
        print_success("API key: configured (from keyring or env var)")
    elif config.provider:
        print_error("API key: not found. Run 'intellapi init' or set INTELLAPI_API_KEY.")
        all_ok = False

    # ── Check 5: Framework detection ────────────────────────────────────
    from intellapi.scanner.framework_detector import detect_framework

    detections = detect_framework(target_path)
    if detections:
        for det in detections:
            print_success(
                f"Framework detected: {det.framework} ({det.language}) "
                f"- {det.confidence:.0%}"
            )
    else:
        print_warning(f"No framework detected in {target_path}")

    # ── Check 6: File discovery ─────────────────────────────────────────
    from intellapi.scanner.file_discovery import discover_files

    files = discover_files(target_path)
    if files:
        print_success(f"Source files found: {len(files)}")
    else:
        print_warning(f"No source files found in {target_path}")

    # ── Check 7: Provider connectivity ──────────────────────────────────
    if config.provider:
        console.print("\n[dim]Testing provider connectivity...[/dim]")
        try:
            from intellapi.llm.client import LLMClient

            client = LLMClient(config)
            if client.validate_connection():
                print_success(f"Provider connectivity: OK ({client.provider_name})")
            else:
                print_error(f"Provider connectivity: FAILED ({client.provider_name})")
                all_ok = False
        except Exception as e:
            print_error(f"Provider initialization failed: {e}")
            all_ok = False

    # ── Summary ─────────────────────────────────────────────────────────
    console.print()
    if all_ok:
        print_success("All checks passed! You're ready to generate documentation.")
    else:
        print_warning("Some checks failed. Fix the issues above and run 'intellapi doctor' again.")

    console.print()


# ─── config commands ────────────────────────────────────────────────────────


@config_app.command("show")
def config_show() -> None:
    """Show the resolved configuration (secrets masked)."""
    try:
        config = resolve_config()
    except Exception as e:
        print_error(f"Config resolution failed: {e}")
        raise typer.Exit(1)

    table = Table(title="Intellapi Configuration", show_header=True)
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="white")
    table.add_column("Source", style="dim")

    display = config.display_dict()

    # Determine source for each key
    user_data = read_user_config()
    from intellapi.config import read_project_config
    project_data = read_project_config()

    for key, value in display.items():
        if key in ("api_key",):
            source = "keyring / env"
        elif key in project_data:
            source = ".intellapi.yml"
        elif key in user_data:
            source = "~/.intellapi/config.yml"
        else:
            source = "default"

        table.add_row(key, str(value), source)

    console.print()
    console.print(table)
    console.print()


@config_app.command("set")
def config_set(
    key: str = typer.Argument(help="Config key to set (e.g., model, provider, aws_region)."),
    value: str = typer.Argument(help="Value to set."),
) -> None:
    """Update a value in the user config (~/.intellapi/config.yml)."""
    if key in SECRET_CONFIG_KEYS:
        print_error(
            f"'{key}' is secret material and cannot be stored in config files. "
            "Use 'intellapi init' or environment variables instead."
        )
        raise typer.Exit(1)

    # Validate known keys
    known_keys = {
        "provider", "model", "base_url", "aws_region", "aws_profile",
        "output_format", "output_filename",
    }

    if key not in known_keys:
        print_warning(
            f"Unknown config key: '{key}'. Known keys: {', '.join(sorted(known_keys))}"
        )
        if not Confirm.ask("Set it anyway?", default=False):
            raise typer.Exit()

    try:
        update_user_config(key, value)
    except ValueError as e:
        print_error(str(e))
        raise typer.Exit(1)
    print_success(f"Set {key} = {value} in {USER_CONFIG_FILE}")
