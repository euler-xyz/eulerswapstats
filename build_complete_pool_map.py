#!/usr/bin/env python3
"""
Build a complete mapping of ALL pools (including uninstalled) to accounts.
Uses GraphQL to get historical pool deployments and V2 API for current state.
"""
import json
import requests
import csv
from datetime import datetime
from typing import Dict, List, Tuple

# API endpoints
V2_API = "https://index-dev.eul.dev/v2/swap/pools"
DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"


def fetch_all_pool_deployments(chain_id: int = 1) -> List[Dict]:
    """Fetch all pool deployments from GraphQL (includes uninstalled pools)."""
    
    all_deployments = []
    cursor = None
    page = 0
    
    while True:
        page += 1
        print(f"Fetching page {page} of pool deployments...")
        
        # Build query with pagination
        if cursor:
            query = f"""
            query {{
              eulerSwapFactoryPoolDeployeds(
                where: {{chainId: {chain_id}}}
                orderBy: "createdAt"
                orderDirection: "desc"
                limit: 100
                after: "{cursor}"
              ) {{
                items {{
                  pool
                  createdAt
                  eulerAccount
                  asset0
                  asset1
                }}
                pageInfo {{
                  hasNextPage
                  endCursor
                }}
              }}
            }}
            """
        else:
            query = f"""
            query {{
              eulerSwapFactoryPoolDeployeds(
                where: {{chainId: {chain_id}}}
                orderBy: "createdAt"
                orderDirection: "desc"
                limit: 100
              ) {{
                items {{
                  pool
                  createdAt
                  eulerAccount
                  asset0
                  asset1
                }}
                pageInfo {{
                  hasNextPage
                  endCursor
                }}
              }}
            }}
            """
        
        try:
            r = requests.post(DEFAULT_GRAPHQL, json={"query": query}, timeout=30)
            r.raise_for_status()
            data = r.json()
            
            deployments = data.get("data", {}).get("eulerSwapFactoryPoolDeployeds", {})
            items = deployments.get("items", [])
            page_info = deployments.get("pageInfo", {})
            
            if not items:
                break
            
            all_deployments.extend(items)
            print(f"  Found {len(items)} deployments (total: {len(all_deployments)})")
            
            # Check if there are more pages
            if not page_info.get("hasNextPage", False):
                break
            
            cursor = page_info.get("endCursor")
            if not cursor:
                break
                
        except Exception as e:
            print(f"Error fetching deployments: {e}")
            break
    
    print(f"Total deployments found: {len(all_deployments)}")
    return all_deployments


def fetch_current_pool_data() -> Dict[str, Dict]:
    """Fetch current pool data from V2 API."""
    
    try:
        print("Fetching current pool data from V2 API...")
        r = requests.get(V2_API, params={'chainId': 1}, timeout=30)
        r.raise_for_status()
        pools = r.json()
        
        # Create mapping by pool address
        current_pools = {}
        for pool in pools:
            pool_addr = pool.get('pool', '').lower()
            current_pools[pool_addr] = pool
        
        print(f"Found {len(current_pools)} active pools")
        return current_pools
    
    except Exception as e:
        print(f"Error fetching current pools: {e}")
        return {}


