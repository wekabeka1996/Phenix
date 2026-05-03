"""Dynamic DeepSeek model registry with live, cached, and static sources."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from ..config import Settings
from ..deepseek_client import DeepSeekClient
from .models import DeepSeekModelInfo, ModelCatalog, ModelProfile


class ModelRegistry:
    """Resolve model inventories without silently replacing user selections."""

    def __init__(
        self,
        settings: Settings,
        *,
        root_dir: str | Path = ".",
        client_factory: Optional[Callable[[], DeepSeekClient]] = None,
    ) -> None:
        self.settings = settings
        self.root_dir = Path(root_dir)
        self.cache_path = self.root_dir / settings.models.registry_cache_path
        self._client_factory = client_factory or (
            lambda: DeepSeekClient(settings.deepseek))
        self._catalog: Optional[ModelCatalog] = None

    def _static_catalog(self, warning: Optional[str] = None) -> ModelCatalog:
        return ModelCatalog(
            source="static_fallback",
            warning=warning,
            models=[
                DeepSeekModelInfo(model_id=model_id, source="static_fallback")
                for model_id in self.settings.models.static_fallback_models
            ],
        )

    def _normalize_catalog(self, raw_models: list[dict]) -> ModelCatalog:
        models: list[DeepSeekModelInfo] = []
        for item in raw_models:
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            models.append(
                DeepSeekModelInfo(
                    model_id=model_id,
                    source="live",
                    name=str(item.get("name") or model_id),
                    context_window=item.get("context_window"),
                    max_output_tokens=item.get("max_output_tokens"),
                    metadata={
                        key: value
                        for key, value in item.items()
                        if key not in {"id", "name", "context_window", "max_output_tokens"}
                    },
                )
            )
        return ModelCatalog(source="live", models=models)

    def save_cache(self, catalog: Optional[ModelCatalog] = None) -> ModelCatalog:
        catalog = catalog or self.list_models()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_path.write_text(
            json.dumps(catalog.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return catalog

    def load_cache(self) -> Optional[ModelCatalog]:
        if not self.cache_path.exists():
            return None
        data = json.loads(self.cache_path.read_text(encoding="utf-8"))
        data["source"] = "cached"
        for item in data.get("models", []):
            item["source"] = "cached"
        return ModelCatalog(**data)

    def refresh_from_api(self) -> ModelCatalog:
        try:
            catalog = self._normalize_catalog(
                self._client_factory().list_models())
        except Exception as exc:  # noqa: BLE001
            cached = self.load_cache()
            if cached is not None and cached.models:
                cached.warning = f"Using cached model registry because live refresh failed: {exc}"
                self._catalog = cached
                return cached
            fallback = self._static_catalog(
                warning=f"Using static fallback model registry because live refresh failed: {exc}"
            )
            self._catalog = fallback
            return fallback

        self._catalog = catalog
        self.save_cache(catalog)
        return catalog

    def list_models(self) -> ModelCatalog:
        if self._catalog is not None:
            return self._catalog
        if self.settings.models.refresh_on_startup:
            return self.refresh_from_api()
        cached = self.load_cache()
        if cached is not None and cached.models:
            self._catalog = cached
            return cached
        fallback = self._static_catalog(
            warning="Live model registry has not been refreshed yet; using static fallback list."
        )
        self._catalog = fallback
        return fallback

    def get_model(self, model_id: str) -> DeepSeekModelInfo:
        selected = str(model_id or "").strip()
        for model in self.list_models().models:
            if model.model_id == selected:
                return model
        raise ValueError(f"Unknown model_id '{selected}'.")

    def validate_model_id(self, model_id: str) -> bool:
        self.get_model(model_id)
        return True

    def resolve_model_id(self, model_id: str, *, advanced_mode: bool = False) -> DeepSeekModelInfo:
        try:
            return self.get_model(model_id)
        except ValueError:
            selected = str(model_id or "").strip()
            if not advanced_mode or not selected:
                raise
            return DeepSeekModelInfo(
                model_id=selected,
                source=self.list_models().source,
                metadata={"advanced_mode": True, "validated": False},
            )

    def get_default_profiles(self) -> list[ModelProfile]:
        context_cfg = self.settings.context
        subagents_cfg = self.settings.subagents
        return [
            ModelProfile(
                profile_id="pro-thinking-max",
                name="Pro Thinking Max",
                model_id="deepseek-v4-pro",
                thinking_type="enabled",
                reasoning_effort="max",
                temperature=0.2,
                top_p=1.0,
                max_tokens=8192,
                response_format="text",
                stream=False,
                tool_mode="auto",
                max_iterations=20,
                command_timeout_sec=120,
                max_command_output_chars=20000,
                context_budget_chars=context_cfg.max_context_chars,
                memory_atom_budget=self.settings.memory.retrieval_top_k,
                recent_turns_budget=12,
                tool_output_budget_chars=context_cfg.tool_output_budget_chars,
            ),
            ModelProfile(
                profile_id="pro-thinking-high",
                name="Pro Thinking High",
                model_id="deepseek-v4-pro",
                thinking_type="enabled",
                reasoning_effort="high",
                temperature=0.2,
                top_p=1.0,
                max_tokens=8192,
                response_format="text",
                stream=False,
                tool_mode="auto",
                max_iterations=20,
                command_timeout_sec=120,
                max_command_output_chars=20000,
                context_budget_chars=context_cfg.max_context_chars,
                memory_atom_budget=self.settings.memory.retrieval_top_k,
                recent_turns_budget=12,
                tool_output_budget_chars=context_cfg.tool_output_budget_chars,
            ),
            ModelProfile(
                profile_id="flash-scout",
                name="Flash Scout",
                model_id="deepseek-v4-flash",
                thinking_type="disabled",
                reasoning_effort="high",
                temperature=0.1,
                top_p=1.0,
                max_tokens=4096,
                response_format="text",
                stream=False,
                tool_mode="auto",
                max_iterations=8,
                command_timeout_sec=subagents_cfg.default_timeout_sec,
                max_command_output_chars=12000,
                context_budget_chars=min(
                    context_cfg.max_context_chars, 200000),
                memory_atom_budget=self.settings.memory.retrieval_top_k,
                recent_turns_budget=8,
                tool_output_budget_chars=24000,
            ),
            ModelProfile(
                profile_id="flash-fast",
                name="Flash Non-thinking Fast",
                model_id="deepseek-v4-flash",
                thinking_type="disabled",
                reasoning_effort="high",
                temperature=0.2,
                top_p=1.0,
                max_tokens=4096,
                response_format="text",
                stream=False,
                tool_mode="auto",
                max_iterations=8,
                command_timeout_sec=90,
                max_command_output_chars=12000,
                context_budget_chars=min(
                    context_cfg.max_context_chars, 160000),
                memory_atom_budget=self.settings.memory.retrieval_top_k,
                recent_turns_budget=8,
                tool_output_budget_chars=24000,
            ),
            ModelProfile(
                profile_id="json-compressor",
                name="JSON Compressor",
                model_id=self.settings.compression.model_id,
                thinking_type=self.settings.compression.thinking_type,
                reasoning_effort="high",
                temperature=0.0,
                top_p=1.0,
                max_tokens=4096,
                response_format="json_object",
                stream=False,
                tool_mode="none",
                max_iterations=4,
                command_timeout_sec=60,
                max_command_output_chars=4000,
                context_budget_chars=self.settings.compression.target_chars,
                memory_atom_budget=self.settings.memory.retrieval_top_k,
                recent_turns_budget=self.settings.compression.keep_recent_turns,
                tool_output_budget_chars=8000,
            ),
        ]
