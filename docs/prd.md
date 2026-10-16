# Product Requirements Document (PRD)

## Repository-Aware Multi-Agent Framework for AI-Assisted Software Engineering

**Project type:** Final Year Project --- Phase II\
**Team size:** 4\
**Primary capability:** Repository-level fault localization\
**Secondary capability:** Patch generation and validation\
**Target users:** Software developers, open-source contributors,
repository maintainers, and researchers evaluating AI-assisted software
engineering systems.

------------------------------------------------------------------------

## 1. Product Overview

### 1.1 Problem

LLMs are strong at understanding isolated functions and files, but
repository-level software engineering tasks require information
distributed across the entire codebase.

A bug report may describe a symptom without naming the faulty function.
The relevant evidence may be distributed across:

-   directories/packages and files;
-   classes, functions, and statements;
-   imports, calls, inheritance, and references;
-   variable definition-use relationships;
-   previous issues and pull requests;
-   historical commits and code changes.

A flat keyword search or embedding-based retrieval can therefore return
code that is semantically similar but structurally unrelated.

### 1.2 Product Goal

Build a **repository intelligence layer** that converts a software
repository into a queryable representation and allows an LLM to retrieve
and reason over multiple forms of repository evidence.

Given:

> **Repository snapshot + issue description**

the system should produce:

> **Ranked file → function/class → statement/line candidates +
> supporting evidence**

The longer-term pipeline may use these localized regions to generate and
validate a patch.

### 1.3 Research Positioning

The project is not simply "build a graph."

It investigates whether combining complementary evidence sources
improves fine-grained repository-level fault localization:

1.  structural code relationships;
2.  statement-level data-flow;
3.  issues and pull requests;
4.  commit/history memory;
5.  LLM reasoning over retrieved evidence.

This follows the project's current research direction and avoids
claiming that any individual component is novel.

------------------------------------------------------------------------

## 2. Target Users

### Primary users

#### Software developers

Need to understand where an issue originates in an unfamiliar
repository.

**Need:** fast, explainable localization.

#### Open-source contributors

Often receive an issue without prior knowledge of the repository
architecture.

**Need:** repository navigation and dependency-aware evidence.

#### Repository maintainers

Need to understand historical context and previously fixed problems.

**Need:** issue/PR/commit context linked to current code.

### Secondary users

#### Software engineering researchers

Need a reproducible framework for testing repository-aware retrieval
strategies.

**Need:** modular components, controlled experiments, metrics, and
ablations.

------------------------------------------------------------------------

## 3. Product Scope

### 3.1 MVP --- Required for the first working prototype

The MVP must support:

1.  repository ingestion from a local repository;
2.  parsing of source code;
3.  repository/package/directory/file hierarchy;
4.  class and function extraction;
5.  import and call relationships where reliably resolvable;
6.  statement/source-span nodes for fine-grained localization;
7.  basic intra-procedural definition-use/data-flow relationships;
8.  issue input;
9.  lexical/entity search;
10. graph traversal;
11. candidate generation;
12. candidate ranking;
13. evidence/context construction;
14. LLM-based localization;
15. file/function/line-level evaluation.

### 3.2 Phase II features

After the MVP is stable:

-   Git commit ingestion;
-   issue and pull-request ingestion;
-   artifact-to-code links;
-   historical/episodic memory;
-   semantic summaries of important code regions;
-   incremental repository updates;
-   patch generation;
-   test-based patch validation;
-   second programming language;
-   web interface.

### 3.3 Explicit non-goals

The first version will **not** attempt to:

-   train a foundation model from scratch;
-   reproduce CGM's model-architecture modifications;
-   build a general autonomous coding agent;
-   support every programming language;
-   create a perfect whole-repository semantic understanding model;
-   automatically accept generated patches without validation;
-   rebuild the entire graph after every repository change.

------------------------------------------------------------------------

## 4. Core User Workflow

``` text
Repository
    |
    v
Repository Ingestion
    |
    +--> Source Parser --------+
    +--> Git History ----------+
    +--> GitHub Artifacts -----+--> Repository Intelligence Layer
    |                           |
    +--> Index Builder --------+
                                |
                                v
Issue Description ----------> Query Planner
                                |
                                v
                       Candidate Generation
                                |
             +------------------+------------------+
             |                  |                  |
             v                  v                  v
        Code Graph         Data Flow          History/Artifacts
             |                  |                  |
             +------------------+------------------+
                                |
                                v
                         Candidate Ranker
                                |
                                v
                         Context Builder
                                |
                                v
                             LLM
                                |
                                v
                  Ranked Fault Locations
                  File / Function / Line
                                |
                                v
                    Optional Patch Generation
                                |
                                v
                         Test Validation
```

------------------------------------------------------------------------

## 5. Functional Requirements

### FR-01 --- Repository ingestion

