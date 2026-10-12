"""Read supplier warranty curves for review; never replace sizing master data."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
import math
from zipfile import ZipFile

from openpyxl import load_workbook


@dataclass(frozen=True)
class SupplierCurve:
    sheet: str
    basis: str
    soc_pct: float
    power_rate: float
    cycles_per_day: float
    years: tuple[int, ...]
    retention_pct: tuple[float | None, ...]
    source_cells: tuple[str, ...]
    issues: tuple[str, ...]

    @property
    def last_supported_year(self) -> int | None:
        return max((y for y, v in zip(self.years, self.retention_pct) if v is not None), default=None)


@dataclass(frozen=True)
class SupplierDataset:
    source_sha256: str
    curves: tuple[SupplierCurve, ...]
    rte_numeric_values: int
    calendar_numeric_values: int


def _number(cell, *, required=True) -> float | None:
    value = cell.value
    if value is None and not required:
        return None
    if cell.data_type == "f":
        raise ValueError(f"{cell.coordinate}: formulas need independently verified calculated values.")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{cell.coordinate}: expected a finite numeric value.")
    return float(value)


def parse_supplier_degradation(data: bytes) -> SupplierDataset:
    if len(data) > 25 * 1024 * 1024:
        raise ValueError("Workbook exceeds the 25 MB preview limit.")
    try:
        with ZipFile(BytesIO(data)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 32 * 1024 * 1024:
                raise ValueError("Expanded workbook exceeds the preview limit.")
        workbook = load_workbook(BytesIO(data), data_only=False, keep_links=False)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("Upload a valid XLSX supplier degradation workbook.") from exc
    curves = []
    try:
        sheets = {sheet.title.strip(): sheet for sheet in workbook}
        for name, basis in [("Degradation-均值", "mean"), ("Degradation-下限值", "lower_limit")]:
            sheet = sheets.get(name)
            if sheet is None:
                raise ValueError(f"Required source worksheet is missing: {name}")
            if sheet.max_row > 500 or sheet.max_column > 64:
                raise ValueError("Source worksheet dimensions exceed the supported preview layout.")
            starts = [r for r in range(1, sheet.max_row + 1) if str(sheet.cell(r, 1).value).strip().upper() == "SOC"]
            if not starts:
                raise ValueError(f"{name}: no SOC blocks found.")
            for index, row in enumerate(starts):
                soc_cell = sheet.cell(row, 3)
                if "%" not in soc_cell.number_format:
                    raise ValueError(f"{name}!{soc_cell.coordinate}: SOC percentage format is required.")
                soc = _number(soc_cell) * 100
                if not 0 <= soc <= 100:
                    raise ValueError(f"{name}: SOC label lies outside 0–100%.")
                if str(sheet.cell(row + 1, 1).value).strip().lower() != "power rate":
                    raise ValueError(f"{name}: unsupported Power Rate header.")
                end = starts[index + 1] if index + 1 < len(starts) else sheet.max_row + 1
                point_rows = [r for r in range(row + 3, end) if sheet.cell(r, 2).value is not None]
                years = tuple(int(_number(sheet.cell(r, 2))) for r in point_rows)
                if not years or years != tuple(range(len(years))) or any(_number(sheet.cell(r, 2)) != y for r, y in zip(point_rows, years)):
                    raise ValueError(f"{name}: source years must be sequential integers starting at zero.")
                rate = None
                for col in range(3, sheet.max_column + 1):
                    rate_cell = sheet.cell(row + 1, col)
                    if rate_cell.value is not None:
                        rate = _number(rate_cell)
                    frequency_cell = sheet.cell(row + 2, col)
                    if frequency_cell.value is None:
                        continue
                    frequency = _number(frequency_cell)
                    if rate is None or rate <= 0 or frequency <= 0:
                        raise ValueError(f"{name}: power rate and daily frequency must be positive.")
                    values, cells, issues = [], [], []
                    for r in point_rows:
                        cell = sheet.cell(r, col)
                        value = _number(cell, required=False)
                        if value is not None and "%" not in cell.number_format:
                            raise ValueError(f"{name}!{cell.coordinate}: retention percentage format is required.")
                        values.append(None if value is None else value * 100)
                        cells.append(cell.coordinate)
                    if values[0] != 100:
                        issues.append("Year 0 is not 100%; the source denominator needs confirmation.")
                    numeric = [(y, v) for y, v in zip(years, values) if v is not None]
                    if any(v < 0 or v > 100 for _, v in numeric):
                        issues.append("Source retention contains a value outside 0–100%.")
                    if any(b > a + 1e-9 for (_, a), (_, b) in zip(numeric, numeric[1:])):
                        issues.append("Source retention increases between annual checkpoints.")
                    if numeric and any(values[y] is None for y in range(numeric[-1][0])):
                        issues.append("Source has an internal missing year; no interpolation is applied.")
                    curves.append(SupplierCurve(sheet.title, basis, soc, rate, frequency, years, tuple(values), tuple(cells), tuple(issues)))
        keys = [(c.basis, c.soc_pct, c.power_rate, c.cycles_per_day) for c in curves]
        if len(keys) != len(set(keys)):
            raise ValueError("Source has duplicated duty cases.")
        by_key = dict(zip(keys, curves))
        for curve in curves:
            if curve.basis == "lower_limit":
                mean = by_key.get(("mean", curve.soc_pct, curve.power_rate, curve.cycles_per_day))
                if mean is None or mean.years != curve.years:
                    raise ValueError("Mean and lower-limit duty cases do not match.")
                if any(lo > hi + 1e-9 for lo, hi in zip(curve.retention_pct, mean.retention_pct) if lo is not None and hi is not None):
                    raise ValueError("Source lower-limit retention exceeds the corresponding mean.")
        def numeric_count(name):
            sheet = sheets.get(name)
            return sum(isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool) for row in sheet for cell in row) if sheet else 0
        return SupplierDataset(sha256(data).hexdigest(), tuple(curves), numeric_count("RTE"), numeric_count("Calender Degradation"))
    finally:
        workbook.close()
