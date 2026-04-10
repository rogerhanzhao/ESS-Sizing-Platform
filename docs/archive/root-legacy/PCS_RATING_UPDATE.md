# PCS Rating Enhancement - 2000 kW Support & Custom Input

## Summary
Added support for 2000 kW PCS rating alongside existing 1250, 1500, 1725, 2500 kW options, plus a new custom PCS rating input modal for flexibility in AC sizing configurations.

## Changes Made

### 1. **ac_sizing_config.py** - Updated Standard PCS Configurations

#### Added `is_custom` field to PCSRecommendation
```python
@dataclass
class PCSRecommendation:
    pcs_count: int      # PCS quantity per AC Block (2 or 4)
    pcs_kw: int         # PCS rating in kW: 1250, 1500, 1725, 2000, 2500
    total_kw: int       # Total power per AC Block
    is_custom: bool = False  # Flag for custom configurations
```

#### Updated PCS Configuration Lists
- **2 PCS per AC Block**: Now includes 2 × 2000 kW = 4000 kW option
  - 2 × 1250 kW = 2500 kW
  - 2 × 1500 kW = 3000 kW
  - 2 × 1725 kW = 3450 kW
  - **2 × 2000 kW = 4000 kW** ✨ NEW
  - 2 × 2500 kW = 5000 kW

- **4 PCS per AC Block**: Now includes 4 × 2000 kW = 8000 kW option
  - 4 × 1250 kW = 5000 kW
  - 4 × 1500 kW = 6000 kW
  - 4 × 1725 kW = 6900 kW
  - **4 × 2000 kW = 8000 kW** ✨ NEW
  - 4 × 2500 kW = 10000 kW

#### Standard Ratings Array
Confirmed inclusion of 2000 kW in standard ratings list:
```python
standard_ratings = [1000, 1250, 1500, 1725, 2000, 2500, 3000, 3500, 4000, 4500, 5000]
```

### 2. **ac_view.py** - Enhanced PCS Selection UI

#### New Custom PCS Rating Modal
- Replaced "Override with custom PCS rating?" checkbox with dropdown option
- Added "🔧 Custom PCS Rating..." option at end of recommendations list
- When selected, displays two input fields for manual configuration:
  - **PCS Count per AC Block**: Range 1-6 PCS per block
  - **PCS Rating (kW)**: Range 1000-5000 kW, step 100 kW

#### Implementation Details
```python
pcs_options = [f"{rec.readable}" for rec in selected_option.pcs_recommendations]
pcs_options.append("🔧 Custom PCS Rating...")

if pcs_choice >= len(selected_option.pcs_recommendations):
    # Custom input section
    pcs_per_ac = st.number_input("PCS Count per AC Block", 1, 6, 2, 1)
    pcs_kw = st.number_input("PCS Rating (kW)", 1000, 5000, 1500, 100)
else:
    # Use recommendation
    chosen_rec = selected_option.pcs_recommendations[pcs_choice]
    pcs_per_ac = chosen_rec.pcs_count
    pcs_kw = chosen_rec.pcs_kw
```

#### Container Size Logic
Container type is determined per single AC Block power:
- **20ft container**: Single AC Block ≤ 5.0 MW
- **40ft container**: Single AC Block > 5.0 MW

Example with 2000 kW PCS:
- 2 × 2000 kW = 4.0 MW → 20ft container
- 4 × 2000 kW = 8.0 MW → 40ft container

## Backward Compatibility

✅ **Fully backward compatible**
- All existing 1250, 1500, 1725, 2500 kW configurations remain unchanged
- Existing sizing logic and calculations unaffected
- No breaking changes to APIs or data models
- Custom input is optional; recommended configurations still available

## Testing Recommendations

### UI Testing
1. Navigate to AC Sizing page after DC Sizing
2. Select different DC:AC ratios (1:1, 1:2, 1:4)
3. Verify 2000 kW option appears in both 2-PCS and 4-PCS configurations
4. Select "🔧 Custom PCS Rating..." option
5. Enter custom values (e.g., 3 PCS × 1800 kW)
6. Verify container size calculation is correct for different AC block powers

### Validation Testing
- Insufficient power: Should warn if total AC power < POI requirement
- Excessive overhead: Should warn if overhead > 30% of POI requirement
- Energy validation: Should check DC energy meets MWh requirement

## Example Configurations Now Available

| Ratio | PCS Count | PCS Rating | Total AC Power | Container |
|-------|-----------|-----------|-----------------|-----------|
| 1:1   | 2 × 2000  | 4.0 MW    | 20ft            | ✅ |
| 1:1   | 4 × 2000  | 8.0 MW    | 40ft            | ✅ |
| 1:2   | 2 × 2000  | 4.0 MW    | 20ft            | ✅ |
| 1:2   | 4 × 2000  | 8.0 MW    | 40ft            | ✅ |
| 1:4   | 2 × 2000  | 4.0 MW    | 20ft            | ✅ |
| 1:4   | 4 × 2000  | 8.0 MW    | 40ft            | ✅ |
| Custom| 3 × 1800  | 5.4 MW    | 40ft            | ✅ |
| Custom| Any valid | Any range | Auto-determined | ✅ |

## Deployment Notes

1. No database migrations required
2. No configuration file updates needed
3. Changes are self-contained in UI and config modules
4. Staging logic and calculation engines remain unchanged
5. Report exports automatically adapt to selected PCS ratings

## Files Modified

- `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/ui/ac_sizing_config.py`
- `/opt/calb/prod/CALB_SIZINGTOOL/calb_sizing_tool/ui/ac_view.py`

## Future Enhancements

Potential additions:
- Save custom configurations as user presets
- Historical tracking of custom configurations used
- Advanced power factor / reactive power considerations for custom PCS ratings
- Integration with equipment database for live PCS availability
