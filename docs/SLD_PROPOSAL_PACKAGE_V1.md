# SLD Proposal Package V1

The SLD pipeline issues a controlled proposal package around the selected
Typical AC Block SLD. It is intended for concept/proposal communication and
traceable engineering review preparation, not construction release.

| Sheet | Output | Purpose | Boundary |
| --- | --- | --- | --- |
| SLD-01 | Site Electrical Index | Lists every AC Block and the sizing-derived PCS, DC Block and transformer allocation. | It is not a site plan and contains no coordinates, roads, fire lanes, cable routes or clearances. |
| SLD-02 | Typical AC Block SLD | Shows the RMU, transformer, LV bus, PCS and DC Block relationship for the selected AC Block. | It is a representative electrical topology, not a full-station drawing. |
| SLD-03 | Electrical Design Basis Schedule | Records calculated sizing values and the formal-readiness issue register. | It does not infer cable, protection, grounding, civil or site-specific engineering specifications. |
| SLD-04 | Concept Interface / Scope | Makes the POI-facing, Typical AC Block and project-integration interface surfaces visible. | It assigns no CALB, EPC, owner, utility or other contractual responsibility; that allocation remains project-specific. |

## Document status

- `official`: the formal-readiness gate passed; artifacts are released as a formal baseline.
- `concept`: readiness is incomplete; all sheets are marked `CONCEPT ONLY - NOT FOR CONSTRUCTION`.
- `draft_override`: an explicit engineering override was used; all sheets are marked `DRAFT / OVERRIDE - NOT FOR CONSTRUCTION`.

The readiness manifest remains the authoritative source for unresolved formal
issue items. SLD-03 provides a readable schedule view of those items, while the
manifest retains the structured diagnostic record.

SLD-04 is intentionally an interface map, not an interface agreement. Its
three zones make the BESS package, POI-facing boundary and project-integration
boundary visible, while marking all responsibility allocation as requiring a
separate project agreement.

## Next boundary

This package deliberately stops before a Concept Master Layout. That later
capability requires a controlled Site Constraint Set, equipment footprint
catalogue, deterministic geometry validation and an explicit project/location
rule basis. It must not be created by extrapolating the AC Block index.
