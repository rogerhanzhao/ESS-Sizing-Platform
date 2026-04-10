# DOCX Report Export Implementation Guide

## Overview

This document provides step-by-step implementation instructions for the remaining DOCX report generation fixes:
1. **Efficiency Chain Consistency & Validation**
2. **AC Sizing Table Deduplication**
3. **SLD/Layout Image Embedding**

---

## 1. Efficiency Chain Consistency & Validation

### Current Issue
The efficiency chain table in the exported DOCX may show:
- `Total Efficiency (one-way)` that doesn't match product of components
- Missing footnote about auxiliary load exclusion
- Inconsistent data source (may not come from DC SIZING module)

### Implementation Steps

#### 1.1 Create Validation Function

**File**: `calb_sizing_tool/reporting/validator.py` (NEW)

```python
def validate_efficiency_chain(dc_results: dict, tolerance: float = 0.001) -> tuple:
    """
    Validate that efficiency chain is internally consistent.
    
    Returns:
        (is_valid: bool, error_message: str or None)
    """
    try:
        components = {
            'dc_cables': dc_results.get('efficiency_dc_cables', 0.0),
            'pcs': dc_results.get('efficiency_pcs', 0.0),
            'transformer': dc_results.get('efficiency_transformer', 0.0),
            'rmu_switchgear': dc_results.get('efficiency_rmu_switchgear', 0.0),
            'hvt_others': dc_results.get('efficiency_hvt_others', 0.0),
        }
        
        # Calculate product of components
        product = 1.0
        for component, value in components.items():
            if value is None or value <= 0:
                continue
            # Handle both fraction (0.97) and percentage (97%) formats
            frac = value if value <= 1.2 else value / 100.0
            product *= frac
        
        # Compare with reported total
        total_reported = dc_results.get('efficiency_total', 1.0)
        total_reported_frac = total_reported if total_reported <= 1.2 else total_reported / 100.0
        
        if abs(product - total_reported_frac) > tolerance:
            return False, (
                f"Efficiency chain mismatch: "
                f"product={product:.4f} vs reported={total_reported_frac:.4f}"
            )
        
        return True, None
        
    except Exception as e:
        return False, str(e)
```

#### 1.2 Update Report Context

**File**: `calb_sizing_tool/reporting/report_context.py`

Ensure `ReportContext` includes efficiency data directly from DC results:

```python
class DCResultsSummary:
    """DC Sizing results summary"""
    
    # ... existing fields ...
    
    # Efficiency Chain (One-Way, No Auxiliary)
    efficiency_dc_cables: float = 0.97
    efficiency_pcs: float = 0.97
    efficiency_transformer: float = 0.985
    efficiency_rmu_switchgear: float = 0.98
    efficiency_hvt_others: float = 0.98
    efficiency_total: float = 0.9674
    
    @property
    def efficiency_chain_dict(self) -> dict:
        """Return efficiency chain as dict for reporting"""
        return {
            'DC Cables': self.efficiency_dc_cables,
            'PCS': self.efficiency_pcs,
            'Transformer': self.efficiency_transformer,
            'RMU / Switchgear / AC Cables': self.efficiency_rmu_switchgear,
            'HVT / Others': self.efficiency_hvt_others,
            'Total Efficiency (one-way)': self.efficiency_total,
        }
```

#### 1.3 Update Report Export

**File**: `calb_sizing_tool/reporting/report_v2.py`

```python
def _add_efficiency_chain_section(doc: Document, dc_results: dict):
    """
    Add Efficiency Chain (one-way) section to report.
    Data sourced from DC SIZING module.
    """
    from calb_sizing_tool.reporting.validator import validate_efficiency_chain
    
    doc.add_heading('Efficiency Chain (one-way)', level=2)
    
    # Validate before rendering
    is_valid, error_msg = validate_efficiency_chain(dc_results)
    if not is_valid:
        doc.add_paragraph(f"⚠️ WARNING: {error_msg}", style='List Bullet')
        # Log error for debugging
        print(f"[ERROR] Efficiency validation failed: {error_msg}")
    
    # Build table
    rows = []
    headers = ['Component', 'Value']
    
    efficiency_chain = {
        'DC Cables': format_percent(dc_results.get('efficiency_dc_cables', 0.97)),
        'PCS': format_percent(dc_results.get('efficiency_pcs', 0.97)),
        'Transformer': format_percent(dc_results.get('efficiency_transformer', 0.985)),
        'RMU / Switchgear / AC Cables': format_percent(
            dc_results.get('efficiency_rmu_switchgear', 0.98)
        ),
        'HVT / Others': format_percent(dc_results.get('efficiency_hvt_others', 0.98)),
        'Total Efficiency (one-way)': format_percent(
            dc_results.get('efficiency_total', 0.9674)
        ),
    }
    
    for component, value in efficiency_chain.items():
        rows.append([component, value])
    
    _add_table(doc, rows, headers)
    
    # Add footnote
    doc.add_paragraph(
        "Note: Efficiency figures exclude auxiliary loads (HVAC, lighting, etc.). "
        "All power and energy calculations use this efficiency profile.",
        style='Normal'
    )
    doc.add_paragraph('')  # Spacing

def _add_dc_power_required(doc: Document, dc_results: dict, inputs: dict):
    """
    Calculate and add DC Power Required, based on POI Power and Efficiency.
    
    DC Power Required = POI Power / Total Efficiency
    """
    poi_power_mw = inputs.get('poi_power_mw', 0.0)
    total_efficiency = dc_results.get('efficiency_total', 0.9674)
    
    # Handle percentage vs fraction
    if total_efficiency > 1.2:
        total_efficiency /= 100.0
    
    if poi_power_mw > 0 and total_efficiency > 0:
        dc_power_mw = poi_power_mw / total_efficiency
        doc.add_paragraph(f"DC Power Required: {dc_power_mw:.2f} MW")
    else:
        doc.add_paragraph("DC Power Required: TBD")
```

