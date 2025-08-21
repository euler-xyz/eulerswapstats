#!/usr/bin/env python3
"""
Fetch daily account NAV history using V2 API's accountNav field.
This uses the pre-calculated NAV from the API which includes all vault positions.
"""
import argparse
import json
import requests
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from tabulate import tabulate
from pool_cache import get_pool_creation_block
from utils import get_token_symbol

# API endpoints
V2_API = "https://index-dev.eul.dev/v2/swap/pools"
DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"

# Retry settings
MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 1
MAX_RETRY_DELAY = 30


def retry_with_backoff(func, *args, **kwargs):
    """Retry a function with exponential backoff for server errors."""
    for attempt in range(MAX_RETRIES):
        try:
            response = func(*args, **kwargs)
            if response.status_code in [500, 502, 503, 504, '500']:
                if attempt == MAX_RETRIES - 1:
                    raise Exception(f"Failed after {MAX_RETRIES} retries - {response.status_code} Server Error")
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"  Server error {response.status_code}, retrying in {delay}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(delay)
                continue
            response.raise_for_status()
            return response
        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES - 1:
                raise
            if "500" in str(e) or "Server Error" in str(e):
                delay = min(INITIAL_RETRY_DELAY * (2 ** attempt), MAX_RETRY_DELAY)
                print(f"  Request error, retrying in {delay}s... (attempt {attempt + 1}/{MAX_RETRIES})")
                time.sleep(delay)
                continue
            raise
    raise Exception(f"Failed after {MAX_RETRIES} retries")


def get_block_by_timestamp(timestamp: int) -> int:
    """Get block number at or after a given timestamp using Etherscan API or estimation."""
    import os
    
    # Try Etherscan API first (much faster than binary search)
    etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
    if etherscan_api_key:
        try:
            url = "https://api.etherscan.io/api"
            params = {
                'module': 'block',
                'action': 'getblocknobytime',
                'timestamp': timestamp,
                'closest': 'after',
                'apikey': etherscan_api_key
            }
            
            r = requests.get(url, params=params, timeout=10)
            data = r.json()
            
            if data.get('status') == '1' and data.get('result'):
                block_number = int(data['result'])
                return block_number
        except Exception as e:
            print(f"  Warning: Etherscan API failed ({e}), falling back to estimation")
    
    # Fallback: Estimate block based on ~12 second block time
    reference_block = 23179760
    reference_timestamp = 1755715200  # 2025-08-20 12:00:00 UTC
    
    seconds_diff = timestamp - reference_timestamp
    blocks_diff = seconds_diff // 12
    estimated_block = reference_block + blocks_diff
    
    return max(estimated_block, 1)


def fetch_account_nav_at_block(pool_address: str, block: int, chain_id: int = 1) -> Dict:
    """Fetch account NAV from V2 API at a specific block."""
    params = {
        'chainId': chain_id,
        'blockNumber': block
    }
    
    r = retry_with_backoff(requests.get, V2_API, params=params)
    all_pools = r.json()
    
    # Find the specific pool
    data = None
    for p in all_pools:
        if p.get('pool', '').lower() == pool_address.lower():
            data = [p]
            break
    
    if not data or len(data) == 0:
        raise RuntimeError(f"No data found for pool {pool_address} at block {block}")
    
    pool = data[0]
    account_nav = pool.get('accountNav', {})
    
    # Extract the key values
    nav = account_nav.get('nav', '0')
    total_assets = account_nav.get('totalAssets', '0')
    total_borrowed = account_nav.get('totalBorrowed', '0')
    breakdown = account_nav.get('breakdown', {})
    
    # Count active vaults
    active_vaults = len(breakdown)
    
    # Get primary vault info
    vault0 = pool.get('vault0', {})
    vault1 = pool.get('vault1', {})
    
    # Extract interest data
    interest_paid = pool.get('interestPaid', {})
    interest_earned = pool.get('interestEarned', {})
    
    # Extract fee and volume data
    fees = pool.get('fees', {})
    volume = pool.get('volume', {})
    
    # Extract APR data
    apr = pool.get('apr', {})
    swap_fees_apr = pool.get('swapFeesAPR', {})
    interest_apr = pool.get('interestApr', {})
    
    # Extract liquidity
    available_liquidity = pool.get('availableLiquidity', '0')
    
    return {
        'nav': nav,
        'total_assets': total_assets,
        'total_borrowed': total_borrowed,
        'active_vaults': active_vaults,
        'vault0_asset': vault0.get('asset', ''),
        'vault1_asset': vault1.get('asset', ''),
        'vault0_decimals': vault0.get('decimals', 18),
        'vault1_decimals': vault1.get('decimals', 18),
        'breakdown': breakdown,
        # New fields
        'interest_paid_total': interest_paid.get('total', '0'),
        'interest_paid_1d': interest_paid.get('total1d', '0'),
        'interest_earned_total': interest_earned.get('total', '0'),
        'interest_earned_1d': interest_earned.get('total1d', '0'),
        'fees_total': fees.get('total', '0'),
        'fees_1d': fees.get('total1d', '0'),
        'volume_total': volume.get('total', '0'),
        'volume_1d': volume.get('total1d', '0'),
        'apr_1d': apr.get('total1d', '0'),
        'swap_fees_apr_1d': swap_fees_apr.get('total1d', '0'),
        'interest_apr_1d': interest_apr.get('total1d', '0'),
        'available_liquidity': available_liquidity,
        'price': pool.get('price', '0'),
        'fee': pool.get('fee', '0')
    }


