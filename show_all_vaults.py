#!/usr/bin/env python3
"""
Show ALL vault data from V2 API for a pool.
The V2 API may include additional vaults beyond vault0 and vault1.
"""
import argparse
import requests
import json
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


def display_vault(vault_name: str, vault_data: Dict[str, Any]):
    """Display a single vault's data."""
    if not vault_data:
        return
    
    # Get basic info
    asset_addr = vault_data.get('asset', '')
    if not asset_addr:
        return
        
    token = get_token_symbol(asset_addr)
    decimals = vault_data.get('decimals', 18)
    
    print(f"\n{'─' * 60}")
    print(f"{vault_name.upper()}")
    print(f"{'─' * 60}")
    print(f"Asset: {asset_addr}")
    print(f"Token: {token}")
    print(f"Decimals: {decimals}")
    
    # Reserves (actual token balance in the vault)
    reserves = float(vault_data.get('reserves', 0))
    if decimals == 6:  # USDC, USDT
        reserves = reserves / 1e6
    elif decimals == 8:  # WBTC
        reserves = reserves / 1e8
    else:
        reserves = reserves / 1e18
    print(f"Reserves: {reserves:,.4f} {token}")
    
    # Account NAV data (lending positions)
    account_nav = vault_data.get('accountNav', {})
    if account_nav:
        assets = float(account_nav.get('assets', 0))
        borrowed = float(account_nav.get('borrowed', 0))
        nav = float(account_nav.get('nav', 0))
        
        # Convert to human readable
        if decimals == 6:
            assets = assets / 1e6
            borrowed = borrowed / 1e6
            nav = nav / 1e6
        elif decimals == 8:
            assets = assets / 1e8
            borrowed = borrowed / 1e8
            nav = nav / 1e8
        else:
            assets = assets / 1e18
            borrowed = borrowed / 1e18
            nav = nav / 1e18
        
        print(f"\nAccount NAV:")
        print(f"  Assets (lent out):   {assets:>15,.4f} {token}")
        print(f"  Borrowed:            {borrowed:>15,.4f} {token}")
        print(f"  NAV (net):           {nav:>15,.4f} {token}")
        
        if assets > 0:
            leverage = borrowed / assets * 100
            print(f"  Leverage:            {leverage:>14.2f}%")
    
    # Additional fields
    if 'apr' in vault_data:
        apr = vault_data.get('apr', {})
        print(f"\nAPR:")
        for period in ['1d', '7d', '30d', '180d']:
            key = f'total{period}'
            if key in apr:
                apr_val = float(apr[key]) / 1e18 * 100
                print(f"  {period:>4}: {apr_val:>10.4f}%")


def main():
    parser = argparse.ArgumentParser(description="Show all vaults for a pool")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--block", type=int, help="Block number (optional)")
    parser.add_argument("--raw", action="store_true", help="Show raw JSON data")
    
    args = parser.parse_args()
    
    pool_address = args.pool
    chain_id = args.chain
    block = args.block
    
    print(f"Fetching all vault data for pool: {pool_address}")
    if block:
        print(f"At block: {block}")
    else:
        # Get creation and current blocks
        created_at, creation_block = get_pool_creation_block(pool_address, chain_id)
        head_hex = rpc_call(DEFAULT_RPC_URL, "eth_blockNumber", [])
        current_block = hex_to_int(head_hex)
        print(f"Creation block: {creation_block}, Current block: {current_block}")
    
    print("=" * 80)
    
    # Fetch V2 data
    pool_data = fetch_v2_pool_at_block(pool_address, chain_id, block)
    
    if not pool_data:
        print("❌ No pool data found")
        return
    
    # Show raw JSON if requested
    if args.raw:
        print("\nRAW JSON DATA:")
        print(json.dumps(pool_data, indent=2))
        return
    
    # Display basic pool info
    print(f"\nPool Address: {pool_data['pool']}")
    print(f"Active: {pool_data.get('active', False)}")
    print(f"Created At: {pool_data.get('createdAt', 'N/A')}")
    print(f"Block Number: {pool_data.get('blockNumber', 'N/A')}")
    
    # Display overall account NAV
    account_nav = pool_data.get('accountNav', {})
    if account_nav:
        print(f"\nOVERALL ACCOUNT NAV:")
        print(f"  Total Assets:   ${float(account_nav.get('totalAssets', 0)) / 1e8:,.2f}")
        print(f"  Total Borrowed: ${float(account_nav.get('totalBorrowed', 0)) / 1e8:,.2f}")
        print(f"  NAV:            ${float(account_nav.get('nav', 0)) / 1e8:,.2f}")
    
    # Look for all vault fields in the data
    print(f"\n{'=' * 60}")
    print("VAULTS FOUND IN DATA:")
    print(f"{'=' * 60}")
    
    vault_count = 0
    
    # Check for numbered vaults (vault0, vault1, vault2, etc.)
    for i in range(10):  # Check up to vault9
        vault_key = f'vault{i}'
        if vault_key in pool_data:
            vault_count += 1
            display_vault(vault_key, pool_data[vault_key])
    
    # Check for other vault-like fields
    for key in pool_data.keys():
        if 'vault' in key.lower() and not key.startswith('vault'):
            vault_count += 1
            display_vault(key, pool_data[key])
    
    # Also check for any borrowing vaults or lending vaults
    for key in ['borrowVault', 'lendVault', 'leverageVault', 'collateralVault']:
        if key in pool_data:
            vault_count += 1
            display_vault(key, pool_data[key])
    
    print(f"\n{'=' * 60}")
    print(f"Total vaults found: {vault_count}")
    
    # Show all top-level keys to understand structure
    print(f"\nAll top-level keys in pool data:")
    for key in sorted(pool_data.keys()):
        value_type = type(pool_data[key]).__name__
        if isinstance(pool_data[key], dict):
            sub_keys = list(pool_data[key].keys())[:3]
            print(f"  {key}: {value_type} with keys {sub_keys}...")
        elif isinstance(pool_data[key], list):
            print(f"  {key}: {value_type} with {len(pool_data[key])} items")
        else:
            print(f"  {key}: {value_type}")


if __name__ == "__main__":
    main()