---

## 2. AC Sizing Table Deduplication

### Current Issue
AC Sizing section lists every AC Block individually, creating long repetitive tables.

### Implementation Steps

#### 2.1 Create Aggregation Function

**File**: `calb_sizing_tool/reporting/ac_aggregator.py` (NEW)

```python
from typing import List, Dict
from dataclasses import dataclass

@dataclass
class ACBlockConfig:
    """Configuration signature for an AC Block"""
    pcs_count: int
    pcs_kw: int
    pcs_voltage: float
    transformer_kva: float
    transformer_voltage_ratio: str  # e.g., "690V / 33kV"
    feeder_count: int
    
    def signature(self) -> str:
        """Unique hash of this configuration"""
        return (
            f"{self.pcs_count}x{self.pcs_kw}kW_"
            f"{self.transformer_kva}kVA_{self.transformer_voltage_ratio}_"
            f"F{self.feeder_count}"
        )

def aggregate_ac_blocks(ac_results: dict) -> List[Dict]:
    """
    Aggregate AC Block configurations by signature.
    
    Input ac_results structure:
    {
        'ac_blocks': [
            {
                'block_id': 1,
                'pcs_count': 2,
                'pcs_kw': 2500,
                'pcs_voltage': 690,
                'transformer_kva': 5000,
                'transformer_voltage_ratio': '690V / 33kV',
                'feeder_count': 4,
                ...
            },
            ... (more blocks with same config)
        ]
    }
    
    Returns:
    [
        {
            'config_type': '2×2500kW PCS + 5MVA Transformer',
            'qty': 3,  # Number of AC Blocks with this config
            'pcs_count': 2,
            'pcs_kw': 2500,
            'total_kw_per_block': 5000,
            'transformer_kva': 5000,
            'transformer_voltage': '690V / 33kV',
            'feeder_count': 4,
            'has_exceptions': False,
        }
    ]
    """
    
    config_map = {}  # signature -> list of blocks
    
    ac_blocks = ac_results.get('ac_blocks', [])
    for block in ac_blocks:
        config = ACBlockConfig(
            pcs_count=block.get('pcs_count', 2),
            pcs_kw=block.get('pcs_kw', 2500),
            pcs_voltage=block.get('pcs_voltage', 690.0),
            transformer_kva=block.get('transformer_kva', 5000.0),
            transformer_voltage_ratio=block.get('transformer_voltage_ratio', '690V / 33kV'),
            feeder_count=block.get('feeder_count', 4),
        )
        sig = config.signature()
        
        if sig not in config_map:
            config_map[sig] = {
                'config': config,
                'blocks': []
            }
        config_map[sig]['blocks'].append(block)
    
    # Build output
    result = []
    for sig, data in config_map.items():
        config = data['config']
        block_count = len(data['blocks'])
        
        result.append({
            'config_type': (
                f"{config.pcs_count}×{config.pcs_kw}kW "
                f"{config.transformer_kva:.0f}kVA Transformer"
            ),
            'qty': block_count,
            'pcs_count': config.pcs_count,
            'pcs_kw': config.pcs_kw,
            'total_kw_per_block': config.pcs_count * config.pcs_kw,
            'transformer_kva': config.transformer_kva,
            'transformer_voltage': config.transformer_voltage_ratio,
            'feeder_count': config.feeder_count,
            'block_ids': [b.get('block_id', i) for i, b in enumerate(data['blocks'])],
        })
    
    return sorted(result, key=lambda x: (-x['qty'], -x['total_kw_per_block']))
```

#### 2.2 Update Report to Use Aggregation

**File**: `calb_sizing_tool/reporting/report_v2.py`