The system shall accept a repository snapshot and identify:

-   repository root;
-   directories/packages;
-   source files;
-   supported programming languages;
-   repository version/commit.

### FR-02 --- Source parsing

The parser shall extract, where supported:

-   files/modules;
-   classes;
-   functions/methods;
-   statements/source spans;
-   definitions;
-   references;
-   imports;
-   function calls;
-   inheritance;
-   data-flow relationships.

Language-specific parsing must be isolated behind a common interface.

### FR-03 --- Repository graph

The system shall construct a directed, typed graph representing
repository structure and dependencies.

The graph should preserve:

``` text
Repository
  └── Directory / Package
       └── File / Module
            ├── Class
            │    └── Method
            └── Function
                 └── Statement
```

and cross-links such as:

``` text
IMPORTS
CALLS
INHERITS
REFERENCES
DEFINES
DATAFLOW_DEF_USE
```

### FR-04 --- Repository artifacts

Where GitHub metadata is available, the system shall ingest:

-   issues;
-   pull requests;
-   issue/PR titles;
-   descriptions;
-   comments where useful;
-   changed files;
-   links between issues and PRs;
-   associated commits.

Artifacts should be linked to code entities using explicit references
first and lexical/entity matching as fallback.

### FR-05 --- Repository history

The system shall ingest commit history containing:

-   commit SHA;
-   message;
-   timestamp;
-   changed files;
-   patch/diff summary;
-   affected code entities where mapping is possible.

The system should support historical search for previously changed or
similar regions.

### FR-06 --- Query planning

Given an issue, the system shall extract search signals such as:

-   explicit symbols;
-   file/path names;
-   class/function names;
-   behavior terms;
-   error messages;
-   variables/data-flow concepts;
-   historical/regression hints.

### FR-07 --- Candidate generation

Candidate locations shall be generated using multiple signals:

-   exact entity matching;
-   BM25/lexical retrieval;
-   optional semantic retrieval;
-   graph neighbors;
-   call/import relationships;
-   issue/PR-linked entities;
-   historical commits;
-   data-flow slices.

### FR-08 --- Candidate ranking

Candidates shall receive a combined score based on evidence.

Conceptually:

``` text
Score(candidate) =
    lexical relevance
  + semantic relevance
  + graph relevance
  + data-flow evidence
  + artifact evidence
  + historical evidence
  + LLM reasoning score
```

The exact weighting must be configurable so that ablation experiments
can remove individual evidence sources.

### FR-09 --- Fine-grained localization

The system shall return candidates at:

1.  file level;
2.  class/function level;
3.  statement/line level.

Each result should contain:

-   repository;
-   file path;
-   enclosing scope;
-   start/end line;
-   confidence/rank;
-   evidence.

### FR-10 --- Evidence explanation

For every top candidate, the system should show why it was selected.

Example:

``` text
Candidate:
  astropy/modeling/separable.py:250

Evidence:
  - issue mentions separability_matrix
  - function is directly matched
  - caller relationship to Model
  - related historical commit
  - data-flow slice reaches line 250
```

### FR-11 --- LLM interaction

The LLM shall consume a **compact evidence bundle**, not the complete
repository graph.

The retrieval layer must remain model-independent.

### FR-12 --- Optional repair

The system may pass localized context to an LLM for patch generation.

Generated patches must be validated using repository tests before being
considered successful.

------------------------------------------------------------------------

## 6. Non-Functional Requirements

### Explainability

Localization results must expose the evidence/path that produced them.

### Reproducibility

The same repository snapshot, issue, configuration, and model should
produce reproducible evaluation runs as far as the selected LLM permits.

### Performance

The system should measure:

-   graph construction time;
-   index construction time;
-   query latency;
-   candidate-ranking latency;
-   LLM latency;
-   context token count.

### Scalability

The architecture must avoid loading an entire large repository into the
LLM context.

### Reliability

Uncertain graph relationships should not be represented as
high-confidence facts. Conservative edge creation is preferred over
large numbers of incorrect edges.

### Security

Repository commands and generated patches must run in isolated
environments.

### Maintainability

Language-specific parsing must be separated from the common graph,
retrieval, ranking, and agent layers.

------------------------------------------------------------------------

## 7. Product Output

### Primary output

``` json
{
  "issue": "...",
  "candidates": [
    {
      "file": "src/example.py",
      "scope": "Example.process",
      "start_line": 42,
      "end_line": 44,
      "score": 0.91,
      "evidence": [
        "entity_match",
        "calls",
        "dataflow",
        "historical_commit"
      ]
    }
  ]
}
```

### UI output

The prototype should display:

-   issue description;
-   repository;
-   ranked candidates;
-   file/function/line;
-   confidence;
-   evidence paths;
-   relevant issue/PR/commit references;
-   optional code preview.

------------------------------------------------------------------------

