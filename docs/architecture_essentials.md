# Architecture Essentials

## Critical Architectural Decisions

This document records the decisions that should remain stable even if
implementation details change.

------------------------------------------------------------------------

## ADR-01 --- Primary Research Target

### Decision

**Fault localization is the primary task. Patch generation and
validation are downstream capabilities.**

### Why

Localization is independently measurable and is the clearest way to
demonstrate whether repository intelligence helps.

The system must be able to answer:

``` text
Given:
    repository + issue

Return:
    ranked file/function/statement/line locations
    + evidence
```

Repair can consume this output later.

### Consequence

The team does not need a complete autonomous coding agent for the
project to be successful.

------------------------------------------------------------------------

# ADR-02 --- Repository Is Not a Flat Document Collection

### Decision

Represent the repository as a structured, multi-granularity graph.

``` text
Repository
  → Directory / Package
    → File / Module
      → Class
        → Function / Method
          → Statement
```

Cross-links:

``` text
IMPORTS
CALLS
INHERITS
REFERENCES
DATAFLOW
```

### Why

Repository-level bugs often require multi-hop reasoning across files and
modules.

A directory relationship alone is insufficient.

### Consequence

The graph is a navigation and evidence substrate, not simply a
visualization.

------------------------------------------------------------------------

# ADR-03 --- Packages/Directories Are First-Class Structural Nodes

### Decision

Directories/packages are represented in the hierarchy.

### Why

They provide:

-   repository organization;
-   scope;
-   module grouping;
-   efficient hierarchical traversal;
-   useful context for agents.

However, a package/directory is **not the same thing as a third-party
library**.

The graph represents the repository's own package/module structure.
External libraries are primarily represented through imports and
dependency metadata unless their source is also ingested.

### Consequence

The model supports:

``` text
repository
  └── package/directory
       └── module/file
```

while still allowing cross-package/module `IMPORTS` and `CALLS`
relationships.

------------------------------------------------------------------------

# ADR-04 --- Statement Nodes, Not Every Physical Line

### Decision

Use statement/source-span nodes for fine-grained localization.

Do **not** create a semantic graph node for every physical line by
default.

### Why

A physical line may be:

-   blank;
-   a comment;
-   part of a multi-line statement;
-   syntactically irrelevant.

Statement nodes retain exact start/end line numbers, giving line-level
output without graph explosion.

### Consequence

The final result can still be:

``` text
file.py:143
```

while the graph node represents:

``` text
statement: lines 143–145
```

------------------------------------------------------------------------

# ADR-05 --- Intra-Procedural Data Flow First

### Decision

Implement definition-use/data-flow analysis within functions before
attempting inter-procedural data-flow.

### Why

It provides a direct route from function-level localization to
suspicious statements.

Example:

``` text
input
  ↓
assignment
  ↓
transformation
  ↓
condition
  ↓
return
```

### Consequence

The first slicing API should support:

``` text
backward
forward
bidirectional
```

within a function/method.

Inter-procedural reasoning is handled initially through `CALLS`
relationships.

------------------------------------------------------------------------

# ADR-06 --- Conservative Relationship Resolution

### Decision

Only create high-confidence semantic edges.

### Why

A wrong `CALLS` or `IMPORTS` edge can actively mislead graph traversal.

Missing edges are often less damaging than incorrect edges.

### Consequence

For dynamic language features:

``` text
uncertain → no edge
```

rather than:

``` text
uncertain → guessed edge
```

The parser should track resolution confidence internally.

------------------------------------------------------------------------

# ADR-07 --- Unified Logical Graph, Modular Physical Storage

### Decision

Conceptually treat repository knowledge as one connected model, but do
not require every object to physically live in one database.

Possible implementation:

``` text
Graph Store
Artifact Store
History Store
Indexes
```

linked through stable entity IDs.

### Why

A single database can become a bottleneck and makes experimentation
harder.

The research contribution is the unified representation/retrieval
strategy, not the choice of database.

------------------------------------------------------------------------

# ADR-08 --- NetworkX First, Neo4j Later

### Decision

Use **NetworkX for the MVP** and keep graph access behind a `GraphStore`
interface.

