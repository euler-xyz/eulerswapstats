#!/usr/bin/env python3
"""
Calculate Net NAV for EulerSwap pools (matching website display).

Net NAV = Value of vault lending positions (assets - borrowed)
This represents the actual economic position after accounting for leverage.

Dependencies:
  - requests (pip install requests)

Usage:
  .venv/bin/python scripts/netnav.py --pool 0xPOOL --chain 1
  .venv/bin/python scripts/netnav.py --pool 0xPOOL --chain 1 --lifespan
  .venv/bin/python scripts/netnav.py --pool 0xPOOL --chain 1 --from-block X --to-block Y
  
  # Can also be imported and used as a library:
  from netnav import get_pool_nav, get_pool_historical_return
"""
import argparse
import json
import sys
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional, List

import requests

DEFAULT_REST_API = "https://index-dev.eul.dev/v1/swap/pools"
DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"
DEFAULT_RPC_URL = "https://ethereum.publicnode.com"


def fetch_pool_data(rest_api: str, chain: int, pool: str, block: int = None) -> Dict[str, Any]:
    """Fetch pool data from REST API.
    
    Args:
        rest_api: REST API endpoint URL
        chain: Chain ID (1 for mainnet)
        pool: Pool address
        block: Optional block number for historical data
    
    Returns:
        Pool data dictionary
    """
    url = f"{rest_api}?chainId={chain}"
    if block:
        url += f"&blockNumber={block}"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    
    pools = r.json()
    if not isinstance(pools, list):
        pools = pools.get("data", [pools]) if isinstance(pools, dict) else [pools]
    
    for p in pools:
        if p.get("pool", "").lower() == pool.lower():
            return p
    
    raise RuntimeError(f"Pool {pool} not found")


def fetch_price(graphql: str, chain: int, asset: str, source: str = "oracle", block: int = None) -> Tuple[int, int]:
    """Fetch price for an asset at or before block.
    
    Args:
        graphql: GraphQL endpoint URL
        chain: Chain ID
        asset: Asset address
        source: Price source (default: "oracle")
        block: Optional block number for historical price
    
    Returns:
        Tuple of (price, scale) where scale is typically 1e8 or 1e18
    """
    where_clause = f'chainId: {chain}, asset: "{asset.lower()}", source: "{source}"'
    if block:
        where_clause += f', blockNumber_lte: "{block}"'
    
    query = f"""
    query {{
      priceCrons(
        where: {{ {where_clause} }}
        orderBy: "blockNumber"
        orderDirection: "desc"
        limit: 1
      ) {{
        items {{ price }}
      }}
    }}
    """
    
    r = requests.post(graphql, json={"query": query}, timeout=30)
    r.raise_for_status()
    
    data = r.json()
    items = data.get("data", {}).get("priceCrons", {}).get("items", [])
    if not items:
        raise RuntimeError(f"No price found for {asset}")
    
    price = int(items[0]["price"])
    
    # Auto-detect scale based on price magnitude (8 digits = 1e8 scale)
    scale = 10**8 if len(str(price)) <= 9 else 10**18
    
    return price, scale


def fetch_pool_created_at(graphql: str, chain: int, pool: str) -> int:
    """Fetch pool creation timestamp.
    
    Args:
        graphql: GraphQL endpoint URL
        chain: Chain ID
        pool: Pool address
    
    Returns:
        Unix timestamp of pool creation
    """
    query = f"""
    query {{
      eulerSwapFactoryPoolDeployed(chainId: {chain}, pool: "{pool}") {{
        createdAt
      }}
    }}
    """
    
    r = requests.post(graphql, json={"query": query}, timeout=30)
    r.raise_for_status()
    
    data = r.json()
    node = data.get("data", {}).get("eulerSwapFactoryPoolDeployed")
    if not node or not node.get("createdAt"):
        raise RuntimeError(f"Pool {pool} not found or missing createdAt")
    
    return int(node["createdAt"])


