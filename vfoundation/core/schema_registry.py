"""
Verb Schema Registry (vFoundation Core Phase 14C).

Loads the verb registry YAML, resolves JSON schemas from the filesystem,
and caches `jsonschema.Draft7Validator` instances for O(1) message validation.
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from jsonschema import RefResolver
from jsonschema.validators import Draft7Validator

logger = logging.getLogger("schema_registry")


class VerbSchemaRegistry:
    """
    Registry for verb schemas. Caches pre-compiled JSON Schema validators.
    """

    def __init__(self, project_root: str = ".") -> None:
        """
        Args:
            project_root: Base directory to resolve schema relative paths against.
        """
        self.project_root = Path(project_root)
        self._validators: Dict[Tuple[str, str], Draft7Validator] = {}
        self._unsupported_verbs: set[Tuple[str, str]] = set()
        self._dir_stores: Dict[Path, Dict[str, Any]] = {}

    @staticmethod
    def _directory_uri(schema_dir: Path) -> str:
        """Return a file URI suitable for resolving sibling JSON schemas."""
        return schema_dir.resolve().as_uri().rstrip("/") + "/"

    def _load_directory_store(self, schema_dir: Path) -> Dict[str, Any]:
        """Load and cache sibling schemas for local $ref resolution."""
        resolved_dir = schema_dir.resolve()
        cached = self._dir_stores.get(resolved_dir)
        if cached is not None:
            return cached

        store: Dict[str, Any] = {}
        for schema_file in sorted(resolved_dir.glob("*.json")):
            try:
                with open(schema_file, "r", encoding="utf-8") as handle:
                    sibling_schema = json.load(handle)
            except Exception as exc:
                logger.debug(
                    "Skipping sibling schema during resolver store load: %s (%s)",
                    schema_file,
                    exc,
                )
                continue

            schema_uri = schema_file.resolve().as_uri()
            store[schema_file.name] = sibling_schema
            store[schema_uri] = sibling_schema

        self._dir_stores[resolved_dir] = store
        return store

    def load_registry(self, yaml_path: str) -> None:
        """
        Load the verb registry from a YAML file.
        
        Args:
            yaml_path: Path to the verb_registry_v1.yaml file.
        """
        full_path = self.project_root / yaml_path
        if not full_path.exists():
            logger.error(f"Verb registry file not found: {full_path}")
            return

        try:
            with open(full_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            logger.exception(f"Failed to parse verb registry YAML {full_path}: {e}")
            return

        registry = data.get("registry", [])
        if not isinstance(registry, list):
            logger.error(f"Invalid verb registry format in {full_path}")
            return

        loaded_count = 0
        missing_count = 0

        for entry in registry:
            op = entry.get("op")
            verb = entry.get("verb")
            schema_rel_path = entry.get("schema")

            if not op or not verb:
                continue

            key = (op, verb)

            if schema_rel_path is None:
                self._unsupported_verbs.add(key)
                missing_count += 1
                continue

            schema_file = self.project_root / schema_rel_path
            if not schema_file.exists():
                logger.error(f"Schema file not found for {op}:{verb} -> {schema_file}")
                self._unsupported_verbs.add(key)
                missing_count += 1
                continue

            try:
                with open(schema_file, "r", encoding="utf-8") as f:
                    schema_dict = json.load(f)

                # Check for Draft7 validity natively if drafts are specified
                Draft7Validator.check_schema(schema_dict)
                schema_dir = schema_file.parent
                resolver = RefResolver(
                    self._directory_uri(schema_dir),
                    {},
                    store=self._load_directory_store(schema_dir),
                )
                self._validators[key] = Draft7Validator(
                    schema_dict,
                    resolver=resolver,
                )
                loaded_count += 1
            except Exception as e:
                logger.error(f"Failed to compile schema for {op}:{verb} from {schema_file}: {e}")
                self._unsupported_verbs.add(key)
                missing_count += 1

        logger.info(
            f"VerbSchemaRegistry loaded: {loaded_count} schemas compiled, "
            f"{missing_count} verbs without schemas (will warn on emit)."
        )

    def get_validator(self, op: str, verb: str) -> Optional[Draft7Validator]:
        """
        Get the pre-compiled JSON schema validator for a specific operation and verb.
        
        Args:
            op: Operation type (e.g., 'CMD', 'EVT', 'DEC').
            verb: Action name (e.g., 'OPEN', 'CLOSE').
            
        Returns:
            Draft7Validator instance if a schema is defined, else None.
        """
        return self._validators.get((op, verb))

    def is_schema_missing(self, op: str, verb: str) -> bool:
        """
        Check if a schema is explicitly known as missing/null in the registry.
        (Used for targeted DeprecationWarnings).
        """
        return (op, verb) in self._unsupported_verbs

    @property
    def total_validators(self) -> int:
        return len(self._validators)


_global_registry: Optional[VerbSchemaRegistry] = None


def init_global_registry(
    project_root: str = ".", yaml_path: str = "apps/reference/dictionaries/verb_registry_v1.yaml"
) -> VerbSchemaRegistry:
    """Initialize and load the global VerbSchemaRegistry singleton."""
    global _global_registry
    _global_registry = VerbSchemaRegistry(project_root)
    _global_registry.load_registry(yaml_path)
    return _global_registry


def get_global_registry() -> Optional[VerbSchemaRegistry]:
    """Get the initialized global VerbSchemaRegistry."""
    return _global_registry
