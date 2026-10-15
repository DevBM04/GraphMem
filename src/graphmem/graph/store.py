from abc import ABC, abstractmethod

from graphmem.models.entities import CodeEntity
from graphmem.models.relations import Relation, RelationType
from graphmem.models.entities import CodeEntity, EntityType

class GraphStore(ABC):
    """
    Abstract interface for GraphMem's repository graph.

    Other modules interact with the graph through this interface
    without needing to know which graph technology is used underneath.
    """

    @abstractmethod
    def add_entity(self, entity: CodeEntity) -> None:
        """Add a code entity to the graph."""
        raise NotImplementedError

    @abstractmethod
    def add_relation(self, relation: Relation) -> None:
        """Add a relationship between two entities."""
        raise NotImplementedError

    @abstractmethod
    def get_entity(self, entity_id: str) -> CodeEntity | None:
        """Return an entity by its ID."""
        raise NotImplementedError

    @abstractmethod
    def neighbors(self, entity_id: str) -> list[CodeEntity]:
        """Return entities directly connected to the given entity."""
        raise NotImplementedError

    @abstractmethod
    def get_entities_by_type(
        self,
        entity_type: EntityType,
    ) -> list[CodeEntity]:
        """Return all entities of a given type."""
        raise NotImplementedError


    @abstractmethod
    def entity_count(self) -> int:
        """Return the number of entities in the graph."""
        raise NotImplementedError


    @abstractmethod
    def relation_count(self) -> int:
        """Return the number of relationships in the graph."""
        raise NotImplementedError

    @abstractmethod
    def out_edges(
        self, entity_id: str
    ) -> list[tuple[CodeEntity, RelationType, dict]]:
        """Outgoing edges as (target entity, relation type, metadata)."""
        raise NotImplementedError

    @abstractmethod
    def in_edges(
        self, entity_id: str
    ) -> list[tuple[CodeEntity, RelationType, dict]]:
        """Incoming edges as (source entity, relation type, metadata)."""
        raise NotImplementedError