def rpc_call(rpc_url: str, method: str, params: list) -> Any:
    """Make RPC call to Ethereum node."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(rpc_url, json=payload, timeout=30)
    r.raise_for_status()
    js = r.json()
    if "error" in js and js["error"]:
        raise RuntimeError(f"RPC error: {js['error']}")
    return js.get("result")


def hex_to_int(x: str) -> int:
    """Convert hex string to int."""
    return int(x, 16)


def block_at_or_after_timestamp(rpc_url: str, ts: int) -> int:
    """Binary search for first block at or after timestamp."""
    head_hex = rpc_call(rpc_url, "eth_blockNumber", [])
    head = hex_to_int(head_hex)
    
    def get_block(num: int) -> Dict[str, Any]:
        num_hex = hex(num)
        res = rpc_call(rpc_url, "eth_getBlockByNumber", [num_hex, False])
        if not res:
            raise RuntimeError("eth_getBlockByNumber returned null")
        return res
    
    # Binary search for the block
    left, right = 0, head
    result = head
    
    while left <= right:
        mid = (left + right) // 2
        block = get_block(mid)
        block_ts = hex_to_int(block["timestamp"])
        
        if block_ts >= ts:
            result = mid
            right = mid - 1
        else:
            left = mid + 1
    
    return result


def find_last_available_block(rest_api: str, chain: int, pool: str, start_block: int, head_block: int) -> Optional[int]:
    """Binary search for last block with available REST data."""
    low, high = start_block, head_block
    last_ok = None
    
    while low <= high:
        mid = (low + high) // 2
        try:
            _ = fetch_pool_data(rest_api, chain, pool, mid)
            last_ok = mid
            low = mid + 1
        except Exception:
            high = mid - 1
    
    return last_ok


def fetch_token_symbol(graphql_url: str, chain: int, address: str) -> str:
    """Fetch token symbol from GraphQL or return short address as fallback."""
    query = f"""
    query {{
        token(chainId: {chain}, address: "{address.lower()}") {{
            symbol
        }}
    }}
    """
    
    try:
        r = requests.post(graphql_url, json={"query": query}, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        token_data = data.get("data", {}).get("token")
        if token_data and token_data.get("symbol"):
            return token_data["symbol"]
    except:
        pass
    
    # Fallback to common known tokens if GraphQL fails
    fallback_tokens = {
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
        "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
        "0xc139190f447e929f090edeb554d95abb8b18ac1c": "RLUSD",
    }
    
    return fallback_tokens.get(address.lower(), address[:8] + "...")


def calculate_net_nav(pool_data: Dict[str, Any], graphql_url: str = DEFAULT_GRAPHQL, chain: int = 1, block: int = None) -> Dict[str, Any]:
    """Calculate net NAV from vault lending positions.
    
    Args:
        pool_data: Pool data from REST API
        graphql_url: GraphQL endpoint URL
        chain: Chain ID
        block: Optional block number for historical prices
    
    Returns:
        Dictionary with NAV and position details
    """
    
    # Extract vault data
    vault0 = pool_data["vault0"]
    vault1 = pool_data["vault1"]
    
    # Get assets and decimals
    asset0 = vault0["asset"]
    asset1 = vault1["asset"]
    dec0 = vault0["decimals"]
    dec1 = vault1["decimals"]
    
    # Fetch token symbols dynamically
    symbol0 = fetch_token_symbol(graphql_url, chain, asset0)
    symbol1 = fetch_token_symbol(graphql_url, chain, asset1)
    
    # Get vault positions (what's borrowed/lent)
    v0_borrowed = int(vault0["accountNav"]["borrowed"])
    v0_assets = int(vault0["accountNav"]["assets"])
    v1_borrowed = int(vault1["accountNav"]["borrowed"])
    v1_assets = int(vault1["accountNav"]["assets"])
    
    # Fetch prices (at block if specified)
    p0, scale0 = fetch_price(graphql_url, chain, asset0, block=block)
    p1, scale1 = fetch_price(graphql_url, chain, asset1, block=block)
    
    # Use the same scale for both (they should match)
    scale = scale0
    
    # Calculate values
    v0_borrowed_value = Decimal(v0_borrowed) / (10**dec0) * Decimal(p0) / Decimal(scale)
    v0_assets_value = Decimal(v0_assets) / (10**dec0) * Decimal(p0) / Decimal(scale)
    v1_borrowed_value = Decimal(v1_borrowed) / (10**dec1) * Decimal(p1) / Decimal(scale)
    v1_assets_value = Decimal(v1_assets) / (10**dec1) * Decimal(p1) / Decimal(scale)
    
    # Net NAV = assets - borrowed
    net_nav = (v0_assets_value + v1_assets_value) - (v0_borrowed_value + v1_borrowed_value)
    
    return {
        "nav": float(net_nav),
        "block": pool_data.get("blockNumber"),
        "timestamp": pool_data.get("blockTimestamp"),
        "positions": {
            "asset0": {
                "symbol": symbol0,
                "borrowed": v0_borrowed / (10**dec0),
                "assets": v0_assets / (10**dec0),
                "net": (v0_assets - v0_borrowed) / (10**dec0),
                "price": float(Decimal(p0) / Decimal(scale))
            },
            "asset1": {
                "symbol": symbol1,
                "borrowed": v1_borrowed / (10**dec1),
                "assets": v1_assets / (10**dec1),
                "net": (v1_assets - v1_borrowed) / (10**dec1),
                "price": float(Decimal(p1) / Decimal(scale))
            }
        }
    }


def main():
    parser = argparse.ArgumentParser(description="Calculate Net NAV for EulerSwap pool")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--chain", type=int, required=True, help="Chain ID")
    parser.add_argument("--rest-api", default=DEFAULT_REST_API, help="REST API URL")
    parser.add_argument("--graphql", default=DEFAULT_GRAPHQL, help="GraphQL URL")
    parser.add_argument("--format", choices=["json", "simple"], default="simple", help="Output format")
    parser.add_argument("--from-block", type=int, help="Start block for historical return")
    parser.add_argument("--to-block", type=int, help="End block for historical return")
    parser.add_argument("--lifespan", action="store_true", help="Calculate return from pool creation to latest available data")
    parser.add_argument("--rpc-url", default=DEFAULT_RPC_URL, help="RPC URL for block resolution")
    
    args = parser.parse_args()
    
    try:
        # Lifespan mode: from creation to latest available
        if args.lifespan:
            # Get pool creation timestamp
            created_at = fetch_pool_created_at(args.graphql, args.chain, args.pool)
            
            # Find creation block
            created_block = block_at_or_after_timestamp(args.rpc_url, created_at)
            
            # Find latest available block
            head_hex = rpc_call(args.rpc_url, "eth_blockNumber", [])
            head_num = hex_to_int(head_hex)
            last_block = find_last_available_block(args.rest_api, args.chain, args.pool, created_block, head_num)
            
            if not last_block:
                raise RuntimeError("No available data found for pool")
            
            # Set blocks for historical calculation
            args.from_block = created_block
            args.to_block = last_block
            
            if args.format == "simple":
                print(f"Lifespan: Block {created_block} → {last_block}")
        
        # Historical return mode
        if args.from_block and args.to_block:
            # Fetch data at both blocks
            start_data = fetch_pool_data(args.rest_api, args.chain, args.pool, args.from_block)
            end_data = fetch_pool_data(args.rest_api, args.chain, args.pool, args.to_block)
            
            # Calculate NAVs
            start_result = calculate_net_nav(start_data, args.graphql, args.chain, args.from_block)
            end_result = calculate_net_nav(end_data, args.graphql, args.chain, args.to_block)
            
            # Calculate return
            start_nav = start_result["nav"]
            end_nav = end_result["nav"]
            abs_return = end_nav - start_nav
            pct_return = (abs_return / start_nav * 100) if start_nav != 0 else 0
            
            # Calculate time metrics
            start_ts = int(start_result.get("timestamp", 0))
            end_ts = int(end_result.get("timestamp", 0))
            days = (end_ts - start_ts) / 86400 if (end_ts and start_ts) else None
            
            # Annualized return
            annual_return = None
            if days and days > 0 and pct_return:
                annual_return = (1 + pct_return/100) ** (365/days) - 1
                annual_return *= 100
            
            if args.format == "json":
                print(json.dumps({
                    "pool": args.pool,
                    "chainId": args.chain,
                    "start": {
                        "block": args.from_block,
                        "timestamp": start_ts,
                        "netNAV": start_nav,
                        "positions": start_result["positions"]
                    },
                    "end": {
                        "block": args.to_block,
                        "timestamp": end_ts,
                        "netNAV": end_nav,
                        "positions": end_result["positions"]
                    },
                    "return": {
                        "absolute": abs_return,
                        "percent": pct_return,
                        "days": days,
                        "annualized": annual_return
                    }
                }, indent=2))
            else:
                print(f"Historical Return Analysis")
                print(f"="*40)
                print(f"Period: Block {args.from_block} → {args.to_block}")
                if days:
                    print(f"Duration: {days:.2f} days")
                print(f"\nStart NAV: ${start_nav:,.2f}")
                print(f"End NAV:   ${end_nav:,.2f}")
                print(f"\nReturn:    ${abs_return:,.2f} ({pct_return:+.2f}%)")
                if annual_return:
                    print(f"Annualized: {annual_return:.2f}%")
            return 0
            
        # Current NAV mode
        pool_data = fetch_pool_data(args.rest_api, args.chain, args.pool)
        result = calculate_net_nav(pool_data, args.graphql, args.chain)
        
        if args.format == "json":
            print(json.dumps({
                "pool": args.pool,
                "chainId": args.chain,
                "netNAV": result["nav"],
                "positions": result["positions"]
            }, indent=2))
        else:
            # Simple format
            nav = result["nav"]
            pos = result["positions"]
            
            print(f"Net NAV: ${nav:,.2f}")
            print(f"\nPositions:")
            print(f"  {pos['asset0']['symbol']}: {pos['asset0']['net']:,.2f} @ ${pos['asset0']['price']:.6f}")
            print(f"  {pos['asset1']['symbol']}: {pos['asset1']['net']:,.2f} @ ${pos['asset1']['price']:.6f}")
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
    return 0


# ============== Convenience Functions for Dashboard Use ==============

def get_pool_nav(pool_address: str, chain: int = 1, block: int = None) -> float:
    """
    Get Net NAV for a pool (simple function for dashboards).
    
    Args:
        pool_address: Pool address
        chain: Chain ID (default: 1 for mainnet)
        block: Optional block number for historical NAV
    
    Returns:
        Net NAV in USD
    """
    try:
        pool_data = fetch_pool_data(DEFAULT_REST_API, chain, pool_address, block)
        result = calculate_net_nav(pool_data, DEFAULT_GRAPHQL, chain, block)
        return result["nav"]
    except Exception:
        return 0.0


def get_pool_historical_return(pool_address: str, 
                              from_block: int, 
                              to_block: int,
                              chain: int = 1) -> Dict[str, float]:
    """
    Calculate historical return for a pool between two blocks.
    
    Args:
        pool_address: Pool address
        from_block: Start block
        to_block: End block
        chain: Chain ID (default: 1 for mainnet)
    
    Returns:
        Dictionary with return metrics
    """
    try:
        # Fetch data at both blocks
        start_data = fetch_pool_data(DEFAULT_REST_API, chain, pool_address, from_block)
        end_data = fetch_pool_data(DEFAULT_REST_API, chain, pool_address, to_block)
        
        # Calculate NAVs
        start_result = calculate_net_nav(start_data, DEFAULT_GRAPHQL, chain, from_block)
        end_result = calculate_net_nav(end_data, DEFAULT_GRAPHQL, chain, to_block)
        
        # Calculate return
        start_nav = start_result["nav"]
        end_nav = end_result["nav"]
        abs_return = end_nav - start_nav
        pct_return = (abs_return / start_nav * 100) if start_nav != 0 else 0
        
        # Calculate time metrics
        start_ts = int(start_result.get("timestamp", 0))
        end_ts = int(end_result.get("timestamp", 0))
        days = (end_ts - start_ts) / 86400 if (end_ts and start_ts) else 0
        
        # Annualized return
        annual_return = 0
        if days and days > 0 and start_nav > 0:
            annual_return = ((end_nav / start_nav) ** (365/days) - 1) * 100
        
        return {
            "start_nav": start_nav,
            "end_nav": end_nav,
            "absolute_return": abs_return,
            "percent_return": pct_return,
            "days": days,
            "annualized_return": annual_return
        }
    except Exception:
        return {
            "start_nav": 0,
            "end_nav": 0,
            "absolute_return": 0,
            "percent_return": 0,
            "days": 0,
            "annualized_return": 0
        }


def get_pool_lifespan_return(pool_address: str, chain: int = 1, use_cache: bool = True) -> Dict[str, Any]:
    """
    Calculate return from pool creation to latest available data.
    
    Args:
        pool_address: Pool address
        chain: Chain ID (default: 1 for mainnet)
        use_cache: Whether to use cached pool creation data (default: True)
    
    Returns:
        Dictionary with lifespan return metrics
    """
    try:
        # Try to use cached version if available
        if use_cache:
            try:
                from pool_cache import get_pool_creation_block
                created_at, created_block = get_pool_creation_block(pool_address, chain)
            except ImportError:
                # Fallback to original functions if cache module not available
                created_at = fetch_pool_created_at(DEFAULT_GRAPHQL, chain, pool_address)
                created_block = block_at_or_after_timestamp(DEFAULT_RPC_URL, created_at)
        else:
            # Use original functions without caching
            created_at = fetch_pool_created_at(DEFAULT_GRAPHQL, chain, pool_address)
            created_block = block_at_or_after_timestamp(DEFAULT_RPC_URL, created_at)
        
        # Find latest available block
        head_hex = rpc_call(DEFAULT_RPC_URL, "eth_blockNumber", [])
        head_num = hex_to_int(head_hex)
        
        # Optimization: Check cache and try current block first
        last_block = None
        
        # First, check if we have a cached last available block (for inactive pools)
        if use_cache:
            try:
                from pool_cache import get_last_available_block, set_last_available_block
                cached_last = get_last_available_block(pool_address, chain)
                
                # If we have a cached block and it's not the head (inactive pool)
                if cached_last and cached_last < head_num:
                    try:
                        # Verify it's still valid
                        _ = fetch_pool_data(DEFAULT_REST_API, chain, pool_address, cached_last)
                        last_block = cached_last
                    except:
                        pass  # Cache invalid, will search
            except ImportError:
                pass  # Cache module not available
        
        # If not cached, try current block (for active pools)
        if not last_block:
            try:
                # Try fetching at current block
                _ = fetch_pool_data(DEFAULT_REST_API, chain, pool_address, head_num)
                last_block = head_num
            except:
                # Fall back to binary search only if current block fails
                last_block = find_last_available_block(DEFAULT_REST_API, chain, pool_address, created_block, head_num - 1)
                
                # Cache the result if it's an inactive pool
                if use_cache and last_block and last_block < head_num - 100:  # Pool is likely inactive
                    try:
                        from pool_cache import set_last_available_block
                        set_last_available_block(pool_address, chain, last_block)
                    except:
                        pass
        
        if not last_block:
            raise RuntimeError("No available data found for pool")
        
        # Get historical return
        result = get_pool_historical_return(pool_address, created_block, last_block, chain)
        result["from_block"] = created_block
        result["to_block"] = last_block
        result["created_at"] = created_at
        
        return result
    except Exception as e:
        return {
            "error": str(e),
            "start_nav": 0,
            "end_nav": 0,
            "absolute_return": 0,
            "percent_return": 0,
            "days": 0,
            "annualized_return": 0
        }


def get_all_pools_nav(chain: int = 1) -> List[Dict[str, Any]]:
    """
    Get Net NAV for all pools on a chain.
    
    Args:
        chain: Chain ID (default: 1 for mainnet)
    
    Returns:
        List of pool data with Net NAV calculated
    """
    try:
        r = requests.get(f"{DEFAULT_REST_API}?chainId={chain}", timeout=30)
        r.raise_for_status()
        pools = r.json()
        
        if not isinstance(pools, list):
            pools = pools.get("data", []) if isinstance(pools, dict) else []
        
        results = []
        for pool_data in pools:
            try:
                nav_result = calculate_net_nav(pool_data, DEFAULT_GRAPHQL, chain)
                results.append({
                    "pool": pool_data["pool"],
                    "active": pool_data.get("active", False),
                    "net_nav": nav_result["nav"],
                    "positions": nav_result["positions"]
                })
            except Exception:
                continue
        
        return results
    except Exception:
        return []


if __name__ == "__main__":
    sys.exit(main())