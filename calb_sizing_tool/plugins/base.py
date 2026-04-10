from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ArtifactPayload:
    artifact_kind: str
    file_name: str
    media_type: str
    content: bytes
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PluginMetadata:
    plugin_id: str
    plugin_name: str
    plugin_version: str
    supported_artifact_kind: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin_id": self.plugin_id,
            "plugin_name": self.plugin_name,
            "plugin_version": self.plugin_version,
            "supported_artifact_kind": list(self.supported_artifact_kind),
        }


class DiagramPlugin(Protocol):
    metadata: PluginMetadata

    def build_input_from_run(self, *args, **kwargs):
        ...

    def validate_input(self, render_input) -> list[str]:
        ...

    def render(self, render_input):
        ...

    def emit_artifact(self, render_output) -> list[ArtifactPayload]:
        ...

    def metadata_payload(self, render_input, render_output) -> dict[str, Any]:
        ...


def json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
