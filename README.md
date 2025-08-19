# EulerSwap Pool Analysis Tools

This repository contains tools for analyzing EulerSwap liquidity pools with automatic pool type detection and optimized visualizations for any token pair.

## Overview

The analysis generates comprehensive charts tailored to your pool type:
- **Stablecoin pools**: Peg deviation analysis, spread metrics
- **LST pools**: Staking premium analysis, ETH-denominated returns  
- **Volatile pools**: Price trends, volatility bands
- **All pools**: NAV evolution, positions, volumes, fees, returns

## Prerequisites

```bash
pip install pandas matplotlib requests tabulate
```

## Quick Start - Universal Workflow

### For ANY Pool (Recommended)

```bash
# Step 1: Fetch daily NAV history for any pool
python daily_nav_history.py --pool <POOL_ADDRESS> --days 30 --output data.json

# Step 2: Generate type-specific visualization (auto-detects pool type)
python parse_and_graph_generic.py --input data.json
```

The generic analyzer automatically:
- Detects pool type (stable/stable, LST/base, volatile/stable, etc.)
- Scales charts appropriately for token magnitudes
- Generates relevant metrics for each pool type
- Creates an 8-panel visualization optimized for the specific pair

### Examples

**Stablecoin Pool (USDe/USDT):**
```bash
python daily_nav_history.py --pool 0x794138c7067d38a46CE29fc84bA661678fAAe8a8 --days 30 --output usde_usdt.json
python parse_and_graph_generic.py --input usde_usdt.json
# Output: USDE_USDT_analysis.png with peg deviation focus
```

**LST Pool (wstETH/WETH):**
```bash
python daily_nav_history.py --pool 0x55dcf9d48c666bb96e90acb17e93196a35bbcc58 --days 30 --output wsteth_weth.json
python parse_and_graph_generic.py --input wsteth_weth.json
# Output: WSTETH_WETH_analysis.png with staking premium analysis
```

**Volatile/Stable Pool (ETH/USDC):**
```bash
python daily_nav_history.py --pool <ETH_USDC_POOL> --days 30 --output eth_usdc.json
python parse_and_graph_generic.py --input eth_usdc.json
# Output: ETH_USDC_analysis.png with price trend analysis
```

## Legacy Workflow (wstETH/WETH Specific)

For wstETH/WETH pools with external stETH price integration:

### Step 1: Fetch Daily NAV History

```bash
python daily_nav_history.py --pool 0x55dcf9455EEe8Fd3f5EEd17606291272cDe428a8 --days 31 --output pool_daily_data.json
```

### Step 2: Fetch External Price Data (Optional)

```bash
# Fetch stETH prices from DeFiLlama
python fetch_external_prices.py steth --days 31 --output steth_prices.json

# Fetch clean wstETH/WETH ratios from DeFiLlama
python fetch_clean_ratios.py

# Fetch clean stETH/WETH ratios from DeFiLlama  
python fetch_steth_weth_ratio.py
```

### Step 3: Merge stETH Prices (Optional)

```bash
python merge_steth_prices.py
```

This creates `pool_data_with_steth.json` with integrated stETH prices.

### Step 4: Generate wstETH-Specific Charts

```bash
# If you merged stETH prices (Step 3):
python parse_and_graph.py --input pool_data_with_steth.json

# If using original data without stETH prices:
python parse_and_graph.py --input pool_daily_data.json
```

**Note:** Use `parse_and_graph_generic.py` for all new analyses as it handles any token pair automatically and provides better scaling.

## Troubleshooting

### Common Issues

1. **Empty tabledata.txt**: Ensure Step 1 completes successfully and you copy the full output

2. **Missing stETH prices**: Steps 2-3 are optional; the script will work without them

3. **Import errors**: Install required packages: `pandas`, `matplotlib`, `requests`

4. **Price scale issues**: The scripts assume 1e8 scale for USD prices from GraphQL

## Advanced Usage

### Customizing Date Range

Adjust the `--days` parameter to analyze different time periods:

```bash
python daily_nav_history.py POOL_ADDRESS --days 7   # Last week
python daily_nav_history.py POOL_ADDRESS --days 90  # Last 3 months
```

### Comparing Multiple Sources

The scripts support comparing prices from different sources:
- GraphQL/Euler API (default)
- DeFiLlama (via fetch_external_prices.py)
- CoinGecko (via fetch_external_prices.py with --source coingecko)

## Notes

- All prices are in USD with 1e8 scale from GraphQL
- Net positions are negative for borrowed assets, positive for owned assets
- The analysis assumes a 1 basis point (0.01%) swap fee
- WETH returns are more meaningful than USD returns for DeFi pools

---

## Additional Tools

### netnav.py - Core NAV Calculator

Calculate Net NAV for EulerSwap pools (matching website display values).

```bash
# Current NAV
python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1

# Pool lifetime return
python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1 --lifespan

# Historical return between blocks
python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1 \
  --from-block 23120299 --to-block 23132700
```

Net NAV = Vault assets - Vault borrowed (the actual economic position after leverage).

### poolinfo.py - Pool Configuration

Get detailed deployment parameters and configuration for a pool.

```bash
python poolinfo.py --pool 0x29bE2d4b843DA604665C2c5C46D596890303E8a8 --chain 1
```

Shows deployment parameters, fees, concentration, vaults, reserves, volume, and APY.

### findpool.py - Pool Discovery

Find EulerSwap pools by token pair, including uninstalled pools.

```bash
python findpool.py --token0 0x66a1e37c9b0eaddca17d3662d6c05f4decf3e110 \
  --token1 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --chain 1
```

### compare_apr.py - APR Analysis

Compare APR calculations between different methodologies.

```bash
python compare_apr.py --chain 1 --pool 0x55dcf9455EEe8Fd3f5EEd17606291272cDe428a8
```

Identifies discrepancies between V2 API and local Net NAV calculations.