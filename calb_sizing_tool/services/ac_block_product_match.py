# -----------------------------------------------------------------------------
# Personal Open-Source Notice — see repository LICENSE.
# -----------------------------------------------------------------------------

"""Match an auto-recommended AC Block spec to real catalogue products.

The auto-recommend (trunk) flow computes an AC Block spec — PCS count and PCS
unit rating. This service finds catalogue ``ProductACBlock`` records whose PCS
count and unit power match that spec, so the generic flow can OPTIONALLY bind a
real product (confirmed transformer nameplate / vector group / cooling) instead
of the ``MW ÷ PF`` estimate. It introduces no new parameter — it only queries
the existing product catalogue by fields it already stores.
"""
from __future__ import annotations

from typing import Any, Optional

from calb_sizing_tool.infra.db.models import ProductACBlock
from calb_sizing_tool.infra.db.session import session_scope

_PCS_KW_TOL = 1.0  # kW; PCS unit ratings are integer-ish, match near-exact.


def match_ac_block_products(
    pcs_count: int,
    pcs_kw: float,
    *,
    db_url: str | None = None,
) -> list[dict[str, Any]]:
    """Catalogue products whose PCS count and unit rating match the given spec.

    Returns a list (possibly empty) of lightweight dicts with the confirmed
    transformer / LV values, ordered by block_code. A match requires the same
    PCS-per-block count and the same PCS unit power (within a small tolerance);
    the resulting AC Block power therefore also matches.
    """
    try:
        want_count = int(pcs_count)
        want_kw = float(pcs_kw)
    except (TypeError, ValueError):
        return []
    if want_count <= 0 or want_kw <= 0:
        return []

    results: list[dict[str, Any]] = []
    with session_scope(db_url) as session:
        rows = (
            session.query(ProductACBlock)
            .filter(ProductACBlock.pcs_count == want_count)
            .order_by(ProductACBlock.block_code.asc())
            .all()
        )
        for row in rows:
            if row.pcs_power_kw is None:
                continue
            if abs(float(row.pcs_power_kw) - want_kw) > _PCS_KW_TOL:
                continue
            metadata = row.metadata_json if isinstance(row.metadata_json, dict) else {}
            results.append({
                "block_code": row.block_code,
                "block_name": row.block_name,
                "vendor": metadata.get("vendor"),
                "pcs_count": row.pcs_count,
                "pcs_power_kw": row.pcs_power_kw,
                "transformer_kva": row.transformer_kva,
                "transformer_vector_group": metadata.get("transformer_vector_group"),
                "transformer_cooling": metadata.get("transformer_cooling"),
                "lv_voltage_v": row.lv_voltage_v,
                "hv_voltage_kv": row.hv_voltage_kv,
                "ac_power_mw": metadata.get("ac_power_mw"),
            })
    return results


def product_transformer_overrides(product: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Confirmed transformer/LV fields to attach to a generic AC output when bound.

    Returns only the keys that carry a real value, so an unset field stays absent
    (and the report/SLD treat it as TBD rather than a fabricated value).
    """
    if not product:
        return {}
    out: dict[str, Any] = {"ac_block_product_block_code": product.get("block_code")}
    if product.get("transformer_kva"):
        out["transformer_kva"] = float(product["transformer_kva"])
        out["transformer_mva"] = round(float(product["transformer_kva"]) / 1000.0, 6)
    if product.get("transformer_vector_group"):
        out["transformer_vector_group"] = product["transformer_vector_group"]
    if product.get("transformer_cooling"):
        out["transformer_cooling"] = product["transformer_cooling"]
    if product.get("lv_voltage_v"):
        out["lv_voltage_v"] = float(product["lv_voltage_v"])
    return out


__all__ = ["match_ac_block_products", "product_transformer_overrides"]
