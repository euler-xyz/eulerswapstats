#!/usr/bin/env python3
"""Check all active pools for extra vaults with non-zero balances."""

import json
import requests
from typing import Dict, List, Any

def analyze_all_pools():
    """Analyze all pools for extra vault activity."""
    
    url = "https://index-dev.eul.dev/v2/swap/pools?chainId=1"
    r = requests.get(url)
    pools = r.json()
    
    pools_with_extra_vaults = []
    total_pools = 0
    active_pools = 0
    
    print("Analyzing all pools for extra vault activity...")
    print("=" * 70)
    
    for p in pools:
        if not p.get('active'):
            continue
            
        active_pools += 1
        pool_addr = p['pool']
        
        # Get pool's configured vaults
        pool_vault0 = p['vault0']['address']
        pool_vault1 = p['vault1']['address']
        pool_vaults = {pool_vault0, pool_vault1}
        
        # Check all vaults in accountNav
        extra_vault_nav = 0
        extra_vaults_info = []
        
        for vault_addr, vault_data in p['accountNav']['breakdown'].items():
            if vault_addr not in pool_vaults:
                # This is an extra vault
                assets = float(vault_data['assets'])
                borrowed = float(vault_data['borrowed'])
                
                if assets > 0 or borrowed > 0:
                    # Has non-zero balance
                    price = float(vault_data['price']) / 1e8
                    asset = vault_data['asset']
                    
                    # Determine decimals
                    if 'a0b869' in asset.lower():  # USDC
                        decimals = 6
                        token = "USDC"
                    elif 'c02aaa' in asset.lower():  # WETH
                        decimals = 18
                        token = "WETH"
                    elif 'dac17f' in asset.lower():  # USDT
                        decimals = 6
                        token = "USDT"
                    elif 'c13919' in asset.lower():  # RLUSD
                        decimals = 18
                        token = "RLUSD"
                    else:
                        decimals = 18
                        token = asset[:8] + "..."
                    
                    vault_nav = (assets / 10**decimals * price) - (borrowed / 10**decimals * price)
                    extra_vault_nav += vault_nav
                    
                    extra_vaults_info.append({
                        'vault': vault_addr,
                        'token': token,
                        'assets': assets / 10**decimals,
                        'borrowed': borrowed / 10**decimals,
                        'nav': vault_nav
                    })
        
        if extra_vaults_info:
            total_nav = float(p['accountNav']['nav']) / 1e8
            
            # Calculate pool-only NAV
            pool_only_nav = 0
            for vault_addr, vault_data in p['accountNav']['breakdown'].items():
                if vault_addr in pool_vaults:
                    assets = float(vault_data['assets'])
                    borrowed = float(vault_data['borrowed'])
                    price = float(vault_data['price']) / 1e8
                    
                    # Determine decimals
                    asset = vault_data['asset']
                    if 'a0b869' in asset.lower() or 'dac17f' in asset.lower():
                        decimals = 6
                    else:
                        decimals = 18
                    
                    vault_nav = (assets / 10**decimals * price) - (borrowed / 10**decimals * price)
                    pool_only_nav += vault_nav
            
            pools_with_extra_vaults.append({
                'pool': pool_addr,
                'owner': p.get('owner', 'Unknown'),
                'total_nav': total_nav,
                'pool_only_nav': pool_only_nav,
                'extra_vault_nav': extra_vault_nav,
                'extra_vaults': extra_vaults_info,
                'nav_difference_pct': (extra_vault_nav / total_nav * 100) if total_nav > 0 else 0
            })
    
    # Print results
    print(f"\nTotal active pools analyzed: {active_pools}")
    print(f"Pools with extra vault activity: {len(pools_with_extra_vaults)}")
    
    if pools_with_extra_vaults:
        print("\n" + "=" * 70)
        print("POOLS WITH EXTRA VAULT ACTIVITY:")
        print("=" * 70)
        
        # Sort by extra vault NAV impact
        pools_with_extra_vaults.sort(key=lambda x: abs(x['extra_vault_nav']), reverse=True)
        
        for pool_info in pools_with_extra_vaults[:10]:  # Show top 10
            print(f"\nPool: {pool_info['pool']}")
            print(f"Owner: {pool_info['owner']}")
            print(f"Total NAV: ${pool_info['total_nav']:,.2f}")
            print(f"Pool-only NAV: ${pool_info['pool_only_nav']:,.2f}")
            print(f"Extra Vault NAV: ${pool_info['extra_vault_nav']:,.2f} ({pool_info['nav_difference_pct']:.2f}%)")
            
            for vault in pool_info['extra_vaults']:
                print(f"  - {vault['token']}: ", end="")
                if vault['assets'] > 0:
                    print(f"Assets: {vault['assets']:,.2f} ", end="")
                if vault['borrowed'] > 0:
                    print(f"Borrowed: {vault['borrowed']:,.2f} ", end="")
                print(f"(NAV: ${vault['nav']:,.2f})")
        
        print("\n" + "=" * 70)
        print("SUMMARY:")
        print("=" * 70)
        print(f"Pools with extra vaults: {len(pools_with_extra_vaults)} out of {active_pools} active pools")
        
        # Calculate statistics
        significant_pools = [p for p in pools_with_extra_vaults if abs(p['nav_difference_pct']) > 1]
        print(f"Pools where extra vaults > 1% of NAV: {len(significant_pools)}")
        
        if significant_pools:
            max_impact = max(significant_pools, key=lambda x: abs(x['nav_difference_pct']))
            print(f"Maximum impact: {max_impact['nav_difference_pct']:.2f}% (Pool: {max_impact['pool'][:10]}...)")
    else:
        print("\n✓ No active pools have non-zero balances in extra vaults")
        print("All NAV comes from the configured pool vaults only")

if __name__ == "__main__":
    analyze_all_pools()