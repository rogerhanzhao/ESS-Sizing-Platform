from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _safe_positive_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        resolved = float(value)
    except Exception:
        return None
    if resolved <= 0:
        return None
    return resolved


def resolve_authoritative_mv_voltage_kv(mv_nominal_voltage_kv: Any) -> float | None:
    return _safe_positive_float(mv_nominal_voltage_kv)


@dataclass(frozen=True)
class MvRmuVoltageContract:
    authoritative_mv_voltage_kv: float
    rmu_rated_voltage_kv: float


def resolve_mv_rmu_voltage_contract(
    *,
    mv_nominal_voltage_kv: Any,
) -> MvRmuVoltageContract:
    mv_kv = resolve_authoritative_mv_voltage_kv(mv_nominal_voltage_kv)
    if mv_kv is None:
        raise ValueError("POI / MV voltage is required before resolving RMU rated voltage.")
    return MvRmuVoltageContract(
        authoritative_mv_voltage_kv=float(mv_kv),
        rmu_rated_voltage_kv=float(mv_kv),
    )
