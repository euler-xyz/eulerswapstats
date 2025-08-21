#!/usr/bin/env python3
"""
Analysis and visualization for account NAV data from V2 API.
Includes interest earned/paid, fees, volume, and APR metrics.
"""
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import Dict, List, Tuple

def parse_account_nav_data(filename: str) -> pd.DataFrame:
    """Parse account NAV data from JSON file."""
    with open(filename, 'r') as f:
        json_data = json.load(f)
    
    # Extract pool info and daily data
    pool_address = json_data.get('pool', '')
    chain_id = json_data.get('chain_id', 1)
    daily_data = json_data.get('daily_data', [])
    
    if not daily_data:
        return pd.DataFrame()
    
    # Convert to DataFrame
    data = []
    for entry in daily_data:
        data.append({
            'date': datetime.strptime(entry['date'], '%Y-%m-%d'),
            'block': entry.get('block', 0),
            'nav_usd': entry.get('nav_usd', 0),
            'total_assets_usd': entry.get('total_assets_usd', 0),
            'total_borrowed_usd': entry.get('total_borrowed_usd', 0),
            'active_vaults': entry.get('active_vaults', 0),
            'token0_symbol': entry.get('token0_symbol', 'TOKEN0'),
            'token1_symbol': entry.get('token1_symbol', 'TOKEN1'),
            # New V2 API fields
            'interest_earned': entry.get('interest_earned', 0),
            'interest_paid': entry.get('interest_paid', 0),
            'net_interest': entry.get('net_interest', 0),
            'fees': entry.get('fees', 0),
            'volume': entry.get('volume', 0),
            'apr': entry.get('apr', 0)
        })
    
    df = pd.DataFrame(data)
    
    # Add metadata to DataFrame attributes
    if not df.empty:
        df.attrs['pool_address'] = pool_address
        df.attrs['chain_id'] = chain_id
        df.attrs['token0_symbol'] = df['token0_symbol'].iloc[0]
        df.attrs['token1_symbol'] = df['token1_symbol'].iloc[0]
    
    return df

