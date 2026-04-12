# SLD UI Override Rules V1

## Default Mode

Default SLD generation mode is **formal / strict**.

In this mode:

- UI reads runtime run data plus AC authoritative allocation
- missing required engineering inputs cause an explicit error
- no silent fallback is allowed
- result is considered the formal output candidate

## Engineering Override Mode

Override mode is off by default.

Users must explicitly enable:

- `Enable Engineering Override Mode`

When enabled:

- override inputs become editable
- pipeline validation mode switches to `draft`
- UI must show a visible warning that the result is non-official
- the result must not silently replace the formal baseline interpretation

## What Override Mode Is For

Override mode is only for:

- internal engineering preview
- temporary completion of missing non-runtime inputs
- exploratory diagram review

Override mode is not for:

- replacing authoritative runtime data
- silently overriding formal feeder / PCS / topology allocation
- creating an unmarked formal artifact

## Override Scope

Current override payload can provide:

- transformer vector group
- transformer uk percent
- DC block voltage
- controlled electrical labels
- controlled equipment ratings
- explicit DC blocks per feeder only when authoritative allocation is absent

## Non-Allowed Behavior

The UI must not:

- default to override mode
- silently auto-enable draft mode
- silently overwrite formal results
- re-infer feeder allocation itself
- build canonical input or topology logic locally

## UI Status Messaging

Formal mode:

- show strict-mode info
- explain that missing required inputs fail fast

Override mode:

- show clear draft warning
- explain that output is non-official
- keep the distinction visible after generation
