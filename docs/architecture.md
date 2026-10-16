# System Architecture

## Repository-Aware Multi-Agent Framework for AI-Assisted Software Engineering

------------------------------------------------------------------------

## 1. Architecture Goals

The architecture is designed around eight principles:

1.  repository-wide rather than file-only understanding;
2.  fine-grained localization;
3.  multiple complementary evidence sources;
4.  queryable retrieval instead of context dumping;
5.  model-independent repository intelligence;
6.  incremental updates;
7.  language-extensible parsing;
8.  independently measurable components.

The logical architecture follows four layers:

``` text
┌──────────────────────────────────────────────────────────────┐
│                    Task / Application Layer                  │
│        Web UI · API · Localization · Repair · Validation    │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                 Retrieval & Reasoning Layer                   │
│ Query Planner · Candidate Generator · Ranker · Context      │
│ Builder · Agent Tools · LLM Interface                       │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                Repository Intelligence Layer                  │
│ Code Graph · Data Flow · Artifacts · Git History · Indexes  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│                       Ingestion Layer                        │
│ Source Parser · Git Parser · GitHub Adapter · Index Builder│
└──────────────────────────────────────────────────────────────┘
```

------------------------------------------------------------------------

# 2. Recommended Technology Stack

## Backend

**Python 3.12+**

Reason:

-   strongest ecosystem for source-code analysis;
-   Tree-sitter bindings;
-   GitPython/PyGithub;
-   NetworkX;
-   FastAPI;
-   ML/LLM ecosystem;
-   rapid research prototyping.

## API

**FastAPI**

Responsibilities:

-   repository ingestion endpoints;
-   issue localization endpoint;
-   graph exploration endpoints;
-   evaluation endpoints;
-   frontend API.

## Parsing

**Tree-sitter**

Use a parser adapter:

``` text
LanguageParser
├── PythonParser
├── JavaParser       (later)
└── OtherParser      (future)
```

Tree-sitter provides a common AST-based parsing interface while allowing
language-specific extraction logic.

## Graph

### MVP

**NetworkX**

Use for:

-   graph construction;
-   traversal;
-   prototyping relation algorithms;
-   debugging and visualization.

### Scale-up option

**Neo4j**

Use only if repository size/query complexity makes an in-memory graph
insufficient.

The application must interact through a `GraphStore` interface so
changing storage does not affect retrieval logic.

``` text
GraphStore
├── NetworkXGraphStore
└── Neo4jGraphStore
```

## Metadata storage

**SQLite for MVP**

Store:

-   repository metadata;
-   source hashes;
-   ingestion state;
-   artifact metadata;
-   commit metadata;
-   evaluation results.

Upgrade to PostgreSQL only if required.

## Lexical retrieval

**BM25**

Recommended implementation:

-   `rank_bm25` initially;
-   or another lightweight inverted-index implementation if scale
    requires it.

Indexes:

``` text
Entity Name
Qualified Entity ID
File Path
Source Content
Issue Text
PR Text
Commit Message
```

## Semantic retrieval

Optional for the first MVP.

Interface:

``` text
SemanticIndex
├── NoOpSemanticIndex
└── EmbeddingSemanticIndex
```

This allows semantic retrieval to be added without changing the
architecture.

## Git

**GitPython** or direct Git CLI wrapper.

Required operations:

-   checkout repository snapshot;
-   read commit history;
-   obtain diffs;
-   identify changed files;
-   map changes to source entities.

## GitHub

**PyGithub** or GitHub REST API adapter.

The adapter should fetch:

-   issues;
-   pull requests;
-   comments if required;
-   labels;
-   linked commits;
-   changed files.

Cache all fetched artifacts locally.

## LLM

Use a provider-independent interface:

``` text
LLMProvider
├── OpenAICompatibleProvider
├── LocalProvider
└── MockProvider
```

For the first prototype, use an OpenAI-compatible endpoint or a locally
hosted open-source coding model.

The exact model should remain configurable rather than becoming an
architectural dependency.

## Agent / tool layer

Use structured Python functions exposed as tools:

``` text
search_entities()
traverse_graph()
get_code_span()
get_entity_info()
get_dataflow_slice()
search_artifacts()
search_history()
build_context_bundle()
rank_suspect_regions()
```

The agent decides which tools to call, but the tools themselves remain
deterministic and bounded.

## Frontend

