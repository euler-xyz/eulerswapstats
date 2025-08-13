#!/usr/bin/env python3
"""
Find EulerSwap pools by token pair.

Searches for pools containing specified tokens, including historical pools that may be uninstalled.

Usage:
  python findpool.py --token0 0x66a1e37c9b0eaddca17d3662d6c05f4decf3e110 --token1 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --chain 1
"""
import argparse
import json
import sys
from typing import List, Dict, Any, Optional

import requests

DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"
DEFAULT_REST_API = "https://index-dev.eul.dev/v1/swap/pools"


def search_pools_graphql(graphql: str, chain: int, token0: str, token1: str) -> List[Dict[str, Any]]:
    """Search for pools containing the token pair in GraphQL."""
    
    # Normalize addresses to lowercase
    token0_lower = token0.lower()
    token1_lower = token1.lower()
    
    # Search for pools with token0 as asset0 OR asset1
    # And token1 as the other asset
    queries = [
        # token0 as asset0, token1 as asset1
        f'eulerSwapFactoryPoolDeployeds(where: {{chainId: {chain}, asset0: "{token0_lower}", asset1: "{token1_lower}"}}, limit: 100)',
        # token1 as asset0, token0 as asset1  
        f'eulerSwapFactoryPoolDeployeds(where: {{chainId: {chain}, asset0: "{token1_lower}", asset1: "{token0_lower}"}}, limit: 100)',
    ]
    
    all_pools = []
    
    for i, q in enumerate(queries):
        query = f"""
        query {{
          pools: {q} {{
            items {{
              pool
              asset0
              asset1
              createdAt
              asset0Decimals
              asset1Decimals
            }}
          }}
        }}
        """
        
        try:
            r = requests.post(graphql, json={"query": query}, timeout=30)
            r.raise_for_status()
            data = r.json()
            pools = data.get("data", {}).get("pools", {}).get("items", [])
            all_pools.extend(pools)
        except Exception as e:
            print(f"Warning: Query {i+1} failed: {e}", file=sys.stderr)
    
    # Remove duplicates based on pool address
    seen = set()
    unique_pools = []
    for pool in all_pools:
        if pool["pool"].lower() not in seen:
            seen.add(pool["pool"].lower())
            unique_pools.append(pool)
    
    return unique_pools


def get_pool_current_status(rest_api: str, chain: int, pool_address: str) -> Optional[Dict[str, Any]]:
    """Check if pool is currently active in REST API."""
    try:
        r = requests.get(f"{rest_api}?chainId={chain}", timeout=30)
        r.raise_for_status()
        
        pools = r.json()
        if not isinstance(pools, list):
            pools = pools.get("data", [pools]) if isinstance(pools, dict) else [pools]
        
        for p in pools:
            if p.get("pool", "").lower() == pool_address.lower():
                return p
    except:
        pass
    
    return None


def fetch_pool_swaps(graphql: str, chain: int, pool: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Fetch recent swaps for a pool."""
    query = f"""
    query {{
      eulerSwapSwaps(
        where: {{chainId: {chain}, pool: "{pool.lower()}"}}
        orderBy: "timestamp"
        orderDirection: "desc"
        limit: {limit}
      ) {{
        items {{
          blockNumber
          timestamp
          reserve0
          reserve1
        }}
      }}
    }}
    """
    
    try:
        r = requests.post(graphql, json={"query": query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data.get("data", {}).get("eulerSwapSwaps", {}).get("items", [])
    except:
        return []


def fetch_token_symbols(graphql: str, chain: int, token0: str, token1: str) -> Dict[str, str]:
    """Fetch token symbols."""
    query = f"""
    query {{
      token0: token(chainId: {chain}, address: "{token0.lower()}") {{
        symbol
        name
      }}
      token1: token(chainId: {chain}, address: "{token1.lower()}") {{
        symbol
        name
      }}
    }}
    """
    
    try:
        r = requests.post(graphql, json={"query": query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        symbols = {}
        t0 = data.get("data", {}).get("token0")
        t1 = data.get("data", {}).get("token1")
        
        if t0:
            symbols[token0.lower()] = t0.get("symbol", token0[:8])
        if t1:
            symbols[token1.lower()] = t1.get("symbol", token1[:8])
            
        return symbols
    except:
        return {token0.lower(): token0[:8], token1.lower(): token1[:8]}


def main():
    parser = argparse.ArgumentParser(description="Find EulerSwap pools by token pair")
    parser.add_argument("--token0", required=True, help="First token address")
    parser.add_argument("--token1", required=True, help="Second token address")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--graphql", default=DEFAULT_GRAPHQL, help="GraphQL endpoint")
    parser.add_argument("--rest-api", default=DEFAULT_REST_API, help="REST API endpoint")
    parser.add_argument("--format", choices=["simple", "json"], default="simple", help="Output format")
    
    args = parser.parse_args()
    
    try:
        # Get token symbols
        symbols = fetch_token_symbols(args.graphql, args.chain, args.token0, args.token1)
        symbol0 = symbols.get(args.token0.lower(), args.token0[:8])
        symbol1 = symbols.get(args.token1.lower(), args.token1[:8])
        
        # Search for pools
        pools = search_pools_graphql(args.graphql, args.chain, args.token0, args.token1)
        
        if not pools:
            print(f"No pools found for {symbol0}/{symbol1} on chain {args.chain}")
            return 1
        
        results = []
        for pool in pools:
            pool_addr = pool["pool"]
            created_at = int(pool.get("createdAt", 0))
            
            # Check current status
            current_status = get_pool_current_status(args.rest_api, args.chain, pool_addr)
            is_active = current_status is not None
            
            # Get recent activity
            recent_swaps = fetch_pool_swaps(args.graphql, args.chain, pool_addr)
            last_activity = recent_swaps[0] if recent_swaps else None
            
            result = {
                "pool": pool_addr,
                "asset0": pool["asset0"],
                "asset1": pool["asset1"],
                "createdAt": created_at,
                "isActive": is_active,
                "lastActivity": last_activity
            }
            results.append(result)
        
        if args.format == "json":
            print(json.dumps({
                "tokens": {
                    "token0": {"address": args.token0, "symbol": symbol0},
                    "token1": {"address": args.token1, "symbol": symbol1}
                },
                "pools": results
            }, indent=2))
        else:
            print(f"Pools for {symbol0}/{symbol1}")
            print("=" * 60)
            
            for r in results:
                print(f"\nPool: {r['pool']}")
                print(f"  Created: Block {r['createdAt']}")
                print(f"  Status: {'ACTIVE' if r['isActive'] else 'INACTIVE/UNINSTALLED'}")
                
                if r['lastActivity']:
                    print(f"  Last Activity: Block {r['lastActivity']['blockNumber']}")
                    print(f"  Last Reserves: {float(r['lastActivity']['reserve0'])/1e6:.2f} / {float(r['lastActivity']['reserve1'])/1e6:.2f}")
                else:
                    print(f"  Last Activity: No swaps found")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())