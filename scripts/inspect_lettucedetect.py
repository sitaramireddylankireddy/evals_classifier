"""Print what the model wrapper needs to know about the lettucedetect package and the model.

For task T012 of feature 003. It only reads files from disk: it does not import
lettucedetect, load the model, or use the network.

The report is written to inspect_output.txt as UTF-8.

Usage:
    python scripts/inspect_lettucedetect.py --model-path C:/models/lettucedect-base-modernbert-en-v1
"""

import argparse
import contextlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path

KEYWORDS = ("format_context", "max_length", "id2label", "offset_mapping", "class TransformerDetector")


def section(title: str) -> None:
    print(f"\n{'=' * 78}\n{title}\n{'=' * 78}")


def show_versions() -> None:
    section("Package versions")
    for name in ("lettucedetect", "transformers", "torch", "tokenizers"):
        try:
            print(f"{name}: {importlib.metadata.version(name)}")
        except importlib.metadata.PackageNotFoundError:
            print(f"{name}: NOT INSTALLED")


def show_package() -> None:
    spec = importlib.util.find_spec("lettucedetect")
    if spec is None or not spec.submodule_search_locations:
        section("lettucedetect is not installed")
        return
    root = Path(next(iter(spec.submodule_search_locations)))

    section(f"Files in {root}")
    files = sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for path in files:
        print(path.relative_to(root).as_posix())

    for path in files:
        relative = path.relative_to(root).as_posix()
        is_english_prompt = (
            "prompt" in relative.lower() and path.suffix != ".py" and "_en" in path.stem.lower()
        )
        if is_english_prompt:
            section(f"Prompt file: {relative}")
            print(path.read_text(encoding="utf-8"))

    for path in files:
        if path.suffix != ".py":
            continue
        source = path.read_text(encoding="utf-8")
        if not any(keyword in source for keyword in KEYWORDS):
            continue
        relative = path.relative_to(root).as_posix()
        # Files about other detectors (LLM or other methods) are not needed.
        if "llm" in relative.lower() or "rag_fact" in relative.lower():
            continue
        section(f"Source: {relative}")
        print(source)


def show_model(model_path: Path) -> None:
    section(f"Model folder: {model_path}")
    if not model_path.is_dir():
        print("Folder not found.")
        return
    for path in sorted(model_path.rglob("*")):
        if path.is_file():
            print(f"{path.relative_to(model_path).as_posix()}  ({path.stat().st_size:,} bytes)")

    config_path = model_path / "config.json"
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        section("config.json (selected keys)")
        for key in (
            "architectures",
            "model_type",
            "id2label",
            "label2id",
            "num_labels",
            "max_position_embeddings",
            "transformers_version",
        ):
            print(f"{key}: {config.get(key)}")

    tokenizer_config_path = model_path / "tokenizer_config.json"
    if tokenizer_config_path.is_file():
        tokenizer_config = json.loads(tokenizer_config_path.read_text(encoding="utf-8"))
        section("tokenizer_config.json (selected keys)")
        for key in ("tokenizer_class", "model_max_length", "cls_token", "sep_token"):
            print(f"{key}: {tokenizer_config.get(key)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model-path", type=Path, help="local folder holding the model")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("inspect_output.txt"),
        help="file to write the report to, as UTF-8 (default: inspect_output.txt)",
    )
    args = parser.parse_args()

    # Written straight to a UTF-8 file: the Windows console encoding cannot
    # represent every character in the package source.
    with args.out.open("w", encoding="utf-8") as handle, contextlib.redirect_stdout(handle):
        show_versions()
        show_package()
        if args.model_path:
            show_model(args.model_path)
    print(f"Report written to {args.out}")


if __name__ == "__main__":
    main()
