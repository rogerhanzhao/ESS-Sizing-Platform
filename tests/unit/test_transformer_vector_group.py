from __future__ import annotations

import pytest

from calb_sizing_tool.sld.transformer_vector_group import (
    TransformerVectorGroupError,
    parse_transformer_vector_group,
)


@pytest.mark.parametrize(
    ("vector_group", "lv_winding_count", "expected_hv", "expected_lv"),
    [
        ("Dyn11", 1, "D", ("yn11",)),
        ("Dy11y11", 2, "D", ("y11", "y11")),
        ("Dy11-y11", 2, "D", ("y11", "y11")),
        ("YNd11y0", 2, "YN", ("d11", "y0")),
    ],
)
def test_parse_transformer_vector_group_requires_one_token_per_lv_winding(
    vector_group,
    lv_winding_count,
    expected_hv,
    expected_lv,
):
    result = parse_transformer_vector_group(
        vector_group,
        lv_winding_count=lv_winding_count,
    )

    assert result.hv_token == expected_hv
    assert result.lv_tokens == expected_lv


@pytest.mark.parametrize(
    ("vector_group", "lv_winding_count"),
    [
        ("Dyn11", 2),
        ("Dy11y11", 1),
        ("Dnot-a-vector", 1),
        ("", 1),
    ],
)
def test_parse_transformer_vector_group_rejects_ambiguous_or_invalid_topology(
    vector_group,
    lv_winding_count,
):
    with pytest.raises(TransformerVectorGroupError):
        parse_transformer_vector_group(
            vector_group,
            lv_winding_count=lv_winding_count,
        )
