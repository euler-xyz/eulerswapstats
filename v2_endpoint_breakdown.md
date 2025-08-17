# v2 REST Endpoint Complete Breakdown

## Endpoint: `https://index-dev.eul.dev/v2/swap/pools?chainId={chainId}`

## Data Structure Analysis

### 1. Pool-Level Data

```json
{
  "pool": "0x0811dB938FfB1EE151db9E8186b390fe2a5FA8A8",
  "vault0": {
    "asset": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  // USDC
    "address": "0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9",
    "reserves": "87859347",
    "availableLiquidity": "87859347",
    "cash": "5978595564429",
    "fees": {...},
    "volume": {...}
  },
  "vault1": {
    "asset": "0xdAC17F958D2ee523a2206206994597C13D831ec7",  // USDT
    "address": "0x313603FA690301b0CaeEf8069c065862f9162162",
    "reserves": "87587053",
    "availableLiquidity": "87587053",
    "cash": "2042341014857",
    "fees": {...},
    "volume": {...}
  },
  "totalReserves": "175446400",  // Sum of vault0 + vault1 reserves
  "price": "1000000000000000000",  // Pool price ratio
  "limit01In": "52135276424327",
  "limit01Out": "87587053",
  "limit10In": "33937623705984",
  "limit10Out": "87859347"
}
```

**Pool-level NAV calculation would be:**
- vault0.reserves * price0 + vault1.reserves * price1
- For USDC/USDT: 87.86 + 87.59 = $175.45

### 2. Account-Level Data (accountNav)

```json
{
  "accountNav": {
    "nav": "12932415246",           // $129.32 - TOTAL ACCOUNT NAV
    "totalAssets": "21752783444",   // $217.53 - All assets
    "totalBorrowed": "8820368198",  // $88.20 - All borrowed
    "breakdown": {
      // POOL VAULTS (2)
      "0x797DD8...": {  // USDC vault (vault0)
        "assets": "87963259",
        "borrowed": "0",
        "price": "99986321"
      },
      "0x313603...": {  // USDT vault (vault1)
        "assets": "87692227",
        "borrowed": "0",
        "price": "100071912"
      },
      
      // EXTRA VAULTS (4) - NOT PART OF POOL
      "0x37223B...": {  // PT-sUSDe-27MAR2025
        "assets": "20793099844514972962",
        "borrowed": "0"
      },
      "0xb7FC5E...": {  // PT-sUSDe-29MAY2025
        "assets": "21124313023902284578",
        "borrowed": "0"
      },
      "0x498c01...": {  // sUSDe borrow vault
        "assets": "0",
        "borrowed": "74273205328817481817"  // $88.20
      },
      "0xD8b27C...": {  // WETH vault (empty)
        "assets": "0",
        "borrowed": "0"
      }
    }
  }
}
```

### 3. Additional Metrics

```json
{
  "apr": {
    "total1d": "0",
    "total7d": "0",
    "total30d": "0",
    "total180d": "0"
  },
  "fees": {
    "total": "0",
    "total1d": "0",
    "total7d": "0",
    "total30d": "0",
    "total180d": "0"
  },
  "volume": {
    "total": "0",
    "total1d": "0",
    "total7d": "0",
    "total30d": "0",
    "total180d": "0"
  },
  "interestEarned": {...},
  "interestPaid": {...}
}
```

## NAV Calculations Provided

### 1. Pool Reserves NAV (Implicit)
**Not directly provided**, but can be calculated from:
- `vault0.reserves` + `vault1.reserves` = $175.45
- OR from `totalReserves` field

### 2. Account NAV (Explicit)
**Directly provided** in `accountNav.nav`: $129.32
- Includes ALL vaults (pool + extra)
- Formula: totalAssets - totalBorrowed

### 3. Vault-Level NAV (Can be derived)
From `accountNav.breakdown`, you can calculate:
- Pool vaults only: $175.72
- Extra vaults: -$46.40
- Total: $129.32

## Key Insights

### What v2 Provides:
1. ✅ **Account-level NAV** - Complete, all vaults
2. ✅ **Pool configuration** - vault0/vault1 details
3. ✅ **Pool reserves** - Current liquidity
4. ✅ **All vault positions** - Every vault the account touches
5. ✅ **APR calculations** - Multiple timeframes
6. ❌ **Pool-only NAV** - Must be calculated from breakdown

### How to Get Different NAVs:

```javascript
// 1. Account NAV (provided)
const accountNAV = data.accountNav.nav / 1e8;

// 2. Pool-only NAV (must calculate)
const poolVaults = [data.vault0.address, data.vault1.address];
let poolNAV = 0;
for (const [vault, info] of Object.entries(data.accountNav.breakdown)) {
  if (poolVaults.includes(vault)) {
    const assets = info.assets / (10 ** decimals);
    const borrowed = info.borrowed / (10 ** decimals);
    const price = info.price / 1e8;
    poolNAV += (assets - borrowed) * price;
  }
}

// 3. Pool reserves (simple)
const reserves0 = data.vault0.reserves / 1e6;  // USDC
const reserves1 = data.vault1.reserves / 1e6;  // USDT
const poolReserves = reserves0 + reserves1;
```

## Comparison with netnav.py

| Metric | v2 REST API | netnav.py |
|--------|-------------|-----------|
| Pool reserves | ✅ Available in vault0/vault1 | ✅ Fetches from REST |
| Pool-only NAV | ⚠️ Must calculate from breakdown | ✅ Direct calculation |
| Account NAV | ✅ Provided in accountNav.nav | ❌ Not available |
| Extra vaults | ✅ All included | ❌ Ignored |
| APR | ✅ Multiple timeframes | ✅ Lifetime only |

## Conclusion

The v2 endpoint is **account-centric**, not pool-centric:
- It provides complete account NAV (all vaults)
- Pool data is available but secondary
- Pool-only NAV must be calculated by filtering the breakdown
- Perfect for risk assessment and portfolio management
- Less ideal for pure pool performance analysis (use netnav.py for that)