#!/usr/bin/env python3
"""
Track complete NAV history for an account across all its pool deployments.
Chains together data from multiple pools to show the full account journey.
"""
import argparse
import json
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from tabulate import tabulate
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from daily_account_nav import get_block_by_timestamp, parse_nav_value, retry_with_backoff
from pool_cache import get_pool_deployment_info
from utils import get_token_symbol

# API endpoints
V2_API = "https://index-dev.eul.dev/v2/swap/pools"
DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"


def find_account_pools_from_map(euler_account: str) -> List[Dict]:
    """Find all pools for an account from the complete pool map."""
    
    try:
        # Load the complete pool map if it exists
        with open('complete_pool_map.json', 'r') as f:
            pool_map = json.load(f)
        
        account_pools = []
        for pool_addr, info in pool_map.items():
            if info.get('account', '').lower() == euler_account.lower():
                account_pools.append({
                    'pool': pool_addr,
                    'created_at': info.get('created_at', 0),
                    'created_date': info.get('created_date', 'Unknown'),
                    'active': info.get('active', False),
                    'token0_symbol': info.get('token0_symbol', ''),
                    'token1_symbol': info.get('token1_symbol', ''),
                    'token0_addr': info.get('token0_addr', ''),
                    'token1_addr': info.get('token1_addr', ''),
                    'current_nav': info.get('current_nav', 0)
                })
        
        # Sort by creation date
        account_pools.sort(key=lambda x: x['created_at'])
        return account_pools
        
    except FileNotFoundError:
        print("Warning: complete_pool_map.json not found. Run build_complete_pool_map.py first.")
        return []


def fetch_account_nav_at_block(euler_account: str, block: int, chain_id: int = 1) -> Dict:
    """Fetch account NAV data at a specific block, aggregating all active pools."""
    
    params = {
        'chainId': chain_id,
        'blockNumber': block
    }
    
    r = retry_with_backoff(requests.get, V2_API, params=params)
    all_pools = r.json()
    
    # Find all pools for this account at this block
    account_data = {
        'nav': 0,
        'total_assets': 0,
        'total_borrowed': 0,
        'pools': [],
        'interest_earned_1d': 0,
        'interest_paid_1d': 0,
        'fees_1d': 0,
        'volume_1d': 0,
        'apr_sum': 0,
        'apr_count': 0
    }
    
    for pool in all_pools:
        # Check if this pool belongs to the account
        pool_account = pool.get('account', '').lower()
        
        # Handle different case variations
        if pool_account == euler_account.lower():
            # This pool belongs to our account
            account_nav = pool.get('accountNav', {})
            
            # Aggregate NAV values
            nav = parse_nav_value(account_nav.get('nav', '0'))
            assets = parse_nav_value(account_nav.get('totalAssets', '0'))
            borrowed = parse_nav_value(account_nav.get('totalBorrowed', '0'))
            
            account_data['nav'] += nav
            account_data['total_assets'] += assets
            account_data['total_borrowed'] += borrowed
            
            # Get token info
            vault0 = pool.get('vault0', {})
            vault1 = pool.get('vault1', {})
            token0_symbol = get_token_symbol(vault0.get('asset', ''))
            token1_symbol = get_token_symbol(vault1.get('asset', ''))
            
            # Add pool info
            account_data['pools'].append({
                'pool': pool['pool'],
                'nav': nav,
                'pair': f"{token0_symbol}/{token1_symbol}",
                'active': pool.get('active', False)
            })
            
            # Aggregate metrics
            interest_earned = pool.get('interestEarned', {})
            interest_paid = pool.get('interestPaid', {})
            fees = pool.get('fees', {})
            volume = pool.get('volume', {})
            apr = pool.get('apr', {})
            
            account_data['interest_earned_1d'] += parse_nav_value(interest_earned.get('total1d', '0'))
            account_data['interest_paid_1d'] += parse_nav_value(interest_paid.get('total1d', '0'))
            account_data['fees_1d'] += parse_nav_value(fees.get('total1d', '0'))
            account_data['volume_1d'] += parse_nav_value(volume.get('total1d', '0'))
            
            # For APR, we'll average across pools
            apr_val = float(apr.get('total1d', '0')) / 1e18 * 100 if apr.get('total1d') else 0
            if apr_val != 0:
                account_data['apr_sum'] += apr_val
                account_data['apr_count'] += 1
    
    # Calculate average APR
    if account_data['apr_count'] > 0:
        account_data['apr'] = account_data['apr_sum'] / account_data['apr_count']
    else:
        account_data['apr'] = 0
    
    return account_data


