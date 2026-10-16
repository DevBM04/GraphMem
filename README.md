# GraphMem

GraphMem is a repository-aware bug-localization prototype. It parses a source
repository, builds a code graph, and ranks likely fault locations for a natural
language bug report.

## Requirements

- Python 3.10 or newer
- `pip` and `venv`

## Quickstart

Run these commands from the repository root.

```bash
# Create and activate an isolated environment
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# On Windows PowerShell: .venv\\Scripts\\Activate.ps1

# Install GraphMem and its development/test dependency
python -m pip install --upgrade pip
python -m pip install -e .

# Run the test suite
python -m pytest

# Localize a sample issue and print JSON
python scripts/localize.py examples/sample_repo \\
  "normalize strips value wrongly" --json
```

The localization command scans the sample repository, builds its graph, and
prints a JSON object containing ranked candidate files/scopes/statements and
supporting evidence. Omit `--json` for a compact human-readable report.

### Issue text from a file

```bash
python scripts/localize.py examples/sample_repo @issue.txt --json
```

### Useful development commands

```bash
python scripts/visualize_graph.py examples/sample_repo
python -m graphmem.cli --help
```

If the CLI command differs from the current implementation, use
`python -m pytest` and `scripts/localize.py` as the verified entry points.

## Project layout

```text
src/graphmem/       Python package
tests/              automated tests
scripts/localize.py localization command-line entry point
examples/sample_repo/ small repository used for manual testing
docs/               architecture and project documentation
```

## Dependencies

Runtime dependencies are declared in `pyproject.toml`. Pytest is declared in `pyproject.toml` so the standard install includes the test runner.