def parse_nav_value(nav_str: str, decimals: int = 18) -> float:
    """Parse NAV string value to USD float.
    
    The NAV from the V2 API appears to be already scaled to USD cents (1e8).
    Based on empirical testing:
    - Most pools use 1e8 scale (USD with 8 decimal places)
    - This gives reasonable USD values for pool NAVs
    """
    try:
        nav_raw = int(nav_str)
        # The V2 API appears to use 1e8 scale for USD values
        # (similar to how Bitcoin uses satoshis)
        return nav_raw / 1e8
        
    except (ValueError, TypeError):
        return 0.0


def get_daily_account_nav_history(pool_address: str, chain_id: int = 1, days: int = 30) -> List[Dict]:
    """Get daily account NAV history for a pool using V2 API."""
    
    # Get pool creation info
    created_at, creation_block = get_pool_creation_block(pool_address, chain_id)
    
    # Get current pool info for token symbols
    # Note: When querying by pool address, the V2 API returns the pool where this is the pool address
    r = retry_with_backoff(requests.get, V2_API, params={"chainId": chain_id})
    all_pools = r.json()
    
    # Find the pool by address
    current_pool = None
    for p in all_pools:
        if p.get('pool', '').lower() == pool_address.lower():
            current_pool = p
            break
    
    if not current_pool:
        raise RuntimeError(f"Pool {pool_address} not found")
    
    vault0 = current_pool.get('vault0', {})
    vault1 = current_pool.get('vault1', {})
    token0_addr = vault0.get('asset', '')
    token1_addr = vault1.get('asset', '')
    token0_symbol = get_token_symbol(token0_addr) if token0_addr else 'Token0'
    token1_symbol = get_token_symbol(token1_addr) if token1_addr else 'Token1'
    
    # Calculate date range
    now = datetime.now()
    start_date = now - timedelta(days=days)
    current_date = start_date
    
    print(f"Fetching daily account NAV history for {token0_symbol}/{token1_symbol}")
    print(f"From {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")
    print("-" * 80)
    
    daily_data = []
    
    while current_date <= now:
        timestamp = int(current_date.timestamp())
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Get block at this timestamp
        block = get_block_by_timestamp(timestamp)
        
        # Skip if before pool creation
        if block < creation_block:
            print(f"  {date_str}: Skipped (before pool creation)")
            current_date += timedelta(days=1)
            continue
        
        try:
            # Fetch account NAV at this block
            nav_data = fetch_account_nav_at_block(pool_address, block, chain_id)
            
            # Parse the NAV value to USD
            nav_usd = parse_nav_value(nav_data['nav'])
            assets_usd = parse_nav_value(nav_data['total_assets'])
            borrowed_usd = parse_nav_value(nav_data['total_borrowed'])
            
            # Parse additional metrics
            interest_earned = parse_nav_value(nav_data['interest_earned_1d'])
            interest_paid = parse_nav_value(nav_data['interest_paid_1d'])
            net_interest = interest_earned - interest_paid
            fees_1d = parse_nav_value(nav_data['fees_1d'])
            volume_1d = parse_nav_value(nav_data['volume_1d'])
            apr_1d = float(nav_data['apr_1d']) / 1e18 if nav_data['apr_1d'] else 0
            
            daily_data.append({
                'date': date_str,
                'block': block,
                'nav_usd': nav_usd,
                'total_assets_usd': assets_usd,
                'total_borrowed_usd': borrowed_usd,
                'active_vaults': nav_data['active_vaults'],
                'nav_raw': nav_data['nav'],
                'token0_symbol': token0_symbol,
                'token1_symbol': token1_symbol,
                'interest_earned': interest_earned,
                'interest_paid': interest_paid,
                'net_interest': net_interest,
                'fees': fees_1d,
                'volume': volume_1d,
                'apr': apr_1d * 100  # Convert to percentage
            })
            
            print(f"  {date_str}: Block {block:,} - NAV ${nav_usd:,.2f} ({nav_data['active_vaults']} vaults)")
            
        except Exception as e:
            print(f"  {date_str}: Failed - {e}")
            daily_data.append({
                'date': date_str,
                'block': block,
                'nav_usd': None,
                'total_assets_usd': None,
                'total_borrowed_usd': None,
                'active_vaults': 0,
                'nav_raw': None,
                'token0_symbol': token0_symbol,
                'token1_symbol': token1_symbol,
                'interest_earned': 0,
                'interest_paid': 0,
                'net_interest': 0,
                'fees': 0,
                'volume': 0,
                'apr': 0
            })
        
        current_date += timedelta(days=1)
    
    return daily_data


