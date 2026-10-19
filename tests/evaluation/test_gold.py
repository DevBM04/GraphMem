from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.repository import ParsedRepository
from graphmem.evaluation.gold import GoldLocation, parse_patch, resolve_functions


MODIFY_METHOD = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,5 +1,5 @@
 class App:
     def run(self):
-        return 1
+        return 2
"""


PURE_ADDITION = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def run():
     start()
+    validate()
     finish()
"""


DELETION = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,4 +1,3 @@
 def run():
     start()
-    obsolete()
     finish()
"""


NEW_FILE = """\
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+def hello():
+    return "hello"
"""


TWO_FILES = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,3 +1,3 @@
 def first():
-    return 1
+    return 2
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,3 +1,3 @@
 def second():
-    return 3
+    return 4
"""


CLASS_BODY = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,5 +1,5 @@
 class Example:
     value = 1
-    other = 2
+    other = 3

     def run(self):
"""


def make_entity(
    entity_id,
    entity_type,
    name,
    path,
    start,
    end,
    qualified_name=None,
):
    return CodeEntity(
        id=entity_id,
        type=entity_type,
        name=name,
        path=path,
        qualified_name=qualified_name,
        start_line=start,
        end_line=end,
    )


def make_repository(*entities):
    return ParsedRepository(
        repository_path="test",
        entities=list(entities),
    )


def test_modify_line_inside_method():
    gold = parse_patch(MODIFY_METHOD)

    assert gold.files == {"app.py"}
    assert gold.lines == {"app.py": {3}}
    assert gold.new_files == set()

    parsed = make_repository(
        make_entity(
            "class:App",
            EntityType.CLASS,
            "App",
            "app.py",
            1,
            5,
            "App",
        ),
        make_entity(
            "method:App.run",
            EntityType.METHOD,
            "run",
            "app.py",
            2,
            3,
            "App.run",
        ),
    )

    resolve_functions(gold, parsed)

    assert gold.functions == {"app.py::App.run"}


def test_pure_addition_uses_previous_context_line():
    gold = parse_patch(PURE_ADDITION)

    assert gold.files == {"app.py"}
    assert gold.lines == {"app.py": {2}}

    parsed = make_repository(
        make_entity(
            "function:run",
            EntityType.FUNCTION,
            "run",
            "app.py",
            1,
            4,
            "run",
        ),
    )

    resolve_functions(gold, parsed)

    assert gold.functions == {"app.py::run"}


def test_deletion_uses_old_line_number():
    gold = parse_patch(DELETION)

    assert gold.files == {"app.py"}
    assert gold.lines == {"app.py": {3}}


def test_new_file_is_not_localized_as_existing_file():
    gold = parse_patch(NEW_FILE)

    assert gold.new_files == {"new.py"}
    assert gold.files == set()
    assert gold.lines == {}


def test_patch_touching_two_files():
    gold = parse_patch(TWO_FILES)

    assert gold.files == {"a.py", "b.py"}
    assert gold.lines == {
        "a.py": {2},
        "b.py": {2},
    }


def test_class_body_outside_method_resolves_to_class():
    gold = parse_patch(CLASS_BODY)

    assert gold.lines == {"app.py": {3}}

    parsed = make_repository(
        make_entity(
            "class:Example",
            EntityType.CLASS,
            "Example",
            "app.py",
            1,
            7,
            "Example",
        ),
        make_entity(
            "method:Example.run",
            EntityType.METHOD,
            "run",
            "app.py",
            6,
            7,
            "Example.run",
        ),
    )

    resolve_functions(gold, parsed)

    assert gold.functions == {"app.py::Example"}


def test_line_outside_all_entities_resolves_to_module():
    gold = GoldLocation(
        files={"app.py"},
        lines={"app.py": {10}},
    )

    parsed = make_repository()

    resolve_functions(gold, parsed)

    assert gold.functions == {"app.py::<module>"}


def test_nested_functions_choose_innermost_entity():
    gold = GoldLocation(
        files={"app.py"},
        lines={"app.py": {5}},
    )

    parsed = make_repository(
        make_entity(
            "outer",
            EntityType.FUNCTION,
            "outer",
            "app.py",
            1,
            10,
            "outer",
        ),
        make_entity(
            "inner",
            EntityType.FUNCTION,
            "inner",
            "app.py",
            4,
            6,
            "outer.inner",
        ),
    )

    resolve_functions(gold, parsed)

    assert gold.functions == {"app.py::outer.inner"}



def test_pure_addition_at_beginning_uses_context_below():
    patch = """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -1,2 +1,3 @@
+import os
 def run():
     return 1
"""

    gold = parse_patch(patch)

    assert gold.files == {"app.py"}
    assert gold.lines == {"app.py": {1}}
    assert gold.new_files == set()
