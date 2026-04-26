from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from calb_sizing_tool.services.sld_pipeline_service import (
    normalize_sld_render_output,
    normalize_sld_topology,
    prepare_sld_pipeline_from_run_bundle,
    render_prepared_sld_pipeline,
    write_normalized_json,
)
from tests.integration.sld_regression_support import build_case_inputs, load_case_definition


def generate_case_baselines(case_dir: Path) -> None:
    case_definition = load_case_definition(case_dir)
    run_bundle, ac_snapshot, options, project_settings = build_case_inputs(case_definition)
    prepared = prepare_sld_pipeline_from_run_bundle(
        run_bundle,
        ac_snapshot=ac_snapshot,
        options=options,
        project_settings=project_settings,
    )
    render_output = render_prepared_sld_pipeline(prepared)
    write_normalized_json(case_dir / "topology_baseline.json", normalize_sld_topology(prepared.topology))
    write_normalized_json(case_dir / "render_baseline.json", normalize_sld_render_output(render_output))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate normalized SLD regression baselines.")
    parser.add_argument(
        "--case-dir",
        type=Path,
        default=Path("tests/fixtures/sld_cases/case01_container_only_group1"),
        help="Path to the SLD regression case directory.",
    )
    args = parser.parse_args()
    generate_case_baselines(args.case_dir)
    print(f"Generated SLD baselines under {args.case_dir}")


if __name__ == "__main__":
    main()