**React + TypeScript**

For the research prototype:

-   issue input;
-   ranked candidate list;
-   source-code preview;
-   evidence panel;
-   graph visualization;
-   latency/token statistics.

------------------------------------------------------------------------

# 3. Repository Data Model

The system uses a multi-granularity property graph.

## 3.1 Node types

### Repository

``` text
Repository {
    id
    name
    url
    default_branch
}
```

### Directory / Package

``` text
Directory {
    id
    path
    parent_id
}
```

Packages are represented as logical repository units/directories when
the language provides no stronger package abstraction.

### File / Module

``` text
File {
    id
    path
    language
    content_hash
    start_line
    end_line
    commit
}
```

### Class

``` text
Class {
    id
    qualified_name
    file_id
    start_line
    end_line
}
```

### Function / Method

``` text
Function {
    id
    qualified_name
    file_id
    parent_class_id?
    start_line
    end_line
}
```

### Statement

A statement is the fine-grained localization unit.

``` text
Statement {
    id
    file_id
    function_id
    start_line
    end_line
    source_span
}
```

A physical line does not automatically need to be a separate semantic
node. Statements carry exact line ranges, while a line index maps
physical lines to statements.

This prevents comments, blank lines, and syntactically irrelevant lines
from exploding the graph size.

------------------------------------------------------------------------

# 4. Artifact Data Model

## Issue

``` text
Issue {
    id
    repository_id
    title
    body
    state
    created_at
    closed_at?
}
```

## Pull Request

``` text
PullRequest {
    id
    repository_id
    title
    body
    state
    created_at
    merged_at?
}
```

## Commit

``` text
Commit {
    sha
    repository_id
    message
    author
    timestamp
}
```

## Memory Summary

``` text
MemorySummary {
    id
    entity_id
    summary
    source_commit?
    generated_at
}
```

------------------------------------------------------------------------

# 5. Edge Model

## Structural relationships

  Edge           Meaning
  -------------- -----------------------------
  `CONTAINS`     parent contains child
  `IMPORTS`      file/module imports another
  `CALLS`        function invokes another
  `INHERITS`     class derives from another
  `REFERENCES`   code references an entity

## Fine-grained relationships

  Edge                 Meaning
  -------------------- --------------------------------------
  `DEFINES`            statement defines a variable/symbol
  `DATAFLOW_DEF_USE`   definition can influence a later use
  `DATAFLOW_USE_DEF`   reverse edge for backward slicing

## Artifact relationships

  Edge          Meaning
  ------------- -------------------------------------
  `MENTIONS`    issue/PR mentions entity
  `CHANGES`     PR/commit changes entity
  `FIXES`       PR/commit associated with issue/fix
  `LINKED_TO`   explicit artifact relationship

## Historical relationships

  Edge           Meaning
  -------------- ---------------------------------
  `SUMMARIZES`   memory summary describes entity
  `PRECEDES`     historical version relationship

------------------------------------------------------------------------

# 6. Stable Entity IDs

Line numbers are not stable across commits.

Therefore, IDs should not be based only on line number.

Recommended:

``` text
repo://<repo>/<path>::<qualified_name>@<commit>
```

Example:

``` text
repo://django/django/db/models/query.py::QuerySet.filter@<sha>
```

For statements:

``` text
repo://django/django/db/models/query.py::QuerySet.filter::stmt-7@<sha>
```

Store:

-   repository;
-   file path;
-   qualified name;
-   source span;
-   commit;
-   content hash / AST fingerprint.

This allows future versions to map old entities to new entities.

------------------------------------------------------------------------

# 7. Ingestion Pipeline

``` text
Repository Snapshot
        |
        v
Repository Scanner
        |
        +--> Files / Directories
        |
        v
Language Parser
        |
        +--> Classes
        +--> Functions
        +--> Statements
        +--> Imports
        +--> Calls
        +--> Inheritance
        +--> References
        |
        v
Data-flow Analyzer
        |
        +--> Definitions
        +--> Uses
        +--> Def-Use edges
        |
        +--------------------------+
                                   |
Git History -----------------------+
                                   |
GitHub Issues / PRs ---------------+
                                   |
                                   v
                         Entity Linker
                                   |
                                   v
                          Graph + Stores
                                   |
                                   v
                             Index Builder
```

------------------------------------------------------------------------

# 8. Repository Graph Construction

## Pass 1 --- Structure

