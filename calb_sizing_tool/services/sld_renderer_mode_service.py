from __future__ import annotations

from calb_sizing_tool.schemas.diagram_inputs import SldRendererMode


DEFAULT_SLD_RENDERER_MODE: SldRendererMode = "engineering_v2"
PRODUCTION_BASELINE_SLD_RENDERER_MODE: SldRendererMode = "legacy_server"
AVAILABLE_SLD_RENDERER_MODES: tuple[SldRendererMode, ...] = ("engineering_v2", "legacy_server")
# Modes offered in the public renderer dropdown. Legacy is an internal
# development / regression-comparison path only — it renders the old patched
# style and must not be user-selectable in production. It stays in
# AVAILABLE_SLD_RENDERER_MODES so dev tooling and tests can still request it.
PUBLIC_SLD_RENDERER_MODES: tuple[SldRendererMode, ...] = ("engineering_v2",)
DEV_ONLY_SLD_RENDERER_MODES: tuple[SldRendererMode, ...] = ("legacy_server",)
RESERVED_SLD_RENDERER_MODES: tuple[SldRendererMode, ...] = ("topology_v1",)

_MODE_LABELS: dict[str, str] = {
    "engineering_v2": "Engineering V2 Professional SLD",
    "legacy_server": "Legacy Compatibility (patched old style)",
    "topology_v1": "Topology V1 (retired internal compatibility)",
}


def normalize_sld_renderer_mode(value: str | None) -> SldRendererMode:
    mode = str(value or DEFAULT_SLD_RENDERER_MODE).strip()
    if mode in AVAILABLE_SLD_RENDERER_MODES or mode in RESERVED_SLD_RENDERER_MODES:
        return mode  # type: ignore[return-value]
    raise ValueError(f"Unsupported SLD renderer mode: {mode}")


def sld_renderer_mode_label(mode: str) -> str:
    return _MODE_LABELS.get(mode, mode)


def is_sld_renderer_mode_available(mode: str) -> bool:
    return normalize_sld_renderer_mode(mode) in AVAILABLE_SLD_RENDERER_MODES


def is_sld_renderer_mode_public(mode: str) -> bool:
    return normalize_sld_renderer_mode(mode) in PUBLIC_SLD_RENDERER_MODES
