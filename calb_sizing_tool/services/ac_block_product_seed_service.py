# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

"""Seed preset AC Block products into ``product_ac_block``.

The record values were transcribed from vendor datasheets (numbers only — the
source PDFs are not stored in the repository). This service is the mechanism to
"preset" those products into the governed AC Block product table so the app has
a starting catalogue.

It is an idempotent upsert keyed by ``block_code``: existing rows are updated in
place, new ones are created. It never fabricates unpublished *numeric* values —
fields the datasheet does not state (e.g. transformer Uk%) stay null and remain
owner confirmation items.

Transformer topology / vector group / LV arrangement are normalized on the way
in (see ``ac_block_transformer_defaults``): they are *derived* from a stated
datasheet vector group where possible, and only otherwise filled with a
conservative standard default that is explicitly marked
``standard_default_pending_confirmation`` so it is never mistaken for a
confirmed OEM value.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from calb_sizing_tool.infra.db.models import ProductACBlock
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.services.ac_block_transformer_defaults import (
    normalize_ac_product_transformer_fields,
)

SEED_PATH = Path(__file__).resolve().parents[2] / "data" / "ac_block_products_seed.json"

_SCALAR_FIELDS = (
    "block_name",
    "pcs_model",
    "pcs_power_kw",
    "pcs_count",
    "transformer_kva",
    "hv_voltage_kv",
    "lv_voltage_v",
    "peak_efficiency_pct",
    "aux_load_kw",
    "notes",
)


def load_seed_document(seed_path: Path | None = None) -> dict[str, Any]:
    path = Path(seed_path) if seed_path is not None else SEED_PATH
    return json.loads(path.read_text(encoding="utf-8"))


def seed_ac_block_products(
    *,
    db_url: str | None = None,
    seed_path: Path | None = None,
    version_tag: str | None = None,
    source_ref: str = "vendor_datasheet_seed",
) -> dict[str, Any]:
    """Upsert the preset AC Block products. Returns a summary of the changes."""
    document = load_seed_document(seed_path)
    products = document.get("products") or []
    tag = version_tag or document.get("version_tag")

    created: list[str] = []
    updated: list[str] = []
    with session_scope(db_url) as session:
        for product in products:
            block_code = str(product.get("block_code") or "").strip()
            if not block_code:
                continue
            values = {field: product.get(field) for field in _SCALAR_FIELDS if field in product}
            values["metadata_json"] = normalize_ac_product_transformer_fields(
                product.get("metadata_json") or {}
            )
            values["efficiency_curve_json"] = product.get("efficiency_curve_json") or {}

            row = (
                session.query(ProductACBlock)
                .filter(ProductACBlock.block_code == block_code)
                .one_or_none()
            )
            if row is None:
                row = ProductACBlock(block_code=block_code, **values)
                row.version_tag = tag
                row.source_ref = source_ref
                session.add(row)
                created.append(block_code)
            else:
                for field, value in values.items():
                    setattr(row, field, value)
                row.version_tag = tag
                row.source_ref = source_ref
                updated.append(block_code)
        session.flush()

    return {
        "created": created,
        "updated": updated,
        "total": len(created) + len(updated),
        "version_tag": tag,
    }


__all__ = ["SEED_PATH", "load_seed_document", "seed_ac_block_products"]
