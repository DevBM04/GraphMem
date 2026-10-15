"""Repository file discovery and directory hierarchy construction."""
from __future__ import annotations

from pathlib import Path, PurePosixPath
from graphmem.models.entities import CodeEntity, EntityType
from graphmem.models.relations import Relation, RelationType
from graphmem.models.repository import ParsedRepository
from graphmem.parsing.common.entity_builder import _FileRecord

class DiscoveryMixin:
        def _discover_files(self, repo_root: Path, repo_name: str, version: str):
            records: list[_FileRecord] = []
            for path in sorted(repo_root.rglob("*.py")):
                relative = path.relative_to(repo_root)
                if any(part in self.excluded_dirs for part in relative.parts):
                    continue
                relative_path = relative.as_posix()
                module_name = self._module_name_for(relative_path)
                entity_id = self.make_entity_id(
                    repo_name, relative_path, version
                )
                records.append(_FileRecord(
                    relative_path=relative_path,
                    absolute_path=path,
                    module_name=module_name,
                    entity_id=entity_id,
                ))
            return records

        @staticmethod
        def _module_name_for(relative_path: str) -> str:
            parts = relative_path.split("/")
            filename = parts[-1]
            if filename.endswith(".py"):
                filename = filename[:-3]
            parts[-1] = filename
            if parts[-1] == "__init__":
                parts = parts[:-1]
            return ".".join(p for p in parts if p)

        def _build_directory_hierarchy(
            self,
            *,
            parsed: ParsedRepository,
            repo_name: str,
            repo_entity_id: str,
            version: str,
            file_records: list[_FileRecord],
        ) -> None:
            directory_paths: set[str] = set()
            for record in file_records:
                parent = PurePosixPath(record.relative_path).parent.as_posix()
                while parent not in (".", ""):
                    directory_paths.add(parent)
                    parent = PurePosixPath(parent).parent.as_posix()

            directory_entity_ids = {"": repo_entity_id}

            for directory_path in sorted(
                directory_paths, key=lambda x: (x.count("/"), x)
            ):
                entity_id = self.make_entity_id(
                    repo_name, directory_path, version
                )
                directory_entity_ids[directory_path] = entity_id
                parsed.add_entity(CodeEntity(
                    id=entity_id,
                    type=EntityType.DIRECTORY,
                    name=PurePosixPath(directory_path).name,
                    path=directory_path,
                    metadata={"language": self.language, "version": version},
                ))

                parent = PurePosixPath(directory_path).parent.as_posix()
                if parent == ".":
                    parent = ""
                parsed.add_relation(Relation(
                    source_id=directory_entity_ids[parent],
                    target_id=entity_id,
                    type=RelationType.CONTAINS,
                ))

            for record in file_records:
                parent = PurePosixPath(record.relative_path).parent.as_posix()
                if parent == ".":
                    parent = ""
                parsed.add_relation(Relation(
                    source_id=directory_entity_ids.get(parent, repo_entity_id),
                    target_id=record.entity_id,
                    type=RelationType.CONTAINS,
                ))
