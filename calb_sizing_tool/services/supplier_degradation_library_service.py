"""Candidate import, provenance and review exports; no active SOH writes."""
from dataclasses import asdict
from hashlib import sha256
from io import BytesIO, StringIO
import csv
import json
from zipfile import ZipFile, ZIP_DEFLATED

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from calb_sizing_tool.infra.db.models import AuditLog, SupplierDegradationImport, UserAccount
from calb_sizing_tool.infra.db.session import session_scope
from calb_sizing_tool.repositories.auth_repository import AuthRepository
from calb_sizing_tool.services.supplier_degradation_service import SupplierCurve, SupplierDataset, parse_supplier_degradation


def _require_admin(session, actor):
    user = session.get(UserAccount, actor)
    if user is None or user.status != "active" or not user.is_active:
        raise PermissionError("An active administrator is required.")
    if "admin" not in {r.role_code for r in AuthRepository(session).list_user_roles(actor) if r.is_active}:
        raise PermissionError("Administrator access required.")


def _summary(row):
    curves = row.dataset_json["curves"]
    return dict(import_id=row.import_id, version_label=row.version_label, filename=row.filename,
                source_sha256=row.source_sha256, status=row.status, actor=row.actor,
                created_at=row.created_at.isoformat(), curve_count=len(curves),
                missing_points=sum(v is None for c in curves for v in c["retention_pct"]))


class SupplierDegradationLibraryService:
    def __init__(self, db_url=None):
        self.db_url = db_url

    def list_versions(self, actor):
        with session_scope(self.db_url) as session:
            _require_admin(session, actor)
            rows = session.scalars(select(SupplierDegradationImport).order_by(SupplierDegradationImport.created_at.desc())).all()
            return [_summary(row) for row in rows]

    def save_candidate(self, data, filename, version_label, actor):
        # Validate every curve before opening a write transaction.
        with session_scope(self.db_url) as session:
            _require_admin(session, actor)
        label = version_label.strip()
        if not label or len(label) > 128:
            raise ValueError("Provide a version label of 1 to 128 characters.")
        filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
        if not filename.lower().endswith(".xlsx") or len(filename) > 255:
            raise ValueError("Provide a valid XLSX filename.")
        dataset = parse_supplier_degradation(data)
        payload = asdict(dataset)
        try:
            with session_scope(self.db_url) as session:
                _require_admin(session, actor)
                existing = session.scalar(select(SupplierDegradationImport).where(SupplierDegradationImport.source_sha256 == dataset.source_sha256))
                if existing:
                    return _summary(existing), False
                row = SupplierDegradationImport(filename=filename, version_label=label, actor=actor,
                    source_sha256=dataset.source_sha256, source_bytes=data, dataset_json=payload, status="candidate")
                session.add(row)
                session.flush()
                session.add(AuditLog(entity_type="supplier_degradation_import", entity_id=row.import_id,
                    action="import_candidate", actor=actor, payload_json={"source_sha256": dataset.source_sha256,
                    "curve_count": len(dataset.curves), "status": "candidate", "version_label": label}))
                return _summary(row), True
        except IntegrityError:
            # A simultaneous import of the same exact file is idempotent too.
            with session_scope(self.db_url) as session:
                _require_admin(session, actor)
                existing = session.scalar(select(SupplierDegradationImport).where(SupplierDegradationImport.source_sha256 == dataset.source_sha256))
                if existing:
                    return _summary(existing), False
            raise

    def load_version(self, import_id, actor):
        with session_scope(self.db_url) as session:
            _require_admin(session, actor)
            row = session.get(SupplierDegradationImport, import_id)
            if row is None:
                raise ValueError("Candidate version not found.")
            raw = row.source_bytes
            if sha256(raw).hexdigest() != row.source_sha256:
                raise ValueError("Stored source checksum mismatch.")
            payload = row.dataset_json
            curves = tuple(SupplierCurve(**{**c, **{k: tuple(c[k]) for k in ("years", "retention_pct", "source_cells", "issues")}}) for c in payload["curves"])
            dataset = SupplierDataset(payload["source_sha256"], curves, payload["rte_numeric_values"], payload["calendar_numeric_values"])
            if dataset != parse_supplier_degradation(raw):
                raise ValueError("Stored curve data do not match the original workbook.")
            return _summary(row), dataset, raw


def _csv(rows):
    output = StringIO(newline="")
    writer = csv.writer(output)
    for row in rows:
        # Supplier sheet/file text remains inert when opened in Excel.
        writer.writerow([("'" + v) if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in row])
    return output.getvalue().encode("utf-8-sig")


def review_attachment(dataset, curves=None, metadata=None):
    """Excel-readable CSV bundle: annual matrix, point provenance and duty screen."""
    curves = tuple(dataset.curves if curves is None else curves)
    if not curves:
        raise ValueError("Select at least one source curve.")
    years = sorted({y for c in curves for y in c.years})
    prefix = ["source_sha256", "source_sheet", "source_series", "source_SOC_label_pct", "source_Power_Rate", "cycles_per_day"]
    annual = [prefix + [f"Year {y} retention_pct" for y in years]]
    points = [prefix + ["year", "retention_pct", "source_cell", "value_status"]]
    duties = [prefix + ["last_source_year", "missing_points", "assumed_hours_per_day", "assumed_24h_screen", "source_issues"]]
    for c in curves:
        identity = [dataset.source_sha256, c.sheet, c.basis, c.soc_pct, c.power_rate, c.cycles_per_day]
        values = dict(zip(c.years, c.retention_pct))
        annual.append(identity + [values.get(y) if values.get(y) is not None else "N/A" for y in years])
        for y, v, cell in zip(c.years, c.retention_pct, c.source_cells):
            points.append(identity + [y, v if v is not None else "", cell, "source_value" if v is not None else "missing"])
        hours = c.cycles_per_day * (2 / c.power_rate + 1)
        duties.append(identity + [c.last_supported_year, sum(v is None for v in c.retention_pct), hours,
                      "exceeds_24h" if hours > 24 else "fits_assumptions_only", " | ".join(c.issues)])
    info = {**(metadata or {}), "source_sha256": dataset.source_sha256, "exported_curves": len(curves),
            "capacity_unit": "percent: 100 means 100%", "status": "candidate/reference; not active for sizing",
            "SOC": "source label only; standby SOC versus cycling window unconfirmed; not relabelled as DOD",
            "series": "Mean and Lower limit are supplier sheet labels; statistical and warranty meaning unconfirmed",
            "time_screen": "Assumes 100% cycle depth, equal nominal charge/discharge rate and two 30-minute rests per cycle. This is not confirmed duty feasibility.",
            "missing_values": "N/A in annual matrix, empty retention_pct with missing status in points; no interpolation or extrapolation",
            "calendar_and_RTE": "No recombination or replacement of platform data", "parser_version": "supplier_v1"}
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, rows in [("annual_retention.csv", annual), ("source_points.csv", points), ("duty_review.csv", duties)]:
            archive.writestr(name, _csv(rows))
        archive.writestr("README.json", json.dumps(info, ensure_ascii=False, indent=2))
    return output.getvalue()
