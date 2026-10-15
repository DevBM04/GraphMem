import networkx as nx

from graphmem.graph.store import GraphStore
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation


class NetworkXGraphStore(GraphStore):
    """
    NetworkX implementation of GraphMem's GraphStore.
    """

    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()

    def add_entity(self, entity: CodeEntity) -> None:
        self.graph.add_node(
            entity.id,
            entity=entity,
        )

    def add_relation(self, relation: Relation) -> None:
        if not self.graph.has_node(relation.source_id):
            raise ValueError(
                f"Source entity does not exist: {relation.source_id}"
            )

        if not self.graph.has_node(relation.target_id):
            raise ValueError(
                f"Target entity does not exist: {relation.target_id}"
            )

        self.graph.add_edge(
            relation.source_id,
            relation.target_id,
            relation_type=relation.type,
            metadata=relation.metadata,
        )

    def get_entity(
        self,
        entity_id: str,
    ) -> CodeEntity | None:

        if not self.graph.has_node(entity_id):
            return None

        return self.graph.nodes[entity_id]["entity"]

    def neighbors(
        self,
        entity_id: str,
    ) -> list[CodeEntity]:

        if not self.graph.has_node(entity_id):
            return []

        outgoing = set(self.graph.successors(entity_id))
        incoming = set(self.graph.predecessors(entity_id))

        neighbor_ids = outgoing | incoming

        return [
            self.graph.nodes[neighbor_id]["entity"]
            for neighbor_id in neighbor_ids
        ]
    
    def get_entities_by_type(
        self,
        entity_type: EntityType,
    ) -> list[CodeEntity]:

        return [
            data["entity"]
            for _, data in self.graph.nodes(data=True)
            if data["entity"].type == entity_type
        ]
    
    def entity_count(self) -> int:
        return self.graph.number_of_nodes()

    def relation_count(self) -> int:
        return self.graph.number_of_edges()

    def out_edges(self, entity_id: str):
        if not self.graph.has_node(entity_id):
            return []
        return [
            (
                self.graph.nodes[target]["entity"],
                data["relation_type"],
                data.get("metadata", {}),
            )
            for _, target, data in self.graph.out_edges(entity_id, data=True)
        ]

    def in_edges(self, entity_id: str):
        if not self.graph.has_node(entity_id):
            return []
        return [
            (
                self.graph.nodes[source]["entity"],
                data["relation_type"],
                data.get("metadata", {}),
            )
            for source, _, data in self.graph.in_edges(entity_id, data=True)
        ]