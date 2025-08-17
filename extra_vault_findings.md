# Extra Vault Analysis - Key Findings

## Executive Summary
Out of 15 active EulerSwap pools, only **1 pool has significant extra vault activity** that materially affects NAV calculations.

## Statistics
- **Total Active Pools**: 15
- **Pools with Extra Vaults**: 3 (20%)
- **Pools with Significant Impact**: 1 (6.7%)

## Detailed Findings

### Pool with Significant Extra Vault Activity

**Pool: 0x0811dB938FfB1EE151db9E8186b390fe2a5FA8A8**
- Owner: 0x75102A2309Cd305c7457a72397d0BCC000c4e047
- **Pool-only NAV**: $175.71
- **Extra Vault NAV**: -$46.38 (negative!)
- **Total NAV (v2 API)**: $129.33
- **Impact**: -35.86% difference

Extra positions:
- Borrowed $88.20 from another vault (creating negative NAV)
- Assets worth $41.83 in two other tokens
- Net effect: Reduces total NAV by $46.38

### Pools with Zero/Minimal Activity
1. **0xA40E0f32...**: Empty pool with registered but unused extra vault
2. **0xC88b618C...**: $5.44 NAV, extra vault has zero balance

## Implications for NAV Calculations

### When to Use Each Approach:

| Method | Best For | Accuracy |
|--------|----------|----------|
| **netnav.py** | Pure swap pool analysis | ✅ 100% for pool-only positions |
| **v2 REST API** | Total account risk assessment | ✅ 100% for complete account |

### Key Differences:
- **For 93% of pools**: netnav.py and v2 API give identical results
- **For 7% of pools**: Extra vaults cause material differences
- **Maximum observed impact**: 35.86% NAV difference

## Example Comparison

For pool 0x0811dB...:
```
netnav.py would show:  $176 (pool positions only)
v2 API actually shows: $129 (includes -$47 from extra borrowing)
Difference:            $47 (27% lower due to external debt)
```

## Conclusion

The v2 REST API's inclusion of all account vaults is **important for risk assessment** but can show significantly different NAV than pool-only calculations when:
1. The account has borrowed from other vaults
2. The account has positions in non-pool tokens

For most pools (93%), both approaches yield identical results as operators typically don't use extra vaults.

## Recommendation

- Use **netnav.py** for analyzing swap pool performance in isolation
- Use **v2 REST API** for complete account risk and total NAV
- Be aware that ~7% of pools may show material differences between the two approaches