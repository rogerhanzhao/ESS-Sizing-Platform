# SLD Formal Readiness Gate V1

## Scope

This gate is part of the SLD reorganization work. It does not change DC sizing,
AC sizing, Site Layout, login/RBAC, or report export behavior.

The goal is to prevent a visually plausible SLD from being treated as a formal
engineering drawing when the underlying runtime data is not physically
consistent.

## Implemented Service

```text
calb_sizing_tool/services/sld_formal_readiness_service.py
```

The service checks a prepared SLD chain:

```text
DcRunBundle
AcSnapshot
SldCanonicalInput
SldRenderOptions
case project_settings
```

It returns:

```text
ready
error_count
warning_count
issues[]
```

## Current Checks

Formal SLD readiness currently requires:

```text
strict validation mode
override mode disabled
AC snapshot source_run_id present
AC snapshot source_run_id matches active run_id
AC allocation total DC Block count matches DC run snapshot
SLD group allocation matches the selected AC allocation group
AC snapshot dc_total_mwh matches DC run nameplate when present
SLD DC Block energy represents the DC run total across the AC allocation
MV/LV/DC cable specs are explicit
BESS cell spec is explicit
```

It also warns when:

```text
case project_settings are not passed
renderer mode is not engineering_v2
```

## Runtime Integration

`sld_pipeline_service.prepare_sld_pipeline_from_run_bundle()` now computes the
readiness report after canonical input/topology preparation.

`run_sld_pipeline_from_run_bundle()` now uses the report as a publication gate:

- strict flow + `ready=true` → `official`;
- strict flow + `ready=false` → `concept` with a `NOT FOR CONSTRUCTION` watermark;
- override flow → `draft_override` with a `NOT FOR CONSTRUCTION` watermark.

The report is stored in every artifact metadata record and emitted as:

```text
sld_readiness_manifest[.concept|.draft].json
```

The Streamlit SLD page surfaces the readiness status in the pipeline status
area.

## Important Current Finding

The existing renderer regression fixture is not formal-ready. It deliberately
uses a simplified AC allocation for renderer regression:

```text
AC allocation: 4 DC Blocks
DC run snapshot: many more DC Blocks from the minimal test Excel
```

The gate now makes that mismatch explicit. This confirms that the fixture is
useful for renderer regression only and must not be interpreted as a real project
SLD.

## Next Step

The next SLD reorganization step is to rebuild the `engineering_v2` visual layer
around a professional sheet/template model:

```text
SldProfessionalSheet
SldProfessionalNotePanel
SldProfessionalRmuTemplate
SldProfessionalLvDcTemplate
```

Only after the readiness gate passes and the professional template passes visual
review should the default renderer be switched away from the server baseline.
