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

import graphviz
import networkx as nx

def render_sld(graph: nx.DiGraph) -> graphviz.Digraph:
    dot = graphviz.Digraph(comment='ESS SLD')
    dot.attr(rankdir='TB', splines='ortho')
    dot.attr(nodesep='0.6', ranksep='0.8')
    
    # Style definitions
    styles = {
        "POI":     {"shape": "doublecircle", "style": "filled", "fillcolor": "#FFD700", "fontname": "Helvetica"},
        "TRAFO":   {"shape": "trapezium",    "style": "filled", "fillcolor": "#87CEEB", "fontname": "Helvetica"},
        "PCS":     {"shape": "box",          "style": "filled", "fillcolor": "#98FB98", "fontname": "Helvetica"},
        "BATTERY": {"shape": "cylinder",     "style": "filled", "fillcolor": "#FFA07A", "fontname": "Helvetica"},
    }

    # Add nodes
    for n, attrs in graph.nodes(data=True):
        ntype = attrs.get("type", "DEFAULT")
        s = styles.get(ntype, {})
        label = attrs.get("label", str(n))
        dot.node(n, label=label, **s)

    # Add edges
    for u, v, attrs in graph.edges(data=True):
        etype = attrs.get("type", "AC")
        color = "red" if etype == "DC" else "black"
        width = "2.0" if etype == "AC_HV" else "1.0"
        dot.edge(u, v, color=color, penwidth=width)

    return dot

