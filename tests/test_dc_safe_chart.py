from __future__ import annotations

import pandas as pd

from calb_sizing_tool.ui.dc_view import _plot_poi_usable_png


def test_poi_usable_chart_renders_to_png_without_streamlit_arrow() -> None:
    chart = _plot_poi_usable_png(
        pd.DataFrame(
            {
                "Year_Index": [0, 1, 2],
                "POI_Usable_Energy_MWh": [100.0, 96.0, 92.0],
            }
        ),
        poi_target=90.0,
        title="POI Usable Energy by Year",
    )

    assert chart.getvalue().startswith(b"\x89PNG\r\n\x1a\n")
