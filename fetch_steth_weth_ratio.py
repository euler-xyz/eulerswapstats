#!/usr/bin/env python3
"""
Fetch stETH and WETH prices from DeFiLlama to calculate clean stETH/WETH ratio.
"""
import json
import requests
from datetime import datetime
from typing import Dict

# DeFiLlama token identifiers
TOKENS = {
    'steth': 'ethereum:0xae7ab96520de3a18e5e111b5eaab095312d7fe84',
    'weth': 'ethereum:0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
}

def fetch_price_history(token_id: str, days: int = 31) -> Dict[str, float]:
    """Fetch historical prices from DeFiLlama."""
    
    print(f"Fetching {days} days of data for {token_id}")
    
    url = f"https://coins.llama.fi/chart/{token_id}"
    params = {
        'period': '1d',
        'span': days
    }
    
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        if 'coins' in data and token_id in data['coins']:
            prices = data['coins'][token_id]['prices']
            
            # Convert to date-indexed dict
            price_dict = {}
            for price_point in prices:
                timestamp = price_point['timestamp']
                price = price_point['price']
                date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                price_dict[date] = price
            
            return price_dict
        else:
            print(f"No data found for {token_id}")
            return {}
            
    except Exception as e:
        print(f"Error fetching from DeFiLlama: {e}")
        return {}


def calculate_clean_steth_weth_ratios():
    """Fetch both prices and calculate clean ratios."""
    
    # Fetch price histories
    print("Fetching stETH prices...")
    steth_prices = fetch_price_history(TOKENS['steth'], days=31)
    
    print("Fetching WETH prices...")
    weth_prices = fetch_price_history(TOKENS['weth'], days=31)
    
    if not steth_prices or not weth_prices:
        print("Failed to fetch prices")
        return
    
    # Calculate ratios
    ratios = []
    for date in sorted(steth_prices.keys()):
        if date in weth_prices and weth_prices[date] > 0:
            ratio = steth_prices[date] / weth_prices[date]
            ratios.append({
                'date': date,
                'steth_price_defillama': steth_prices[date],
                'weth_price_defillama': weth_prices[date],
                'steth_weth_ratio_defillama': ratio
            })
    
    print(f"\nCalculated {len(ratios)} daily ratios")
    
    # Show sample
    print("\nSample data (last 5 days):")
    print(f"{'Date':<12} {'stETH':<10} {'WETH':<10} {'Ratio':<10}")
    print("-" * 45)
    
    for entry in ratios[-5:]:
        print(f"{entry['date']:<12} ${entry['steth_price_defillama']:>8.0f}  ${entry['weth_price_defillama']:>8.0f}  {entry['steth_weth_ratio_defillama']:>8.4f}")
    
    # Calculate average
    avg_ratio = sum(r['steth_weth_ratio_defillama'] for r in ratios) / len(ratios)
    print(f"\nAverage stETH/WETH ratio (DeFiLlama): {avg_ratio:.4f}")
    
    # Save to file
    with open('steth_weth_ratios_defillama.json', 'w') as f:
        json.dump(ratios, f, indent=2)
    print(f"\nSaved {len(ratios)} ratios to steth_weth_ratios_defillama.json")
    
    # Merge with existing pool data
    try:
        with open('pool_data.json', 'r') as f:
            pool_data = json.load(f)
        
        # Create date-indexed dict
        ratio_dict = {r['date']: r['steth_weth_ratio_defillama'] for r in ratios}
        
        # Add to pool data
        updated = 0
        for entry in pool_data:
            if entry['date'] in ratio_dict:
                entry['steth_weth_ratio_defillama'] = ratio_dict[entry['date']]
                updated += 1
        
        # Save updated data
        with open('pool_data_clean_ratios.json', 'w') as f:
            json.dump(pool_data, f, indent=2)
        
        print(f"Updated {updated} entries in pool_data_clean_ratios.json")
        
    except FileNotFoundError:
        print("pool_data.json not found, skipping merge")
    
    return ratios


if __name__ == "__main__":
    calculate_clean_steth_weth_ratios()