#!/usr/bin/env python3
"""
Show vault data from V2 API at creation block and latest block.
This helps understand how the V2 API tracks vault positions over time.
"""
import argparse
import requests
from typing import Dict, Any
from pool_cache import get_pool_creation_block
from netnav import (
    rpc_call,
    hex_to_int,
    DEFAULT_RPC_URL
)
from utils import format_nav, get_token_symbol

# V2 API endpoint
V2_API = "https://index-dev.eul.dev/v2/swap/pools"


def fetch_v2_pool_at_block(pool_address: str, chain_id: int, block: int = None) -> Dict[str, Any]:
    """Fetch pool data from V2 API at specific block."""
    params = {"chainId": chain_id}
    if block:
        params["blockNumber"] = block
    
    r = requests.get(V2_API, params=params, timeout=30)
    r.raise_for_status()
    pools = r.json()
    
    for p in pools:
        if p['pool'].lower() == pool_address.lower():
            return p
    
    return None


def format_vault_data(vault: Dict[str, Any], token_symbol: str) -> Dict[str, Any]:
    """Format vault data for display."""
    decimals = vault.get('decimals', 18)
    
    # Get reserves (actual token balance)
    reserves = float(vault.get('reserves', 0))
    if decimals == 6:  # USDC, USDT
        reserves = reserves / 1e6
    elif decimals == 8:  # WBTC
        reserves = reserves / 1e8
    else:
        reserves = reserves / 1e18
    
    # Get account NAV data
    account_nav = vault.get('accountNav', {})
    assets = float(account_nav.get('assets', 0))
    borrowed = float(account_nav.get('borrowed', 0))
    
    # Convert to human readable
    if decimals == 6:
        assets = assets / 1e6
        borrowed = borrowed / 1e6
    elif decimals == 8:
        assets = assets / 1e8
        borrowed = borrowed / 1e8
    else:
        assets = assets / 1e18
        borrowed = borrowed / 1e18
    
    net_position = assets - borrowed
    
    return {
        'token': token_symbol,
        'reserves': reserves,
        'assets': assets,
        'borrowed': borrowed,
        'net_position': net_position,
        'leverage': borrowed / assets if assets > 0 else 0
    }


