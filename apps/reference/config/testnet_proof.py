"""Strict P46-1G proof-only configuration contract."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


TESTNET_HOST = "testnet.binancefuture.com"


class ProofSymbolSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allowed_symbols: list[str] = Field(..., min_length=1)
    preferred_symbol: str = Field(..., min_length=2)

    @field_validator("allowed_symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        symbols = [str(item).strip().upper() for item in value]
        if any(not item or not item.isalnum() for item in symbols):
            raise ValueError("allowed symbols must be non-empty alphanumeric values")
        if len(symbols) != len(set(symbols)):
            raise ValueError("allowed symbols must be unique")
        return symbols

    @field_validator("preferred_symbol")
    @classmethod
    def normalize_preferred(cls, value: str) -> str:
        symbol = str(value).strip().upper()
        if not symbol.isalnum():
            raise ValueError("preferred symbol must be alphanumeric")
        return symbol

    @model_validator(mode="after")
    def preferred_is_allowed(self) -> "ProofSymbolSelection":
        if self.preferred_symbol not in self.allowed_symbols:
            raise ValueError("preferred symbol must be in allowed_symbols")
        return self


class ProofExposure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_notional_quote: Decimal = Field(..., gt=0)
    operator_max_notional_quote: Decimal = Field(..., gt=0)

    @model_validator(mode="after")
    def target_within_cap(self) -> "ProofExposure":
        if self.target_notional_quote > self.operator_max_notional_quote:
            raise ValueError("target_notional_quote exceeds operator maximum")
        return self


class ProofTimeouts(BaseModel):
    model_config = ConfigDict(extra="forbid")

    submit_ack_timeout_sec: int = Field(..., ge=1)
    venue_query_timeout_sec: int = Field(..., ge=1)
    cancel_timeout_sec: int = Field(..., ge=1)
    flatten_timeout_sec: int = Field(..., ge=1)
    total_proof_timeout_sec: int = Field(..., ge=1)

    @model_validator(mode="after")
    def operations_fit_total(self) -> "ProofTimeouts":
        required = (
            self.submit_ack_timeout_sec
            + self.venue_query_timeout_sec
            + self.cancel_timeout_sec
            + self.flatten_timeout_sec
        )
        if self.total_proof_timeout_sec < required:
            raise ValueError("total proof timeout is shorter than bounded lifecycle operations")
        return self


class ProofCleanup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cancel_unfilled: Literal[True]
    close_if_filled: Literal[True]
    require_final_flat: Literal[True]
    require_no_related_open_orders: Literal[True]


class P46TestnetProofConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    enabled: Literal[True]
    environment: Literal["binance_futures_testnet"]
    endpoint: str
    symbol_selection: ProofSymbolSelection
    exposure: ProofExposure
    timeouts: ProofTimeouts
    cleanup: ProofCleanup

    @field_validator("endpoint")
    @classmethod
    def testnet_endpoint_only(cls, value: str) -> str:
        parsed = urlparse(str(value).strip())
        if parsed.scheme != "https" or parsed.hostname != TESTNET_HOST or parsed.path not in {"", "/"}:
            raise ValueError("endpoint must be the canonical Binance Futures Testnet HTTPS root")
        return str(value).rstrip("/")


def load_p46_testnet_proof_config(path: str | Path) -> P46TestnetProofConfig:
    config_path = Path(path)
    if not config_path.is_file():
        raise RuntimeError(f"proof config missing: {config_path}")
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return P46TestnetProofConfig.model_validate(raw)
