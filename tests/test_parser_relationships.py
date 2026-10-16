"""Focused integration tests for GraphMem Python relationship edges.

Run from the repository root with:
    pytest -q tests/test_parser_relationships.py
"""
from graphmem.models.entities import EntityType
from graphmem.models.relations import RelationType
from graphmem.parsing.python_parser import PythonParser


def test_inheritance_and_references_are_graph_edges(tmp_path):
    (tmp_path / "models.py").write_text(
        "class Animal:\n"
        "    def speak(self):\n"
        "        return 'sound'\n"
        "\n"
        "class Dog(Animal):\n"
        "    def speak(self):\n"
        "        sound = super().speak()\n"
        "        return sound\n",
        encoding="utf-8",
    )
    (tmp_path / "consumer.py").write_text(
        "from models import Animal, Dog\n"
        "\n"
        "def make_animal():\n"
        "    animal = Animal()\n"
        "    dog = Dog()\n"
        "    return animal\n",
        encoding="utf-8",
    )

    parsed = PythonParser().parse_repository(str(tmp_path))
    entities_by_id = {entity.id: entity for entity in parsed.entities}

    classes = {
        entity.name: entity
        for entity in parsed.entities
        if entity.type == EntityType.CLASS
    }
    assert {"Animal", "Dog"}.issubset(classes)

    inheritance_edges = [
        relation for relation in parsed.relations
        if relation.type == RelationType.INHERITS
    ]
    assert any(
        relation.source_id == classes["Dog"].id
        and relation.target_id == classes["Animal"].id
        for relation in inheritance_edges
    )

    reference_edges = [
        relation for relation in parsed.relations
        if relation.type == RelationType.REFERENCES
    ]
    assert reference_edges, "Expected resolved non-call symbol references"
    assert all(relation.source_id in entities_by_id for relation in reference_edges)
    assert all(relation.target_id in entities_by_id for relation in reference_edges)


def test_inheritance_does_not_guess_ambiguous_external_base(tmp_path):
    (tmp_path / "one.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    (tmp_path / "child.py").write_text("class Child(Base):\n    pass\n", encoding="utf-8")

    parsed = PythonParser().parse_repository(str(tmp_path))
    child = next(
        entity for entity in parsed.entities
        if entity.type == EntityType.CLASS and entity.name == "Child"
    )
    inheritance_edges = [
        relation for relation in parsed.relations
        if relation.type == RelationType.INHERITS
        and relation.source_id == child.id
    ]
    assert inheritance_edges == []
