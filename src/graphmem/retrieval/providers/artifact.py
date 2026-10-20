from __future__ import annotations

import re
from datetime import datetime, timezone

from graphmem.artifacts.models import Artifact
from graphmem.indexing.code_index import tokenize
from graphmem.models.entities import CodeEntity
from graphmem.retrieval.evidence import Evidence


MAX_ARTIFACTS = 5


def _normalize_path(path: str | None) -> str | None:
    """Normalize repository-relative paths for comparison."""
    if not path:
        return None

    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]

    return normalized or None


def _comparable_time(value: datetime) -> datetime:
    """Treat naive timestamps as UTC for consistent comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


def _contains_whole_name(text: str, name: str | None) -> bool:
    """Match an entity name without matching it inside another identifier."""
    if not name:
        return False

    pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


class ArtifactProvider:
    """Evidence provider backed by historical issues and pull requests."""

    signal = "artifact"

    def __init__(
        self,
        artifacts: list[Artifact],
        as_of: datetime | None = None,
    ) -> None:
        cutoff = _comparable_time(as_of) if as_of is not None else None

        # ADR-13: exclude artifacts created after the evaluation timestamp.
        self.artifacts = [
            artifact
            for artifact in artifacts
            if cutoff is None
            or _comparable_time(artifact.created_at) <= cutoff
        ]

    def score(
        self,
        scopes: list[CodeEntity],
        issue: str,
    ) -> dict[str, list[Evidence]]:
        """Return artifact evidence only when a defensible entity link exists."""
        if not scopes or not self.artifacts:
            return {}

        issue_tokens = set(tokenize(issue))
        if not issue_tokens:
            return {}

        # Rank artifacts by lexical overlap with the issue.
        ranked: list[tuple[int, Artifact]] = []

        for artifact in self.artifacts:
            artifact_text = f"{artifact.title} {artifact.body}"
            artifact_tokens = set(tokenize(artifact_text))
            overlap = len(issue_tokens & artifact_tokens)

            if overlap > 0:
                ranked.append((overlap, artifact))

        ranked.sort(key=lambda item: item[0], reverse=True)
        candidates = ranked[:MAX_ARTIFACTS]

        if not candidates:
            return {}

        best_overlap = candidates[0][0]
        results: dict[str, list[Evidence]] = {}

        for scope in scopes:
            scope_path = _normalize_path(scope.path)
            scope_names = {
                name
                for name in (scope.name, scope.qualified_name)
                if name
            }

            for overlap, artifact in candidates:
                artifact_text = f"{artifact.title}\n{artifact.body}"

                # Explicit path links take precedence over name mentions.
                changed_paths = {
                    normalized
                    for path in artifact.files
                    if (normalized := _normalize_path(path)) is not None
                }

                if scope_path is not None and scope_path in changed_paths:
                    link = "explicit_path"
                    confidence = 1.0
                elif any(
                    _contains_whole_name(artifact_text, name)
                    for name in scope_names
                ):
                    link = "entity_mention"
                    confidence = 0.8
                else:
                    # ADR-06: similarity alone never establishes a link.
                    continue

                artifact_relevance = overlap / best_overlap
                weight = artifact_relevance * confidence

                if artifact.kind == "pr":
                    source = (
                        f"PR #{artifact.number} '{artifact.title}' "
                        f"changed or referenced this code"
                        if link == "explicit_path"
                        else (
                            f"PR #{artifact.number} '{artifact.title}' "
                            f"mentions {scope.name}"
                        )
                    )
                else:
                    source = (
                        f"Issue #{artifact.number} '{artifact.title}' "
                        f"references this file"
                        if link == "explicit_path"
                        else (
                            f"Issue #{artifact.number} '{artifact.title}' "
                            f"mentions {scope.name}"
                        )
                    )

                evidence = Evidence(
                    type="artifact",
                    source=source,
                    weight=max(0.0, min(1.0, weight)),
                    detail={
                        "artifact": f"{'PR' if artifact.kind == 'pr' else 'Issue'}"
                        f"#{artifact.number}",
                        "link": link,
                        "confidence": confidence,
                    },
                )

                results.setdefault(scope.id, []).append(evidence)

        return results
