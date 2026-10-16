"""Tree-sitter constants shared by the Python language adapter."""

DEFAULT_EXCLUDED_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", ".tox",
    ".mypy_cache", ".pytest_cache", "build", "dist", "node_modules",
    ".idea", ".vscode",
    "tests", "docs", "examples", "benchmarks",
}

STATEMENT_TYPES = {
    "assert_statement", "break_statement", "continue_statement",
    "delete_statement", "exec_statement", "expression_statement",
    "for_statement", "global_statement", "if_statement",
    "import_from_statement", "import_statement", "nonlocal_statement",
    "pass_statement", "raise_statement", "return_statement",
    "try_statement", "while_statement", "with_statement", "match_statement",
}

DEFINITION_TYPES = {
    "class_definition", "function_definition", "async_function_definition",
}
