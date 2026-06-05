"""Order-policy resolution helpers for IntentBuilder."""

from typing import Any, Callable, Optional

from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons


def resolve_order_policy(
    *,
    config: Any,
    reject_fn: Callable[..., None],
    symbol: str,
    strategy_id: str,
    side: str,
    rid: str,
    tf_sec: Optional[int],
    reduce_only: bool,
    why_chain: list,
) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """Resolve order_type, tif, valid_for_ms. Returns None tuple on rejection."""

    def reject(*, reason_code: str, context: str) -> tuple[None, None, None]:
        reject_fn(
            symbol=symbol,
            strategy_id=strategy_id,
            side=side,
            rid=rid,
            reason_code=reason_code,
            context=context,
            why_chain=why_chain,
        )
        return None, None, None

    order_type: Optional[str] = None
    tif: Optional[str] = None
    try:
        strat_cfg = getattr(config.strategies, str(strategy_id), None)
        exec_cfg = getattr(strat_cfg, "execution", None) if strat_cfg else None
        if reduce_only and exec_cfg is not None:
            # Close orders use exit_order_type/exit_tif when configured,
            # falling back to entry fields for backward compatibility.
            order_type = getattr(exec_cfg, "exit_order_type", None) or getattr(
                exec_cfg,
                "entry_order_type",
                None,
            )
            tif = (
                getattr(exec_cfg, "exit_tif", None)
                if getattr(exec_cfg, "exit_order_type", None)
                else getattr(exec_cfg, "entry_tif", None)
            )
        else:
            order_type = getattr(exec_cfg, "entry_order_type",
                                 None) if exec_cfg else None
            tif = getattr(exec_cfg, "entry_tif", None) if exec_cfg else None
    except Exception:
        pass

    if not order_type:
        return reject(
            reason_code=NormalizedRejectReasons.ORDER_TYPE_MISSING,
            context="ORDER-POLICY-01: missing entry_order_type",
        )

    order_type_u = str(order_type).upper()

    try:
        caps = config.domains.execution_position.order_capabilities
        supported_types = set(str(x).upper()
                              for x in (caps.supported_order_types or []))
        supported_tifs = set(str(x).upper()
                             for x in (caps.supported_tif or []))
    except Exception:
        supported_types, supported_tifs = set(), set()

    if supported_types and order_type_u not in supported_types:
        return reject(
            reason_code=NormalizedRejectReasons.UNSUPPORTED_ORDER_TYPE,
            context=f"ORDER-POLICY-01: unsupported order_type={order_type_u}",
        )

    if order_type_u == "LIMIT":
        if tif is None:
            return reject(
                reason_code=NormalizedRejectReasons.TIF_REQUIRED_FOR_LIMIT,
                context="ORDER-POLICY-01: LIMIT requires explicit tif",
            )
        tif_u = str(tif).upper()
        if supported_tifs and tif_u not in supported_tifs:
            return reject(
                reason_code=NormalizedRejectReasons.UNSUPPORTED_TIF,
                context=f"ORDER-POLICY-01: unsupported tif={tif_u}",
            )
        tif = tif_u
    else:
        if tif is not None:
            return reject(
                reason_code=NormalizedRejectReasons.UNSUPPORTED_TIF,
                context="ORDER-POLICY-01: MARKET must have tif=null",
            )
        tif = None

    # Close-path exemption: reduce_only LIMIT intents use exit_limit_ttl_ms
    # from config (if set), avoiding the entry-path tf_sec -> ttl_by_tf_sec
    # pipeline. Normal entry (reduce_only=False) is unchanged.
    valid_for_ms: Optional[int] = None
    if order_type_u == "LIMIT" and reduce_only:
        try:
            strat_cfg = getattr(config.strategies, str(strategy_id), None)
            exec_cfg = getattr(strat_cfg, "execution",
                               None) if strat_cfg else None
            exit_ttl = getattr(exec_cfg, "exit_limit_ttl_ms",
                               None) if exec_cfg else None
            if exit_ttl is not None:
                valid_for_ms = int(exit_ttl)
        except Exception:
            pass
        if valid_for_ms is None:
            return reject(
                reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                context="ORDER-POLICY-01: reduce_only LIMIT requires execution.exit_limit_ttl_ms",
            )
    elif order_type_u == "LIMIT" and not reduce_only:
        if tf_sec is None:
            return reject(
                reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                context="EP-01.3-INT: LIMIT requires tf_sec",
            )
        try:
            pe_ttl_cfg = config.domains.execution_position.pending_entry_ttl
            if pe_ttl_cfg.enabled and tf_sec is not None:
                ttl_by_tf = pe_ttl_cfg.ttl_by_tf_sec
                if tf_sec in ttl_by_tf:
                    valid_for_ms = int(ttl_by_tf[tf_sec]) * 1000
                elif pe_ttl_cfg.reject_unknown_tf:
                    return reject(
                        reason_code=NormalizedRejectReasons.MISSING_TF_SEC,
                        context=f"EP-01.3-INT: tf_sec={tf_sec} not in ttl_by_tf_sec",
                    )
        except Exception as exc:
            return reject(
                reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                context=f"EP-01.3-INT: valid_for_ms error: {exc}",
            )

        if valid_for_ms is None:
            return reject(
                reason_code=NormalizedRejectReasons.DATA_NOT_READY,
                context="EP-01.3-INT: LIMIT requires valid_for_ms",
            )

    return order_type_u, tif, valid_for_ms
