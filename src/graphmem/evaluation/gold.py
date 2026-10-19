"""Gold locations extracted from unified diffs."""

from dataclasses import dataclass, field
import re

from graphmem.models.entities import EntityType


@dataclass
class GoldLocation:
    files: set[str] = field(default_factory=set)
    lines: dict[str, set[int]] = field(default_factory=dict)
    functions: set[str] = field(default_factory=set)
    new_files: set[str] = field(default_factory=set)


_HUNK_HEADER = re.compile(
    r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@"
)


def _strip_prefix(path: str) -> str:
    """Remove Git's a/ or b/ prefix while preserving the remaining path."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path


def _parse_hunk(
    hunk_lines: list[str],
    old_start: int,
    result: set[int],
) -> None:
    """Extract changed old-side lines from one unified-diff hunk."""
    old_line = old_start
    operations: list[tuple[str, int | None]] = []
    has_removals = False

    for line in hunk_lines:
        if not line:
            continue

        marker = line[0]

        if marker == " ":
            operations.append(("context", old_line))
            old_line += 1
        elif marker == "-":
            operations.append(("remove", old_line))
            old_line += 1
            has_removals = True
        elif marker == "+":
            operations.append(("add", None))
        elif marker == "\\":
            # For example: \ No newline at end of file
            continue

    for index, (operation, line_number) in enumerate(operations):
        if operation == "remove":
            # Removed lines include the old side of modifications.
            result.add(line_number)

        elif operation == "add" and not has_removals:
            # Pure insertion: prefer the closest old context line above.
            above = next(
                (
                    number
                    for kind, number in reversed(operations[:index])
                    if kind == "context"
                ),
                None,
            )

            if above is None:
                # At the beginning of a file/hunk, use the first context
                # line below the insertion instead.
                below = next(
                    (
                        number
                        for kind, number in operations[index + 1 :]
                        if kind == "context"
                    ),
                    None,
                )
                above = below

            if above is not None:
                result.add(above)


def parse_patch(patch_text: str) -> GoldLocation:
    """Extract changed files and old-side line numbers from a unified diff."""
    gold = GoldLocation()
    lines = patch_text.splitlines()
    index = 0

    while index < len(lines):
        # A file header consists of an old path followed by a new path.
        if not (
            lines[index].startswith("--- ")
            and index + 1 < len(lines)
            and lines[index + 1].startswith("+++ ")
        ):
            index += 1
            continue

        old_path = lines[index][4:].split("\t", 1)[0].strip()
        new_path = lines[index + 1][4:].split("\t", 1)[0].strip()
        index += 2

        # Ignore timestamps and other metadata by using only the path token.
        old_path = old_path.split(" ", 1)[0]
        new_path = new_path.split(" ", 1)[0]

        if old_path == "/dev/null":
            # A new file has no old-side source to localize.
            gold.new_files.add(_strip_prefix(new_path))
            is_new_file = True
            current_path = None
        else:
            current_path = _strip_prefix(old_path)
            gold.files.add(current_path)
            gold.lines.setdefault(current_path, set())
            is_new_file = False

        while index < len(lines):
            header = _HUNK_HEADER.match(lines[index])

            if header:
                old_start = int(header.group(1))
                old_count = int(header.group(2) or "1")
                new_count = int(header.group(4) or "1")
                index += 1

                hunk_lines: list[str] = []
                consumed_old = 0
                consumed_new = 0

                while index < len(lines):
                    line = lines[index]

                    if _HUNK_HEADER.match(line):
                        break

                    # Stop at the next file header.
                    if (
                        line.startswith("--- ")
                        and index + 1 < len(lines)
                        and lines[index + 1].startswith("+++ ")
                    ):
                        break

                    if line.startswith(("diff --git ", "diff --cc ")):
                        break

                    if line.startswith("\\"):
                        hunk_lines.append(line)
                    elif line.startswith(" "):
                        hunk_lines.append(line)
                        consumed_old += 1
                        consumed_new += 1
                    elif line.startswith("-"):
                        hunk_lines.append(line)
                        consumed_old += 1
                    elif line.startswith("+"):
                        hunk_lines.append(line)
                        consumed_new += 1
                    else:
                        break

                    index += 1

                    if consumed_old >= old_count and consumed_new >= new_count:
                        break

                if not is_new_file and current_path is not None:
                    _parse_hunk(
                        hunk_lines,
                        old_start,
                        gold.lines[current_path],
                    )

                continue

            if (
                lines[index].startswith("--- ")
                and index + 1 < len(lines)
                and lines[index + 1].startswith("+++ ")
            ):
                break

            if lines[index].startswith(("diff --git ", "diff --cc ")):
                break

            index += 1

    # Files with no localized lines still remain in gold.files.
    return gold


def resolve_functions(gold: GoldLocation, parsed) -> GoldLocation:
    """Map gold line locations to their innermost enclosing code entities."""
    for path, changed_lines in gold.lines.items():
        entities = parsed.entities_in_file(path)

        for line in changed_lines:
            covering = [
                entity
                for entity in entities
                if entity.start_line is not None
                and entity.end_line is not None
                and entity.start_line <= line <= entity.end_line
            ]

            callable_entities = [
                entity
                for entity in covering
                if entity.type in (EntityType.FUNCTION, EntityType.METHOD)
            ]

            if callable_entities:
                # The smallest span is the most deeply nested callable.
                entity = min(
                    callable_entities,
                    key=lambda item: item.end_line - item.start_line,
                )
                qualified_name = entity.qualified_name or entity.name

            else:
                classes = [
                    entity
                    for entity in covering
                    if entity.type == EntityType.CLASS
                ]

                if classes:
                    entity = min(
                        classes,
                        key=lambda item: item.end_line - item.start_line,
                    )
                    qualified_name = entity.qualified_name or entity.name
                else:
                    qualified_name = "<module>"

            gold.functions.add(f"{path}::{qualified_name}")

    return gold