Traverse directories and source files.

Create:

``` text
Repository
→ Directory
→ File
→ Class
→ Function/Method
→ Statement
```

## Pass 2 --- Symbol resolution

Resolve:

-   imports;
-   function calls;
-   class inheritance;
-   references.

Only create high-confidence edges.

Incorrect edges can mislead graph traversal more severely than missing
edges.

## Pass 3 --- Data flow

For each function/method:

1.  identify variable definitions;
2.  identify variable uses;
3.  map uses to relevant preceding definitions;
4.  create `DATAFLOW_DEF_USE`;
5.  create reverse `DATAFLOW_USE_DEF`.

The initial implementation should be intra-procedural.

------------------------------------------------------------------------

# 9. Artifact Ingestion

GitHub data is handled independently from source parsing.

``` text
GitHub API
   |
   +--> Issues
   +--> Pull Requests
   +--> Comments
   +--> Linked commits
   +--> Changed files
   |
   v
Artifact Normalizer
   |
   v
Artifact Store
   |
   v
Entity Linker
```

### Linking strategy

Priority:

1.  explicit file/path references;
2.  explicit issue/PR references;
3.  exact entity names;
4.  qualified names;
5.  BM25/entity similarity;
6.  optional semantic similarity.

Every link should record its source and confidence.

------------------------------------------------------------------------

# 10. Repository Memory

## Episodic memory

Represents events:

``` text
Commit
→ changed files
→ changed functions
→ changed statements
→ linked issue/PR
```

The retrieval system can ask:

> "Which previous changes affected this region?"

## Semantic memory

Short summaries of important repository regions.

Example:

``` text
Entity:
django.contrib.auth.management.create_permissions

Summary:
Creates missing ContentType permissions during post-migrate
processing and interacts with the app registry.
```

Only important/high-churn entities need summaries in the first version.

------------------------------------------------------------------------

# 11. Retrieval Architecture

## Step 1 --- Issue understanding

Input:

``` text
Issue description
```

Extract:

``` text
symbols
paths
behavior terms
error messages
variables
historical clues
```

## Step 2 --- Parallel retrieval

``` text
                 Issue
                   |
       +-----------+-----------+
       |           |           |
       v           v           v
   Entity/BM25   Graph      Artifacts
       |        Traversal      |
       |           |           |
       +-----------+-----------+
                   |
               History
                   |
               Data Flow
                   |
                   v
          Candidate Generator
```

## Step 3 --- Candidate ranking

Initial ranking model:

``` text
candidate_score =
    w1 * lexical_score
  + w2 * semantic_score
  + w3 * graph_score
  + w4 * artifact_score
  + w5 * history_score
  + w6 * dataflow_score
```

Weights must be configurable.

The LLM should not be the only ranking mechanism.

------------------------------------------------------------------------

# 12. Agent Tool API

The LLM should interact with bounded tools.

### `search_entities`

Input:

``` json
{
  "query": "separability_matrix",
  "limit": 10
}
```

Output:

``` json
[
  {
    "entity_id": "...",
    "type": "function",
    "file": "...",
    "line": 250
  }
]
```

### `traverse_graph`

Parameters:

-   starting entity;
-   direction;
-   hop count;
-   allowed edge types;
-   allowed node types.

### `get_code_span`

Input:

``` text
file + start_line + end_line
```

### `get_dataflow_slice`

Input:

``` text
file
line
variable
direction = backward | forward | both
```

### `search_artifacts`

Search:

-   issues;
-   PRs;
-   titles;
-   bodies.

### `search_history`

Search:

-   commit messages;
-   changed files;
-   affected entities.

### `build_context_bundle`

Combines evidence under a token budget.

------------------------------------------------------------------------

# 13. Context Construction

The graph should never be dumped into the LLM.

The context builder should return:

``` text
Issue
+
Top candidate
+
Relevant source span
+
Graph relationships
+
Data-flow slice
+
Related issue/PR
+
Relevant historical change
```

Example:

``` text
Candidate: src/parser.py:142

Why:
- Issue keyword "invalid token" matches Parser.parse
- Parser.parse calls Tokenizer.next
- Data-flow reaches variable token at line 142
- Previous commit changed the same statement
- Related PR mentions malformed token handling
```

This is the project's central architectural principle:

> **Retrieve evidence, not the entire context.**

------------------------------------------------------------------------