## 8. Success Metrics

### Localization

Measure:

-   File Recall@1 / @5;
-   Function Recall@1 / @5;
-   Line Recall@1 / @5;
-   Mean Reciprocal Rank;
-   Top-k candidate coverage.

### End-to-end repair

If repair is implemented:

-   patch success rate;
-   test pass rate;
-   Pass@k.

### System performance

Measure:

-   graph construction time;
-   incremental update time;
-   retrieval latency;
-   LLM latency;
-   token usage;
-   storage size.

### Research evaluation

Compare:

``` text
Baseline 1: lexical/BM25
Baseline 2: semantic retrieval
Baseline 3: structural graph
Baseline 4: graph + data-flow
Baseline 5: graph + artifacts
Baseline 6: graph + history
Full:      graph + data-flow + artifacts + history
```

The central research question is whether the combined system improves
localization over simpler alternatives.

------------------------------------------------------------------------

## 9. Evaluation Dataset

Initial evaluation:

-   SWE-bench Verified / SWE-bench Lite-compatible repository issues;
-   selected public repositories;
-   repository snapshots fixed at the benchmark base commit.

For the first implementation, prioritize a manageable Python subset.

Cross-language support should only be claimed after implementing and
evaluating a second language.

------------------------------------------------------------------------

## 10. MVP Acceptance Criteria

The MVP is considered complete when:

-   [ ] A repository can be ingested from a local path.
-   [ ] Source files are parsed.
-   [ ] Repository/package/directory/file/class/function hierarchy is
    represented.
-   [ ] Calls/imports are represented where reliably resolvable.
-   [ ] Statement/source-span locations are available.
-   [ ] At least basic data-flow slicing works inside functions.
-   [ ] BM25/entity search works.
-   [ ] Graph traversal works.
-   [ ] An issue can be submitted.
-   [ ] The system returns ranked file/function/line candidates.
-   [ ] Each candidate has evidence.
-   [ ] At least one benchmark/evaluation pipeline works.
-   [ ] A baseline comparison can be reproduced.

------------------------------------------------------------------------

## 11. Team Plan

### Member 1 --- Repository Parser & Graph

Own:

-   Tree-sitter/language parsing;
-   repository hierarchy;
-   graph schema;
-   calls/imports/inheritance;
-   graph construction;
-   graph persistence.

### Member 2 --- Data Flow & Repository History

Own:

-   statement extraction;
-   definition-use analysis;
-   slicing;
-   Git commit ingestion;
-   historical memory;
-   incremental update logic.

### Member 3 --- GitHub Artifacts & Retrieval

Own:

-   GitHub issue/PR ingestion;
-   artifact-code linking;
-   entity/BM25 indexes;
-   candidate generation;
-   ranking;
-   evidence tracking.

### Member 4 --- LLM, Agent & Evaluation

Own:

-   query planner;
-   tool API;
-   context builder;
-   LLM integration;
-   localization output;
-   benchmark runner;
-   evaluation metrics;
-   web prototype integration.

### Shared responsibilities

All members contribute to:

-   architecture decisions;
-   integration;
-   experiments;
-   case studies;
-   documentation;
-   final paper.

------------------------------------------------------------------------

## 12. One-Week Mid-Review Target

The team should **not** try to finish the complete system before the
mid-review.

The strongest demonstration is a vertical slice:

``` text
GitHub/Python repository
        ↓
Parser
        ↓
Repository graph
        ↓
BM25/entity search
        ↓
Graph traversal
        ↓
Issue
        ↓
Top candidate files/functions
        ↓
Evidence visualization
```

Minimum live demo:

> Give the system a real issue → retrieve a relevant entity → traverse
> its dependencies → return a ranked localization with evidence.

Stretch demo:

> Add statement-level data-flow and show that the result moves from a
> function to a suspicious line.

------------------------------------------------------------------------

## 13. Risks

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  Graph becomes too complex           Start with a small reliable schema

  Incorrect call resolution           Add only high-confidence edges

  Multi-language support consumes     Build language adapter interface;
  time                                implement one language first

  LLM dominates the system            Keep retrieval/ranking
                                      independently measurable

  Too much context reaches LLM        Use ranking + token-budgeted
                                      context builder

  GitHub API limits                   Cache downloaded artifacts

  Benchmark leakage                   Build history only from information
                                      available at the task base commit

  Full repair becomes too large       Treat localization as primary;
                                      repair as downstream

  Team members work in isolation      Integrate interfaces early and
                                      maintain a shared schema
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 14. Product Principle

> **The graph is not the product. Repository intelligence is the
> product.**

The graph is the structured substrate that allows the system to connect
issue symptoms to code, dependencies, historical changes, and
fine-grained data-flow evidence.

The final product should therefore demonstrate **better localization
with explainable evidence**, not merely graph construction.