### Why

NetworkX:

-   is easy to debug;
-   is fast enough for selected benchmark repositories;
-   requires little infrastructure;
-   allows rapid experimentation.

Neo4j can be added later if graph scale/query complexity requires it.

### Consequence

Do not let application code directly call NetworkX.

Use:

``` python
GraphStore
```

everywhere.

------------------------------------------------------------------------

# ADR-09 --- BM25 Before Embeddings

### Decision

Implement lexical/entity retrieval first. Add embeddings only after the
baseline works.

### Why

BM25 is:

-   cheap;
-   explainable;
-   easy to reproduce;
-   strong for symbols, paths, error messages, and identifiers.

It also gives a clean baseline for research.

### Consequence

The first retrieval stack is:

``` text
Exact match
     ↓
BM25
     ↓
Graph expansion
     ↓
Ranking
```

Semantic retrieval becomes an optional evidence source.

------------------------------------------------------------------------

# ADR-10 --- LLM Is a Reasoning Layer, Not the Database

### Decision

The LLM should query repository intelligence through tools.

### Do not do this

``` text
Entire repository → giant prompt → LLM
```

### Do this

``` text
Issue
  ↓
Query planning
  ↓
Search / traversal / slicing / history
  ↓
Rank evidence
  ↓
Compact context
  ↓
LLM reasoning
```

### Why

This improves:

-   context efficiency;
-   explainability;
-   reproducibility;
-   model independence;
-   evaluation of retrieval separately from generation.

------------------------------------------------------------------------

# ADR-11 --- Model Independence

### Decision

Do not make the repository intelligence layer dependent on one LLM.

Use:

``` text
LLMProvider
```

as an abstraction.

### Why

The project needs to evaluate whether the repository representation
helps, not whether one specific model is better.

### Consequence

Possible backends:

``` text
local open-source model
OpenAI-compatible API
mock model for testing
```

------------------------------------------------------------------------

# ADR-12 --- Artifact Layer Is Separate but Connected

### Decision

Issues, PRs, and commits are first-class repository artifacts.

### Why

The current code does not always contain enough information to explain
why a region exists or how a bug evolved.

Artifacts provide:

``` text
Issue
  ↓
PR
  ↓
Commit
  ↓
Changed code
```

and therefore additional evidence for localization.

### Consequence

Artifact links should carry provenance:

``` text
source = explicit_link
source = entity_match
source = lexical_similarity
```

with confidence.

------------------------------------------------------------------------

# ADR-13 --- Historical Evidence Must Respect Repository Time

### Decision

Benchmark localization must never use information that was unavailable
at the task's base commit.

### Why

Otherwise the system can accidentally see:

-   the golden patch;
-   future commits;
-   future issue comments;
-   future PR information.

That creates benchmark leakage.

### Consequence

For each benchmark task:

``` text
base_commit
     ↓
construct current graph
     ↓
only expose history ≤ base_commit
```

------------------------------------------------------------------------

# ADR-14 --- Stable IDs Must Survive Source Changes

### Decision

Entity IDs must include repository identity, logical identity, and
version information.

### Example

``` text
repo://repo/path/file.py::Class.method@<commit>
```

Statements additionally require a source fingerprint or local statement
identity.

### Why

Line numbers move after edits.

### Consequence

Incremental updates can map:

``` text
old entity → changed entity → new entity
```

rather than assuming line 120 is always the same code.

------------------------------------------------------------------------

# ADR-15 --- Incremental Updates

### Decision

Repository changes should update affected entities rather than always
rebuilding the entire repository.

### Trigger

``` text
new commit
```

### Process

``` text
changed files
    ↓
reparse
    ↓
update affected nodes
    ↓
recompute affected edges
    ↓
update indexes
    ↓
update memory/artifacts
```

### Consequence

The architecture supports long-lived repository intelligence.

------------------------------------------------------------------------

# ADR-16 --- Evidence Has Provenance

### Decision

Every localization signal should retain where it came from.

Example:

