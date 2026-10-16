
from graphmem.ingestion.pipeline import RepositoryIngestor


REPOSITORY_PATH = "examples/sample_repo"

ISSUE = """
The normalize function removes leading and trailing whitespace and converts
text to lowercase, but it does not handle None values. Calling it with None
raises an exception.
"""

def main():
    print("Parsing repository and building graph...")

    repository = RepositoryIngestor().ingest(REPOSITORY_PATH)

    print(f"Found {len(repository.parsed.entities)} entities")
    print(f"Found {len(repository.parsed.relations)} relations")
    print(
        f"Graph built: {repository.graph.entity_count()} nodes, "
        f"{repository.graph.relation_count()} edges"
    )

    print("\nLocalizing issue...")

    result = repository.localizer.localize(ISSUE, top_k=10)

    print("\nTop candidates:\n")

    if not result.scopes:
        print("No candidates found.")
        return

    for rank, hit in enumerate(result.scopes, start=1):
        entity = hit.entity
        location = f"{entity.path or '<unknown>'}:{entity.start_line or '?'}"
        name = entity.qualified_name or entity.name

        print(
            f"{rank:2}. {hit.score:.4f} | "
            f"{entity.type.value} | {location} | {name}"
        )


if __name__ == "__main__":
    main()
