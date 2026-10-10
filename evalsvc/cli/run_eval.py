"""Measure the detector against a golden set and write a report.

Usage:
    python -m evalsvc.cli.run_eval --config config.toml --golden golden.jsonl --out reports

Add --sweep for the threshold sweep, --compare-models to compare the large and
base models of this config, --compare OTHER.toml to compare with another
config, and --model large|base to force a model.

Nothing is written to the result store and the judge is not called.
"""

import argparse
import gc
import hashlib
import logging
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from evalsvc.config import ConfigError, Settings, load_settings
from evalsvc.harness.golden import load_golden
from evalsvc.harness.metrics import compare
from evalsvc.harness.report import ConfigReport, Report, build_config_report, write_report
from evalsvc.harness.scoring import ScoredItem, score_items
from evalsvc.ingest.json_list import InputFileError, build_parser
from evalsvc.pipeline import Components, build_components
from evalsvc.records import ResultRecord
from evalsvc.runtime import set_offline_env

EXIT_OK = 0
EXIT_BAD_INPUT = 2


class NoStore:
    """Takes the place of the result store: the harness must never write to it."""

    def write(self, record: ResultRecord) -> None:
        raise RuntimeError("the golden-set harness does not write result records")

    def get_current(self, item_id: str) -> None:
        return None

    def iter_current(self):
        return iter(())


def harness_components(settings: Settings) -> Components:
    return build_components(settings, store=NoStore())


def _force_model(settings: Settings, variant: str) -> Settings:
    return settings.model_copy(
        update={"model": settings.model.model_copy(update={"select": variant})}
    )


def _release_model() -> None:
    """Free the previous model's memory before the next one is loaded."""
    gc.collect()
    torch = sys.modules.get("torch")
    if torch is not None and torch.cuda.is_available():
        torch.cuda.empty_cache()


def _evaluate_config(
    label: str,
    settings: Settings,
    golden_path: Path,
    with_sweep: bool,
    components_factory: Callable[[Settings], Components],
) -> tuple[ConfigReport, list[ScoredItem]]:
    # The file is read first, so a bad path fails before a model is loaded.
    load = load_golden(golden_path, build_parser(settings), settings.golden)
    components = components_factory(settings)
    scored = score_items(load.items, components)
    report = build_config_report(
        label=label,
        model=components.detector.info,
        threshold=components.detection.threshold,
        load=load,
        scored=scored,
        golden=settings.golden,
        sweep_settings=settings.sweep if with_sweep else None,
    )
    del components
    _release_model()
    return report, scored


def main(
    argv: list[str] | None = None,
    components_factory: Callable[[Settings], Components] = harness_components,
) -> int:
    parser = argparse.ArgumentParser(description="Measure the detector against a golden set.")
    parser.add_argument("--config", type=Path, required=True, help="path to the TOML config file")
    parser.add_argument("--golden", type=Path, required=True, help="labelled .json or .jsonl file")
    parser.add_argument("--out", type=Path, default=Path("reports"), help="folder for reports")
    parser.add_argument("--sweep", action="store_true", help="report measures at each threshold")
    parser.add_argument("--model", choices=["large", "base"], help="force a model for this run")
    comparing = parser.add_mutually_exclusive_group()
    comparing.add_argument("--compare", type=Path, help="a second config file to compare with")
    comparing.add_argument(
        "--compare-models", action="store_true", help="compare the large and base models"
    )
    parser.add_argument("--verbose", action="store_true", help="show progress events")
    args = parser.parse_args(argv)
    if args.model and args.compare_models:
        parser.error("--model cannot be used with --compare-models")

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    set_offline_env()

    try:
        settings = load_settings(args.config)
        if args.compare_models:
            runs = [
                ("large", _force_model(settings, "large")),
                ("base", _force_model(settings, "base")),
            ]
        else:
            first = _force_model(settings, args.model) if args.model else settings
            runs = [(args.model or args.config.stem, first)]
            if args.compare:
                runs.append((args.compare.stem, load_settings(args.compare)))

        results = [
            _evaluate_config(label, run_settings, args.golden, args.sweep, components_factory)
            for label, run_settings in runs
        ]
        golden_sha256 = hashlib.sha256(args.golden.read_bytes()).hexdigest()
    except (ConfigError, InputFileError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_BAD_INPUT

    comparison = None
    if len(results) == 2:
        (report_a, scored_a), (report_b, scored_b) = results
        comparison = compare(
            report_a.label,
            scored_a,
            report_a.threshold,
            report_b.label,
            scored_b,
            report_b.threshold,
            settings.golden.min_group_size,
        )

    now = datetime.now(UTC)
    report = Report(
        run_id=f"{now:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}",
        date=now.isoformat(timespec="seconds"),
        golden_file=args.golden.name,
        golden_sha256=golden_sha256,
        configs=[config for config, _ in results],
        comparison=comparison,
    )
    folder = write_report(report, args.out)

    # Numbers and identifiers only. Nothing from the items is printed.
    for config in report.configs:
        m = config.overall
        recall = f"{m.recall:.3f}" if m.recall is not None else "n/a"
        precision = f"{m.precision:.3f}" if m.precision is not None else "n/a"
        print(
            f"{config.label}: recall on known failures {recall}, precision {precision}, "
            f"evaluated {m.n}, labelled failures {m.failures}"
        )
    print(f"Report written to: {folder}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
