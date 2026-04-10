# Quick Start: PCS 2000 kW & Custom Rating

## What's New? 🎉

✨ **2000 kW PCS Rating** - New standard option  
✨ **Custom PCS Input** - Use any rating 1000-5000 kW  

## 5-Second Setup

### Standard Configuration (2000 kW)
1. AC Sizing page → Select "2 × 2000 kW = 4000 kW"
2. Container: Auto-selects **20ft** (4.0 MW per block)
3. Run AC Sizing → Done!

### Custom Configuration
1. AC Sizing page → Select "🔧 Custom PCS Rating..."
2. Enter: **PCS Count** (1-6) and **PCS Rating** (1000-5000 kW)
3. Container: Auto-selects **20ft or 40ft** based on power
4. Run AC Sizing → Done!

## Examples

### Example 1: Standard 2000 kW
```
Choose: 2 × 2000 kW
Result: 4.0 MW per block → 20ft container
Total: 4 blocks = 16 MW system
```

### Example 2: Custom Mid-Range
```
Choose: Custom PCS Rating
Enter: 3 PCS × 1800 kW
Result: 5.4 MW per block → 40ft container
```

### Example 3: Large Custom
```
Choose: Custom PCS Rating
Enter: 4 PCS × 2000 kW
Result: 8.0 MW per block → 40ft container
```

## Container Rules

```
Single AC Block Power = (PCS Count) × (PCS Rating) / 1000

If Power ≤ 5.0 MW → 20ft  ✅
If Power > 5.0 MW → 40ft  ✅
```

## All 5 Standard Ratings

| Rating | 2-PCS | 4-PCS | Notes |
|--------|-------|-------|-------|
| 1250kW | 2.5MW | 5.0MW | Smallest |
| 1500kW | 3.0MW | 6.0MW | Mid-range |
| 1725kW | 3.45MW | 6.9MW | Optimized |
| **2000kW** | **4.0MW** | **8.0MW** | **NEW ✨** |
| 2500kW | 5.0MW | 10.0MW | Largest |

## Validation Warnings

⚠️ **Power Overhead > 30%**  
↳ Solution: Try smaller PCS rating or fewer units

⚠️ **Insufficient Power**  
↳ Solution: Increase PCS rating or count

⚠️ **Excess Energy**  
↳ Solution: Return to DC Sizing, reduce DC blocks

## Tips

1. Start with standard ratings for most projects
2. Use custom only when standard doesn't fit exactly
3. Watch the container size (20ft vs 40ft affects cost)
4. Warnings help you optimize - don't ignore them!

## Troubleshooting

**Custom input won't accept value?**  
- PCS Count: Must be 1-6
- PCS Rating: Must be 1000-5000, step 100

**Container showing wrong size?**  
- Check single block power = (PCS Count × PCS Rating) / 1000
- Compare to 5.0 MW boundary

**Getting validation errors?**  
- Read the error message carefully
- Adjust PCS config or DC blocks accordingly

## Still Using Old Configs?

No problem! All existing AC Block configurations:
- ✅ Still work
- ✅ Still recommended
- ✅ Continue to be suggested
- ✅ No changes to your saved projects

---

**Need more help?** See `PCS_RATING_GUIDE.md` for detailed documentation.
