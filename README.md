# EulerSwap Pool Analysis Tools

This repository contains tools for analyzing EulerSwap liquidity pools, with a focus on wstETH/WETH pools and comprehensive performance visualization.

## Overview

The analysis generates a comprehensive chart showing:
- Net NAV in USD and WETH terms
- Token price ratios (wstETH/ETH, stETH/WETH)
- Net token positions (borrowed vs assets)
- Performance comparison vs benchmarks
- Daily trading volume and swap counts

## Prerequisites

```bash
pip install pandas matplotlib requests
```

## Workflow Steps

### Step 1: Fetch Daily NAV History with Volumes

```bash
# Save directly to JSON (recommended)
python daily_nav_history.py --pool 0x55dcf9455EEe8Fd3f5EEd17606291272cDe428a8 --days 31 --output pool_daily_data.json

# Or display table only (old method - requires manual copy to tabledata.txt)
python daily_nav_history.py --pool 0x55dcf9455EEe8Fd3f5EEd17606291272cDe428a8 --days 31
```

The `--output` option automatically saves the data in JSON format, which is easier to parse and doesn't require manual copying.

### Step 2: Fetch External Price Data (Optional)

If you want to add stETH prices or clean ratio comparisons:

```bash
# Fetch stETH prices from DeFiLlama
python fetch_external_prices.py steth --days 31 --output steth_prices.json

# Fetch clean wstETH/WETH ratios from DeFiLlama
python fetch_clean_ratios.py

# Fetch clean stETH/WETH ratios from DeFiLlama  
python fetch_steth_weth_ratio.py
```

### Step 3: Merge stETH Prices (Optional)

If you fetched stETH prices and want to include them:

```bash
python merge_steth_prices.py
```

This creates `pool_data_with_steth.json` with integrated stETH prices.

### Step 4: Generate Analysis Charts

```bash
# Using JSON input (recommended)
python parse_and_graph_wsteth_weth.py --input pool_daily_data.json

# Or using text table (default)
python parse_and_graph_wsteth_weth.py --input tabledata.txt
```

This generates:
- `pool_performance_analysis.png` - 8-panel visualization
- `pool_data.json` - Structured data for further analysis
- Summary statistics printed to console

## Quick Start - Simplified Workflow

For the fastest analysis, use JSON throughout:

```bash
# Step 1: Fetch data and save to JSON
python daily_nav_history.py --pool 0x55dcf9455EEe8Fd3f5EEd17606291272cDe428a8 --days 31 --output pool_daily_data.json

# Step 2: Generate charts from JSON
python parse_and_graph_wsteth_weth.py --input pool_daily_data.json
```

That's it! The charts and analysis will be generated automatically.

## Output Files

- **pool_performance_analysis.png**: Main visualization with 8 charts
- **pool_data.json**: Parsed pool data in JSON format
- **pool_data_with_steth.json**: Pool data with stETH prices (if Step 3 was run)
- **pool_data_clean_ratios.json**: Pool data with clean DeFiLlama ratios (if Step 2 was run)

## Understanding the Results

### Key Metrics

1. **Fee Return**: Calculated as `(Total Volume × Fee Rate) / Starting NAV`
   - Example: $139M volume × 0.01% fee / $2.1M NAV = 0.66% return

2. **WETH Return**: Change in NAV when measured in WETH terms
   - Negative values indicate underperformance vs holding WETH

3. **Leverage Evolution**: Change in borrowed position over time
   - Higher leverage amplifies both gains and losses

### Chart Panels

1. **Net NAV in USD**: Total value of pool in USD terms
2. **Net NAV in WETH**: Total value measured in WETH (shows real performance)
3. **wstETH/ETH Ratio**: Premium of wrapped staked ETH over regular ETH
4. **stETH/WETH Ratio**: Shows liquid staking token parity with ETH
5. **Net Positions**: Borrowed (negative) vs asset (positive) amounts
6. **Performance Comparison**: Returns vs benchmarks
7. **Daily Volume**: Trading activity in USD
8. **Daily Swaps**: Number of transactions

## Example Analysis

For pool 0x55dcf9455EEe8Fd3f5EEd17606291272cDe428a8 over 31 days:

```
Period: 2025-07-20 to 2025-08-19
NAV Performance:
  USD Return: 14.80%
  WETH Return: -2.31%
  
Fee Metrics:
  Total Volume: $139M
  Fee Return: 0.66% (7.77% APR)
  
Leverage:
  Initial: -1,374 wstETH borrowed
  Final: -4,255 wstETH borrowed (3.1x increase)
```

## Troubleshooting

### Common Issues

1. **Empty tabledata.txt**: Ensure Step 1 completes successfully and you copy the full output

2. **Missing stETH prices**: Steps 2-3 are optional; the script will work without them

3. **Import errors**: Install required packages: `pandas`, `matplotlib`, `requests`

4. **Price scale issues**: The scripts assume 1e8 scale for USD prices from GraphQL

## Advanced Usage

### Analyzing Different Pools

Replace the pool address in Step 1 with any wstETH/WETH pool:

```bash
python daily_nav_history.py YOUR_POOL_ADDRESS --days 30
```

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