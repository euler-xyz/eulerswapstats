#!/usr/bin/env python3
"""
Parse table data and create graphs for wstETH/WETH pool performance analysis.
This script is specifically designed for analyzing wstETH/WETH liquidity pools.
"""
import re
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime

def parse_json_data(filename):
    """Parse data from JSON file."""
    with open(filename, 'r') as f:
        json_data = json.load(f)
    
    data = []
    for entry in json_data:
        # Map JSON fields to expected format
        data.append({
            'date': datetime.strptime(entry['date'], '%Y-%m-%d'),
            'block': entry['block'],
            'nav_usd': entry['nav_usd'],
            'wsteth_net': entry.get('token0_net', 0),  # Assuming token0 is wstETH
            'weth_net': entry.get('token1_net', 0),     # Assuming token1 is WETH
            'wsteth_price': entry.get('token0_price', 0),
            'weth_price': entry.get('token1_price', 0),
            'nav_weth': entry.get('nav_weth', 0),
            'wsteth_eth_ratio': entry.get('token0_price', 0) / entry.get('token1_price', 1) if entry.get('token1_price', 0) > 0 else 0,
            'daily_volume': entry.get('daily_volume', 0),
            'swaps': entry.get('swaps', 0),
            'steth_price': None,
            'steth_eth_ratio': None
        })
    
    return pd.DataFrame(data)

def parse_table_data(filename='tabledata.txt'):
    """Parse the table data from file."""
    # Check if it's a JSON file
    if filename.endswith('.json'):
        return parse_json_data(filename)
    
    with open(filename, 'r') as f:
        lines = f.readlines()
    
    data = []
    for line in lines:
        # Skip separator and header lines
        if line.startswith('+') or line.startswith('|============') or 'Date' in line:
            continue
        
        # Parse data lines
        if line.startswith('|') and '2025' in line:
            parts = line.split('|')
            if len(parts) >= 11:
                try:
                    # Clean and parse each field
                    date_str = parts[1].strip()
                    block = int(parts[2].strip())
                    
                    # Parse Net NAV (remove $ and commas)
                    nav_str = parts[3].strip().replace('$', '').replace(',', '')
                    nav = float(nav_str)
                    
                    # Parse wstETH Net
                    wsteth_net = float(parts[6].strip().replace(',', ''))
                    
                    # Parse WETH Net
                    weth_net = float(parts[7].strip().replace(',', ''))
                    
                    # Parse prices (remove $ and commas)
                    wsteth_price = float(parts[8].strip().replace('$', '').replace(',', ''))
                    weth_price = float(parts[9].strip().replace('$', '').replace(',', ''))
                    
                    # Parse NAV in WETH
                    nav_in_weth = float(parts[10].strip())
                    
                    # Parse Daily Volume (remove $ and commas, handle '-')
                    volume_str = parts[11].strip()
                    if volume_str == '-':
                        daily_volume = 0
                    else:
                        daily_volume = float(volume_str.replace('$', '').replace(',', ''))
                    
                    # Parse Swaps (handle '-')
                    swaps_str = parts[12].strip()
                    if swaps_str == '-':
                        swaps = 0
                    else:
                        swaps = int(swaps_str)
                    
                    data.append({
                        'date': datetime.strptime(date_str, '%Y-%m-%d'),
                        'block': block,
                        'nav_usd': nav,
                        'wsteth_net': wsteth_net,
                        'weth_net': weth_net,
                        'wsteth_price': wsteth_price,
                        'weth_price': weth_price,
                        'nav_weth': nav_in_weth,
                        'wsteth_eth_ratio': wsteth_price / weth_price if weth_price > 0 else 0,
                        'daily_volume': daily_volume,
                        'swaps': swaps,
                        'steth_price': None,  # Will be populated from external data
                        'steth_eth_ratio': None
                    })
                except (ValueError, IndexError) as e:
                    print(f"Error parsing line: {line}")
                    print(f"Error: {e}")
                    continue
    
    # Load stETH prices if available
    try:
        with open('pool_data_with_steth.json', 'r') as f:
            steth_data = json.load(f)
            steth_price_map = {}
            for entry in steth_data:
                if entry.get('steth_price'):
                    steth_price_map[entry['date']] = {
                        'price': entry['steth_price'],
                        'ratio': entry.get('steth_eth_ratio')
                    }
            
            # Add stETH prices to data
            for row in data:
                date_str = row['date'].strftime('%Y-%m-%d')
                if date_str in steth_price_map:
                    row['steth_price'] = steth_price_map[date_str]['price']
                    row['steth_eth_ratio'] = steth_price_map[date_str]['ratio']
    except FileNotFoundError:
        print("Note: stETH prices not found (pool_data_with_steth.json missing)")
    
    # Load clean DeFiLlama ratios if available
    try:
        with open('pool_data_with_defillama.json', 'r') as f:
            defillama_data = json.load(f)
            defillama_ratio_map = {}
            for entry in defillama_data:
                if entry.get('wsteth_eth_ratio_defillama'):
                    defillama_ratio_map[entry['date']] = entry['wsteth_eth_ratio_defillama']
            
            # Add DeFiLlama ratios to data
            for row in data:
                date_str = row['date'].strftime('%Y-%m-%d')
                if date_str in defillama_ratio_map:
                    row['wsteth_eth_ratio_defillama'] = defillama_ratio_map[date_str]
    except FileNotFoundError:
        print("Note: DeFiLlama ratios not found (pool_data_with_defillama.json missing)")
    
    # Load clean stETH/WETH ratios from DeFiLlama if available
    try:
        with open('pool_data_clean_ratios.json', 'r') as f:
            clean_ratio_data = json.load(f)
            steth_weth_ratio_map = {}
            for entry in clean_ratio_data:
                if entry.get('steth_weth_ratio_defillama'):
                    steth_weth_ratio_map[entry['date']] = entry['steth_weth_ratio_defillama']
            
            # Add clean stETH/WETH ratios to data
            for row in data:
                date_str = row['date'].strftime('%Y-%m-%d')
                if date_str in steth_weth_ratio_map:
                    row['steth_weth_ratio_defillama'] = steth_weth_ratio_map[date_str]
    except FileNotFoundError:
        print("Note: Clean stETH/WETH ratios not found (pool_data_clean_ratios.json missing)")
    
    return pd.DataFrame(data)

