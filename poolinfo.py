#!/usr/bin/env python3
"""
Get detailed information about an EulerSwap pool.

Fetches deployment parameters, configuration, and current status for a pool address.

Usage:
  python poolinfo.py --pool 0xa4e744240a15af0afbef2618d9a0edaa228428a8 --chain 1
"""
import argparse
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional

import requests

DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"
DEFAULT_REST_API = "https://index-dev.eul.dev/v1/swap/pools"


def fetch_pool_deployment(graphql: str, chain: int, pool: str) -> Optional[Dict[str, Any]]:
    """Fetch pool deployment information from GraphQL."""
    query = f"""
    query {{
      deployment: eulerSwapFactoryPoolDeployed(chainId: {chain}, pool: "{pool.lower()}") {{
        pool
        asset0
        asset1
        asset0Decimals
        asset1Decimals
        createdAt
      }}
      config: eulerSwapFactoryPoolConfig(chainId: {chain}, pool: "{pool.lower()}") {{
        fee
        protocolFee
        protocolFeeRecipient
        vault0
        vault1
        eulerAccount
        currReserve0
        currReserve1
      }}
    }}
    """
    
    r = requests.post(graphql, json={"query": query}, timeout=30)
    r.raise_for_status()
    
    data = r.json()
    if "errors" in data:
        print(f"GraphQL errors: {data['errors']}", file=sys.stderr)
    deployment = data.get("data", {}).get("deployment")
    config = data.get("data", {}).get("config")
    
    if deployment:
        # Merge config into deployment
        if config:
            deployment.update(config)
        return deployment
    
    return None


def get_token_symbol(address: str) -> str:
    """Get token symbol from known addresses."""
    known_tokens = {
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
        "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
        "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
        "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
        "0x66a1e37c9b0eaddca17d3662d6c05f4decf3e110": "USR",
        "0x4c9edd5852cd905f086c759e8383e09bff1e68b3": "USDe",
        "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK",
        "0x7d1afa7b718fb893db30a3abc0cfc608aacfebb0": "MATIC",
        "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": "SHIB",
    }
    return known_tokens.get(address.lower(), address[:8] + "...")


def fetch_current_status(rest_api: str, chain: int, pool: str) -> Optional[Dict[str, Any]]:
    """Check current pool status from REST API."""
    try:
        r = requests.get(f"{rest_api}?chainId={chain}", timeout=30)
        r.raise_for_status()
        
        pools = r.json()
        if not isinstance(pools, list):
            pools = pools.get("data", [pools]) if isinstance(pools, dict) else [pools]
        
        for p in pools:
            if p.get("pool", "").lower() == pool.lower():
                return p
    except:
        pass
    
    return None


