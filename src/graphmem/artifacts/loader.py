from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from graphmem.artifacts.models import Artifact


def load_artifacts(json_path: str | Path) -> list[Artifact]:
    """Load historical issues and pull requests from a JSON file."""
    path = Path(json_path)

    with path.open("r", encoding="utf-8") as file:
        records = json.load(file)

    if not isinstance(records, list):
        raise ValueError("Artifact JSON must contain a list of objects")

    artifacts: list[Artifact] = []

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"Artifact at index {index} must be an object")

        kind = record.get("kind")
        if kind not in {"issue", "pr"}:
            raise ValueError(f"Invalid artifact kind at index {index}: {kind!r}")

        files = record.get("files", [])
        if not isinstance(files, list) or not all(
            isinstance(item, str) for item in files
        ):
            raise ValueError(f"Invalid files list at index {index}")

        try:
            created_at = datetime.fromisoformat(record["created_at"])
            artifact = Artifact(
                kind=kind,
                number=int(record["number"]),
                title=str(record["title"]),
                body=str(record.get("body") or ""),
                created_at=created_at,
                files=files,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"Invalid artifact record at index {index}: {exc}"
            ) from exc

        artifacts.append(artifact)

    return artifacts
