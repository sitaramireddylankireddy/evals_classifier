"""Evaluate a file of items and write one result record per item.

Usage:
    python -m evalsvc.cli.run --config config.toml --input items.json

Exit codes: 0 the run completed (whatever the verdicts), 2 bad config or input,
3 the run broke part-way, for example because the store could not be written.
"""

import argparse
import logging
import sys
from collections.abc import Callable
from pathlib import Path

from evalsvc.config import ConfigError, Settings, load_settings
from evalsvc.ingest.json_list import InputFileError, build_parser, load_json_file
from evalsvc.pipeline import Components, build_components, evaluate_items
from evalsvc.records import RunSummary
from evalsvc.runtime import set_offline_env
from evalsvc.store.results import StoreError

EXIT_OK = 0
EXIT_BAD_INPUT = 2
EXIT_RUN_FAILED = 3


def _print_summary(summary: RunSummary, store_path: str) -> None:
    # Counts and identifiers only. Nothing from the items is printed.
    print(f"Run {summary.run_id}")
    print(f"Model: {summary.model} (device: {summary.device}), threshold {summary.threshold}")
    print(f"Received: {summary.received} | skipped at input: {summary.skipped_at_input}")
    print(
        f"Evaluated: {summary.evaluated} | passed: {summary.passed} | "
        f"failed: {summary.failed} | not evaluable: {summary.not_evaluable}"
    )
    print(f"Escalated: {summary.escalated} | escalation failed: {summary.escalation_failed}")
    print(f"Results written to: {store_path}")


def main(
    argv: list[str] | None = None,
    components_factory: Callable[[Settings], Components] = build_components,
) -> int:
    parser = argparse.ArgumentParser(description="Evaluate a file of items for groundedness.")
    parser.add_argument("--config", type=Path, required=True, help="path to the TOML config file")
    parser.add_argument("--input", type=Path, required=True, help="path to a .json or .jsonl file")
    parser.add_argument("--verbose", action="store_true", help="show progress events")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    set_offline_env()

    try:
        settings = load_settings(args.config)
        raw = load_json_file(args.input)
        ingest = build_parser(settings).parse(raw)
        components = components_factory(settings)
    except (ConfigError, InputFileError, StoreError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT

    try:
        summary = evaluate_items(ingest.items, components, skipped_at_input=len(ingest.issues))
    except StoreError as exc:
        print(f"Run stopped: {exc}", file=sys.stderr)
        return EXIT_RUN_FAILED

    _print_summary(summary, settings.store.path)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
