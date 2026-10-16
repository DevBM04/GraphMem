
from dataclasses import dataclass

from graphmem.graph.builder import GraphBuilder
from graphmem.graph.networkx_store import NetworkXGraphStore
from graphmem.ingestion.scanner import RepositoryScanner
from graphmem.models.repository import ParsedRepository
from graphmem.retrieval.localizer import Localizer


@dataclass
class RepositoryIndex:
    repository_path: str
    parsed: ParsedRepository
    graph: NetworkXGraphStore
    localizer: Localizer


class RepositoryIngestor:
    """Parse a repository, build its graph, and prepare bug localization."""

    def ingest(self, repository_path: str) -> RepositoryIndex:
        scanner = RepositoryScanner(repository_path)
        parsed = scanner.parse()

        builder = GraphBuilder()
        graph = builder.build(parsed)

        localizer = Localizer(graph)

        return RepositoryIndex(
            repository_path=str(scanner.repository_path),
            parsed=parsed,
            graph=graph,
            localizer=localizer,
        )