def query_pool_config(pool_address: str, chain_id: int = 1) -> Tuple[str, str]:
    """Query pool configuration to get vault addresses."""
    
    query = f"""
    query {{
      config: eulerSwapFactoryPoolConfig(chainId: {chain_id}, pool: "{pool_address.lower()}") {{
        vault0
        vault1
      }}
    }}
    """
    
    try:
        r = requests.post(DEFAULT_GRAPHQL, json={"query": query}, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        config = data.get("data", {}).get("config", {})
        return config.get("vault0", ""), config.get("vault1", "")
    except:
        return "", ""


def query_vault_info(vault_address: str, chain_id: int = 1) -> Tuple[str, str]:
    """Query vault to get underlying asset."""
    
    query = f"""
    query {{
      eulerVault(chainId: {chain_id}, address: "{vault_address.lower()}") {{
        asset
        symbol
      }}
    }}
    """
    
    try:
        r = requests.post(DEFAULT_GRAPHQL, json={"query": query}, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        vault = data.get("data", {}).get("eulerVault", {})
        return vault.get("asset", ""), vault.get("symbol", "")
    except:
        return "", ""


def query_pool_at_block(pool_address: str, block: int, chain_id: int = 1) -> Dict:
    """Query V2 API for pool data at a specific block."""
    
    try:
        params = {
            'chainId': chain_id,
            'blockNumber': block
        }
        r = requests.get(V2_API, params=params, timeout=30)
        r.raise_for_status()
        pools = r.json()
        
        # Find our pool in the response
        for pool in pools:
            if pool.get('pool', '').lower() == pool_address.lower():
                return pool
    except:
        pass
    
    return {}


def build_complete_pool_map(deployments: List[Dict], current_pools: Dict[str, Dict]) -> Tuple[Dict, Dict]:
    """Build complete mapping including historical and current data."""
    
    pool_map = {}
    account_map = {}  # Map accounts to their pools
    
    print("Building complete pool map...")
    total = len(deployments)
    
    for i, deployment in enumerate(deployments):
        if (i + 1) % 10 == 0:
            print(f"  Processing pool {i+1}/{total}...")
        
        pool_addr = deployment['pool'].lower()
        created_at = int(deployment.get('createdAt', 0))
        created_block = 0  # Will estimate from timestamp
        euler_account = deployment.get('eulerAccount', '').lower()
        asset0 = deployment.get('asset0', '').lower()
        asset1 = deployment.get('asset1', '').lower()
        
        # Check if pool is currently active
        current_data = current_pools.get(pool_addr)
        
        pool_info = {
            'pool': pool_addr,
            'created_at': created_at,
            'created_block': created_block,
            'created_date': datetime.fromtimestamp(created_at).strftime('%Y-%m-%d') if created_at else 'Unknown',
            'active': current_data is not None,
            'account': euler_account,  # From deployment event
            'owner': '',
            'token0_symbol': '',
            'token1_symbol': '',
            'token0_addr': asset0,  # From deployment event
            'token1_addr': asset1,  # From deployment event
            'current_nav': 0,
            'total_volume': 0,
            'total_fees': 0
        }
        
        # Get token symbols for the assets
        from utils import get_token_symbol
        if asset0:
            pool_info['token0_symbol'] = get_token_symbol(asset0)
        if asset1:
            pool_info['token1_symbol'] = get_token_symbol(asset1)
        
        if current_data:
            # Pool is active, update with current data (account should match)
            # Use current account if available, otherwise keep deployment account
            if current_data.get('account'):
                pool_info['account'] = current_data.get('account', '')
            pool_info['owner'] = current_data.get('owner', '')
            
            vault0 = current_data.get('vault0', {})
            vault1 = current_data.get('vault1', {})
            pool_info['token0_addr'] = vault0.get('asset', '')
            pool_info['token1_addr'] = vault1.get('asset', '')
            
            # Get token symbols
            from utils import get_token_symbol
            pool_info['token0_symbol'] = get_token_symbol(pool_info['token0_addr']) if pool_info['token0_addr'] else ''
            pool_info['token1_symbol'] = get_token_symbol(pool_info['token1_addr']) if pool_info['token1_addr'] else ''
            
            # Get financial data
            nav = current_data.get('accountNav', {}).get('nav', '0')
            pool_info['current_nav'] = int(nav) / 1e8 if nav else 0
            
            volume = current_data.get('volume', {}).get('total', '0')
            pool_info['total_volume'] = int(volume) / 1e8 if volume else 0
            
            fees = current_data.get('fees', {}).get('total', '0')
            pool_info['total_fees'] = int(fees) / 1e8 if fees else 0
        else:
            # Pool is inactive, query at deployment block to find account
            if created_block > 0:
                historical_data = query_pool_at_block(pool_addr, created_block + 100)  # Query slightly after deployment
                
                if historical_data:
                    pool_info['account'] = historical_data.get('account', '')
                    pool_info['owner'] = historical_data.get('owner', '')
                    
                    vault0 = historical_data.get('vault0', {})
                    vault1 = historical_data.get('vault1', {})
                    pool_info['token0_addr'] = vault0.get('asset', '')
                    pool_info['token1_addr'] = vault1.get('asset', '')
                    
                    from utils import get_token_symbol
                    pool_info['token0_symbol'] = get_token_symbol(pool_info['token0_addr']) if pool_info['token0_addr'] else ''
                    pool_info['token1_symbol'] = get_token_symbol(pool_info['token1_addr']) if pool_info['token1_addr'] else ''
                else:
                    # Fallback to GraphQL config
                    vault0, vault1 = query_pool_config(pool_addr)
                    
                    if vault0 and vault1:
                        # Get token info from vaults
                        token0_addr, token0_symbol = query_vault_info(vault0)
                        token1_addr, token1_symbol = query_vault_info(vault1)
                        
                        pool_info['token0_addr'] = token0_addr
                        pool_info['token1_addr'] = token1_addr
                        pool_info['token0_symbol'] = token0_symbol or 'Unknown'
                        pool_info['token1_symbol'] = token1_symbol or 'Unknown'
        
        # Store in map
        pool_map[pool_addr] = pool_info
        
        # Track by account if we have one
        if pool_info['account']:
            account = pool_info['account'].lower()
            if account not in account_map:
                account_map[account] = []
            account_map[account].append(pool_info)
    
    print(f"Processed {len(pool_map)} pools")
    return pool_map, account_map


def save_complete_mappings(pool_map: Dict, account_map: Dict):
    """Save complete mappings to files."""
    
    # Save complete pool map as JSON
    with open('complete_pool_map.json', 'w') as f:
        json.dump(pool_map, f, indent=2)
    print(f"Saved complete pool map to complete_pool_map.json ({len(pool_map)} pools)")
    
    # Save as CSV for easy viewing
    with open('complete_pool_map.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Pool', 'Created', 'Active', 'Account', 'Token0', 'Token1', 'NAV', 'Volume', 'Fees'])
        
        for pool_addr, info in pool_map.items():
            writer.writerow([
                pool_addr,
                info['created_date'],
                'Yes' if info['active'] else 'No',
                info['account'] or 'Unknown',
                info['token0_symbol'],
                info['token1_symbol'],
                f"${info['current_nav']:,.0f}" if info['current_nav'] else '-',
                f"${info['total_volume']:,.0f}" if info['total_volume'] else '-',
                f"${info['total_fees']:,.0f}" if info['total_fees'] else '-'
            ])
    print("Saved complete pool map to complete_pool_map.csv")
    
    # Save account mapping
    if account_map:
        with open('complete_account_map.json', 'w') as f:
            json.dump(account_map, f, indent=2)
        print(f"Saved account map to complete_account_map.json ({len(account_map)} accounts)")


def print_complete_statistics(pool_map: Dict, account_map: Dict):
    """Print statistics about the complete mapping."""
    
    print("\n" + "="*70)
    print("COMPLETE POOL MAPPING STATISTICS")
    print("="*70)
    
    total_pools = len(pool_map)
    active_pools = sum(1 for p in pool_map.values() if p['active'])
    inactive_pools = total_pools - active_pools
    identified_pools = sum(1 for p in pool_map.values() if p['token0_symbol'] and p['token0_symbol'] != 'Unknown')
    
    print(f"Total pools deployed: {total_pools}")
    print(f"  Active: {active_pools}")
    print(f"  Inactive/Uninstalled: {inactive_pools}")
    print(f"  With token info: {identified_pools}")
    print(f"  Unknown tokens: {total_pools - identified_pools}")
    
    if account_map:
        print(f"\nAccounts with pools: {len(account_map)}")
        
        # Find accounts with multiple pools
        multi_pool = [(acc, len(pools)) for acc, pools in account_map.items() if len(pools) > 1]
        if multi_pool:
            multi_pool.sort(key=lambda x: x[1], reverse=True)
            print(f"Accounts with multiple pools: {len(multi_pool)}")
            for acc, count in multi_pool[:5]:
                print(f"  {acc[:10]}...: {count} pools")
    
    # Token pair statistics
    pairs = {}
    for pool in pool_map.values():
        if pool['token0_symbol'] and pool['token0_symbol'] != 'Unknown':
            pair = f"{pool['token0_symbol']}/{pool['token1_symbol']}"
            if pair not in pairs:
                pairs[pair] = {'total': 0, 'active': 0}
            pairs[pair]['total'] += 1
            if pool['active']:
                pairs[pair]['active'] += 1
    
    if pairs:
        print(f"\nToken pairs found: {len(pairs)}")
        popular = sorted(pairs.items(), key=lambda x: x[1]['total'], reverse=True)
        print("Most deployed pairs:")
        for pair, stats in popular[:10]:
            print(f"  {pair}: {stats['total']} deployments ({stats['active']} active)")
    
    # Timeline analysis
    pools_by_date = {}
    for pool in pool_map.values():
        date = pool['created_date']
        if date != 'Unknown':
            if date not in pools_by_date:
                pools_by_date[date] = 0
            pools_by_date[date] += 1
    
    if pools_by_date:
        sorted_dates = sorted(pools_by_date.items())
        print(f"\nDeployment timeline:")
        print(f"  First deployment: {sorted_dates[0][0]}")
        print(f"  Latest deployment: {sorted_dates[-1][0]}")
        print(f"  Most active day: {max(pools_by_date.items(), key=lambda x: x[1])}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Build complete pool mapping including historical pools")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--stats-only", action="store_true", help="Only show statistics")
    
    args = parser.parse_args()
    
    try:
        # Fetch all historical deployments
        deployments = fetch_all_pool_deployments(args.chain)
        
        if not deployments:
            print("No deployments found")
            return 1
        
        # Fetch current pool data
        current_pools = fetch_current_pool_data()
        
        # Build complete mapping
        pool_map, account_map = build_complete_pool_map(deployments, current_pools)
        
        # Print statistics
        print_complete_statistics(pool_map, account_map)
        
        # Save unless stats-only
        if not args.stats_only:
            save_complete_mappings(pool_map, account_map)
    
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())