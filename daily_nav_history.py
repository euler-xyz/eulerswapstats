#!/usr/bin/env python3
"""
Show daily NAV history for a pool along with token prices.
"""
import argparse
import csv
import json
import requests
import time
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

def get_token_decimals(token_address: str) -> int:
    """Fetch token decimals from the blockchain via RPC."""
    if not token_address:
        raise ValueError("Token address cannot be empty")
    
    # ERC20 decimals() function selector
    decimals_selector = "0x313ce567"
    
    # First check known values for common tokens
    known_decimals = {
        '0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48': 6,   # USDC
        '0xdac17f958d2ee523a2206206994597c13d831ec7': 6,   # USDT
        '0x2260fac5e5542a773aa44fbcfedf7c193bc2c599': 8,   # WBTC
        '0x6c3ea9036406852006290770bedfcaba0e23a0e8': 6,   # PYUSD
    }
    
    addr_lower = token_address.lower()
    if addr_lower in known_decimals:
        return known_decimals[addr_lower]
    
    try:
        # Make eth_call to get decimals
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{
                "to": token_address,
                "data": decimals_selector
            }, "latest"],
            "id": 1
        }
        
        r = requests.post(DEFAULT_RPC_URL, json=payload, timeout=10)
        r.raise_for_status()
        result = r.json()
        
        if 'result' in result and result['result'] != '0x':
            # Convert hex to int
            decimals = int(result['result'], 16)
            if 0 < decimals <= 77:  # Sanity check
                return decimals
            else:
                raise ValueError(f"Invalid decimals value {decimals} for token {token_address}")
        else:
            raise RuntimeError(f"Empty response when fetching decimals for {token_address}")
    except Exception as e:
        raise RuntimeError(f"Failed to fetch decimals for {token_address}: {e}")

# Retry configuration
MAX_RETRIES = 10
INITIAL_RETRY_DELAY = 1  # seconds
MAX_RETRY_DELAY = 30  # seconds


def retry_with_backoff(func, *args, **kwargs):
    """Execute a function with exponential backoff retry logic."""
    last_exception = None
    delay = INITIAL_RETRY_DELAY
    
    for attempt in range(MAX_RETRIES):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exception = e
            if attempt < MAX_RETRIES - 1:
                # Check if it's a server error worth retrying
                error_msg = str(e).lower()
                if any(x in error_msg for x in ['500', '502', '503', '504', '520', 'timeout', 'connection', 'server error']):
                    print(f"    Retry {attempt + 1}/{MAX_RETRIES} after {delay}s due to: {e}")
                    time.sleep(delay)
                    delay = min(delay * 2, MAX_RETRY_DELAY)  # Exponential backoff with cap
                else:
                    # Don't retry for client errors
                    raise
            else:
                raise
    
    # Should never reach here, but just in case
    if last_exception:
        raise last_exception


