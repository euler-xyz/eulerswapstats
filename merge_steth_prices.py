#!/usr/bin/env python3
"""
Merge stETH prices into pool_data.json
"""
import json
from datetime import datetime

# Load pool data
with open('pool_data.json', 'r') as f:
    pool_data = json.load(f)

# Load stETH prices
with open('steth_prices.json', 'r') as f:
    steth_prices = json.load(f)

# Create a date-indexed dict for stETH prices
steth_price_map = {p['date']: p['price'] for p in steth_prices}

# Add stETH prices to pool data
for entry in pool_data:
    date = entry['date']
    if date in steth_price_map:
        entry['steth_price'] = steth_price_map[date]
        # Calculate stETH/ETH ratio
        if entry.get('weth_price', 0) > 0:
            entry['steth_eth_ratio'] = entry['steth_price'] / entry['weth_price']
    else:
        entry['steth_price'] = None
        entry['steth_eth_ratio'] = None

# Save updated data
with open('pool_data_with_steth.json', 'w') as f:
    json.dump(pool_data, f, indent=2)

print(f"Added stETH prices to {len(pool_data)} entries")
print("Saved as pool_data_with_steth.json")

# Show sample of the data
print("\nSample data (last 5 days):")
print(f"{'Date':<12} {'NAV (USD)':<12} {'NAV (WETH)':<10} {'wstETH':<10} {'WETH':<10} {'stETH':<10} {'stETH/ETH':<10}")
print("-" * 80)

for entry in pool_data[-5:]:
    nav_usd = entry['nav_usd']
    nav_weth = entry['nav_weth']
    wsteth_price = entry['wsteth_price']
    weth_price = entry['weth_price']
    steth_price = entry.get('steth_price', 0)
    steth_ratio = entry.get('steth_eth_ratio', 0)
    
    print(f"{entry['date']:<12} ${nav_usd/1e6:>9.2f}M  {nav_weth:>9.2f}  ${wsteth_price:>8.0f}  ${weth_price:>8.0f}  ${steth_price:>8.0f}  {steth_ratio:>9.4f}")

# Calculate some statistics
steth_prices_available = [e for e in pool_data if e.get('steth_price')]
if steth_prices_available:
    avg_steth_ratio = sum(e['steth_eth_ratio'] for e in steth_prices_available if e.get('steth_eth_ratio')) / len(steth_prices_available)
    print(f"\nAverage stETH/ETH ratio: {avg_steth_ratio:.4f}")
    
    # Check correlation with wstETH/ETH ratio
    wsteth_ratios = [e['wsteth_eth_ratio'] for e in steth_prices_available if e.get('wsteth_eth_ratio')]
    steth_ratios = [e['steth_eth_ratio'] for e in steth_prices_available if e.get('steth_eth_ratio')]
    
    if wsteth_ratios and steth_ratios:
        avg_wsteth_ratio = sum(wsteth_ratios) / len(wsteth_ratios)
        print(f"Average wstETH/ETH ratio: {avg_wsteth_ratio:.4f}")
        print(f"wstETH premium over stETH: {(avg_wsteth_ratio / avg_steth_ratio - 1) * 100:.2f}%")