def create_account_nav_charts(df: pd.DataFrame) -> plt.Figure:
    """Create comprehensive charts for account NAV analysis."""
    
    token0 = df.attrs.get('token0_symbol', 'TOKEN0')
    token1 = df.attrs.get('token1_symbol', 'TOKEN1')
    pool_addr = df.attrs.get('pool_address', '')
    
    # Create figure with 6 subplots
    fig, axes = plt.subplots(3, 2, figsize=(15, 12))
    axes = axes.flatten()
    
    # Add title with pool info
    title = f'{token0}/{token1} Account NAV Analysis (V2 API)'
    if pool_addr:
        title += f'\nPool: {pool_addr[:10]}...'
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    date_format = mdates.DateFormatter('%m/%d')
    
    # 1. Account NAV Over Time
    ax = axes[0]
    nav_scale = 1e6 if df['nav_usd'].max() > 1e6 else 1e3
    scale_label = 'M' if nav_scale == 1e6 else 'K'
    
    ax.plot(df['date'], df['nav_usd'] / nav_scale, 'b-', linewidth=2, label='Account NAV')
    # Don't force y-axis to 0 - let matplotlib auto-scale for better visibility
    ax.set_title('Account NAV (All Vaults)')
    ax.set_ylabel(f'NAV (${scale_label})')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(date_format)
    
    # Calculate and display return
    initial_nav = df['nav_usd'].iloc[0]
    final_nav = df['nav_usd'].iloc[-1]
    days = len(df)
    total_return = ((final_nav/initial_nav - 1) * 100) if initial_nav > 0 else 0
    annualized_return = total_return * (365 / days) if days > 0 else 0
    
    ax.text(0.02, 0.98, f'Total Return: {total_return:.2f}%\nAnnualized: {annualized_return:.2f}%', 
            transform=ax.transAxes, verticalalignment='top',
            bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
    
    # 2. Assets vs Borrowed
    ax = axes[1]
    assets_scale = 1e6 if df['total_assets_usd'].max() > 1e6 else 1e3
    scale_label = 'M' if assets_scale == 1e6 else 'K'
    
    ax.plot(df['date'], df['total_assets_usd'] / assets_scale, 'g-', linewidth=2, label='Total Assets')
    ax.plot(df['date'], df['total_borrowed_usd'] / assets_scale, 'r-', linewidth=2, label='Total Borrowed')
    ax.fill_between(df['date'], df['total_assets_usd'] / assets_scale, 
                     df['total_borrowed_usd'] / assets_scale, alpha=0.3, color='green')
    ax.set_title('Assets vs Borrowed')
    ax.set_ylabel(f'Value (${scale_label})')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(date_format)
    
    # 3. Net Interest (Earned - Paid)
    ax = axes[2]
    
    # Calculate cumulative net interest
    df['cumulative_net_interest'] = df['net_interest'].cumsum()
    
    # Create bar chart for daily net interest
    colors = ['green' if x >= 0 else 'red' for x in df['net_interest']]
    ax.bar(df['date'], df['net_interest'], color=colors, alpha=0.7)
    ax.set_title('Daily Net Interest (Earned - Paid)')
    ax.set_ylabel('Net Interest ($)')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax.xaxis.set_major_formatter(date_format)
    
    # Add cumulative line on secondary axis
    ax2 = ax.twinx()
    ax2.plot(df['date'], df['cumulative_net_interest'], 'b-', linewidth=2, label='Cumulative')
    ax2.set_ylabel('Cumulative ($)', color='b')
    ax2.tick_params(axis='y', labelcolor='b')
    
    # 4. Daily Fees Earned
    ax = axes[3]
    
    # Calculate cumulative fees
    df['cumulative_fees'] = df['fees'].cumsum()
    
    ax.bar(df['date'], df['fees'], color='gold', alpha=0.7)
    ax.set_title('Daily Fees Earned')
    ax.set_ylabel('Fees ($)')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(date_format)
    
    # Add cumulative line
    ax2 = ax.twinx()
    ax2.plot(df['date'], df['cumulative_fees'], 'orange', linewidth=2)
    ax2.set_ylabel('Cumulative ($)', color='orange')
    ax2.tick_params(axis='y', labelcolor='orange')
    
    # 5. Daily Volume
    ax = axes[4]
    
    volume_scale = 1e6 if df['volume'].max() > 1e6 else 1e3
    scale_label = 'M' if volume_scale == 1e6 else 'K'
    
    ax.bar(df['date'], df['volume'] / volume_scale, color='steelblue', alpha=0.7)
    ax.set_title('Daily Trading Volume')
    ax.set_ylabel(f'Volume (${scale_label})')
    ax.grid(True, alpha=0.3)
    
    # Add 7-day moving average if we have enough data
    if len(df) >= 7:
        df['volume_ma7'] = df['volume'].rolling(window=7).mean()
        ax.plot(df['date'], df['volume_ma7'] / volume_scale, 'r-', linewidth=2, label='7-day MA')
        ax.legend()
    
    ax.xaxis.set_major_formatter(date_format)
    
    # 6. APR Over Time
    ax = axes[5]
    
    ax.plot(df['date'], df['apr'], 'purple', linewidth=2)
    ax.fill_between(df['date'], 0, df['apr'], alpha=0.3, color='purple')
    ax.set_title('APR (1-day trailing)')
    ax.set_ylabel('APR (%)')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax.xaxis.set_major_formatter(date_format)
    
    # Add average APR
    avg_apr = df['apr'].mean()
    ax.axhline(y=avg_apr, color='red', linestyle='--', alpha=0.5, label=f'Avg: {avg_apr:.2f}%')
    ax.legend()
    
    plt.tight_layout()
    
    # Save figure
    import os
    os.makedirs('data', exist_ok=True)
    
    # Create filename with pool prefix
    pool_prefix = pool_addr[:6] if pool_addr.startswith('0x') else ''
    output_file = f'data/account_nav_{token0}_{token1}_{pool_prefix}.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Graph saved as '{output_file}'")
    
    return fig

def print_account_nav_summary(df: pd.DataFrame):
    """Print comprehensive summary statistics for account NAV data."""
    
    token0 = df.attrs.get('token0_symbol', 'TOKEN0')
    token1 = df.attrs.get('token1_symbol', 'TOKEN1')
    pool_addr = df.attrs.get('pool_address', '')
    
    print("\n" + "="*70)
    print("ACCOUNT NAV SUMMARY (V2 API)")
    print("="*70)
    
    if pool_addr:
        print(f"Pool: {pool_addr}")
    print(f"Pair: {token0}/{token1}")
    print(f"Period: {df['date'].iloc[0].strftime('%Y-%m-%d')} to {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"Days: {len(df)}")
    print(f"Active Vaults: {df['active_vaults'].iloc[-1] if not df.empty else 0}")
    
    # NAV Performance
    initial_nav = df['nav_usd'].iloc[0]
    final_nav = df['nav_usd'].iloc[-1]
    nav_change = final_nav - initial_nav
    nav_return = ((final_nav/initial_nav - 1) * 100) if initial_nav > 0 else 0
    days = len(df)
    annualized_return = nav_return * (365 / days) if days > 0 else 0
    
    print(f"\nAccount NAV Performance:")
    print(f"  Starting NAV: ${initial_nav:,.2f}")
    print(f"  Ending NAV: ${final_nav:,.2f}")
    print(f"  Change: ${nav_change:+,.2f} ({nav_return:+.2f}%)")
    print(f"  Annualized Return: {annualized_return:.2f}%")
    
    # Assets and Borrowed
    initial_assets = df['total_assets_usd'].iloc[0]
    final_assets = df['total_assets_usd'].iloc[-1]
    initial_borrowed = df['total_borrowed_usd'].iloc[0]
    final_borrowed = df['total_borrowed_usd'].iloc[-1]
    
    print(f"\nAssets & Borrowed:")
    print(f"  Initial Assets: ${initial_assets:,.2f}")
    print(f"  Final Assets: ${final_assets:,.2f}")
    print(f"  Initial Borrowed: ${initial_borrowed:,.2f}")
    print(f"  Final Borrowed: ${final_borrowed:,.2f}")
    
    avg_leverage = df['total_borrowed_usd'].mean() / df['nav_usd'].mean() if df['nav_usd'].mean() > 0 else 0
    print(f"  Average Leverage: {avg_leverage:.2f}x")
    
    # Interest Analysis
    total_earned = df['interest_earned'].sum()
    total_paid = df['interest_paid'].sum()
    net_interest = df['net_interest'].sum()
    
    print(f"\nInterest Summary:")
    print(f"  Total Earned: ${total_earned:,.2f}")
    print(f"  Total Paid: ${total_paid:,.2f}")
    print(f"  Net Interest: ${net_interest:+,.2f}")
    
    # Daily averages
    avg_daily_earned = df['interest_earned'].mean()
    avg_daily_paid = df['interest_paid'].mean()
    avg_daily_net = df['net_interest'].mean()
    
    print(f"  Daily Avg Earned: ${avg_daily_earned:,.2f}")
    print(f"  Daily Avg Paid: ${avg_daily_paid:,.2f}")
    print(f"  Daily Avg Net: ${avg_daily_net:+,.2f}")
    
    # Fee Analysis
    total_fees = df['fees'].sum()
    avg_daily_fees = df['fees'].mean()
    fee_return = (total_fees / initial_nav * 100) if initial_nav > 0 else 0
    fee_apr = fee_return * (365 / days) if days > 0 else 0
    
    print(f"\nFee Summary:")
    print(f"  Total Fees: ${total_fees:,.2f}")
    print(f"  Daily Average: ${avg_daily_fees:,.2f}")
    print(f"  Fee Return: {fee_return:.2f}%")
    print(f"  Fee APR: {fee_apr:.2f}%")
    
    # Volume Analysis
    total_volume = df['volume'].sum()
    avg_daily_volume = df['volume'].mean()
    max_daily_volume = df['volume'].max()
    
    print(f"\nVolume Summary:")
    print(f"  Total Volume: ${total_volume:,.0f}")
    print(f"  Daily Average: ${avg_daily_volume:,.0f}")
    print(f"  Max Daily: ${max_daily_volume:,.0f}")
    
    # APR Analysis
    avg_apr = df['apr'].mean()
    max_apr = df['apr'].max()
    min_apr = df['apr'].min()
    current_apr = df['apr'].iloc[-1]
    
    print(f"\nAPR Metrics:")
    print(f"  Current APR: {current_apr:.2f}%")
    print(f"  Average APR: {avg_apr:.2f}%")
    print(f"  Max APR: {max_apr:.2f}%")
    print(f"  Min APR: {min_apr:.2f}%")
    
    # Component Returns
    print(f"\nReturn Components:")
    print(f"  Base Return: {nav_return:.2f}%")
    print(f"  - From Fees: {fee_return:.2f}%")
    interest_return = (net_interest / initial_nav * 100) if initial_nav > 0 else 0
    print(f"  - From Net Interest: {interest_return:.2f}%")
    other_return = nav_return - fee_return - interest_return
    print(f"  - Other (Price/Rebalancing): {other_return:.2f}%")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyze account NAV data from V2 API")
    parser.add_argument("--input", required=True, help="Input JSON file from daily_account_nav.py")
    parser.add_argument("--no-plot", action="store_true", help="Skip plotting, only show summary")
    
    args = parser.parse_args()
    
    # Load and parse data
    df = parse_account_nav_data(args.input)
    
    if df.empty:
        print(f"No data parsed from {args.input}")
        return
    
    print(f"Loaded {len(df)} days of account NAV data")
    
    # Create visualizations unless skipped
    if not args.no_plot:
        fig = create_account_nav_charts(df)
    
    # Print summary statistics
    print_account_nav_summary(df)
    
    # Show plot
    if not args.no_plot:
        plt.show()

if __name__ == "__main__":
    main()