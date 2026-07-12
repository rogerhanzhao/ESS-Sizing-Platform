# Site Constraint Set V1

`Site Constraint Set V1` is the controlled input required before the product
can attempt a deterministic Concept Master Layout. It is not a construction
site plan and it does not derive geometry from sizing results.

## Required input groups

1. Coordinate reference: CRS and north reference.
2. Site boundary: polygon with at least three coordinate points.
3. POI / interconnection location.
4. Access, construction and emergency routes.
5. Fire, egress and maintenance constraints.
6. Controlled equipment footprint catalogue.
7. MV collection corridor or routing constraint.
8. Applicable project, authority or technical-agreement rule basis.
9. By-others zones and interface points.

The readiness check confirms only that these groups are present and that basic
point/polygon structures are supplied. It does not validate authority code
compliance, fire separation, civil design, cable capacity, collision clearance,
vehicle turning or construction feasibility.

## Safe workflow

1. Download the template from **Typical AC Block Arrangement**.
2. Populate project-controlled values and assess the JSON in the same page.
3. Click **Register uploaded Site Constraint Set to this run** to store the
   uploaded JSON as a versioned artifact with run-level audit history.
4. Resolve every readiness item with the project engineering team. Incomplete
   inputs are stored as `draft_incomplete`; they do not unlock a Master Layout.
5. Only then enable a deterministic geometry validator and Concept Master
   Layout builder.

No `CALB`, `EPC`, owner, utility or other contractual responsibility is
assigned by this schema. That allocation belongs in project agreements and the
approved interface matrix.