def fetch_last_activity(graphql: str, chain: int, pool: str) -> Optional[Dict[str, Any]]:
    """Fetch last swap activity."""
    query = f"""
    query {{
      swaps: eulerSwapSwaps(
        where: {{chainId: {chain}, pool: "{pool.lower()}"}}
        orderBy: "timestamp"
        orderDirection: "desc"
        limit: 1
      ) {{
        items {{
          blockNumber
          timestamp
          reserve0
          reserve1
          fee0
          fee1
        }}
      }}
    }}
    """
    
    try:
        r = requests.post(graphql, json={"query": query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", {}).get("swaps", {}).get("items", [])
        return items[0] if items else None
    except:
        return None


def fetch_swap_count(graphql: str, chain: int, pool: str) -> int:
    """Get total number of swaps for the pool."""
    query = f"""
    query {{
      swaps: eulerSwapSwaps(
        where: {{chainId: {chain}, pool: "{pool.lower()}"}}
        limit: 1000
      ) {{
        items {{
          blockNumber
        }}
      }}
    }}
    """
    
    try:
        r = requests.post(graphql, json={"query": query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", {}).get("swaps", {}).get("items", [])
        return len(items)
    except:
        return 0


def format_timestamp(ts: int) -> str:
    """Format Unix timestamp to readable date."""
    if not ts:
        return "Unknown"
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S UTC")


def format_fee(fee) -> str:
    """Format fee as basis points."""
    if fee is None:
        return "Unknown"
    try:
        # Convert to int if it's a string
        fee_int = int(fee) if isinstance(fee, str) else fee
        # Fee is typically stored as parts per 1e15
        # 5000000000000 = 0.05% = 5 bps
        bps = fee_int / 1e11  # Convert to basis points
        pct = fee_int / 1e13  # Convert to percentage
        return f"{bps:.2f} bps ({pct:.3f}%)"
    except (ValueError, TypeError):
        return "Unknown"


def main():
    parser = argparse.ArgumentParser(description="Get EulerSwap pool information")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--graphql", default=DEFAULT_GRAPHQL, help="GraphQL endpoint")
    parser.add_argument("--rest-api", default=DEFAULT_REST_API, help="REST API endpoint")
    parser.add_argument("--format", choices=["simple", "json"], default="simple", help="Output format")
    
    args = parser.parse_args()
    
    try:
        # Fetch pool deployment info
        pool_data = fetch_pool_deployment(args.graphql, args.chain, args.pool)
        
        if not pool_data:
            print(f"Pool {args.pool} not found on chain {args.chain}")
            return 1
        
        # Get token symbols and decimals
        symbol0 = get_token_symbol(pool_data["asset0"])
        symbol1 = get_token_symbol(pool_data["asset1"])
        dec0 = int(pool_data.get("asset0Decimals", 18))
        dec1 = int(pool_data.get("asset1Decimals", 18))
        
        # Get last activity first
        last_activity = fetch_last_activity(args.graphql, args.chain, args.pool)
        
        # Check current status
        current_status = fetch_current_status(args.rest_api, args.chain, args.pool)
        
        # If inactive, try to get last known status from historical data
        if not current_status and last_activity:
            try:
                # Fetch historical data at last activity block
                import requests
                hist_url = f"{args.rest_api}?chainId={args.chain}&blockNumber={last_activity['blockNumber']}"
                r = requests.get(hist_url, timeout=30)
                r.raise_for_status()
                pools = r.json()
                if not isinstance(pools, list):
                    pools = pools.get("data", [pools]) if isinstance(pools, dict) else [pools]
                for p in pools:
                    if p.get("pool", "").lower() == args.pool.lower():
                        current_status = p
                        current_status['isHistorical'] = True
                        break
            except:
                pass
        
        # Get swap count
        swap_count = fetch_swap_count(args.graphql, args.chain, args.pool)
        
        if args.format == "json":
            output = {
                "pool": args.pool,
                "chainId": args.chain,
                "deployment": {
                    "createdAt": pool_data.get("createdAt"),
                    "createdAtFormatted": format_timestamp(int(pool_data.get("createdAt", 0))),
                },
                "tokens": {
                    "token0": {
                        "address": pool_data["asset0"],
                        "symbol": symbol0,
                        "decimals": dec0
                    },
                    "token1": {
                        "address": pool_data["asset1"],
                        "symbol": symbol1,
                        "decimals": dec1
                    },
                },
                "configuration": {
                    "fee": pool_data.get("fee"),
                    "feeFormatted": format_fee(pool_data.get("fee")),
                    "protocolFee": pool_data.get("protocolFee"),
                    "protocolFeeFormatted": format_fee(pool_data.get("protocolFee")),
                    "protocolFeeRecipient": pool_data.get("protocolFeeRecipient"),
                    "vault0": pool_data.get("vault0"),
                    "vault1": pool_data.get("vault1"),
                    "eulerAccount": pool_data.get("eulerAccount"),
                },
                "currentReserves": {
                    "reserve0": pool_data.get("currReserve0"),
                    "reserve1": pool_data.get("currReserve1"),
                    "formatted": {
                        symbol0: float(int(pool_data.get("currReserve0", 0)) / 10**dec0),
                        symbol1: float(int(pool_data.get("currReserve1", 0)) / 10**dec1),
                    }
                },
                "status": {
                    "isActive": current_status is not None,
                    "totalSwaps": swap_count,
                    "lastActivity": last_activity,
                },
                "concentration": {
                    symbol0: float(current_status.get('conc0', 0)) / 1e18 * 100 if current_status and current_status.get('conc0') else None,
                    symbol1: float(current_status.get('conc1', 0)) / 1e18 * 100 if current_status and current_status.get('conc1') else None,
                } if current_status else None
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"Pool Information: {args.pool}")
            print("=" * 70)
            
            print(f"\nDeployment:")
            print(f"  Created:     {format_timestamp(int(pool_data.get('createdAt', 0)))}")
            print(f"  Status:      {'ACTIVE' if current_status else 'INACTIVE/UNINSTALLED'}")
            print(f"  Total Swaps: {swap_count}")
            
            # Add volume and APY if active
            if current_status:
                if current_status.get('volume7d'):
                    vol = float(current_status.get('volume7d', 0))
                    print(f"  7d Volume:   ${vol:,.2f}")
                if current_status.get('apy'):
                    apy = float(current_status.get('apy', 0)) / 1e18 * 100
                    print(f"  APY:         {apy:.2f}%")
            
            print(f"\nTokens:")
            print(f"  Token0:      {symbol0}")
            print(f"               {pool_data.get('asset0')}")
            print(f"               Decimals: {dec0}")
            
            print(f"  Token1:      {symbol1}")
            print(f"               {pool_data.get('asset1')}")
            print(f"               Decimals: {dec1}")
            
            print(f"\nConfiguration:")
            print(f"  Fee:         {format_fee(pool_data.get('fee'))}")
            print(f"  Protocol Fee: {format_fee(pool_data.get('protocolFee'))}")
            if pool_data.get('protocolFeeRecipient') and pool_data.get('protocolFeeRecipient') != "0x0000000000000000000000000000000000000000":
                print(f"  Fee Recipient: {pool_data.get('protocolFeeRecipient')}")
            
            # Add concentration if available from current status
            if current_status and current_status.get('conc0'):
                conc0 = float(current_status.get('conc0', 0)) / 1e18 * 100
                conc1 = float(current_status.get('conc1', 0)) / 1e18 * 100
                print(f"\nConcentration{' (at last activity)' if current_status.get('isHistorical') else ''}:")
                print(f"  {symbol0}: {conc0:.4f}%")
                print(f"  {symbol1}: {conc1:.4f}%")
            
            print(f"\nVaults:")
            print(f"  Vault0:      {pool_data.get('vault0', 'Unknown')}")
            print(f"  Vault1:      {pool_data.get('vault1', 'Unknown')}")
            
            print(f"\nAccounts:")
            print(f"  Euler Account: {pool_data.get('eulerAccount', 'Unknown')}")
            
            if pool_data.get('currReserve0') or pool_data.get('currReserve1'):
                r0 = int(pool_data.get('currReserve0', 0))
                r1 = int(pool_data.get('currReserve1', 0))
                print(f"\nCurrent Reserves (from config):")
                print(f"  {symbol0}: {r0/10**dec0:,.2f}")
                print(f"  {symbol1}: {r1/10**dec1:,.2f}")
                
                # Add equilibrium reserves if available
                if current_status and current_status.get('equilibriumReserves0'):
                    eq0 = float(current_status.get('equilibriumReserves0', 0))
                    eq1 = float(current_status.get('equilibriumReserves1', 0))
                    print(f"\nEquilibrium Reserves:")
                    print(f"  {symbol0}: {eq0/10**dec0:,.2f}")
                    print(f"  {symbol1}: {eq1/10**dec1:,.2f}")
            
            if last_activity:
                print(f"\nLast Activity:")
                print(f"  Block:       {last_activity['blockNumber']}")
                print(f"  Timestamp:   {format_timestamp(int(last_activity['timestamp']))}")
                if last_activity.get('reserve0'):
                    print(f"  Reserves:    {float(last_activity['reserve0'])/10**dec0:,.2f} / {float(last_activity['reserve1'])/10**dec1:,.2f}")
                if last_activity.get('fee0') or last_activity.get('fee1'):
                    print(f"  Fees Collected: {float(last_activity.get('fee0', 0))/10**dec0:.4f} / {float(last_activity.get('fee1', 0))/10**dec1:.4f}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())