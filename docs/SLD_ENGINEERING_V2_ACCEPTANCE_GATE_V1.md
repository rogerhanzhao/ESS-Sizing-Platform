# SLD Engineering V2 Acceptance Gate V1

## Scope

This patch keeps `engineering_v2` as a manual preview renderer and adds an
automated acceptance gate for the V2 layout plan.

It does not change:

```text
Site Layout
login
RBAC
DC sizing math
default SLD renderer mode
```

## Why This Gate Exists

The earlier V2 steps proved that a port/bay model can render a cleaner SLD, but
the drawing still needed machine-checkable guardrails. Without those guardrails,
bad drawings can return through future edits as:

```text
overlapped equipment boxes
text that does not fit
missing transformer parameters
floating DC busbar labels
duplicate connector IDs
multi-DC-block feeder overlaps
```

## New Validation Boundary

New file:

```text
calb_diagrams/sld_engineering_v2_validation.py
```

The validator consumes only:

```text
SldV2LayoutPlan
```

It does not read session state, topology, AC dictionaries, DB rows, or DC sizing
snapshots. This keeps the acceptance gate on the drawing plan boundary.

## Checks Added

The gate checks:

1. Every box stays inside its section.
2. Equipment boxes do not overlap, except intentional RMU parent/bay nesting.
3. Internal text fits the box for normal equipment boxes.
4. Forbidden floating DC busbar labels are absent.
5. Transformer label includes voltage, MVA, and Uk%.
6. Connector IDs are unique.

The preview script also records PNG dimensions so a cropped render can be
detected without manual image inspection. The `engineering_v2` plugin metadata
records the same PNG dimensions for UI/artifact-path renders.

Missing professional drawing inputs are warnings, not layout errors. They are
reported in metadata as `layout_warning_count` / `engineering_v2_layout_warning_count`.
Examples include cable specifications or BESS cell specification when the
authoritative input has not supplied them.

## Layout Fix Included

V2 now lays out multiple DC blocks under the same feeder without stacking them in
the same coordinates.

For example:

```text
F1=2, F2=1, F3=2, F4=1
```

is rendered as separate DC block boxes under F1 and F3, not overlapped boxes.

The preview script can now stress-test this scenario directly:

```text
python scripts/generate_sld_engineering_v2_preview.py --dc-blocks-per-feeder 2,1,2,1 --output-dir outputs/sld_engineering_v2_preview/multi_dc
```

## Drawing Content Fix Included

The V2 transformer label now includes:

```text
HV/LV voltage
MVA
vector group
Uk%
cooling, when available
```

The Equipment List PCS row now includes LV voltage:

```text
4 x 1250 kW @ 690 V
```

## Regression Coverage Added

Tests now verify:

```text
default V2 preview renders 1780 x 900 PNG
default V2 preview has zero layout issues
multi-DC-block preview renders without overlap
engineering_v2 plugin mode handles multi-DC-block feeders
```

## Current Status

`engineering_v2` is still not the production default. It is now suitable for
manual visual review with automated guardrails protecting the obvious readability
failures.
