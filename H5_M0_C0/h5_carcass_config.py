# -*- coding: utf-8 -*-
"""Clean carcass routing metadata for H5_M0_C0."""

CARCASS_ID = "H5_M0_C0"

PROFILES = {
    "HARD_2M3W0S": {
        "quota": 9,
        "supported_modes": ("MODE_A", "MODE_B", "MODE_C"),
        "closed_modes": ("MODE_B", "MODE_C"),
        "active_runtime_modes": ("MODE_B", "MODE_C"),
        "not_ready_modes": ("MODE_A",),
        "mode_weights": {"MODE_B": 1.0, "MODE_C": 1.0},
        "notes": "Real runtime modes for HARD_2M3W0S are MODE_B/MODE_C. MODE_A is not ready.",
    },
    "HARD_2M2W1S": {
        "quota": 9,
        "supported_modes": ("MODE_A", "MODE_B", "MODE_C"),
        "closed_modes": ("MODE_B",),
        "active_runtime_modes": ("MODE_B",),
        "not_ready_modes": ("MODE_A", "MODE_C"),
        "mode_weights": {"MODE_B": 1.0},
        "notes": "Current self-series of HARD_2M2W1S is MODE_B only. MODE_A/MODE_C are not ready.",
    },
}