```python
def _add_ac_sizing_section(doc: Document, ac_results: dict, ac_config: dict):
    """
    Add AC Sizing section with deduplicated configurations.
    """
    from calb_sizing_tool.reporting.ac_aggregator import aggregate_ac_blocks
    
    doc.add_heading('AC Sizing', level=2)
    
    # Add summary
    total_ac_blocks = ac_config.get('total_ac_blocks', 0)
    total_ac_power = ac_config.get('total_ac_power_mw', 0.0)
    doc.add_paragraph(
        f"Total AC Blocks: {total_ac_blocks} | "
        f"Total AC Power: {total_ac_power:.2f} MW"
    )
    
    # Aggregate configurations
    aggregated = aggregate_ac_blocks(ac_results)
    
    if not aggregated:
        doc.add_paragraph("No AC configuration data available.")
        return
    
    # Build table
    rows = []
    headers = [
        'Configuration Type',
        'Qty (Blocks)',
        'PCS per Block',
        'Power per Block (MW)',
        'Transformer (kVA)',
        'Feeders'
    ]
    
    for config in aggregated:
        rows.append([
            config['config_type'],
            str(config['qty']),
            str(config['pcs_count']),
            f"{config['total_kw_per_block'] / 1000:.2f}",
            f"{config['transformer_kva']:.0f}",
            str(config['feeder_count']),
        ])
    
    _add_table(doc, rows, headers)
    
    # Add note if there are variations
    if len(aggregated) > 1:
        doc.add_paragraph(
            f"Note: {len(aggregated)} different AC Block configuration types detected. "
            "The above table aggregates blocks with identical electrical parameters.",
            style='Normal'
        )
```

---

## 3. SLD & Layout Image Embedding

### Current Issue
Exported DOCX does not include SLD and Layout diagram images.

### Implementation Steps

#### 3.1 Add Image Embedding Function

**File**: `calb_sizing_tool/reporting/export_docx.py`

```python
from pathlib import Path
from docx.shared import Inches

def _add_sld_and_layout_images(doc: Document, outputs_dir: str = "outputs"):
    """
    Embed latest SLD and Layout images into DOCX report.
    """
    doc.add_page_break()
    doc.add_heading('Single Line Diagram (SLD)', level=1)
    
    sld_png = Path(outputs_dir) / "sld_latest.png"
    if sld_png.exists():
        doc.add_paragraph("Engineering-readable Single Line Diagram for AC Block group:")
        doc.add_picture(str(sld_png), width=Inches(6.0))
    else:
        doc.add_paragraph(
            "SLD not generated. Please complete the 'Single Line Diagram' page to generate this diagram.",
            style='List Bullet'
        )
    
    doc.add_page_break()
    doc.add_heading('Site Layout (Top View)', level=1)
    
    layout_png = Path(outputs_dir) / "layout_latest.png"
    if layout_png.exists():
        doc.add_paragraph("Physical site layout showing DC and AC Block container placement:")
        doc.add_picture(str(layout_png), width=Inches(6.0))
    else:
        doc.add_paragraph(
            "Layout not generated. Please complete the 'Site Layout' page to generate this diagram.",
            style='List Bullet'
        )

def create_combined_report_v2(
    dc_output: dict,
    ac_output: dict,
    inputs: dict,
    ac_config: dict,
    outputs_dir: str = "outputs"
) -> bytes:
    """
    Generate complete technical proposal DOCX (V2.1).
    """
    doc = Document()
    
    # ... (existing sections) ...
    
    # Add diagrams at end
    _add_sld_and_layout_images(doc, outputs_dir)
    
    # Convert to bytes
    return _doc_to_bytes(doc)
```

#### 3.2 Update Export Entry Point

**File**: `calb_sizing_tool/ui/report_export_view.py`

```python
def export_combined_report(dc_output, ac_output, inputs, ac_config):
    """
    Export combined technical proposal (V2.1 only).
    """
    from calb_sizing_tool.reporting.report_v2 import create_combined_report_v2
    
    try:
        docx_bytes = create_combined_report_v2(
            dc_output=dc_output,
            ac_output=ac_output,
            inputs=inputs,
            ac_config=ac_config,
            outputs_dir="outputs"  # Must match where SLD/Layout are saved
        )
        
        filename = f"CALB_ESS_Proposal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.docx"
        
        st.download_button(
            label="📥 Download Technical Proposal (DOCX)",
            data=docx_bytes,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        
        st.success("✅ Report generated successfully!")
        
    except Exception as e:
        st.error(f"❌ Report generation failed: {str(e)}")
        st.write(traceback.format_exc())
```

---

## 4. Testing Strategy

### Unit Tests

**File**: `tests/test_report_export_fixes.py`

