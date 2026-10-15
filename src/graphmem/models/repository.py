from dataclasses import dataclass, field

from graphmem.models.entities import CodeEntity
from graphmem.models.relations import Relation


@dataclass
class ParsedRepository:
    repository_path: str

    entities: list[CodeEntity] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)

    # Private indexes, kept in sync by add_entity / add_relation.
    _by_id: dict[str, CodeEntity] = field(default_factory=dict, init=False, repr=False)
    _by_path: dict[str, list[CodeEntity]] = field(default_factory=dict, init=False, repr=False)
    _relation_keys: set = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        for entity in self.entities:
            self._index_entity(entity)
        for relation in self.relations:
            self._relation_keys.add(self._key(relation))

    @staticmethod
    def _key(relation: Relation) -> tuple:
        return (relation.source_id, relation.target_id, relation.type)

    def _index_entity(self, entity: CodeEntity) -> None:
        self._by_id[entity.id] = entity
        if entity.path:
            self._by_path.setdefault(entity.path, []).append(entity)

    def add_entity(self, entity: CodeEntity) -> None:
        self.entities.append(entity)
        self._index_entity(entity)

    def add_relation(self, relation: Relation) -> None:
        self.relations.append(relation)
        self._relation_keys.add(self._key(relation))

    def has_relation(self, relation: Relation) -> bool:
        return self._key(relation) in self._relation_keys

    def get_entity(self, entity_id: str) -> CodeEntity | None:
        return self._by_id.get(entity_id)

    def entities_in_file(self, path: str) -> list[CodeEntity]:
        return self._by_path.get(path, [])