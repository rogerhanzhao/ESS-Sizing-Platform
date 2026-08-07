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

"""SLD support modules.

This package re-exported an entire pypowsybl / IIDM SLD stack — snapshot
builders, an IIDM network builder, a QC pass, renderers and an SVG template.
None of it had a product consumer: it was superseded by the engineering_v2
pipeline in calb_diagrams, and its only two tests had been SKIPPED all along
because pypowsybl is not a dependency of this project. Retired 2026-08-06.

What remains is imported directly by the modules that need it — voltage_contract,
transformer_vector_group and standard_transformer_impedance — so this file
deliberately re-exports nothing.
"""
