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

import pandas as pd

def load_dc_data(data_path: str):
    """
    Load DC Block related data from Data Dictionary.
    """
    return pd.read_excel(data_path, sheet_name=None)

def calculate_dc_energy(dc_params: dict, profile: list):
    """
    Compute DC energy deliverable based on profile and DC Block params.
    """
    # Example placeholder; replace with actual logic.
    total_energy = dc_params.get("capacity_nominal", 0)
    delivered = sum(profile) / len(profile) * total_energy
    return delivered

def dc_rte_calculation(dc_params: dict):
    """
    Compute DC round-trip efficiency.
    """
    # Placeholder formula for illustration.
    return dc_params.get("rte_dc", 0.94)

