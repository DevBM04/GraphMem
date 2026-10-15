from __future__ import annotations

from dataclasses import dataclass, field, replace

from graphmem.models.relations import RelationType


def _default_weights() -> dict[str, float]:
    return {
        "lexical": 0.5,
        "graph": 0.25,
        "dataflow": 0.25,
        "history": 0.0,
        "artifact": 0.0,
        "semantic": 0.0,
    }


def _default_edge_weights() -> dict[RelationType, float]:
    return {
        RelationType.CALLS: 1.0,
        RelationType.INHERITS: 0.8,
        RelationType.REFERENCES: 0.6,
        RelationType.IMPORTS: 0.4,
    }


@dataclass
class RankConfig:
    name: str = "full"
    weights: dict[str, float] = field(default_factory=_default_weights)
    edge_weights: dict[RelationType, float] = field(default_factory=_default_edge_weights)

    lexical_pool: int = 100       # BM25 hits kept
    seed_limit: int = 8           # lexical seeds used for graph expansion
    max_depth: int = 2            # graph hops
    hop_decay: float = 0.6        # multiplier per hop
    max_neighbors: int = 30       # per-node cap (avoids hub explosion)
    pool_size: int = 30           # scopes that get statement-level analysis
    dataflow_seeds: int = 3       # statements used as slice seeds per scope
    slice_depth: int = 3
    statements_per_scope: int = 5
    statement_scope_mix: float = 0.3  # share of scope score in statement score

    def with_weights(self, name: str | None = None, **weights: float) -> "RankConfig":
        merged = dict(self.weights)
        merged.update(weights)
        return replace(self, name=name or self.name, weights=merged)

    def without(self, *signals: str) -> "RankConfig":
        return self.with_weights(
            name=f"{self.name}-no-{'-'.join(signals)}",
            **{s: 0.0 for s in signals},
        )


def ablation_configs() -> dict[str, RankConfig]:
    """PRD §8 baselines. History/artifact only matter once providers exist."""
    off = {"graph": 0.0, "dataflow": 0.0, "history": 0.0, "artifact": 0.0, "semantic": 0.0}
    base = RankConfig()
    return {
        "bm25": base.with_weights("bm25", **off),
        "graph": base.with_weights("graph", **{**off, "graph": 0.25}),
        "graph+dataflow": base.with_weights("graph+dataflow", **{**off, "graph": 0.25, "dataflow": 0.25}),
        "graph+history": base.with_weights("graph+history", **{**off, "graph": 0.25, "history": 0.15}),
        "graph+artifact": base.with_weights("graph+artifact", **{**off, "graph": 0.25, "artifact": 0.10}),
        "full": base.with_weights("full", history=0.15, artifact=0.10),
    }