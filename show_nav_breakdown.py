#!/usr/bin/env python3
"""
Show the full accountNav breakdown from V2 API.
This reveals all the underlying Euler vault positions.
"""
import argparse
import requests
import json
from typing import Dict, Any
from pool_cache import get_pool_creation_block
from utils import get_token_symbol

# V2 API endpoint
V2_API = "https://index-dev.eul.dev/v2/swap/pools"

# Known vault addresses to names (if available)
KNOWN_VAULTS = {
    "0x797DD80692c3b2dAdabCe8e30C07fDE5307D48a9": "USDC Vault",
    "0x313603FA690301b0CaeEf8069c065862f9162162": "USDT Vault",
    "0xD8b27CF359b7D15710a5BE299AF6e7Bf904984C2": "WETH Vault",
}


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


def format_value(value: str, decimals: int = 18) -> float:
    """Convert string value to float with decimals."""
    try:
        val = float(value)
        if decimals == 6:
            return val / 1e6
        elif decimals == 8:
            return val / 1e8
        else:
            return val / 1e18
    except:
        return 0.0


def get_token_decimals(token_symbol: str) -> int:
    """Get decimals for known tokens."""
    if token_symbol in ['USDC', 'USDT']:
        return 6
    elif token_symbol == 'WBTC':
        return 8
    else:
        return 18


def main():
    parser = argparse.ArgumentParser(description="Show accountNav breakdown")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--block", type=int, help="Block number (optional)")
    parser.add_argument("--compare", action="store_true", help="Compare creation and current")
    
    args = parser.parse_args()
    
    pool_address = args.pool
    chain_id = args.chain
    
    print(f"Fetching accountNav breakdown for pool: {pool_address}")
    print("=" * 80)
    
    blocks_to_check = []
    
    if args.compare:
        # Get creation and current blocks
        created_at, creation_block = get_pool_creation_block(pool_address, chain_id)
        blocks_to_check = [
            ("Creation", creation_block),
            ("Current", None)
        ]
    elif args.block:
        blocks_to_check = [("Specified", args.block)]
    else:
        blocks_to_check = [("Current", None)]
    
    for block_label, block_num in blocks_to_check:
        print(f"\n{'=' * 80}")
        print(f"{block_label.upper()} BLOCK" + (f" ({block_num})" if block_num else ""))
        print(f"{'=' * 80}")
        
        # Fetch pool data
        pool_data = fetch_v2_pool_at_block(pool_address, chain_id, block_num)
        
        if not pool_data:
            print(f"❌ No data available at {block_label} block")
            continue
        
        # Get accountNav
        account_nav = pool_data.get('accountNav', {})
        if not account_nav:
            print("No accountNav data")
            continue
        
        # Display overall NAV
        print(f"\nOVERALL ACCOUNT NAV:")
        total_assets = float(account_nav.get('totalAssets', 0)) / 1e8
        total_borrowed = float(account_nav.get('totalBorrowed', 0)) / 1e8
        nav = float(account_nav.get('nav', 0)) / 1e8
        
        print(f"  Total Assets:   ${total_assets:>15,.2f}")
        print(f"  Total Borrowed: ${total_borrowed:>15,.2f}")
        print(f"  NAV:            ${nav:>15,.2f}")
        
        # Get breakdown
        breakdown = account_nav.get('breakdown', {})
        if not breakdown:
            print("\nNo breakdown available")
            continue
        
        print(f"\nBREAKDOWN BY VAULT ({len(breakdown)} vaults):")
        print("-" * 80)
        
        # Process each vault in breakdown
        vault_num = 0
        total_value = 0
        
        for vault_addr, vault_data in breakdown.items():
            vault_num += 1
            
            # Get token info
            asset_addr = vault_data.get('asset', '')
            token_symbol = get_token_symbol(asset_addr)
            decimals = get_token_decimals(token_symbol)
            
            # Get vault name if known
            vault_name = KNOWN_VAULTS.get(vault_addr, f"Vault {vault_num}")
            
            # Parse values
            shares = format_value(vault_data.get('shares', '0'), decimals)
            assets = format_value(vault_data.get('assets', '0'), decimals)
            borrowed = format_value(vault_data.get('borrowed', '0'), decimals)
            price = float(vault_data.get('price', '0')) / 1e8  # Prices are in 1e8 format
            
            # Calculate net position and value
            net_position = assets - borrowed
            position_value = net_position * price
            total_value += position_value
            
            # Display vault info
            print(f"\n{vault_num}. {vault_name}")
            print(f"   Vault Address: {vault_addr}")
            print(f"   Asset: {asset_addr}")
            print(f"   Token: {token_symbol}")
            
            print(f"\n   Position:")
            print(f"     Shares:    {shares:>15,.4f} shares")
            print(f"     Assets:    {assets:>15,.4f} {token_symbol}")
            print(f"     Borrowed:  {borrowed:>15,.4f} {token_symbol}")
            print(f"     Net:       {net_position:>15,.4f} {token_symbol}")
            
            print(f"\n   Valuation:")
            print(f"     Price:     ${price:>15,.6f}")
            print(f"     Value:     ${position_value:>15,.2f}")
            
            # Show status
            if assets > 0 and borrowed > 0:
                leverage = (borrowed / assets) * 100
                print(f"     Leverage:  {leverage:>14.2f}%")
                print(f"     Status:    Leveraged position")
            elif assets > 0:
                print(f"     Status:    Long position (no leverage)")
            elif borrowed > 0:
                print(f"     Status:    Borrowed position")
            else:
                print(f"     Status:    No position")
        
        print(f"\n{'-' * 80}")
        print(f"Total Value from Breakdown: ${total_value:,.2f}")
        print(f"Reported NAV:               ${nav:,.2f}")
        print(f"Difference:                 ${abs(total_value - nav):,.2f}")
    
    # If comparing, show changes
    if args.compare and len(blocks_to_check) == 2:
        print(f"\n{'=' * 80}")
        print("CHANGES FROM CREATION TO CURRENT")
        print(f"{'=' * 80}")
        
        # Fetch both blocks' data
        creation_data = fetch_v2_pool_at_block(pool_address, chain_id, blocks_to_check[0][1])
        current_data = fetch_v2_pool_at_block(pool_address, chain_id, blocks_to_check[1][1])
        
        if creation_data and current_data:
            creation_nav = float(creation_data.get('accountNav', {}).get('nav', 0)) / 1e8
            current_nav = float(current_data.get('accountNav', {}).get('nav', 0)) / 1e8
            
            nav_change = current_nav - creation_nav
            nav_return = (nav_change / creation_nav * 100) if creation_nav > 0 else 0
            
            print(f"\nNAV Change: ${nav_change:+,.2f} ({nav_return:+.2f}%)")


if __name__ == "__main__":
    main()