```python
import pytest
from calb_sizing_tool.reporting.validator import validate_efficiency_chain
from calb_sizing_tool.reporting.ac_aggregator import aggregate_ac_blocks

def test_efficiency_chain_validation_pass():
    """Valid efficiency chain should pass"""
    dc_results = {
        'efficiency_dc_cables': 0.97,
        'efficiency_pcs': 0.97,
        'efficiency_transformer': 0.985,
        'efficiency_rmu_switchgear': 0.98,
        'efficiency_hvt_others': 0.98,
        'efficiency_total': 0.9674,  # Product of above
    }
    is_valid, msg = validate_efficiency_chain(dc_results)
    assert is_valid, f"Validation failed: {msg}"

def test_efficiency_chain_validation_fail():
    """Inconsistent efficiency chain should fail"""
    dc_results = {
        'efficiency_dc_cables': 0.97,
        'efficiency_pcs': 0.97,
        'efficiency_transformer': 0.985,
        'efficiency_rmu_switchgear': 0.98,
        'efficiency_hvt_others': 0.98,
        'efficiency_total': 0.95,  # Wrong!
    }
    is_valid, msg = validate_efficiency_chain(dc_results)
    assert not is_valid, "Should have failed validation"

def test_ac_aggregation():
    """AC Blocks with same config should aggregate"""
    ac_results = {
        'ac_blocks': [
            {
                'block_id': 1,
                'pcs_count': 2,
                'pcs_kw': 2500,
                'pcs_voltage': 690,
                'transformer_kva': 5000,
                'transformer_voltage_ratio': '690V / 33kV',
                'feeder_count': 4,
            },
            {
                'block_id': 2,
                'pcs_count': 2,
                'pcs_kw': 2500,
                'pcs_voltage': 690,
                'transformer_kva': 5000,
                'transformer_voltage_ratio': '690V / 33kV',
                'feeder_count': 4,
            },
            {
                'block_id': 3,
                'pcs_count': 4,
                'pcs_kw': 1250,
                'pcs_voltage': 690,
                'transformer_kva': 5000,
                'transformer_voltage_ratio': '690V / 33kV',
                'feeder_count': 4,
            }
        ]
    }
    
    aggregated = aggregate_ac_blocks(ac_results)
    
    assert len(aggregated) == 2, "Should have 2 unique configurations"
    assert aggregated[0]['qty'] == 2, "First config should have qty=2"
    assert aggregated[1]['qty'] == 1, "Second config should have qty=1"
```

### Integration Test

```python
def test_full_docx_generation_flow():
    """End-to-end DOCX generation with all fixes"""
    
    # Setup test data
    dc_output = load_test_dc_sizing_output()
    ac_output = load_test_ac_sizing_output()
    inputs = load_test_inputs()
    ac_config = load_test_ac_config()
    
    # Generate DOCX
    from calb_sizing_tool.reporting.report_v2 import create_combined_report_v2
    docx_bytes = create_combined_report_v2(
        dc_output, ac_output, inputs, ac_config, outputs_dir="test_outputs"
    )
    
    # Validate DOCX content
    doc = Document(io.BytesIO(docx_bytes))
    full_text = '\n'.join([p.text for p in doc.paragraphs])
    
    # Check 1: Efficiency chain present and validated
    assert "Efficiency Chain (one-way)" in full_text
    assert "exclude auxiliary" in full_text
    
    # Check 2: AC aggregation (fewer rows than blocks)
    ac_blocks_count = len(ac_output.get('ac_blocks', []))
    ac_table_rows = count_table_rows(doc, "Configuration Type")
    assert ac_table_rows <= ac_blocks_count, "Aggregation should reduce rows"
    
    # Check 3: SLD/Layout images embedded
    assert len(doc.inline_shapes) >= 2, "Should have at least 2 images"
```

---

## Summary Checklist

- [ ] Create `calb_sizing_tool/reporting/validator.py` with efficiency chain validation
- [ ] Create `calb_sizing_tool/reporting/ac_aggregator.py` with AC block aggregation
- [ ] Update `calb_sizing_tool/reporting/report_context.py` with efficiency fields
- [ ] Update `calb_sizing_tool/reporting/report_v2.py` with validation calls and aggregation
- [ ] Update `calb_sizing_tool/reporting/export_docx.py` with image embedding function
- [ ] Update `calb_sizing_tool/ui/report_export_view.py` to use new functions
- [ ] Add unit tests in `tests/test_report_export_fixes.py`
- [ ] Add integration test for full DOCX generation
- [ ] Run full test suite and verify no regressions
- [ ] Manual smoke test: Export report and validate all sections

---

**Implementation Status**: 🔄 **READY FOR DEVELOPMENT**  
**Estimated Effort**: 4–6 hours (implementation + testing)  
**Dependencies**: None (all modules can be developed in parallel)