def main():
    parser = argparse.ArgumentParser(description="Show vault history for a pool")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    
    args = parser.parse_args()
    
    pool_address = args.pool
    chain_id = args.chain
    
    print(f"Fetching vault history for pool: {pool_address}")
    print("=" * 80)
    
    # Get creation block (will use cache if available)
    print("\n1. Getting pool creation block...")
    created_at, creation_block = get_pool_creation_block(pool_address, chain_id)
    print(f"   Created at timestamp: {created_at}")
    print(f"   Creation block: {creation_block}")
    
    # Get current block
    print("\n2. Getting current block...")
    head_hex = rpc_call(DEFAULT_RPC_URL, "eth_blockNumber", [])
    current_block = hex_to_int(head_hex)
    print(f"   Current block: {current_block}")
    
    # Fetch V2 data at creation block
    print(f"\n3. Fetching V2 data at creation block {creation_block}...")
    creation_data = fetch_v2_pool_at_block(pool_address, chain_id, creation_block)
    
    if not creation_data:
        print("   ⚠️  No data available at creation block")
        creation_data = None
    
    # Fetch V2 data at current block
    print(f"\n4. Fetching V2 data at current block {current_block}...")
    current_data = fetch_v2_pool_at_block(pool_address, chain_id, current_block)
    
    if not current_data:
        print("   ⚠️  No data available at current block")
        # Try without block parameter (latest)
        print("\n   Trying latest data (no block parameter)...")
        current_data = fetch_v2_pool_at_block(pool_address, chain_id)
    
    if not current_data:
        print("   ❌ Could not fetch current data")
        return
    
    # Display the data
    print("\n" + "=" * 80)
    print("VAULT DATA COMPARISON")
    print("=" * 80)
    
    # Get token symbols
    token0_addr = current_data.get('vault0', {}).get('asset', '')
    token1_addr = current_data.get('vault1', {}).get('asset', '')
    token0 = get_token_symbol(token0_addr)
    token1 = get_token_symbol(token1_addr)
    
    print(f"\nPool: {pool_address}")
    print(f"Pair: {token0}/{token1}")
    print(f"Active: {current_data.get('active', False)}")
    
    # Process and display vault data
    for vault_idx in [0, 1]:
        vault_key = f'vault{vault_idx}'
        token = token0 if vault_idx == 0 else token1
        
        print(f"\n{'─' * 40}")
        print(f"VAULT {vault_idx} ({token})")
        print(f"{'─' * 40}")
        
        # Creation block data
        if creation_data:
            print(f"\nAt Creation (Block {creation_block}):")
            creation_vault = format_vault_data(creation_data.get(vault_key, {}), token)
            print(f"  Reserves:     {creation_vault['reserves']:>15,.4f} {token}")
            print(f"  Assets:       {creation_vault['assets']:>15,.4f} {token}")
            print(f"  Borrowed:     {creation_vault['borrowed']:>15,.4f} {token}")
            print(f"  Net Position: {creation_vault['net_position']:>15,.4f} {token}")
            print(f"  Leverage:     {creation_vault['leverage']:>15.2%}")
        else:
            print(f"\nAt Creation: No data available")
        
        # Current block data
        print(f"\nAt Current (Block {current_block}):")
        current_vault = format_vault_data(current_data.get(vault_key, {}), token)
        print(f"  Reserves:     {current_vault['reserves']:>15,.4f} {token}")
        print(f"  Assets:       {current_vault['assets']:>15,.4f} {token}")
        print(f"  Borrowed:     {current_vault['borrowed']:>15,.4f} {token}")
        print(f"  Net Position: {current_vault['net_position']:>15,.4f} {token}")
        print(f"  Leverage:     {current_vault['leverage']:>15.2%}")
        
        # Changes
        if creation_data:
            print(f"\nChanges:")
            creation_vault = format_vault_data(creation_data.get(vault_key, {}), token)
            reserve_change = current_vault['reserves'] - creation_vault['reserves']
            assets_change = current_vault['assets'] - creation_vault['assets']
            borrowed_change = current_vault['borrowed'] - creation_vault['borrowed']
            net_change = current_vault['net_position'] - creation_vault['net_position']
            
            print(f"  Reserves:     {reserve_change:>+15,.4f} {token}")
            print(f"  Assets:       {assets_change:>+15,.4f} {token}")
            print(f"  Borrowed:     {borrowed_change:>+15,.4f} {token}")
            print(f"  Net Position: {net_change:>+15,.4f} {token}")
    
    # Overall NAV comparison
    print(f"\n{'=' * 40}")
    print("ACCOUNT NAV COMPARISON")
    print(f"{'=' * 40}")
    
    if creation_data:
        creation_nav = format_nav(creation_data.get('accountNav', {}))
        print(f"\nCreation NAV: ${creation_nav:,.2f}")
    
    current_nav = format_nav(current_data.get('accountNav', {}))
    print(f"Current NAV:  ${current_nav:,.2f}")
    
    if creation_data:
        nav_change = current_nav - creation_nav
        nav_return = (nav_change / creation_nav * 100) if creation_nav > 0 else 0
        print(f"Change:       ${nav_change:+,.2f} ({nav_return:+.2f}%)")
    
    # APR data
    print(f"\n{'=' * 40}")
    print("APR DATA (from V2 API)")
    print(f"{'=' * 40}")
    
    apr_data = current_data.get('apr', {})
    print(f"  1d:   {float(apr_data.get('total1d', 0)) / 1e18 * 100:.2f}%")
    print(f"  7d:   {float(apr_data.get('total7d', 0)) / 1e18 * 100:.2f}%")
    print(f"  30d:  {float(apr_data.get('total30d', 0)) / 1e18 * 100:.2f}%")
    print(f"  180d: {float(apr_data.get('total180d', 0)) / 1e18 * 100:.2f}%")


if __name__ == "__main__":
    main()