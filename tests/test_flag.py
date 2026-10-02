import json
from pathlib import Path

import pytest

from claims.tools import flag_for_human_review


def test_flag_appends_one_record(tmp_path: Path) -> None:
    queue_path = tmp_path / "review_queue.json"
    record = flag_for_human_review(
        "E103",
        "I need a new iPhone.",
        "phone is not covered",
        queue_path=queue_path,
    )
    saved = json.loads(queue_path.read_text(encoding="utf-8"))
    assert saved == [record]


def test_flag_empty_reason_writes_nothing(tmp_path: Path) -> None:
    queue_path = tmp_path / "review_queue.json"
    with pytest.raises(ValueError):
        flag_for_human_review("E103", "I need a phone.", "  ", queue_path=queue_path)
    assert not queue_path.exists()


def test_flag_unknown_employee_writes_nothing(tmp_path: Path) -> None:
    queue_path = tmp_path / "review_queue.json"
    with pytest.raises(KeyError):
        flag_for_human_review("E999", "I need a monitor.", "unknown id", queue_path=queue_path)
    assert not queue_path.exists()