def create_graphs(df):
    """Create visualization graphs."""
    # Set up the figure with subplots - now 4 rows to include volume
    fig, axes = plt.subplots(4, 2, figsize=(15, 16))
    fig.suptitle('EulerSwap Pool Performance Analysis\n(wstETH/WETH Pool)', fontsize=16, fontweight='bold')
    
    # Format dates for x-axis
    date_format = mdates.DateFormatter('%m/%d')
    
    # 1. NAV in USD
    ax1 = axes[0, 0]
    ax1.plot(df['date'], df['nav_usd'] / 1e6, 'b-', linewidth=2)
    ax1.set_title('Net NAV in USD')
    ax1.set_ylabel('NAV ($M)')
    ax1.grid(True, alpha=0.3)
    ax1.axhline(y=df['nav_usd'].iloc[0] / 1e6, color='r', linestyle='--', alpha=0.5, label='Starting NAV')
    ax1.legend()
    ax1.xaxis.set_major_formatter(date_format)
    
    # 2. NAV in WETH
    ax2 = axes[0, 1]
    ax2.plot(df['date'], df['nav_weth'], 'g-', linewidth=2)
    ax2.set_title('Net NAV in WETH Terms')
    ax2.set_ylabel('NAV (WETH)')
    ax2.grid(True, alpha=0.3)
    ax2.axhline(y=df['nav_weth'].iloc[0], color='r', linestyle='--', alpha=0.5, label='Starting NAV')
    ax2.legend()
    ax2.xaxis.set_major_formatter(date_format)
    
    # 3. wstETH/ETH Price Ratio
    ax3 = axes[1, 0]
    ax3.plot(df['date'], df['wsteth_eth_ratio'], 'purple', linewidth=2)
    ax3.set_title('wstETH/ETH Price Ratio')
    ax3.set_ylabel('Ratio')
    ax3.grid(True, alpha=0.3)
    ax3.xaxis.set_major_formatter(date_format)
    
    # 4. stETH/WETH Ratio (DeFiLlama)
    ax4 = axes[1, 1]
    
    # Plot clean DeFiLlama stETH/WETH ratio if available
    if 'steth_weth_ratio_defillama' in df.columns and df['steth_weth_ratio_defillama'].notna().any():
        ax4.plot(df['date'], df['steth_weth_ratio_defillama'], 'orange', linewidth=2)
        ax4.set_title('stETH/WETH Ratio (DeFiLlama)')
        ax4.set_ylabel('Ratio')
        
        # Show average
        avg_ratio = df['steth_weth_ratio_defillama'].mean()
        ax4.axhline(y=avg_ratio, color='gray', linestyle='--', alpha=0.5)
        ax4.text(0.02, 0.98, f'Avg: {avg_ratio:.4f}', 
                transform=ax4.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    else:
        # If no stETH data, show message
        ax4.text(0.5, 0.5, 'stETH/WETH ratio data not available', 
                transform=ax4.transAxes, ha='center', va='center',
                fontsize=12, color='gray')
        ax4.set_title('stETH/WETH Ratio (DeFiLlama)')
        ax4.set_ylabel('Ratio')
    
    ax4.grid(True, alpha=0.3)
    ax4.xaxis.set_major_formatter(date_format)
    
    # 5. Net Positions
    ax5 = axes[2, 0]
    ax5.plot(df['date'], df['wsteth_net'], 'orange', label='wstETH (borrowed)', linewidth=2)
    ax5.plot(df['date'], df['weth_net'], 'blue', label='WETH (assets)', linewidth=2)
    ax5.set_title('Net Token Positions')
    ax5.set_ylabel('Amount')
    ax5.set_xlabel('Date')
    ax5.legend()
    ax5.grid(True, alpha=0.3)
    ax5.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax5.xaxis.set_major_formatter(date_format)
    
    # 6. Performance Comparison
    ax6 = axes[2, 1]
    # Calculate cumulative returns
    initial_nav_usd = df['nav_usd'].iloc[0]
    initial_nav_weth = df['nav_weth'].iloc[0]
    initial_weth_price = df['weth_price'].iloc[0]
    
    nav_return = ((df['nav_usd'] / initial_nav_usd) - 1) * 100
    weth_return = ((df['nav_weth'] / initial_nav_weth) - 1) * 100
    weth_price_return = ((df['weth_price'] / initial_weth_price) - 1) * 100
    
    ax6.plot(df['date'], nav_return, 'b-', label='NAV (USD)', linewidth=2)
    ax6.plot(df['date'], weth_return, 'g-', label='NAV (WETH)', linewidth=2)
    ax6.plot(df['date'], weth_price_return, 'r--', label='WETH Price', linewidth=2)
    ax6.set_title('Cumulative Returns Comparison')
    ax6.set_ylabel('Return (%)')
    ax6.set_xlabel('Date')
    ax6.legend()
    ax6.grid(True, alpha=0.3)
    ax6.axhline(y=0, color='black', linestyle='-', alpha=0.3)
    ax6.xaxis.set_major_formatter(date_format)
    
    # 7. Daily Volume
    ax7 = axes[3, 0]
    ax7.bar(df['date'], df['daily_volume'] / 1e6, color='steelblue', alpha=0.7)
    ax7.set_title('Daily Trading Volume')
    ax7.set_ylabel('Volume ($M)')
    ax7.set_xlabel('Date')
    ax7.grid(True, alpha=0.3)
    ax7.xaxis.set_major_formatter(date_format)
    
    # Add 7-day moving average
    if len(df) >= 7:
        ma7 = df['daily_volume'].rolling(window=7).mean() / 1e6
        ax7.plot(df['date'], ma7, 'r-', label='7-day MA', linewidth=2)
        ax7.legend()
    
    # 8. Daily Swap Count
    ax8 = axes[3, 1]
    ax8.bar(df['date'], df['swaps'], color='darkgreen', alpha=0.7)
    ax8.set_title('Daily Swap Count')
    ax8.set_ylabel('Number of Swaps')
    ax8.set_xlabel('Date')
    ax8.grid(True, alpha=0.3)
    ax8.xaxis.set_major_formatter(date_format)
    
    # Add correlation with volume
    if df['swaps'].sum() > 0:
        avg_vol_per_swap = df['daily_volume'].sum() / df['swaps'].sum()
        ax8.text(0.02, 0.98, f'Avg per swap: ${avg_vol_per_swap:,.0f}', 
                transform=ax8.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    # Adjust layout
    plt.tight_layout()
    
    # Save the figure
    plt.savefig('pool_performance_analysis.png', dpi=150, bbox_inches='tight')
    print("Graph saved as 'pool_performance_analysis.png'")
    
    # Also save data as JSON for easy reuse
    json_data = df.to_dict('records')
    # Convert datetime to string for JSON serialization
    for record in json_data:
        record['date'] = record['date'].strftime('%Y-%m-%d')
    
    with open('pool_data.json', 'w') as f:
        json.dump(json_data, f, indent=2)
    print("Data saved as 'pool_data.json'")
    
    # Print summary statistics
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"Period: {df['date'].iloc[0].strftime('%Y-%m-%d')} to {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"Days: {len(df)}")
    print(f"\nNAV Performance:")
    print(f"  Starting NAV (USD): ${initial_nav_usd:,.0f}")
    print(f"  Ending NAV (USD): ${df['nav_usd'].iloc[-1]:,.0f}")
    print(f"  USD Return: {nav_return.iloc[-1]:.2f}%")
    print(f"\n  Starting NAV (WETH): {initial_nav_weth:.2f}")
    print(f"  Ending NAV (WETH): {df['nav_weth'].iloc[-1]:.2f}")
    print(f"  WETH Return: {weth_return.iloc[-1]:.2f}%")
    print(f"\nBenchmark:")
    print(f"  WETH Price Return: {weth_price_return.iloc[-1]:.2f}%")
    print(f"  Underperformance vs WETH: {weth_return.iloc[-1]:.2f}%")
    
    print(f"\nLeverage Evolution:")
    print(f"  Initial wstETH borrowed: {df['wsteth_net'].iloc[0]:,.0f}")
    print(f"  Final wstETH borrowed: {df['wsteth_net'].iloc[-1]:,.0f}")
    print(f"  Leverage increase: {abs(df['wsteth_net'].iloc[-1] / df['wsteth_net'].iloc[0]):.1f}x")
    
    # Add stETH statistics if available
    if 'steth_eth_ratio' in df.columns and df['steth_eth_ratio'].notna().any():
        print(f"\nStaked ETH Ratios:")
        avg_wsteth_ratio = df['wsteth_eth_ratio'].mean()
        avg_steth_ratio = df[df['steth_eth_ratio'].notna()]['steth_eth_ratio'].mean()
        premium = (avg_wsteth_ratio / avg_steth_ratio - 1) * 100 if avg_steth_ratio > 0 else 0
        
        print(f"  Average wstETH/ETH ratio: {avg_wsteth_ratio:.4f}")
        print(f"  Average stETH/ETH ratio: {avg_steth_ratio:.4f}")
        print(f"  wstETH premium over stETH: {premium:.2f}%")
    
    print(f"\nVolume Statistics:")
    total_volume = df['daily_volume'].sum()
    total_swaps = df['swaps'].sum()
    avg_daily_volume = df['daily_volume'].mean()
    avg_swap_size = total_volume / total_swaps if total_swaps > 0 else 0
    
    print(f"  Total Volume: ${total_volume:,.0f}")
    print(f"  Average Daily Volume: ${avg_daily_volume:,.0f}")
    print(f"  Total Swaps: {total_swaps:,}")
    print(f"  Average Swap Size: ${avg_swap_size:,.0f}")
    print(f"  Peak Daily Volume: ${df['daily_volume'].max():,.0f} on {df.loc[df['daily_volume'].idxmax(), 'date'].strftime('%Y-%m-%d')}")
    print(f"  Peak Daily Swaps: {df['swaps'].max():,} on {df.loc[df['swaps'].idxmax(), 'date'].strftime('%Y-%m-%d')}")
    
    return fig

def main():
    # Parse the data
    df = parse_and_graph.parse_table_data('tabledata.txt')
    
    if df.empty:
        print("No data parsed from file")
        return
    
    print(f"Parsed {len(df)} days of data")
    
    # Create graphs
    fig = create_graphs(df)
    
    # Show the plot
    plt.show()

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Parse and graph wstETH/WETH pool data")
    parser.add_argument("--input", default="tabledata.txt", help="Input file (text table or JSON)")
    
    args = parser.parse_args()
    
    # Parse the data
    df = parse_table_data(args.input)
    
    if df.empty:
        print(f"No data parsed from {args.input}")
    else:
        print(f"Parsed {len(df)} days of data from {args.input}")
        
        # Create graphs
        fig = create_graphs(df)
        
        # Show the plot
        plt.show()