def rpc_call(rpc_url: str, method: str, params: list):
    """Make RPC call to Ethereum node."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = retry_with_backoff(requests.post, rpc_url, json=payload, timeout=30)
    r.raise_for_status()
    js = r.json()
    if "error" in js and js["error"]:
        raise RuntimeError(f"RPC error: {js['error']}")
    return js.get("result")


def get_block_by_timestamp(timestamp: int) -> int:
    """Get block number at or after a given timestamp using Etherscan API."""
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
                'closest': 'after',  # Get block at or after timestamp
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
    # Reference: block 23179760 at 2025-08-20 12:00:00 UTC
    reference_block = 23179760
    reference_timestamp = 1755715200  # 2025-08-20 12:00:00 UTC
    
    seconds_diff = timestamp - reference_timestamp
    blocks_diff = seconds_diff // 12  # ~12 seconds per block
    estimated_block = reference_block + blocks_diff
    
    # Ensure we don't return negative or future blocks
    if estimated_block < 0:
        estimated_block = 1
    
    return estimated_block


def fetch_swap_volumes(pool_address: str, start_date: datetime, end_date: datetime, 
                      token0_addr: str = None, token1_addr: str = None) -> Dict[str, Dict]:
    """Fetch daily swap volumes from GraphQL with cursor-based pagination."""
    
    # Get token decimals once at the start
    decimals0 = get_token_decimals(token0_addr) if token0_addr else 18
    decimals1 = get_token_decimals(token1_addr) if token1_addr else 18
    print(f"  Token decimals: token0={decimals0}, token1={decimals1}")
    
    daily_volumes = {}
    all_swaps = []
    cursor = None
    limit = 1000
    page_num = 0
    
    try:
        while True:
            page_num += 1
            
            # Build query with optional cursor
            if cursor:
                query = '''
                query {
                  eulerSwapSwaps(
                    where: {pool: "%s"}
                    orderBy: "blockNumber"
                    orderDirection: "desc"
                    limit: %d
                    after: "%s"
                  ) {
                    items {
                      blockNumber
                      timestamp
                      amount0In
                      amount1In
                      amount0Out
                      amount1Out
                    }
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                  }
                }
                ''' % (pool_address.lower(), limit, cursor)
            else:
                query = '''
                query {
                  eulerSwapSwaps(
                    where: {pool: "%s"}
                    orderBy: "blockNumber"
                    orderDirection: "desc"
                    limit: %d
                  ) {
                    items {
                      blockNumber
                      timestamp
                      amount0In
                      amount1In
                      amount0Out
                      amount1Out
                    }
                    pageInfo {
                      hasNextPage
                      endCursor
                    }
                  }
                }
                ''' % (pool_address.lower(), limit)
            
            print(f"  Fetching page {page_num} of swaps...")
            r = retry_with_backoff(requests.post, DEFAULT_GRAPHQL, json={'query': query}, timeout=60)
            data = r.json()
            
            if 'errors' in data:
                print(f"  GraphQL errors: {data['errors']}")
                break
            
            if 'data' in data and data['data'] and 'eulerSwapSwaps' in data['data']:
                result = data['data']['eulerSwapSwaps']
                swaps = result.get('items', [])
                page_info = result.get('pageInfo', {})
                
                if not swaps:
                    break
                    
                all_swaps.extend(swaps)
                
                # Check if oldest swap is before our start date
                if swaps:
                    oldest_timestamp = int(swaps[-1]['timestamp'])
                    oldest_date = datetime.fromtimestamp(oldest_timestamp)
                    if oldest_date < start_date:
                        print(f"  Reached swaps before start date, stopping pagination")
                        break
                
                # Check if there are more pages
                if page_info.get('hasNextPage'):
                    cursor = page_info.get('endCursor')
                else:
                    break
            else:
                break
        
        print(f"  Total swaps fetched: {len(all_swaps)}")
        
        # Process all swaps
        for swap in all_swaps:
            timestamp = int(swap['timestamp'])
            swap_date = datetime.fromtimestamp(timestamp)
            
            # Skip if outside our date range
            if swap_date < start_date or swap_date > end_date:
                continue
                
            date_str = swap_date.strftime('%Y-%m-%d')
            
            # Parse amounts using correct decimals
            amt0_in = int(swap['amount0In']) / (10 ** decimals0) if swap['amount0In'] else 0
            amt1_in = int(swap['amount1In']) / (10 ** decimals1) if swap['amount1In'] else 0
            amt0_out = int(swap['amount0Out']) / (10 ** decimals0) if swap['amount0Out'] else 0
            amt1_out = int(swap['amount1Out']) / (10 ** decimals1) if swap['amount1Out'] else 0
            
            if date_str not in daily_volumes:
                daily_volumes[date_str] = {
                    'swap_count': 0,
                    'volume_token0': 0,
                    'volume_token1': 0
                }
            
            daily_volumes[date_str]['swap_count'] += 1
            daily_volumes[date_str]['volume_token0'] += max(amt0_in, amt0_out)
            daily_volumes[date_str]['volume_token1'] += max(amt1_in, amt1_out)
        
        print(f"  Swaps grouped into {len(daily_volumes)} days")
        return daily_volumes
        
    except Exception as e:
        print(f"Error fetching swap volumes: {e}")
        return {}


def get_pool_fee_rate(pool_address: str, chain_id: int = 1) -> float:
    """Get pool fee rate as a decimal (e.g., 0.0005 for 5 bps)."""
    try:
        query = f"""
        query {{
          config: eulerSwapFactoryPoolConfig(chainId: {chain_id}, pool: "{pool_address.lower()}") {{
            fee
          }}
        }}
        """
        
        r = retry_with_backoff(requests.post, DEFAULT_GRAPHQL, json={"query": query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        fee = data.get("data", {}).get("config", {}).get("fee")
        if fee:
            # Fee is stored as parts per 1e18
            # 50000000000000 = 0.005% = 0.00005
            return int(fee) / 1e18
    except Exception as e:
        print(f"Warning: Could not fetch pool fee rate: {e}")
    
    # Default to 1 bp (0.01%) if fetch fails
    return 0.0001



def fetch_all_historical_prices(token_addr: str, days: int) -> Dict[str, float]:
    """Fetch all historical prices for a token in one API call."""
    import requests
    import time
    from datetime import datetime, timedelta
    
    try:
        # Use CoinGecko market_chart endpoint to get all prices at once
        url = f"https://api.coingecko.com/api/v3/coins/ethereum/contract/{token_addr.lower()}/market_chart?vs_currency=usd&days={days}"
        r = requests.get(url, timeout=30)
        
        if r.status_code == 429:
            print("    Rate limited by CoinGecko, waiting 15s...")
            time.sleep(15)
            r = requests.get(url, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            if 'prices' in data and data['prices']:
                # Convert to date-indexed dict
                prices_by_date = {}
                for timestamp_ms, price in data['prices']:
                    date = datetime.fromtimestamp(timestamp_ms / 1000)
                    date_str = date.strftime('%Y-%m-%d')
                    # Store the last price for each date
                    prices_by_date[date_str] = price
                return prices_by_date
        
        # Try fallback for native ETH
        if token_addr.lower() in ['0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee', '0x0000000000000000000000000000000000000000']:
            url = f"https://api.coingecko.com/api/v3/coins/ethereum/market_chart?vs_currency=usd&days={days}"
            r = requests.get(url, timeout=30)
            if r.status_code == 200:
                data = r.json()
                if 'prices' in data and data['prices']:
                    prices_by_date = {}
                    for timestamp_ms, price in data['prices']:
                        date = datetime.fromtimestamp(timestamp_ms / 1000)
                        date_str = date.strftime('%Y-%m-%d')
                        prices_by_date[date_str] = price
                    return prices_by_date
        
        return {}
    except Exception as e:
        print(f"    Error fetching historical prices: {e}")
        return {}


def get_daily_nav_history(pool_address: str, chain_id: int = 1, days: int = 30) -> List[Dict]:
    """Get daily NAV history for a pool."""
    
    # Get pool fee rate
    fee_rate = get_pool_fee_rate(pool_address, chain_id)
    fee_bps = fee_rate * 10000  # Convert to basis points for display
    print(f"Pool fee rate: {fee_bps:.2f} bps ({fee_rate*100:.3f}%)")
    
    # Get pool creation info
    # Note: third value is actually last_available_block from cache (misnamed for historical reasons)
    created_at, creation_block, last_available_from_cache = get_pool_creation_block(pool_address, chain_id)
    creation_date = datetime.fromtimestamp(created_at)
    
    # Get current time
    now = datetime.now()
    
    # Determine start date (either creation or N days ago)
    start_date = max(creation_date, now - timedelta(days=days))
    
    # Get token info from V2 API first (needed for decimals)
    r = retry_with_backoff(requests.get, V2_API, params={"chainId": chain_id})
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
    
    # Check if pool is active
    pool_is_active = False
    for p in pools_v2:
        if p['pool'].lower() == pool_address.lower():
            pool_is_active = True
            break
    
    # If not found in V2 API (inactive pool), try GraphQL
    if not token0_addr or not token1_addr:
        print("Pool not found in V2 API, checking GraphQL for token addresses...")
        query = f'''
        query {{
          pools: eulerSwapFactoryPoolDeployeds(
            where: {{chainId: {chain_id}, pool: "{pool_address.lower()}"}}
          ) {{
            items {{
              asset0
              asset1
            }}
          }}
        }}
        '''
        
        try:
            r = retry_with_backoff(requests.post, DEFAULT_GRAPHQL, json={"query": query}, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            items = data.get("data", {}).get("pools", {}).get("items", [])
            if items:
                pool_data = items[0]
                token0_addr = pool_data.get('asset0', '')
                token1_addr = pool_data.get('asset1', '')
                print(f"  Found tokens in GraphQL: {token0_addr[:10]}... / {token1_addr[:10]}...")
                print(f"  WARNING: This is an INACTIVE/UNINSTALLED pool - historical NAV data may not be available")
            else:
                print(f"  WARNING: Pool {pool_address} not found in GraphQL either")
        except Exception as e:
            print(f"  Error fetching from GraphQL: {e}")
    
    token0_symbol = get_token_symbol(token0_addr) if token0_addr else 'Token0'
    token1_symbol = get_token_symbol(token1_addr) if token1_addr else 'Token1'
    
    # For now, assume pools are available from creation block
    # TODO: Add proper tracking of first available block (API indexing delay)
    query_start_block = creation_block
    
    # Check for last available block from cache (for inactive/uninstalled pools)
    max_query_block = None
    if not pool_is_active:
        print(f"  WARNING: This pool appears to be INACTIVE/UNINSTALLED")
        print(f"  Will attempt to fetch historical data but it may not be available")
        
        # Try to get last available block from cache
        try:
            with open('pool_creation_blocks.csv', 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row['pool_address'].lower() == pool_address.lower():
                        if row.get('last_available_block'):
                            max_query_block = int(row['last_available_block'])
                            print(f"  Pool was last available at block {max_query_block}")
                        break
        except Exception as e:
            print(f"  Could not read last available block from cache: {e}")
    
    # Fetch daily swap volumes
    print("Fetching swap volumes...")
    daily_volumes = fetch_swap_volumes(pool_address, start_date, now, token0_addr, token1_addr)
    
    # Generate daily timestamps from start to now
    daily_data = []
    current_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    
    print(f"Fetching daily NAV history for {token0_symbol}/{token1_symbol}")
    print(f"From {start_date.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}")
    
    # Pre-fetch all historical prices in just 2 API calls
    print("Fetching all historical prices...")
    prices_token0 = fetch_all_historical_prices(token0_addr, days + 1) if token0_addr else {}
    time.sleep(3)  # Wait between API calls to avoid rate limiting
    prices_token1 = fetch_all_historical_prices(token1_addr, days + 1) if token1_addr else {}
    
    if not prices_token0 or not prices_token1:
        print("Warning: Could not fetch all historical prices, falling back to per-day fetching")
    else:
        print(f"  Got {len(prices_token0)} days of {token0_symbol} prices")
        print(f"  Got {len(prices_token1)} days of {token1_symbol} prices")
    
    print("-" * 80)
    
    while current_date <= now:
        timestamp = int(current_date.timestamp())
        date_str = current_date.strftime('%Y-%m-%d')
        
        # Function to fetch a single day's data
        def fetch_day_data():
            # Get block at this timestamp
            block = get_block_by_timestamp(timestamp)
            
            # Skip if block is before pool creation
            if block < query_start_block:
                print(f"  {date_str}: Skipped (before pool creation at block {creation_block})")
                return None
            
            # For inactive pools, skip if block is after last available
            if max_query_block and block > max_query_block:
                print(f"  {date_str}: Skipped (pool was uninstalled, block {block} > last available {max_query_block})")
                return None
            
            # Fetch pool data at this block
            # Use V2 API which supports blockNumber parameter
            pool_data = fetch_pool_data(V2_API, chain_id, pool_address, block)
            
            # Get prices from pre-fetched data or fall back to individual calls
            if date_str in prices_token0 and date_str in prices_token1:
                # Use pre-fetched prices (much faster!)
                price0 = int(prices_token0[date_str] * 1e8)
                price1 = int(prices_token1[date_str] * 1e8)
            else:
                # Fall back to individual API calls (this shouldn't happen if pre-fetch worked)
                print(f"    DEBUG: Falling back to API for {date_str} - token0: {date_str in prices_token0}, token1: {date_str in prices_token1}")
                price0, _ = fetch_price(DEFAULT_GRAPHQL, chain_id, token0_addr, block=block)
                time.sleep(2)  # Wait 2 seconds between price calls
                price1, _ = fetch_price(DEFAULT_GRAPHQL, chain_id, token1_addr, block=block)
            
            # Calculate NAV with pre-fetched prices
            nav_result = calculate_net_nav(pool_data, DEFAULT_GRAPHQL, chain_id, block, prices=(price0, price1))
            
            # Extract net positions from the positions structure
            positions = nav_result.get('positions', {})
            net0 = positions.get('asset0', {}).get('net', 0) if positions else 0
            net1 = positions.get('asset1', {}).get('net', 0) if positions else 0
            
            # Get volume data for this date
            vol_data = daily_volumes.get(date_str, {})
            
            # Calculate USD volume
            volume_usd = 0
            if vol_data:
                volume_usd = (vol_data.get('volume_token0', 0) * (price0 / 1e8) + 
                             vol_data.get('volume_token1', 0) * (price1 / 1e8)) / 2
            
            # Calculate NAV in quote token (token1)
            nav_in_quote = nav_result['nav'] / (price1 / 1e8) if price1 > 0 else 0
            
            return {
                'date': date_str,
                'block': block,
                'nav': nav_result['nav'],
                'nav_usd': nav_result['nav'],  # Add explicit nav_usd field
                'net0': net0,
                'net1': net1,
                'price0': price0 / 1e8,  # Convert to USD
                'price1': price1 / 1e8,  # Convert to USD
                'value0': net0 * (price0 / 1e8),
                'value1': net1 * (price1 / 1e8),
                'nav_in_quote': nav_in_quote,
                'nav_quote': nav_in_quote,  # Add nav_quote alias for compatibility
                'swap_count': vol_data.get('swap_count', 0),
                'volume_token0': vol_data.get('volume_token0', 0),
                'volume_token1': vol_data.get('volume_token1', 0),
                'volume_usd': volume_usd,
                'daily_volume': volume_usd  # Add daily_volume alias for compatibility
            }
        
        # Try to fetch data with retries
        try:
            day_data = retry_with_backoff(fetch_day_data)
            
            if day_data:
                daily_data.append(day_data)
                print(f"  {date_str}: Block {day_data['block']} - NAV ${day_data['nav']:,.2f}")
            
        except Exception as e:
            print(f"  {date_str}: Failed after {MAX_RETRIES} retries - {str(e)}")
            # Add null data for failed day
            daily_data.append({
                'date': date_str,
                'block': None,
                'nav': None,
                'nav_usd': None,
                'net0': None,
                'net1': None,
                'price0': None,
                'price1': None,
                'value0': None,
                'value1': None,
                'nav_in_quote': None,
                'nav_quote': None,
                'swap_count': 0,
                'volume_token0': 0,
                'volume_token1': 0,
                'volume_usd': 0,
                'daily_volume': 0,
                'token0_symbol': token0_symbol,
                'token1_symbol': token1_symbol
            })
        
        current_date += timedelta(days=1)
    
    return daily_data, token0_symbol, token1_symbol, fee_rate


def display_nav_table(daily_data: List[Dict], token0_symbol: str, token1_symbol: str, fee_rate: float = 0.0001):
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
            
            # Get volume data
            volume_usd = day.get('volume_usd', 0)
            swap_count = day.get('swap_count', 0)
            
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
                f"{nav_in_weth:,.2f}" if nav_in_weth > 0 else 'N/A',
                f"${volume_usd:,.0f}" if volume_usd > 0 else '-',
                f"{swap_count}" if swap_count > 0 else '-'
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
                'N/A',
                '-',
                '-'
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
        'NAV in WETH',
        'Daily Volume',
        'Swaps'
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
        
        # Calculate volume totals and fees with actual rate
        total_volume = sum(d.get('volume_usd', 0) for d in daily_data)
        total_swaps = sum(d.get('swap_count', 0) for d in daily_data)
        avg_daily_volume = total_volume / len(daily_data) if len(daily_data) > 0 else 0
        total_fees = total_volume * fee_rate
        fee_return = (total_fees / first_nav * 100) if first_nav > 0 else 0
        fee_apr = (fee_return / len(valid_navs) * 365) if len(valid_navs) > 0 else 0
        
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
        
        print(f"\nVolume & Fee Statistics:")
        print(f"Total Volume: ${total_volume:,.0f}")
        print(f"Total Swaps: {total_swaps:,}")
        print(f"Average Daily Volume: ${avg_daily_volume:,.0f}")
        print(f"Pool Fee Rate: {fee_rate*10000:.2f} bps ({fee_rate*100:.3f}%)")
        print(f"Fees Earned: ${total_fees:,.0f}")
        print(f"Fee Return: {fee_return:.2f}%")
        print(f"Fee APR: {fee_apr:.2f}%")


def main():
    parser = argparse.ArgumentParser(description="Show daily NAV history for a pool")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--days", type=int, default=30, help="Number of days to show (default: 30)")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--output", help="Output file (JSON format)")
    
    args = parser.parse_args()
    
    try:
        daily_data, token0_symbol, token1_symbol, fee_rate = get_daily_nav_history(
            args.pool, 
            args.chain,
            args.days
        )
        
        # Determine output filename
        import os
        os.makedirs('data', exist_ok=True)
        
        if args.output:
            # If output specified, use it (but still in data directory if not absolute path)
            if not os.path.isabs(args.output):
                output_file = f"data/{args.output}"
            else:
                output_file = args.output
        else:
            # Default to pool address in data directory
            output_file = f"data/{args.pool}.json"
        
        # Always save to JSON
        # Convert datetime to string for JSON serialization
        json_data = []
        for entry in daily_data:
            json_entry = entry.copy()
            # Date might already be a string
            if hasattr(entry['date'], 'strftime'):
                json_entry['date'] = entry['date'].strftime('%Y-%m-%d')
            else:
                json_entry['date'] = entry['date']  # Already a string
            json_entry['token0_symbol'] = token0_symbol
            json_entry['token1_symbol'] = token1_symbol
            json_data.append(json_entry)
        
        # Save metadata at the end
        metadata = {
            'pool_address': args.pool,
            'chain_id': args.chain,
            'fee_rate': fee_rate,
            'fee_bps': fee_rate * 10000,
            'token0_symbol': token0_symbol,
            'token1_symbol': token1_symbol
        }
        
        # Save both data and metadata
        output_data = {
            'metadata': metadata,
            'daily_data': json_data
        }
        
        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)
        print(f"\nData saved to {output_file}")
        
        # Always display the table
        display_nav_table(daily_data, token0_symbol, token1_symbol, fee_rate)
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()