def get_account_nav_history(euler_account: str, days: int = 30, chain_id: int = 1) -> List[Dict]:
    """Get daily NAV history for an account across all its pools."""
    
    # Find all pools for this account
    print(f"Finding all pools for account {euler_account[:10]}...")
    account_pools = find_account_pools_from_map(euler_account)
    
    if not account_pools:
        print("No pools found for this account")
        return []
    
    print(f"Found {len(account_pools)} pool(s) for account:")
    for pool in account_pools:
        status = "ACTIVE" if pool['active'] else "inactive"
        print(f"  - {pool['pool'][:10]}... {pool['token0_symbol']}/{pool['token1_symbol']} ({pool['created_date']}) - {status}")
    
    # Calculate date range
    now = datetime.now()
    start_date = now - timedelta(days=days)
    current_date = start_date
    
    print(f"\nFetching daily account NAV history")
    print(f"From {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")
    print("-" * 80)
    
    daily_data = []
    
    while current_date <= now:
        timestamp = int(current_date.timestamp())
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Get block at this timestamp
        block = get_block_by_timestamp(timestamp)
        
        try:
            # Fetch aggregated account data at this block
            account_data = fetch_account_nav_at_block(euler_account, block, chain_id)
            
            if account_data['nav'] > 0 or len(account_data['pools']) > 0:
                # Account has data at this block
                daily_data.append({
                    'date': date_str,
                    'block': block,
                    'nav_usd': account_data['nav'],
                    'total_assets_usd': account_data['total_assets'],
                    'total_borrowed_usd': account_data['total_borrowed'],
                    'num_pools': len(account_data['pools']),
                    'pools': account_data['pools'],
                    'interest_earned': account_data['interest_earned_1d'],
                    'interest_paid': account_data['interest_paid_1d'],
                    'net_interest': account_data['interest_earned_1d'] - account_data['interest_paid_1d'],
                    'fees': account_data['fees_1d'],
                    'volume': account_data['volume_1d'],
                    'apr': account_data['apr']
                })
                
                # Show active pools
                active_pools = [p for p in account_data['pools'] if p['active']]
                if active_pools:
                    pool_str = ', '.join([f"{p['pair']}" for p in active_pools[:3]])
                    if len(active_pools) > 3:
                        pool_str += f" +{len(active_pools)-3}"
                    print(f"  {date_str}: NAV ${account_data['nav']:,.0f} ({len(active_pools)} pools: {pool_str})")
                else:
                    print(f"  {date_str}: NAV ${account_data['nav']:,.0f} (no active pools)")
            else:
                print(f"  {date_str}: No data")
                
        except Exception as e:
            print(f"  {date_str}: Error - {e}")
        
        current_date += timedelta(days=1)
    
    return daily_data