``` json
{
  "candidate": "src/parser.py:143",
  "evidence": [
    {
      "type": "CALLS",
      "source": "src/api.py:88"
    },
    {
      "type": "DATAFLOW",
      "source": "parse():token"
    },
    {
      "type": "HISTORY",
      "source": "commit abc123"
    }
  ]
}
```

### Why

The system should be explainable and research-friendly.

This also enables ablations.

------------------------------------------------------------------------

# ADR-17 --- Candidate Ranking Must Be Configurable

### Decision

Do not hard-code one opaque ranking formula.

Use configurable weights:

``` text
lexical
semantic
graph
dataflow
artifact
history
LLM
```

### Why

The main research experiment is to determine which evidence sources
matter.

### Consequence

The same benchmark can run:

``` text
graph only
graph + dataflow
graph + artifacts
graph + history
full
```

------------------------------------------------------------------------

# ADR-18 --- Evaluation Is a First-Class Component

### Decision

Evaluation code lives inside the architecture, not as an afterthought.

### Required metrics

``` text
File Recall@1/@5
Function Recall@1/@5
Line Recall@1/@5
MRR
candidate coverage
```

Optional:

``` text
repair success
test pass rate
latency
token usage
```

### Why

The project is research-oriented.

A working demo without controlled evaluation is not enough.

------------------------------------------------------------------------

# ADR-19 --- Language Extensibility Through Adapters

### Decision

The common graph/retrieval layer must not know language-specific AST
details.

``` text
LanguageParser
├── PythonParser
├── JavaParser
└── ...
```

Each parser emits the common intermediate representation:

``` text
File
Class
Function
Statement
Import
Call
Inheritance
Definition
Use
```

### Why

This directly supports the project's cross-language research goal.

### Consequence

Implement Python first, then a second language only after the first
pipeline is stable.

------------------------------------------------------------------------

# ADR-20 --- Security Boundary Around Execution

### Decision

Generated patches and repository commands must execute in isolated
environments.

### Why

Repository content can be untrusted and generated code can be unsafe.

### Consequence

The repair layer should use a sandbox/container.

The localization-only MVP does not need arbitrary command execution.

------------------------------------------------------------------------

# ADR-21 --- Four-Person Team Architecture

The architecture must permit parallel development.

``` text
Member 1
Parser + Graph
       |
       v
Shared Graph Schema
       |
       +-------------------+
       |                   |
       v                   v
Member 2              Member 3
Data Flow + History   Artifacts + Retrieval
       |                   |
       +---------+---------+
                 |
                 v
             Member 4
        LLM + Agent + Evaluation
```

### Critical integration contract

Everyone agrees on the graph schema before implementing independently.

The following must be frozen early:

-   node types;
-   edge types;
-   node ID format;
-   source location format;
-   serialization format;
-   tool API.

------------------------------------------------------------------------

# ADR-22 --- Mid-Review Scope

For the mid-review, the team should demonstrate a **vertical slice**,
not the full final system.

## Required

``` text
Repository
   ↓
Parser
   ↓
Graph
   ↓
BM25/entity index
   ↓
Issue
   ↓
Graph retrieval
   ↓
Ranked localization
```

## Strong stretch goal

``` text
Issue
   ↓
Graph retrieval
   ↓
Data-flow slice
   ↓
Line-level localization
   ↓
Evidence explanation
```

## Do not block the review on

-   Neo4j;
-   semantic embeddings;
-   multi-language support;
-   complete GitHub ingestion;
-   full autonomous repair;
-   model fine-tuning;
-   production deployment.

------------------------------------------------------------------------

# ADR-23 --- Definition of "Done"

A component is done only when it has:

1.  implementation;
2.  unit tests;
3.  sample input/output;
4.  documented interface;
5.  integration test where applicable;
6.  measurable performance.

A graph parser that merely creates nodes is not considered complete.

The output must be consumable by retrieval and localization.

------------------------------------------------------------------------

# ADR-24 --- Core Research Hypothesis

The architecture is designed to test:

> **Does combining structural, data-flow, repository-artifact, and
> historical evidence improve fine-grained repository-level fault
> localization compared with individual evidence sources?**

This is the central hypothesis.

Everything else should support measuring it.
