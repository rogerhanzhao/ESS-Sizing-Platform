"""Preflight Admin products against the existing 314Ah sizing-curve basis.

This is deliberately an applicability check, not a product selector or a curve
resolver. The frozen selector still determines the product, and the existing
Excel/DB SOH and RTE loaders still supply the curves. A published product alone
does not establish that those curves apply to its linked cell.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd

from calb_sizing_tool.services.stage2_service import pick_dc_block


_CURRENT_CELL_CODE = "CALB-314AH-A"
_CURRENT_SOURCE_SHEETS = frozenset({"soh_profile_314_data", "soh_curve_314_template"})


@dataclass(frozen=True)
class AdminDcCurvePreflight:
    selections: tuple[dict[str, Any], ...]
    errors: tuple[str, ...]


def check_admin_dc_curve_applicability(
    df_blocks: pd.DataFrame,
    catalogue: Mapping[str, Any] | None,
    *,
    forms: Iterable[str] = ("container",),
) -> AdminDcCurvePreflight:
    """Inspect exactly the products the original picker will use for a new run.

    Only the explicitly linked, owner-approved legacy 314Ah-A basis is supported here. Neither a
    product name nor a nominal Ah match authorizes a different cell. The
    declared curve may not conflict with that basis. An empty legacy curve code
    retains the original approved 314Ah-A path; no new registration is required.
    A curve code is evidence of applicability, not an instruction to switch
    runtime curves. A future product-specific SOH/RTE resolver needs separate work.
    """
    catalogue = catalogue or {}
    selections: list[dict[str, Any]] = []
    errors: list[str] = []
    for form in dict.fromkeys(forms):
        selected = pick_dc_block(df_blocks, form)
        if selected is None:
            errors.append(f"No active {form} DC Block is available in the Admin product library.")
            continue
        block_code, block_name, capacity_mwh = selected
        products = [row for row in catalogue.get("dc_blocks", ()) if row.get("block_code") == block_code]
        product = products[0] if len(products) == 1 else {}
        cell_id = product.get("product_cell_id")
        cells = [row for row in catalogue.get("cells", ())
                 if cell_id and row.get("product_cell_id") == cell_id]
        cell = cells[0] if len(cells) == 1 else {}
        cell_code = cell.get("cell_code")
        cell_label = str(cell_code or "unverified linked cell")
        if cell:
            cell_label += f" ({cell.get('nominal_capacity_ah', 'unknown')} Ah, {cell.get('nominal_voltage_v', 'unknown')} V)"
        selections.append({
            "form": form, "block_code": block_code, "block_name": block_name,
            "capacity_mwh": capacity_mwh, "cell_code": cell_code,
        })
        label = f"Selected {form}: {block_name} ({block_code}); cell: {cell_label}."
        if not product or not cell:
            errors.append(label + " The exact product-to-cell link cannot be verified.")
            continue
        try:
            has_approved_ratings = (
                float(cell.get("nominal_capacity_ah")) == 314.0
                and float(cell.get("nominal_voltage_v")) == 3.2
                and str(cell.get("manufacturer") or "").strip().upper() == "CALB"
                and str(cell.get("chemistry") or "").strip().upper() == "LFP"
            )
        except (TypeError, ValueError):
            has_approved_ratings = False
        if cell_code != _CURRENT_CELL_CODE or not has_approved_ratings:
            errors.append(label + " The current sizing SOH/RTE curves are approved for the legacy "
                          "CALB 314Ah-A / 3.2 V LFP family only; they are not verified for this cell.")
            continue
        curve_code = product.get("default_degradation_curve_code")
        if not curve_code:
            continue
        curves = [row for row in catalogue.get("degradation_curves", ())
                  if curve_code and row.get("curve_code") == curve_code]
        curve = curves[0] if len(curves) == 1 else {}
        metadata = curve.get("metadata_json") or {}
        has_current_basis = (
            curve.get("product_cell_id") == cell_id
            and curve.get("basis_cell_code") == "CALB-314AH"
            and curve.get("data_status") == "active_default_314Ah"
            and curve.get("is_active") is True
            and _CURRENT_SOURCE_SHEETS.issubset(metadata.get("source_sheets") or ())
            and bool(curve.get("cycle_points_json"))
        )
        if not has_current_basis:
            errors.append(label + " Its declared curve does not verify the same linked cell and existing "
                          "314Ah source basis.")
    return AdminDcCurvePreflight(tuple(selections), tuple(errors))
