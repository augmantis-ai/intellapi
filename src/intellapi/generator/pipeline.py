"""Pipeline orchestration for documentation generation."""

from __future__ import annotations

from pathlib import Path

from intellapi.config import IntellapiConfig, OutputFormat
from intellapi.generator.renderer import render_markdown, render_plaintext
from intellapi.llm.client import LLMClient
from intellapi.llm.schemas import DocumentationDraft
from intellapi.openapi import load_openapi_spec, merge_openapi_into_ir
from intellapi.privacy import PrivacyFilterResult, filter_files, print_audit_log
from intellapi.scanner.file_discovery import discover_files
from intellapi.scanner.framework_detector import DetectionResult, detect_framework
from intellapi.scanner.ir import IntermediateRepresentation
from intellapi.scanner.node_extractor import NodeExtractor
from intellapi.scanner.python_extractor import PythonExtractor
from intellapi.utils import console, create_progress, print_error, print_info, print_success, print_warning


def run_pipeline(
    target_path: Path,
    config: IntellapiConfig,
    dry_run: bool = False,
    verbose: bool = False,
) -> Path | None:
    """Run the documentation pipeline."""
    target_path = target_path.resolve()

    if not target_path.exists() or not target_path.is_dir():
        print_error(f"Target path does not exist or is not a directory: {target_path}")
        return None

    openapi_spec: dict | None = None
    openapi_source: str | None = None

    with create_progress() as progress:
        task = progress.add_task("Scanning files...", total=6)

        files = discover_files(target_path)
        if not files:
            print_error(f"No source files found in {target_path}")
            return None

        print_info(f"Found {len(files)} source files")
        progress.advance(task)

        progress.update(task, description="Applying privacy filters...")
        filter_result: PrivacyFilterResult = filter_files(files)
        if verbose:
            print_audit_log(filter_result)

        if not filter_result.allowed:
            print_error("All files were filtered by privacy rules. Nothing to analyze.")
            return None

        print_info(
            f"Privacy filter: {filter_result.allowed_count} allowed, "
            f"{filter_result.skipped_count} skipped"
        )
        progress.advance(task)

        progress.update(task, description="Detecting framework...")
        detections = detect_framework(target_path)
        if detections:
            detection = detections[0]
            print_info(
                f"Detected: {detection.framework} ({detection.language}) "
                f"- {detection.confidence:.0%} confidence"
            )
            for evidence in detection.evidence:
                print_info(f"  - {evidence}")
        else:
            print_warning("Could not auto-detect framework. Using generic analysis.")
            detection = DetectionResult(
                framework="unknown",
                language="unknown",
                confidence=0.0,
                evidence=["No framework detected"],
            )
        progress.advance(task)

        progress.update(task, description="Loading OpenAPI input...")
        if config.openapi_file or config.openapi_url:
            openapi_spec, openapi_source = load_openapi_spec(
                openapi_file=config.openapi_file,
                openapi_url=config.openapi_url,
            )
            path_count = len(openapi_spec.get("paths", {})) if isinstance(openapi_spec.get("paths"), dict) else 0
            print_info(f"OpenAPI loaded: {openapi_source}")
            print_info(f"OpenAPI paths: {path_count}")
        progress.advance(task)

        if dry_run:
            console.print()
            console.print("[bold]Dry Run Summary[/bold]")
            print_info(f"Target: {target_path}")
            print_info(f"Framework: {detection.framework}")
            print_info(f"Language: {detection.language}")
            print_info(f"Files to analyze: {filter_result.allowed_count}")
            print_info(f"Files skipped: {filter_result.skipped_count}")
            if openapi_source:
                print_info(f"OpenAPI source: {openapi_source}")
            for output_target in _selected_output_paths(target_path, config):
                print_info(f"Output: {output_target}")
            print_info(f"Format: {config.output_format}")
            console.print("\n[dim]No LLM call made. Remove --dry-run to generate.[/dim]")
            return None

        progress.update(task, description="Analyzing code...")
        ir = _extract(detection, filter_result.allowed)
        if openapi_spec and openapi_source:
            ir = merge_openapi_into_ir(ir, openapi_spec, openapi_source)
        for warning in ir.extraction_warnings:
            print_warning(warning)
        print_info(f"Extracted {len(ir.endpoints)} endpoints, {len(ir.models)} models")
        if not ir.endpoints:
            print_error(
                "No API endpoints could be derived from source analysis. "
                "Provide --openapi-file/--openapi-url or wait for the framework extractor milestone."
            )
            return None
        progress.advance(task)

        progress.update(task, description="Generating documentation...")
        if not config.provider:
            print_error("No provider configured. Run 'intellapi init' first.")
            return None

        client = LLMClient(config)
        draft = client.generate_documentation(ir)
        progress.advance(task)

    output_path = _write_output(target_path, config, draft)
    print_success(f"Documentation written to {output_path}")
    return output_path


def _extract(detection: DetectionResult, files: list[Path]) -> IntermediateRepresentation:
    """Route to the correct extractor based on framework detection."""
    if detection.language == "python":
        extractor = PythonExtractor(framework=detection.framework)
    elif detection.framework in ("express", "nextjs", "sveltekit"):
        extractor = NodeExtractor(framework=detection.framework)
    else:
        extractor = PythonExtractor(framework=detection.framework)
    return extractor.extract(files)


def _write_output(target_path: Path, config: IntellapiConfig, draft: DocumentationDraft) -> Path:
    """Render the draft and write to disk."""
    output_paths = _planned_output_paths(target_path, config)

    if config.output_format in (OutputFormat.MD, OutputFormat.BOTH):
        md_path = output_paths["md"]
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(render_markdown(draft), encoding="utf-8")

    if config.output_format in (OutputFormat.TXT, OutputFormat.BOTH):
        txt_path = output_paths["txt"]
        txt_path.parent.mkdir(parents=True, exist_ok=True)
        txt_path.write_text(render_plaintext(draft), encoding="utf-8")

    if config.output_format == OutputFormat.TXT:
        return output_paths["txt"]
    return output_paths["md"]


def _planned_output_paths(target_path: Path, config: IntellapiConfig) -> dict[str, Path]:
    """Resolve output file paths for each requested format."""
    if config.output_path:
        base_path = Path(config.output_path)
        if not base_path.is_absolute():
            base_path = (Path.cwd() / base_path).resolve()
    else:
        base_path = target_path / config.output_filename

    suffix = base_path.suffix.lower()
    stem_path = base_path.with_suffix("") if suffix else base_path
    md_path = base_path if suffix == ".md" else stem_path.with_suffix(".md")
    txt_path = base_path if suffix == ".txt" else stem_path.with_suffix(".txt")
    return {"md": md_path, "txt": txt_path}


def _selected_output_paths(target_path: Path, config: IntellapiConfig) -> list[Path]:
    """Return only the output files requested by the selected format."""
    output_paths = _planned_output_paths(target_path, config)
    if config.output_format == OutputFormat.MD:
        return [output_paths["md"]]
    if config.output_format == OutputFormat.TXT:
        return [output_paths["txt"]]
    return [output_paths["md"], output_paths["txt"]]
