# SLD Renderer Mode Retirement V2

This step removes `topology_v1` from the public SLD renderer selector.

## Public Modes

The SLD page now exposes only:

- `engineering_v2` - professional SLD candidate and default UI mode
- `legacy_server` - old running-server baseline for manual comparison only

`topology_v1` remains as a reserved compatibility value so old serialized
requests can still be read during transition, but it is no longer an available
UI mode and should not be used for new previews.

## Why

`topology_v1` was an intermediate block-style renderer. It had useful data
contract value, but the visual result was not a professional single-line
electrical drawing. Keeping it in the selector created confusion because users
could select a retired path and expect it to behave like the final SLD.

## Drawing Changes

The `engineering_v2` candidate now makes the visible drawing change clearer:

- RMU/Ring In/Ring Out labels are shown in the MV area.
- The RMU voltage label is shown on the RMU bus.
- DC Block labels and energy values are visible below each BESS block.
- Multiple DC blocks under one PCS are spaced so the branch and blocks remain
  readable.

The legacy compatibility path is also patched so it no longer emits the old
per-PCS `BUSBAR A (Ckt A)` / `BUSBAR B (Ckt B)` structure. Its PCS symbol is
kept to the left side of the PCS box and the label/rating are kept on the right
to avoid the overlap shown in review screenshots.

## Not Changed

- No Site Layout code was changed.
- No login or RBAC code was changed.
- No DC sizing or AC sizing math was changed.
- The legacy server baseline renderer is still available only for comparison.