def display_results(daily_data: List[Dict]):
    """Display the results in a formatted table."""
    
    # Prepare table data
    table_data = []
    prev_nav = None
    
    for day in daily_data:
        nav = day['nav_usd']
        
        # Calculate change
        change = None
        change_pct = None
        if nav is not None and prev_nav is not None:
            change = nav - prev_nav
            change_pct = (change / prev_nav) * 100 if prev_nav != 0 else 0
        
        # Format row
        row = [
            day['date'],
            day['block'] if day['block'] else 'N/A',
            f"${nav:,.0f}" if nav is not None else 'N/A',
            f"${day['total_assets_usd']:,.0f}" if day['total_assets_usd'] is not None else 'N/A',
            f"${day['total_borrowed_usd']:,.0f}" if day['total_borrowed_usd'] is not None else 'N/A',
            f"${change:+,.0f}" if change is not None else '',
            f"{change_pct:+.2f}%" if change_pct is not None else '',
            day['active_vaults'] if day['active_vaults'] else 'N/A'
        ]
        table_data.append(row)
        
        if nav is not None:
            prev_nav = nav
    
    # Display table
    headers = ['Date', 'Block', 'Account NAV', 'Total Assets', 'Total Borrowed', 'Change', 'Change %', 'Vaults']
    
    print("\n" + "=" * 120)
    print("DAILY ACCOUNT NAV HISTORY (V2 API)")
    print("=" * 120)
    print(tabulate(table_data, headers=headers, tablefmt='grid'))
    
    # Calculate summary statistics
    valid_navs = [d['nav_usd'] for d in daily_data if d['nav_usd'] is not None]
    if len(valid_navs) >= 2:
        start_nav = valid_navs[0]
        end_nav = valid_navs[-1]
        total_change = end_nav - start_nav
        total_change_pct = (total_change / start_nav) * 100 if start_nav != 0 else 0
        
        print("\n" + "=" * 120)
        print("SUMMARY")
        print("=" * 120)
        print(f"Period: {daily_data[0]['date']} to {daily_data[-1]['date']}")
        print(f"Starting NAV: ${start_nav:,.2f}")
        print(f"Ending NAV: ${end_nav:,.2f}")
        print(f"Total Change: ${total_change:+,.2f} ({total_change_pct:+.2f}%)")
        print(f"Days with data: {len(valid_navs)}")
        
        if len(valid_navs) > 1:
            daily_changes = []
            for i in range(1, len(valid_navs)):
                daily_change = (valid_navs[i] - valid_navs[i-1]) / valid_navs[i-1] * 100
                daily_changes.append(daily_change)
            
            avg_daily_change = sum(daily_changes) / len(daily_changes)
            annualized = avg_daily_change * 365
            
            print(f"Average Daily Change: {avg_daily_change:+.2f}%")
            print(f"Annualized Return: {annualized:+.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Fetch daily account NAV history using V2 API")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--days", type=int, default=30, help="Number of days of history (default: 30)")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1 for Ethereum)")
    parser.add_argument("--output", help="Output JSON file")
    
    args = parser.parse_args()
    
    try:
        # Fetch daily data
        daily_data = get_daily_account_nav_history(args.pool, args.chain, args.days)
        
        # Display results
        display_results(daily_data)
        
        # Save to file if requested
        if args.output:
            output_data = {
                'pool': args.pool,
                'chain_id': args.chain,
                'daily_data': daily_data
            }
            with open(args.output, 'w') as f:
                json.dump(output_data, f, indent=2)
            print(f"\nData saved to {args.output}")
    
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())