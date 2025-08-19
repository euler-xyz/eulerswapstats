#!/usr/bin/env python3
"""
Show daily NAV history for a pool along with token prices.
"""
import argparse
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from tabulate import tabulate
from netnav import calculate_net_nav, fetch_pool_data, fetch_price
from pool_cache import get_pool_creation_block
from utils import get_token_symbol

# API endpoints
V1_API = "https://index-dev.eul.dev/v1/swap/pools"
V2_API = "https://index-dev.eul.dev/v2/swap/pools"
DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"
DEFAULT_RPC_URL = "https://ethereum.publicnode.com"


def rpc_call(rpc_url: str, method: str, params: list):
    """Make RPC call to Ethereum node."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(rpc_url, json=payload, timeout=30)
    r.raise_for_status()
    js = r.json()
    if "error" in js and js["error"]:
        raise RuntimeError(f"RPC error: {js['error']}")
    return js.get("result")


def get_block_by_timestamp(timestamp: int) -> int:
    """Get block number at or after a given timestamp."""
    # Use binary search to find the block
    head_hex = rpc_call(DEFAULT_RPC_URL, "eth_blockNumber", [])
    head = int(head_hex, 16)
    
    def get_block_timestamp(block_num: int) -> int:
        block_hex = hex(block_num)
        block_data = rpc_call(DEFAULT_RPC_URL, "eth_getBlockByNumber", [block_hex, False])
        if not block_data:
            return None
        return int(block_data["timestamp"], 16)
    
    # Binary search
    left, right = 0, head
    result = head
    
    while left <= right:
        mid = (left + right) // 2
        mid_ts = get_block_timestamp(mid)
        
        if mid_ts is None:
            right = mid - 1
            continue
            
        if mid_ts >= timestamp:
            result = mid
            right = mid - 1
        else:
            left = mid + 1
    
    return result


def get_daily_nav_history(pool_address: str, chain_id: int = 1, days: int = 30) -> List[Dict]:
    """Get daily NAV history for a pool."""
    
    # Get pool creation info
    created_at, creation_block = get_pool_creation_block(pool_address, chain_id)
    creation_date = datetime.fromtimestamp(created_at)
    
    # Get current time
    now = datetime.now()
    
    # Determine start date (either creation or N days ago)
    start_date = max(creation_date, now - timedelta(days=days))
    
    # Generate daily timestamps from start to now
    daily_data = []
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get token info from V2 API
    r = requests.get(V2_API, params={"chainId": chain_id})
    pools_v2 = r.json()
    token0_addr = None
    token1_addr = None
    
    for p in pools_v2:
        if p['pool'].lower() == pool_address.lower():
            vault0 = p.get('vault0', {})
            vault1 = p.get('vault1', {})
            token0_addr = vault0.get('asset', '')
            token1_addr = vault1.get('asset', '')
            break
    
    token0_symbol = get_token_symbol(token0_addr) if token0_addr else 'Token0'
    token1_symbol = get_token_symbol(token1_addr) if token1_addr else 'Token1'
    
    print(f"Fetching daily NAV history for {token0_symbol}/{token1_symbol}")
    print(f"From {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")
    print("-" * 80)
    
    while current_date <= now:
        timestamp = int(current_date.timestamp())
        
        # Get block at this timestamp
        try:
            block = get_block_by_timestamp(timestamp)
            
            # Fetch pool data at this block
            pool_data = fetch_pool_data(V1_API, chain_id, pool_address, block)
            
            # Calculate NAV
            nav_result = calculate_net_nav(pool_data, DEFAULT_GRAPHQL, chain_id, block)
            
            # Get prices at this block
            price0, _ = fetch_price(DEFAULT_GRAPHQL, chain_id, token0_addr, block=block)
            price1, _ = fetch_price(DEFAULT_GRAPHQL, chain_id, token1_addr, block=block)
            
            # Extract net positions from the positions structure
            positions = nav_result.get('positions', {})
            net0 = positions.get('asset0', {}).get('net', 0) if positions else 0
            net1 = positions.get('asset1', {}).get('net', 0) if positions else 0
            
            daily_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'block': block,
                'nav': nav_result['nav'],
                'net0': net0,
                'net1': net1,
                'price0': price0 / 1e8,  # Convert to USD
                'price1': price1 / 1e8,  # Convert to USD
                'value0': net0 * (price0 / 1e8),
                'value1': net1 * (price1 / 1e8)
            })
            
            print(f"  {current_date.strftime('%Y-%m-%d')}: Block {block} - NAV ${nav_result['nav']:,.2f}")
            
        except Exception as e:
            print(f"  {current_date.strftime('%Y-%m-%d')}: Error - {str(e)}")
            daily_data.append({
                'date': current_date.strftime('%Y-%m-%d'),
                'block': None,
                'nav': None,
                'net0': None,
                'net1': None,
                'price0': None,
                'price1': None,
                'value0': None,
                'value1': None
            })
        
        current_date += timedelta(days=1)
    
    return daily_data, token0_symbol, token1_symbol


def display_nav_table(daily_data: List[Dict], token0_symbol: str, token1_symbol: str):
    """Display NAV history as a formatted table."""
    
    # Prepare table data
    table_data = []
    prev_nav = None
    
    for day in daily_data:
        if day['nav'] is not None:
            nav_change = ''
            nav_change_pct = ''
            
            if prev_nav is not None and prev_nav > 0:
                change = day['nav'] - prev_nav
                change_pct = (change / prev_nav) * 100
                nav_change = f"${change:+,.0f}"
                nav_change_pct = f"{change_pct:+.2f}%"
            
            # Calculate NAV in WETH terms
            nav_in_weth = day['nav'] / day['price1'] if day['price1'] and day['price1'] > 0 else 0
            
            table_data.append([
                day['date'],
                day['block'] if day['block'] else 'N/A',
                f"${day['nav']:,.0f}" if day['nav'] else 'N/A',
                nav_change,
                nav_change_pct,
                f"{day['net0']:,.2f}" if day['net0'] is not None else 'N/A',
                f"{day['net1']:,.2f}" if day['net1'] is not None else 'N/A',
                f"${day['price0']:,.2f}" if day['price0'] else 'N/A',
                f"${day['price1']:,.2f}" if day['price1'] else 'N/A',
                f"{nav_in_weth:,.2f}" if nav_in_weth > 0 else 'N/A'
            ])
            
            if day['nav'] is not None:
                prev_nav = day['nav']
        else:
            table_data.append([
                day['date'],
                'N/A',
                'N/A',
                '',
                '',
                'N/A',
                'N/A',
                'N/A',
                'N/A',
                'N/A'
            ])
    
    # Display table
    headers = [
        'Date',
        'Block',
        'Net NAV',
        'Change',
        'Change %',
        f'{token0_symbol} Net',
        f'{token1_symbol} Net',
        f'{token0_symbol} Price',
        f'{token1_symbol} Price',
        'NAV in WETH'
    ]
    
    print("\n" + "=" * 120)
    print("DAILY NAV HISTORY")
    print("=" * 120)
    print(tabulate(table_data, headers=headers, tablefmt='grid', floatfmt='.2f'))
    
    # Calculate summary statistics
    valid_navs = [d['nav'] for d in daily_data if d['nav'] is not None]
    if len(valid_navs) >= 2:
        first_nav = valid_navs[0]
        last_nav = valid_navs[-1]
        total_change = last_nav - first_nav
        total_change_pct = (total_change / first_nav * 100) if first_nav > 0 else 0
        
        print("\n" + "=" * 120)
        print("SUMMARY")
        print("=" * 120)
        print(f"Period: {daily_data[0]['date']} to {daily_data[-1]['date']}")
        print(f"Starting NAV: ${first_nav:,.2f}")
        print(f"Ending NAV: ${last_nav:,.2f}")
        print(f"Total Change: ${total_change:+,.2f} ({total_change_pct:+.2f}%)")
        print(f"Days: {len(valid_navs)}")
        
        if len(valid_navs) > 1:
            daily_avg_change = total_change_pct / len(valid_navs)
            annualized = ((last_nav / first_nav) ** (365 / len(valid_navs)) - 1) * 100 if first_nav > 0 else 0
            print(f"Average Daily Change: {daily_avg_change:+.2f}%")
            print(f"Annualized Return: {annualized:+.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Show daily NAV history for a pool")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--days", type=int, default=30, help="Number of days to show (default: 30)")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    
    args = parser.parse_args()
    
    try:
        daily_data, token0_symbol, token1_symbol = get_daily_nav_history(
            args.pool, 
            args.chain,
            args.days
        )
        
        display_nav_table(daily_data, token0_symbol, token1_symbol)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()