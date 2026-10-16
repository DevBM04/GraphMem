
# C03 Performance Evaluation

## Environment and methodology

GraphMem was benchmarked using the `graphmem_profile.py` script against
three local repositories: Flask, Requests, and pytest.

The reported ingestion time includes the work performed by the profiling
script's ingestion entry point. Measurements were collected from repeated
runs in the same development environment.

Cache entries are stored under `.cache/graphmem/` as pickle files.
The cache uses repository path, Git commit SHA, parser configuration,
and working-tree metadata to decide whether a parsed representation
can be reused.

## Baseline measurements

Measurements collected before adding the additional directory exclusions:

| Repository | Cold run | Warm run |
|---|---:|---:|
| Flask | 0.72 s | 0.18 s |
| Requests | 0.50 s | 0.12 s |
| pytest | 5.66 s | 1.69 s |

Entity and relation counts in these runs:

| Repository | Entities | Relations |
|---|---:|---:|
| Flask | 7,907 | 13,037 |
| Requests | 5,066 | 8,964 |
| pytest | 45,073 | 88,545 |

## Measurements after adding directory exclusions

The parser defaults were extended to exclude `tests`, `docs`,
`examples`, and `benchmarks`, in addition to the existing environment
and build directories.

| Repository | First observed run | Second observed run |
|---|---:|---:|
| Flask | 0.28 s | 0.07 s |
| Requests | 0.23 s | 0.06 s |
| pytest | 1.69 s | 1.84 s |

Entity and relation counts:

| Repository | Entities | Relations |
|---|---:|---:|
| Flask | 2,810 | 4,752 |
| Requests | 2,323 | 3,952 |
| pytest | 45,027 | 88,494 |

The Flask and Requests counts dropped substantially after the exclusions
were added. This is an expected trade-off: excluding directories reduces
the amount of code represented in the graph.

The pytest timings were not consistently faster on the second observed
run, so these measurements alone do not establish a reliable warm-cache
speedup for pytest after the exclusions.

## Cache design

- Cache files are stored locally under `.cache/graphmem/`.
- Cache writes use a temporary file and atomic replacement.
- Cache entries include a cache version and parser configuration.
- Working-tree metadata is checked before reusing a cached entry.
- A different commit SHA produces a different cache key.

The working-tree fingerprint uses Git status and file metadata for changed
files rather than hashing every source-file byte. It is therefore a
lightweight invalidation mechanism, not a cryptographic guarantee against
every possible same-size, same-timestamp edit.

## Limitations and next steps

1. Directory exclusions reduce graph coverage and must be configurable.
2. Cold and warm timings should be measured separately with explicit cache
   hit/miss reporting.
3. Cache invalidation and corrupted-cache recovery should be covered by
   automated regression tests.
4. The full test suite and large-file recursion checks must pass before C03
   is considered complete.
