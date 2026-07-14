from __future__ import annotations

import hashlib
import json
from typing import Any

from calb_sizing_tool.schemas.sld_engineering_v2 import (
    SldEngineeringV2Graph,
    SldV2Edge,
    SldV2Node,
    SldV2Port,
)
from calb_sizing_tool.schemas.sld_topology import SldTopology


def _topology_hash(topology: SldTopology) -> str:
    payload = json.dumps(topology.model_dump(mode="python"), sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _port(
    port_id: str,
    display_name: str,
    port_role: str,
    side: str,
    voltage_domain: str,
    *,
    feeder_index: int | None = None,
    dc_block_index: int | None = None,
    attributes: dict[str, Any] | None = None,
) -> SldV2Port:
    return SldV2Port(
        port_id=port_id,
        display_name=display_name,
        port_role=port_role,  # type: ignore[arg-type]
        side=side,  # type: ignore[arg-type]
        voltage_domain=voltage_domain,  # type: ignore[arg-type]
        feeder_index=feeder_index,
        dc_block_index=dc_block_index,
        attributes=attributes or {},
    )


def _edge(
    edge_id: str,
    edge_type: str,
    source_node_id: str,
    source_port_id: str,
    target_node_id: str,
    target_port_id: str,
    *,
    feeder_index: int | None = None,
    dc_block_index: int | None = None,
    attributes: dict[str, Any] | None = None,
) -> SldV2Edge:
    return SldV2Edge(
        edge_id=edge_id,
        edge_type=edge_type,  # type: ignore[arg-type]
        source_node_id=source_node_id,
        source_port_id=source_port_id,
        target_node_id=target_node_id,
        target_port_id=target_port_id,
        feeder_index=feeder_index,
        dc_block_index=dc_block_index,
        attributes=attributes or {},
    )


def build_sld_engineering_v2_graph(topology: SldTopology) -> SldEngineeringV2Graph:
    """Build the port/bay/terminal engineering graph for the future V2 renderer.

    This is a model boundary only. It does not render SVG and does not change
    sizing, AC allocation, or persisted-data behavior.
    """
    summary = topology.summary
    group_token = f"G{summary.group_index:02d}"

    nodes: list[SldV2Node] = []
    edges: list[SldV2Edge] = []

    ring_in_terminal_id = f"{group_token}-MV-RING-IN-TERMINAL"
    ring_out_terminal_id = f"{group_token}-MV-RING-OUT-TERMINAL"
    rmu_switchgear_id = f"{group_token}-RMU-SWITCHGEAR"
    rmu_ring_in_bay_id = f"{group_token}-RMU-BAY-RING-IN"
    rmu_tx_feeder_bay_id = f"{group_token}-RMU-BAY-TX-FEEDER"
    rmu_ring_out_bay_id = f"{group_token}-RMU-BAY-RING-OUT"
    transformer_id = f"{group_token}-TRANSFORMER"
    lv_busbar_id = f"{group_token}-LV-BUSBAR"
    rmu_equipment_id = f"{group_token}-RMU"
    transformer_equipment_id = f"{group_token}-TX"
    lv_busbar_equipment_id = f"{group_token}-LV-BUSBAR"

    nodes.extend(
        [
            SldV2Node(
                node_id=ring_in_terminal_id,
                node_type="mv_ring_in_terminal",
                display_name="Ring In",
                ports=[_port("line_port", "Ring In Line", "line", "top", "mv_ac")],
                attributes={"mv_voltage_kv": summary.mv_voltage_kv},
            ),
            SldV2Node(
                node_id=ring_out_terminal_id,
                node_type="mv_ring_out_terminal",
                display_name="Ring Out",
                ports=[_port("line_port", "Ring Out Line", "line", "top", "mv_ac")],
                attributes={"mv_voltage_kv": summary.mv_voltage_kv},
            ),
            SldV2Node(
                node_id=rmu_switchgear_id,
                node_type="rmu_switchgear",
                display_name="RMU / MV Switchgear",
                equipment_id=rmu_equipment_id,
                ports=[
                    _port("ring_in_bus_port", "Ring-In Bus Connection", "bus", "left", "mv_ac"),
                    _port("transformer_feeder_bus_port", "Transformer Feeder Bus Connection", "bus", "bottom", "mv_ac"),
                    _port("ring_out_bus_port", "Ring-Out Bus Connection", "bus", "right", "mv_ac"),
                ],
                attributes=topology.equipment_ratings.rmu.model_dump(mode="python"),
            ),
            SldV2Node(
                node_id=rmu_ring_in_bay_id,
                node_type="rmu_ring_in_bay",
                display_name="RMU Ring-In Bay",
                equipment_id=rmu_equipment_id,
                ports=[
                    _port("line_port", "Ring-In Cable Terminal", "line", "top", "mv_ac"),
                    _port("bus_port", "Ring-In Bus Terminal", "bus", "right", "mv_ac"),
                ],
                attributes={"mv_voltage_kv": summary.mv_voltage_kv},
            ),
            SldV2Node(
                node_id=rmu_tx_feeder_bay_id,
                node_type="rmu_transformer_feeder_bay",
                display_name="Transformer Feeder Bay",
                equipment_id=rmu_equipment_id,
                ports=[
                    _port("bus_port", "Feeder Bus Terminal", "bus", "top", "mv_ac"),
                    _port("load_port", "Transformer Cable Terminal", "load", "bottom", "mv_ac"),
                ],
                attributes={"mv_voltage_kv": summary.mv_voltage_kv},
            ),
            SldV2Node(
                node_id=rmu_ring_out_bay_id,
                node_type="rmu_ring_out_bay",
                display_name="RMU Ring-Out Bay",
                equipment_id=rmu_equipment_id,
                ports=[
                    _port("bus_port", "Ring-Out Bus Terminal", "bus", "left", "mv_ac"),
                    _port("line_port", "Ring-Out Cable Terminal", "line", "top", "mv_ac"),
                ],
                attributes={"mv_voltage_kv": summary.mv_voltage_kv},
            ),
            SldV2Node(
                node_id=transformer_id,
                node_type="transformer",
                display_name="Transformer",
                equipment_id=transformer_equipment_id,
                ports=[
                    _port("hv_port", "Transformer HV Terminal", "hv", "top", "mv_ac"),
                    _port("lv_port", "Transformer LV Terminal", "lv", "bottom", "lv_ac"),
                ],
                attributes={
                    "mv_voltage_kv": summary.mv_voltage_kv,
                    "lv_voltage_v_ll": summary.lv_voltage_v_ll,
                    "transformer_rating_mva": summary.transformer_rating_mva,
                    "transformer_vector_group": summary.transformer_vector_group,
                    "transformer_uk_percent": summary.transformer_uk_percent,
                    "transformer_cooling": topology.equipment_ratings.transformer_cooling,
                },
            ),
        ]
    )

    lv_busbar_ports = [
        _port("transformer_port", "Transformer Incomer", "input", "top", "lv_ac"),
    ]
    for feeder_index in range(1, summary.feeder_count + 1):
        lv_busbar_ports.append(
            _port(
                f"feeder_F{feeder_index:02d}_port",
                f"Feeder F{feeder_index}",
                "tap",
                "bottom",
                "lv_ac",
                feeder_index=feeder_index,
            )
        )
    nodes.append(
        SldV2Node(
            node_id=lv_busbar_id,
            node_type="lv_busbar",
            display_name="LV Busbar",
            equipment_id=lv_busbar_equipment_id,
            ports=lv_busbar_ports,
            attributes={
                "lv_voltage_v_ll": summary.lv_voltage_v_ll,
                **topology.equipment_ratings.lv_busbar.model_dump(mode="python"),
            },
        )
    )

    edges.extend(
        [
            _edge(
                f"{group_token}-E-RINGIN-TERM-BAY",
                "ring_in_terminal_to_rmu_bay",
                ring_in_terminal_id,
                "line_port",
                rmu_ring_in_bay_id,
                "line_port",
            ),
            _edge(
                f"{group_token}-E-RINGIN-BAY-BUS",
                "rmu_bay_to_bus",
                rmu_ring_in_bay_id,
                "bus_port",
                rmu_switchgear_id,
                "ring_in_bus_port",
            ),
            _edge(
                f"{group_token}-E-BUS-TX-FEEDER-BAY",
                "rmu_bus_to_transformer_feeder_bay",
                rmu_switchgear_id,
                "transformer_feeder_bus_port",
                rmu_tx_feeder_bay_id,
                "bus_port",
            ),
            _edge(
                f"{group_token}-E-TX-FEEDER-BAY-TX",
                "transformer_feeder_bay_to_transformer_hv",
                rmu_tx_feeder_bay_id,
                "load_port",
                transformer_id,
                "hv_port",
            ),
            _edge(
                f"{group_token}-E-BUS-RINGOUT-BAY",
                "rmu_bus_to_ring_out_bay",
                rmu_switchgear_id,
                "ring_out_bus_port",
                rmu_ring_out_bay_id,
                "bus_port",
            ),
            _edge(
                f"{group_token}-E-RINGOUT-BAY-TERM",
                "rmu_ring_out_bay_to_terminal",
                rmu_ring_out_bay_id,
                "line_port",
                ring_out_terminal_id,
                "line_port",
            ),
            _edge(
                f"{group_token}-E-TX-LV-LVBUS",
                "transformer_lv_to_lv_busbar",
                transformer_id,
                "lv_port",
                lv_busbar_id,
                "transformer_port",
            ),
        ]
    )

    # DC block -> PCS feeder mapping. When there are fewer DC blocks than PCS
    # feeders (e.g. 2 x 5 MWh blocks feeding 4 x 1250 kW PCS), each block's DC
    # combiner feeds a contiguous span of PCS feeders through that feeder's own
    # isolator/fuse — a PCS feeder without any DC source is not a valid
    # electrical topology and must not be drawn dangling.
    pcs_total = len(summary.pcs_rating_kw_list)
    dc_total_blocks = sum(int(count) for count in summary.dc_blocks_per_feeder)
    shared_dc_mode = 0 < dc_total_blocks < pcs_total
    block_feeder_spans: list[list[int]] = []
    if shared_dc_mode:
        from calb_sizing_tool.common.allocation import evenly_distribute

        cursor = 1
        for span_size in evenly_distribute(pcs_total, dc_total_blocks):
            block_feeder_spans.append(list(range(cursor, cursor + span_size)))
            cursor += span_size
        feeder_dc_count = {fi: 1 for span in block_feeder_spans for fi in span}
    else:
        feeder_dc_count = {
            index: int(count)
            for index, count in enumerate(summary.dc_blocks_per_feeder, start=1)
        }

    dc_block_ordinal = 0
    for feeder_index, (pcs_rating_kw, dc_blocks_for_feeder) in enumerate(
        zip(summary.pcs_rating_kw_list, summary.dc_blocks_per_feeder),
        start=1,
    ):
        feeder_token = f"{group_token}-F{feeder_index:02d}"
        lv_feeder_id = f"{feeder_token}-LV-FEEDER"
        pcs_id = f"{feeder_token}-PCS"
        dc_interface_id = f"{feeder_token}-DC-INTERFACE"

        nodes.extend(
            [
                SldV2Node(
                    node_id=lv_feeder_id,
                    node_type="lv_feeder",
                    display_name=f"LV Feeder F{feeder_index}",
                    feeder_index=feeder_index,
                    ports=[
                        _port("busbar_port", "LV Busbar Tap", "input", "top", "lv_ac", feeder_index=feeder_index),
                        _port("pcs_port", "PCS AC Terminal", "output", "bottom", "lv_ac", feeder_index=feeder_index),
                    ],
                    attributes={"feeder_id": f"F{feeder_index}"},
                ),
                SldV2Node(
                    node_id=pcs_id,
                    node_type="pcs",
                    display_name=f"PCS-{feeder_index}",
                    equipment_id=f"{feeder_token}-PCS",
                    feeder_index=feeder_index,
                    ports=[
                        _port("ac_port", "PCS AC Port", "ac", "top", "lv_ac", feeder_index=feeder_index),
                        _port("dc_port", "PCS DC Port", "dc", "bottom", "dc", feeder_index=feeder_index),
                    ],
                    attributes={
                        "pcs_rating_kw": pcs_rating_kw,
                        "lv_voltage_v_ll": summary.lv_voltage_v_ll,
                        "project_frequency_hz": summary.project_frequency_hz,
                        "dc_block_voltage_v": summary.dc_block_voltage_v,
                    },
                ),
                SldV2Node(
                    node_id=dc_interface_id,
                    node_type="dc_interface",
                    display_name=f"DC Interface F{feeder_index}",
                    equipment_id=f"{feeder_token}-DC-INTERFACE",
                    feeder_index=feeder_index,
                    ports=[
                        _port("pcs_port", "PCS DC Terminal", "input", "top", "dc", feeder_index=feeder_index),
                        _port("block_port", "DC Block Terminal", "output", "bottom", "dc", feeder_index=feeder_index),
                    ],
                    attributes={
                        "dc_block_count": feeder_dc_count.get(feeder_index, 0),
                        "dc_block_voltage_v": summary.dc_block_voltage_v,
                        "fuse_spec": topology.equipment_ratings.dc_fuse.fuse_spec,
                        "shared_dc_block": shared_dc_mode,
                    },
                ),
            ]
        )

        edges.extend(
            [
                _edge(
                    f"{feeder_token}-E-LVBUS-LVFEEDER",
                    "lv_busbar_to_lv_feeder",
                    lv_busbar_id,
                    f"feeder_F{feeder_index:02d}_port",
                    lv_feeder_id,
                    "busbar_port",
                    feeder_index=feeder_index,
                ),
                _edge(
                    f"{feeder_token}-E-LVFEEDER-PCS",
                    "lv_feeder_to_pcs",
                    lv_feeder_id,
                    "pcs_port",
                    pcs_id,
                    "ac_port",
                    feeder_index=feeder_index,
                ),
                _edge(
                    f"{feeder_token}-E-PCS-DCIF",
                    "pcs_to_dc_interface",
                    pcs_id,
                    "dc_port",
                    dc_interface_id,
                    "pcs_port",
                    feeder_index=feeder_index,
                ),
            ]
        )

        for local_block_index in range(1, (0 if shared_dc_mode else int(dc_blocks_for_feeder)) + 1):
            dc_block_ordinal += 1
            dc_block_id = f"{feeder_token}-DC-BLOCK-{local_block_index:02d}"
            nodes.append(
                SldV2Node(
                    node_id=dc_block_id,
                    node_type="dc_block",
                    display_name=f"DC Block #{dc_block_ordinal}",
                    equipment_id=dc_block_id,
                    feeder_index=feeder_index,
                    dc_block_index=dc_block_ordinal,
                    ports=[
                        _port(
                            "input_port",
                            "DC Input",
                            "input",
                            "top",
                            "dc",
                            feeder_index=feeder_index,
                            dc_block_index=dc_block_ordinal,
                        )
                    ],
                    attributes={
                        "local_block_index": local_block_index,
                        "dc_block_energy_mwh": summary.dc_block_energy_mwh,
                        "dc_block_voltage_v": summary.dc_block_voltage_v,
                    },
                )
            )
            edges.append(
                _edge(
                    f"{dc_block_id}-E-DCIF-BLOCK",
                    "dc_interface_to_dc_block",
                    dc_interface_id,
                    "block_port",
                    dc_block_id,
                    "input_port",
                    feeder_index=feeder_index,
                    dc_block_index=dc_block_ordinal,
                    attributes={"local_block_index": local_block_index},
                )
            )

    if shared_dc_mode:
        for span in block_feeder_spans:
            dc_block_ordinal += 1
            anchor_feeder = span[0]
            dc_block_id = f"{group_token}-DC-BLOCK-{dc_block_ordinal:02d}"
            nodes.append(
                SldV2Node(
                    node_id=dc_block_id,
                    node_type="dc_block",
                    display_name=f"DC Block #{dc_block_ordinal}",
                    equipment_id=dc_block_id,
                    feeder_index=anchor_feeder,
                    dc_block_index=dc_block_ordinal,
                    ports=[
                        _port(
                            "input_port",
                            "DC Input",
                            "input",
                            "top",
                            "dc",
                            feeder_index=anchor_feeder,
                            dc_block_index=dc_block_ordinal,
                        )
                    ],
                    attributes={
                        "local_block_index": dc_block_ordinal,
                        "dc_block_energy_mwh": summary.dc_block_energy_mwh,
                        "dc_block_voltage_v": summary.dc_block_voltage_v,
                        "feeder_span": list(span),
                    },
                )
            )
            for feeder_index in span:
                edges.append(
                    _edge(
                        f"{group_token}-F{feeder_index:02d}-E-DCIF-BLOCK",
                        "dc_interface_to_dc_block",
                        f"{group_token}-F{feeder_index:02d}-DC-INTERFACE",
                        "block_port",
                        dc_block_id,
                        "input_port",
                        feeder_index=feeder_index,
                        dc_block_index=dc_block_ordinal,
                        attributes={"shared_dc_block": True},
                    )
                )

    return SldEngineeringV2Graph(
        run_id=topology.run_id,
        project_name=topology.project_name,
        scenario_id=topology.scenario_id,
        validation_mode=topology.validation_mode,
        source_topology_hash=_topology_hash(topology),
        labels=topology.labels,
        equipment_ratings=topology.equipment_ratings,
        summary=topology.summary,
        nodes=nodes,
        edges=edges,
    )
