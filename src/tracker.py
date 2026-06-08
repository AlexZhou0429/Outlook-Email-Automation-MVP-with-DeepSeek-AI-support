from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

FIELDNAMES = [
    "processed_at_utc",
    "message_id",
    "conversation_id",
    "received_at",
    "subject",
    "from",
    "task_type_id",
    "task_type_name",
    "priority",
    "counterparty",
    "fund_or_entity",
    "due_date",
    "missing_items",
    "next_action",
    "risk_flags",
    "human_review_required",
    "draft_created",
    "confidence",
    "notes",
]


def already_processed(path: str | Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    with path.open("r", newline="", encoding="utf-8") as f:
        return {row["message_id"] for row in csv.DictReader(f) if row.get("message_id")}


def append_rows(path: str | Path, rows: Iterable[dict]) -> None:
    path = Path(path)
    path_exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not path_exists:
            writer.writeheader()
        for row in rows:
            clean = {name: row.get(name, "") for name in FIELDNAMES}
            writer.writerow(clean)


def make_tracker_row(message: dict, result: dict, draft_created: bool) -> dict:
    sender = ((message.get("from") or {}).get("emailAddress") or {})
    return {
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "message_id": message.get("id", ""),
        "conversation_id": message.get("conversationId", ""),
        "received_at": message.get("receivedDateTime", ""),
        "subject": message.get("subject", ""),
        "from": sender.get("address") or sender.get("name") or "",
        "task_type_id": result.get("task_type_id", ""),
        "task_type_name": result.get("task_type_name", ""),
        "priority": result.get("priority", ""),
        "counterparty": result.get("counterparty") or "",
        "fund_or_entity": result.get("fund_or_entity") or "",
        "due_date": result.get("due_date") or "",
        "missing_items": " | ".join(result.get("missing_items") or []),
        "next_action": result.get("next_action", ""),
        "risk_flags": " | ".join(result.get("risk_flags") or []),
        "human_review_required": str(result.get("human_review_required", True)),
        "draft_created": str(draft_created),
        "confidence": result.get("confidence", ""),
        "notes": result.get("notes", ""),
    }
