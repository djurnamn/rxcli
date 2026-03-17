"""CLI entry point for rxcli."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import ax
from .rx import RX, RXError


def setup_logging(verbose: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger = logging.getLogger("rxcli")
    logger.setLevel(level)
    logger.addHandler(handler)


def output_json(data: dict):
    """Print structured JSON result to stdout."""
    json.dump(data, sys.stdout, indent=2)
    sys.stdout.write("\n")


def emit_progress(module: str, stage: str, step: int, total: int):
    """Emit a JSON progress line to stderr."""
    line = json.dumps({"module": module, "stage": stage, "step": step, "total": total})
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


def _emit_module_progress(stage: str, step: int, total: int):
    """Emit progress for the standalone debleed command (single-module shorthand)."""
    emit_progress("debleed", stage, step, total)


def cmd_reset(args):
    """Reset RX to a clean state."""
    rx = RX()
    rx.launch()
    rx.reset()
    output_json({"status": "success", "action": "reset"})


def cmd_debleed(args):
    """Run De-bleed processing — shorthand for a single-step pipeline."""
    from .pipeline import run_pipeline

    rx = RX()
    rx.launch()

    if args.reset_before:
        rx.reset()

    on_progress = emit_progress if args.progress else None

    step = {"module": "debleed", "reference": args.reference}
    if args.preset is not None:
        step["preset"] = args.preset
    if args.reduction is not None:
        step["reduction"] = args.reduction
    if args.smoothing is not None:
        step["smoothing"] = args.smoothing

    try:
        result = run_pipeline(
            rx,
            input_path=args.input,
            output_path=args.output,
            steps=[step],
            on_progress=on_progress,
        )
        output_json(result)
    except RXError as e:
        output_json({
            "status": "error",
            "module": "debleed",
            "error": str(e),
        })
        sys.exit(1)
    finally:
        if args.reset_after:
            rx.reset()
        if args.quit:
            rx.quit()


def cmd_pipeline(args):
    """Run a multi-step pipeline from a JSON config file."""
    from .pipeline import run_pipeline

    with open(args.config) as f:
        config = json.load(f)

    input_path = config.get("input")
    output_path = config.get("output")
    steps = config.get("steps", [])

    if not input_path:
        print("ERROR: Pipeline config missing 'input'", file=sys.stderr)
        sys.exit(1)
    if not output_path:
        print("ERROR: Pipeline config missing 'output'", file=sys.stderr)
        sys.exit(1)
    if not steps:
        print("ERROR: Pipeline config has no 'steps'", file=sys.stderr)
        sys.exit(1)

    rx = RX()
    rx.launch()

    if args.reset_before:
        rx.reset()

    on_progress = emit_progress if args.progress else None

    try:
        result = run_pipeline(
            rx,
            input_path=input_path,
            output_path=output_path,
            steps=steps,
            on_progress=on_progress,
        )
        output_json(result)
    except RXError as e:
        output_json({
            "status": "error",
            "error": str(e),
        })
        sys.exit(1)
    finally:
        if args.reset_after:
            rx.reset()
        if args.quit:
            rx.quit()


def cmd_inspect(args):
    """Inspect the current RX UI state (for debugging)."""
    rx = RX()
    rx.launch()

    windows = rx.windows()
    result = {
        "windows": [],
        "status": rx.status_text(),
    }
    for w in windows:
        win_info = {"title": w.title, "role": w.role}
        result["windows"].append(win_info)

    output_json(result)


def main():
    if not ax.check_accessibility():
        print("ERROR: Accessibility permissions not granted.", file=sys.stderr)
        print("Go to System Settings > Privacy & Security > Accessibility", file=sys.stderr)
        print("and add your terminal application.", file=sys.stderr)
        sys.exit(1)

    parser = argparse.ArgumentParser(
        prog="rxcli",
        description="CLI tool for automating iZotope RX 11 Audio Editor",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="verbose logging")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # -- reset --
    p_reset = subparsers.add_parser("reset", help="Reset RX to a clean state")
    p_reset.set_defaults(func=cmd_reset)

    # -- debleed (shorthand for single-step pipeline) --
    p_debleed = subparsers.add_parser("debleed", help="Run De-bleed processing")
    p_debleed.add_argument("--input", "-i", required=True, help="Audio file to process")
    p_debleed.add_argument("--reference", "-r", required=True, help="Bleed source track")
    p_debleed.add_argument("--output", "-o", required=True, help="Output file path")
    p_debleed.add_argument("--preset", help="Load a preset by exact name")
    p_debleed.add_argument("--reduction", type=float, default=None,
                           help="Reduction strength 0.0-8.0 (overrides preset)")
    p_debleed.add_argument("--smoothing", type=float, default=None,
                           help="Artifact smoothing 0.0-15.0 (overrides preset)")
    p_debleed.add_argument("--reset-before", action="store_true", default=True,
                           help="Reset RX before processing (default: true)")
    p_debleed.add_argument("--no-reset-before", action="store_false", dest="reset_before")
    p_debleed.add_argument("--reset-after", action="store_true", default=True,
                           help="Reset RX after processing (default: true)")
    p_debleed.add_argument("--no-reset-after", action="store_false", dest="reset_after")
    p_debleed.add_argument("--quit", action="store_true",
                           help="Quit RX after processing")
    p_debleed.add_argument("--progress", action="store_true",
                           help="Emit JSON progress lines to stderr")
    p_debleed.set_defaults(func=cmd_debleed)

    # -- pipeline --
    p_pipeline = subparsers.add_parser("pipeline", help="Run a multi-step pipeline from JSON config")
    p_pipeline.add_argument("--config", "-c", required=True,
                            help="Path to pipeline JSON config file")
    p_pipeline.add_argument("--reset-before", action="store_true", default=True,
                            help="Reset RX before processing (default: true)")
    p_pipeline.add_argument("--no-reset-before", action="store_false", dest="reset_before")
    p_pipeline.add_argument("--reset-after", action="store_true", default=True,
                            help="Reset RX after processing (default: true)")
    p_pipeline.add_argument("--no-reset-after", action="store_false", dest="reset_after")
    p_pipeline.add_argument("--quit", action="store_true",
                            help="Quit RX after processing")
    p_pipeline.add_argument("--progress", action="store_true",
                            help="Emit JSON progress lines to stderr")
    p_pipeline.set_defaults(func=cmd_pipeline)

    # -- inspect --
    p_inspect = subparsers.add_parser("inspect", help="Inspect current RX UI state")
    p_inspect.set_defaults(func=cmd_inspect)

    args = parser.parse_args()
    setup_logging(args.verbose)
    args.func(args)
