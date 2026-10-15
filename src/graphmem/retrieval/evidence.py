from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from graphmem.models.entities import CodeEntity


@dataclass
class Evidence:
    type: str        # lexical | graph | dataflow | history | artifact | semantic
    source: str      # human-readable provenance
    weight: float    # raw signal strength in [0, 1]
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = {"type": self.type, "source": self.source, "weight": round(self.weight, 4)}
        if self.detail:
            out["detail"] = self.detail
        return out


class EvidenceProvider(Protocol):
    """Plug-in signal (history, artifacts, semantic ...).

    `signal` must match a key in RankConfig.weights. `score` receives the
    candidate scopes and returns {entity_id: [Evidence, ...]} with each
    Evidence.weight in [0, 1].
    """

    signal: str

    def score(
        self, scopes: list[CodeEntity], issue: str
    ) -> dict[str, list[Evidence]]: ...