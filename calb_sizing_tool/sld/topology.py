# -----------------------------------------------------------------------------
# Personal Open-Source Notice
#
# Copyright (c) 2026 Alex.Zhao. All rights reserved.
#
# This repository is released under the MIT License (see LICENSE file).
# Intended use: learning, evaluation, and engineering reference for Utility-scale
# BESS/ESS sizing and Reporting workflows.
#
# DISCLAIMER: This software is provided "AS IS", without warranty of any kind,
# express or implied. In no event shall the author(s) be liable for any claim,
# damages, or other liability arising from, out of, or in connection with the
# software or the use or other dealings in the software.
#
# NOTE: This is a personal project. It is not an official product or statement
# of any company or organization.
# -----------------------------------------------------------------------------

import networkx as nx
from calb_sizing_tool.models import ProjectSizingResult

class ElectricalTopology:
    def __init__(self, sizing_data: ProjectSizingResult):
        self.data = sizing_data
        self.graph = nx.DiGraph()
        self._build_network()

    def _build_network(self):
        # 1. Root node (POI)
        poi_id = "POI"
        self.graph.add_node(
            poi_id, 
            type="POI", 
            label=f"POI\n{self.data.total_power_mw:.1f} MW"
        )

        # 2. Traverse AC blocks
        for i, ac in enumerate(self.data.ac_blocks):
            # Transformer
            trafo_id = f"Trafo_{i+1}"
            trafo_label = f"Trafo {i+1}\n{ac.mv_voltage_kv}/{ac.lv_voltage_v/1000}kV"
            self.graph.add_node(trafo_id, type="TRAFO", label=trafo_label)
            self.graph.add_edge(poi_id, trafo_id, type="AC_HV", label=f"{ac.mv_voltage_kv}kV")

            # PCS
            for p in range(ac.num_pcs):
                pcs_id = f"T{i+1}_PCS_{p+1}"
                pcs_label = f"PCS\n{ac.pcs_power_kw} kW"
                self.graph.add_node(pcs_id, type="PCS", label=pcs_label)
                self.graph.add_edge(trafo_id, pcs_id, type="AC_LV", label="AC Bus")

                # Battery (DC)
                # Simplified logic: assume each PCS connects to one or more battery clusters
                dc_block = self.data.dc_blocks[i] if i < len(self.data.dc_blocks) else None
                if dc_block:
                    bat_id = f"{pcs_id}_BAT"
                    bat_label = f"Cluster Group\n{dc_block.racks_per_cluster} Racks\n{dc_block.battery_voltage_v}V"
                    self.graph.add_node(bat_id, type="BATTERY", label=bat_label)
                    self.graph.add_edge(pcs_id, bat_id, type="DC", label="DC Bus")

    def get_graph(self):
        return self.graph

