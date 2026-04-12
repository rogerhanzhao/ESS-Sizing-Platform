# SLD Renderer Boundary V1

## Renderer Boundary

Renderer now only does four things:

- read `SldTopology`
- read the resolved layout profile
- draw symbols and connectors
- export SVG / PNG

Renderer must not:

- read `ac_output`
- read `stage13_output`
- read session state
- re-allocate feeders
- guess transformer / PCS / DC block counts
- infer engineering topology

## Responsibility Split

### Topology Builder

Owned by:

- `calb_sizing_tool/services/sld_topology_builder.py`

Responsibilities:

- PCS / feeder count
- DC blocks per feeder
- MV / RMU / transformer / LV / PCS / DC block relationships
- semantic node / edge / equipment creation
- authoritative engineering relationship graph

### Layout Engine

Owned by:

- `calb_diagrams/sld_layout_engine.py`

Responsibilities:

- choose compact vs engineering-readable placement profile
- compute canvas size
- compute panel geometry
- compute symbol positions
- compute connector routes
- compute summary/equipment text blocks

Layout engine does not decide engineering relationships. It only places already-defined topology.

### Symbol Library

Owned by:

- `calb_diagrams/symbol_library.py`

Responsibilities:

- draw each symbol type
- render only the geometry and text given by the layout plan

Symbol library must not decide:

- whether a symbol exists
- how many feeders exist
- which device connects to which device

### Renderer

Owned by:

- `calb_diagrams/sld_pro_renderer.py`

Responsibilities:

- call layout engine
- loop through panels / connectors / symbols
- write SVG
- optionally export PNG

## Logic Removed From Renderer

The following logic is no longer authoritative inside renderer:

- feeder count / PCS count decisions
- DC block allocation decisions
- topology branching decisions
- compact/full engineering quantity inference
- transformer / PCS default guessing
- old dict-based runtime source reads

## Compatibility Layer

Old `render_sld_pro_svg(spec, ...)` remains as a compatibility wrapper only.

It now:

- converts legacy `SldGroupSpec` into topology
- delegates to `render_sld_svg(topology, layout_profile, theme, ...)`

It must not evolve back into an engineering logic sink.
