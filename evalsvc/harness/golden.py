"""Load the golden set: input items that carry a known correct label."""

from pathlib import Path

from evalsvc.config import GoldenSettings
from evalsvc.ingest.json_list import load_json_file
from evalsvc.interfaces import InputParser
from evalsvc.safelog import log_event
from evalsvc.types import FrozenModel, IngestIssue, Item


class GoldenItem(FrozenModel):
    item: Item
    is_failure: bool  # True when the label says the answer has unsupported content
    category: str | None = None


class GoldenLoad(FrozenModel):
    items: list[GoldenItem]
    issues: list[IngestIssue]  # objects rejected by the input parser
    unlabelled: int  # items with a missing or unknown label, left out


def load_golden(path: Path, parser: InputParser, settings: GoldenSettings) -> GoldenLoad:
    """Read a golden-set file in the normal input format.

    The label and the category are extra keys on each object.
    """
    ingest = parser.parse(load_json_file(path))

    items: list[GoldenItem] = []
    unlabelled = 0
    for item in ingest.items:
        label = item.metadata.get(settings.label_key)
        if label == settings.failure_value:
            is_failure = True
        elif label == settings.pass_value:
            is_failure = False
        else:
            unlabelled += 1
            log_event("golden.unlabelled", item_id=item.id)
            continue
        category = item.metadata.get(settings.category_key)
        if not isinstance(category, str) or not category.strip():
            category = None
        items.append(GoldenItem(item=item, is_failure=is_failure, category=category))

    return GoldenLoad(items=items, issues=ingest.issues, unlabelled=unlabelled)
