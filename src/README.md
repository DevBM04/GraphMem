# GraphMem Python parser refactor

This package keeps the existing import path working:

```python
from graphmem.parsing.python_parser import PythonParser
```

The implementation is split into `graphmem/parsing/python/` mixins and shared helpers in `graphmem/parsing/common/`.

## Relationship resolution changes

- `INHERITS`: emitted from subclass to resolved superclass. Supports same-file names, imported classes/aliases, module aliases, qualified names, and unique class-name fallback. Ambiguous or external bases are ignored rather than guessed.
- `REFERENCES`: emitted from a statement to a resolved class/function/method used as a non-call symbol reference. Calls remain represented by `CALLS`; unresolved/external names are ignored.
- `IMPORTS`, `CALLS`, and `DATAFLOW_DEF_USE` remain their own edge types.
- Statement `uses`/`defines`, source text, line numbers, base spellings, and parser diagnostics remain useful descriptive metadata. They are not replaced wholesale by edges.

The parser does **not** yet create explicit variable-symbol entities or `DEFINES`/`USES` edges. Those require a separate design decision about variable identity and scope. `MENTIONS`, `CHANGES`, and `FIXES` are also future/history/documentation relationships rather than parser-generated edges at this stage.

## Tests

Run from the GraphMem repository root, in the environment where GraphMem and Tree-sitter dependencies are installed:

```bash
pytest -q tests/test_parser_relationships.py
```

The tests cover inheritance direction, imported symbol references, and conservative handling of ambiguous base names.

## Validation note

The included Python modules have been syntax-compiled. Full integration tests require your GraphMem model package and installed `tree-sitter` / `tree-sitter-python` dependencies.