def plot_account_history(daily_data: List[Dict], euler_account: str):
    """Create comprehensive visualization of account history."""
    
    if not daily_data:
        print("No data to plot")
        return
    
    # Convert to DataFrame
    df = pd.DataFrame(daily_data)
    df['date'] = pd.to_datetime(df['date'])
    
    # Create figure with 6 subplots
    fig, axes = plt.subplots(3, 2, figsize=(15, 12))
    axes = axes.flatten()
    
    # Add title
    title = f'Account NAV History: {euler_account[:10]}...'
    fig.suptitle(title, fontsize=16, fontweight='bold')
    
    date_format = mdates.DateFormatter('%m/%d')
    
    # 1. Total Account NAV
    ax = axes[0]
    nav_scale = 1e6 if df['nav_usd'].max() > 1e6 else 1e3
    scale_label = 'M' if nav_scale == 1e6 else 'K'
    
    ax.plot(df['date'], df['nav_usd'] / nav_scale, 'b-', linewidth=2)
    ax.set_title('Total Account NAV (All Pools)')
    ax.set_ylabel(f'NAV (${scale_label})')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(date_format)
    
    # Add return annotation
    if len(df) > 1 and df['nav_usd'].iloc[0] > 0:
        initial_nav = df['nav_usd'].iloc[0]
        final_nav = df['nav_usd'].iloc[-1]
        total_return = ((final_nav/initial_nav - 1) * 100)
        annualized = total_return * (365 / len(df))
        ax.text(0.02, 0.98, f'Return: {total_return:.1f}%\nAnnualized: {annualized:.1f}%',
                transform=ax.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
    
    # 2. Number of Active Pools
    ax = axes[1]
    ax.bar(df['date'], df['num_pools'], color='green', alpha=0.7)
    ax.set_title('Number of Active Pools')
    ax.set_ylabel('Pool Count')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(date_format)
    
    # 3. Assets vs Borrowed
    ax = axes[2]
    assets_scale = 1e6 if df['total_assets_usd'].max() > 1e6 else 1e3
    scale_label = 'M' if assets_scale == 1e6 else 'K'
    
    ax.plot(df['date'], df['total_assets_usd'] / assets_scale, 'g-', linewidth=2, label='Assets')
    ax.plot(df['date'], df['total_borrowed_usd'] / assets_scale, 'r-', linewidth=2, label='Borrowed')
    ax.fill_between(df['date'], df['total_assets_usd'] / assets_scale,
                     df['total_borrowed_usd'] / assets_scale, alpha=0.3, color='green')
    ax.set_title('Total Assets vs Borrowed')
    ax.set_ylabel(f'Value (${scale_label})')
    ax.legend()
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(date_format)
    
    # 4. Net Interest
    ax = axes[3]
    colors = ['green' if x >= 0 else 'red' for x in df['net_interest']]
    ax.bar(df['date'], df['net_interest'], color=colors, alpha=0.7)
    ax.set_title('Daily Net Interest (Earned - Paid)')
    ax.set_ylabel('Net Interest ($)')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax.xaxis.set_major_formatter(date_format)
    
    # 5. Daily Volume
    ax = axes[4]
    volume_scale = 1e6 if df['volume'].max() > 1e6 else 1e3
    scale_label = 'M' if volume_scale == 1e6 else 'K'
    
    ax.bar(df['date'], df['volume'] / volume_scale, color='steelblue', alpha=0.7)
    ax.set_title('Daily Trading Volume (All Pools)')
    ax.set_ylabel(f'Volume (${scale_label})')
    ax.grid(True, alpha=0.3)
    ax.xaxis.set_major_formatter(date_format)
    
    # 6. Average APR
    ax = axes[5]
    ax.plot(df['date'], df['apr'], 'purple', linewidth=2)
    ax.fill_between(df['date'], 0, df['apr'], alpha=0.3, color='purple')
    ax.set_title('Average APR Across Pools')
    ax.set_ylabel('APR (%)')
    ax.grid(True, alpha=0.3)
    ax.axhline(y=0, color='black', linestyle='-', alpha=0.5)
    ax.xaxis.set_major_formatter(date_format)
    
    # Add average line
    avg_apr = df['apr'].mean()
    ax.axhline(y=avg_apr, color='red', linestyle='--', alpha=0.5, label=f'Avg: {avg_apr:.2f}%')
    ax.legend()
    
    plt.tight_layout()
    
    # Save figure
    import os
    os.makedirs('data', exist_ok=True)
    output_file = f'data/account_history_{euler_account[:10]}.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"\nGraph saved as '{output_file}'")
    
    return fig


def display_summary(daily_data: List[Dict], euler_account: str):
    """Display summary statistics for account history."""
    
    if not daily_data:
        return
    
    df = pd.DataFrame(daily_data)
    
    print("\n" + "="*80)
    print("ACCOUNT HISTORY SUMMARY")
    print("="*80)
    print(f"Account: {euler_account}")
    print(f"Period: {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
    print(f"Days tracked: {len(df)}")
    
    # NAV Performance
    initial_nav = df['nav_usd'].iloc[0]
    final_nav = df['nav_usd'].iloc[-1]
    
    if initial_nav > 0:
        nav_change = final_nav - initial_nav
        nav_return = ((final_nav/initial_nav - 1) * 100)
        annualized = nav_return * (365 / len(df))
        
        print(f"\nNAV Performance:")
        print(f"  Starting NAV: ${initial_nav:,.2f}")
        print(f"  Ending NAV: ${final_nav:,.2f}")
        print(f"  Change: ${nav_change:+,.2f} ({nav_return:+.2f}%)")
        print(f"  Annualized Return: {annualized:.2f}%")
    
    # Pool Activity
    max_pools = df['num_pools'].max()
    avg_pools = df['num_pools'].mean()
    
    print(f"\nPool Activity:")
    print(f"  Maximum concurrent pools: {max_pools}")
    print(f"  Average active pools: {avg_pools:.1f}")
    
    # Find unique pools
    all_pools = set()
    for row in daily_data:
        for pool in row['pools']:
            all_pools.add(f"{pool['pool']}:{pool['pair']}")
    
    print(f"  Unique pools operated: {len(all_pools)}")
    
    # Interest and Fees
    total_interest_earned = df['interest_earned'].sum()
    total_interest_paid = df['interest_paid'].sum()
    net_interest = df['net_interest'].sum()
    total_fees = df['fees'].sum()
    
    print(f"\nInterest & Fees:")
    print(f"  Total Interest Earned: ${total_interest_earned:,.2f}")
    print(f"  Total Interest Paid: ${total_interest_paid:,.2f}")
    print(f"  Net Interest: ${net_interest:+,.2f}")
    print(f"  Total Fees Earned: ${total_fees:,.2f}")
    
    # Volume
    total_volume = df['volume'].sum()
    avg_daily_volume = df['volume'].mean()
    
    print(f"\nVolume:")
    print(f"  Total Volume: ${total_volume:,.0f}")
    print(f"  Daily Average: ${avg_daily_volume:,.0f}")
    
    # APR
    avg_apr = df['apr'].mean()
    max_apr = df['apr'].max()
    current_apr = df['apr'].iloc[-1]
    
    print(f"\nAPR Metrics:")
    print(f"  Current APR: {current_apr:.2f}%")
    print(f"  Average APR: {avg_apr:.2f}%")
    print(f"  Max APR: {max_apr:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Track complete NAV history for an account")
    parser.add_argument("--account", required=True, help="Euler account address")
    parser.add_argument("--days", type=int, default=30, help="Number of days of history (default: 30)")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--output", help="Output JSON file")
    parser.add_argument("--no-plot", action="store_true", help="Skip plotting")
    
    args = parser.parse_args()
    
    try:
        # Get account history
        daily_data = get_account_nav_history(args.account, args.days, args.chain)
        
        if not daily_data:
            print("No data found for account")
            return 1
        
        # Display summary
        display_summary(daily_data, args.account)
        
        # Create plots unless skipped
        if not args.no_plot:
            plot_account_history(daily_data, args.account)
            plt.show()
        
        # Save to file if requested
        if args.output:
            output_data = {
                'account': args.account,
                'chain_id': args.chain,
                'daily_data': daily_data
            }
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"\nData saved to {args.output}")
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())