# 14. LLM Layer

Use an abstraction:

``` python
class LLMProvider:
    def generate(self, messages, tools=None):
        ...
```

This allows:

``` text
Qwen
DeepSeek
Llama
OpenAI-compatible endpoint
Local model
Mock model
```

without changing repository intelligence.

The first implementation should avoid model fine-tuning.

------------------------------------------------------------------------

# 15. Optional Repair Pipeline

``` text
Localization
     |
     v
Context Builder
     |
     v
LLM Patch Generator
     |
     v
Unified Diff
     |
     v
Sandbox
     |
     +--> Apply Patch
     |
     +--> Run Tests
     |
     v
Validation Result
```

Repair is downstream of localization and should not block the core
research contribution.

------------------------------------------------------------------------

# 16. Incremental Updates

When a commit arrives:

``` text
Commit
  |
  v
Changed files
  |
  +--> Reparse changed files
  +--> Recompute affected relationships
  +--> Update graph nodes
  +--> Update indexes
  +--> Update artifact links
  +--> Update memory
```

Do not rebuild the entire repository unless required.

------------------------------------------------------------------------

# 17. Repository Versioning

Every graph entity should be associated with a repository
snapshot/commit.

For benchmark tasks:

``` text
Repository
     |
     +--> Base Commit
     |
     +--> Graph built from base state
     |
     +--> Historical data restricted to information available at base
```

This prevents future commits or golden patches from leaking into
localization.

------------------------------------------------------------------------

# 18. Evaluation Architecture

``` text
Benchmark Instance
      |
      +--> Repository Base Commit
      |
      +--> Issue
      |
      v
Localization System
      |
      v
Ranked Candidates
      |
      +--> File Recall
      +--> Function Recall
      +--> Line Recall
      +--> MRR
      |
      v
Optional Repair
      |
      +--> Patch success
      +--> Test success
```

------------------------------------------------------------------------

# 19. Repository Store Abstraction

Do not let application code directly depend on NetworkX.

``` python
class GraphStore:
    def add_node(...)
    def add_edge(...)
    def get_node(...)
    def neighbors(...)
    def traverse(...)
    def search(...)
```

Implementation:

``` text
GraphStore
     |
     +-- NetworkXGraphStore
     |
     +-- Neo4jGraphStore (future)
```

This is important because graph storage is an implementation choice, not
the research contribution.

------------------------------------------------------------------------

# 20. Suggested Repository Structure

``` text
repository-intelligence/
├── apps/
│   ├── api/
│   └── web/
│
├── ingestion/
│   ├── repository_scanner.py
│   ├── git_ingester.py
│   └── github_ingester.py
│
├── parsing/
│   ├── base.py
│   ├── python_parser.py
│   └── language_registry.py
│
├── graph/
│   ├── schema.py
│   ├── store.py
│   ├── networkx_store.py
│   └── builder.py
│
├── analysis/
│   ├── symbol_resolution.py
│   └── dataflow.py
│
├── artifacts/
│   ├── linker.py
│   └── models.py
│
├── memory/
│   ├── episodic.py
│   └── semantic.py
│
├── retrieval/
│   ├── entity_search.py
│   ├── artifact_search.py
│   ├── history_search.py
│   ├── candidate_generator.py
│   └── ranker.py
│
├── agent/
│   ├── tools.py
│   ├── planner.py
│   └── context_builder.py
│
├── llm/
│   ├── base.py
│   └── providers.py
│
├── evaluation/
│   ├── datasets.py
│   ├── metrics.py
│   └── runner.py
│
└── tests/
```

------------------------------------------------------------------------

# 21. Key Interfaces

The system should be built around stable interfaces:

``` text
RepositoryParser
GraphStore
ArtifactStore
HistoryStore
EntityIndex
SemanticIndex
Retriever
Ranker
ContextBuilder
LLMProvider
Evaluator
```

This allows four team members to work in parallel without constantly
changing each other's implementation.

------------------------------------------------------------------------

# 22. MVP Architecture

For the mid-review, use:

``` text
Python
├── Tree-sitter
├── NetworkX
├── SQLite
├── BM25
├── FastAPI
└── Configurable LLM provider
```

Do **not** introduce Neo4j, embeddings, multi-language parsing,
autonomous repair, and distributed infrastructure simultaneously.

The architecture supports those features later, but the first
implementation should prove the core pipeline.
