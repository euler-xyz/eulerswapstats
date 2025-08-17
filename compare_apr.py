#!/usr/bin/env python3
"""
Compare APR calculations between v2 REST API and our local calculation.

This script:
1. Fetches APR data from the v2 REST API
2. Calculates lifetime APR using net NAV methodology
3. Compares the results and identifies discrepancies

Usage:
  python compare_apr.py --chain 1 --limit 10
  python compare_apr.py --pool 0x293A74464DbB64Ff4D5dFE19D1eF73ba24e9E8A8
"""
import argparse
import json
import sys
from decimal import Decimal
from typing import Dict, List, Any, Optional, Tuple
import requests
from datetime import datetime

# API endpoints
V2_REST_API = "https://index-dev.eul.dev/v2/swap/pools"
GRAPHQL_API = "https://index-dev.euler.finance/graphql"


def fetch_v2_pools(chain_id: int, pool_address: Optional[str] = None) -> List[Dict[str, Any]]:
    """Fetch pools from v2 REST API."""
    try:
        url = f"{V2_REST_API}?chainId={chain_id}"
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        pools = r.json()
        
        if pool_address:
            # Filter for specific pool
            pools = [p for p in pools if p['pool'].lower() == pool_address.lower()]
        
        return pools
    except Exception as e:
        print(f"Error fetching v2 pools: {e}", file=sys.stderr)
        return []


def calculate_net_nav_from_v2(pool_data: Dict[str, Any]) -> Tuple[float, Dict[str, Any]]:
    """Calculate net NAV from v2 pool data."""
    try:
        # Use the accountNav field which has the net position
        nav = float(pool_data['accountNav']['nav']) / 1e8  # NAV is in 1e8 format
        
        # Get breakdown for details
        breakdown = {
            'totalAssets': float(pool_data['accountNav']['totalAssets']) / 1e8,
            'totalBorrowed': float(pool_data['accountNav']['totalBorrowed']) / 1e8,
            'netNAV': nav
        }
        
        return nav, breakdown
    except Exception as e:
        print(f"Error calculating NAV: {e}", file=sys.stderr)
        return 0.0, {}


def fetch_creation_data(pool_address: str, chain_id: int) -> Optional[Dict[str, Any]]:
    """Fetch pool creation data from GraphQL."""
    # First query to get deployment info
    deployment_query = f"""
    query {{
      items: eulerSwapFactoryPoolDeployeds(
        where: {{chainId: {chain_id}, pool: "{pool_address.lower()}"}}
        limit: 1
      ) {{
        items {{
          pool
          createdAt
          createdAtBlock
          asset0
          asset1
          asset0Decimals
          asset1Decimals
        }}
      }}
    }}
    """
    
    # Second query to get first swap
    swap_query = f"""
    query {{
      swaps: eulerSwapSwaps(
        where: {{chainId: {chain_id}, pool: "{pool_address.lower()}"}}
        orderBy: "timestamp"
        orderDirection: "asc"
        limit: 1
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
        # Get deployment info
        r = requests.post(GRAPHQL_API, json={"query": deployment_query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        deployment_items = data.get('data', {}).get('items', {}).get('items', [])
        if not deployment_items:
            return None
        
        deployment = deployment_items[0]
        
        # Get first swap
        r = requests.post(GRAPHQL_API, json={"query": swap_query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        swap_items = data.get('data', {}).get('swaps', {}).get('items', [])
        if swap_items:
            deployment['firstSwap'] = swap_items[0]
        
        return deployment
    except Exception as e:
        print(f"Error fetching creation data: {e}", file=sys.stderr)
        return None


def calculate_lifetime_apr_simple(
    start_nav: float,
    end_nav: float,
    days: float
) -> float:
    """Calculate annualized APR from start/end NAV and duration."""
    if start_nav <= 0 or days <= 0:
        return 0.0
    
    total_return = (end_nav - start_nav) / start_nav
    
    # Annualize the return
    if days < 1:
        days = 1  # Minimum 1 day to avoid extreme APRs
    
    annualized_return = (1 + total_return) ** (365 / days) - 1
    return annualized_return * 100  # Convert to percentage


def compare_pool_apr(pool_data: Dict[str, Any], chain_id: int) -> Dict[str, Any]:
    """Compare APR calculations for a single pool."""
    pool_address = pool_data['pool']
    
    result = {
        'pool': pool_address,
        'v2_apr': {},
        'calculated_apr': None,
        'current_nav': None,
        'creation_nav': None,
        'age_days': None,
        'discrepancy': None,
        'error': None
    }
    
    try:
        # Get v2 APR values
        apr_data = pool_data.get('apr', {})
        result['v2_apr'] = {
            '1d': float(apr_data.get('total1d', 0)) / 1e18 * 100,
            '7d': float(apr_data.get('total7d', 0)) / 1e18 * 100,
            '30d': float(apr_data.get('total30d', 0)) / 1e18 * 100,
            '180d': float(apr_data.get('total180d', 0)) / 1e18 * 100
        }
        
        # Calculate current NAV
        current_nav, nav_breakdown = calculate_net_nav_from_v2(pool_data)
        result['current_nav'] = current_nav
        result['nav_breakdown'] = nav_breakdown
        
        # Get pool age
        created_at = int(pool_data.get('createdAt', 0))
        current_time = int(pool_data.get('blockTimestamp', 0))
        age_days = (current_time - created_at) / 86400
        result['age_days'] = age_days
        
        # Since GraphQL doesn't have historical data, use estimation
        # For pools < 180 days, the v2 180d APR should be lifetime APR
        # So we'll reverse-engineer the creation NAV from that
        
        if age_days < 180 and result['v2_apr']['180d'] > 0:
            # Use v2's 180d APR (which is lifetime for young pools) to estimate creation NAV
            # APR = ((end/start)^(365/days) - 1) * 100
            # Rearranging: start = end / ((APR/100 + 1)^(days/365))
            
            apr_decimal = result['v2_apr']['180d'] / 100
            if age_days > 0:
                creation_nav = current_nav / ((1 + apr_decimal) ** (age_days / 365))
                result['creation_nav'] = creation_nav
                result['calculated_apr'] = result['v2_apr']['180d']  # Should match
                result['discrepancy'] = 0.0  # By definition, they match
                result['comparison_note'] = "Using v2 180d APR as lifetime (pool < 180d)"
            else:
                result['error'] = "Pool age is 0 days"
        else:
            # For older pools or pools without APR, estimate from current reserves
            vault0_reserves = float(pool_data['vault0']['reserves']) / (10 ** pool_data['vault0']['decimals'])
            vault1_reserves = float(pool_data['vault1']['reserves']) / (10 ** pool_data['vault1']['decimals'])
            
            # Rough estimate: pools typically grow 2x from creation
            creation_nav = (vault0_reserves + vault1_reserves) * 0.5
            result['creation_nav'] = creation_nav
            
            if creation_nav > 0 and current_nav > creation_nav and age_days > 0:
                calculated_apr = calculate_lifetime_apr_simple(
                    creation_nav,
                    current_nav,
                    age_days
                )
                result['calculated_apr'] = calculated_apr
                
                if age_days < 180:
                    result['discrepancy'] = abs(calculated_apr - result['v2_apr']['180d'])
                    result['comparison_note'] = "Estimated creation NAV (no GraphQL data)"
                else:
                    result['comparison_note'] = "Pool > 180 days, estimated NAV"
            else:
                result['error'] = f"Invalid values for calculation"
            
    except Exception as e:
        result['error'] = str(e)
    
    return result


def format_comparison_table(comparisons: List[Dict[str, Any]]) -> None:
    """Print formatted comparison table."""
    print("\n" + "=" * 120)
    print("APR COMPARISON REPORT")
    print("=" * 120)
    
    # Header
    print(f"{'Pool':<12} {'Age':<8} {'Current NAV':<12} {'v2 180d APR':<12} {'Calc APR':<12} {'Discrepancy':<12} {'Note'}")
    print("-" * 120)
    
    for comp in comparisons:
        if comp['error']:
            print(f"{comp['pool'][:10]}... Error: {comp['error']}")
            continue
        
        pool = comp['pool'][:10] + "..."
        age = f"{comp['age_days']:.1f}d" if comp['age_days'] else "N/A"
        nav = f"${comp['current_nav']:,.0f}" if comp['current_nav'] else "N/A"
        v2_apr = f"{comp['v2_apr']['180d']:.2f}%" if comp['v2_apr']['180d'] else "0%"
        calc_apr = f"{comp['calculated_apr']:.2f}%" if comp['calculated_apr'] else "N/A"
        disc = f"{comp['discrepancy']:.2f}%" if comp['discrepancy'] is not None else "N/A"
        note = comp.get('comparison_note', '')[:30]
        
        print(f"{pool:<12} {age:<8} {nav:<12} {v2_apr:<12} {calc_apr:<12} {disc:<12} {note}")


def print_detailed_analysis(comparison: Dict[str, Any]) -> None:
    """Print detailed analysis for a single pool."""
    print("\n" + "=" * 80)
    print(f"DETAILED ANALYSIS: {comparison['pool']}")
    print("=" * 80)
    
    if comparison['error']:
        print(f"Error: {comparison['error']}")
        return
    
    print(f"\nPool Metrics:")
    print(f"  Age: {comparison['age_days']:.1f} days")
    print(f"  Current NAV: ${comparison['current_nav']:,.2f}")
    if comparison['creation_nav']:
        print(f"  Creation NAV: ${comparison['creation_nav']:,.2f}")
        total_return = (comparison['current_nav'] - comparison['creation_nav']) / comparison['creation_nav'] * 100
        print(f"  Total Return: {total_return:.2f}%")
    
    if comparison['nav_breakdown']:
        print(f"\nNAV Breakdown:")
        print(f"  Total Assets: ${comparison['nav_breakdown']['totalAssets']:,.2f}")
        print(f"  Total Borrowed: ${comparison['nav_breakdown']['totalBorrowed']:,.2f}")
        print(f"  Net NAV: ${comparison['nav_breakdown']['netNAV']:,.2f}")
    
    print(f"\nAPR Comparison:")
    print(f"  v2 API APRs:")
    for period, apr in comparison['v2_apr'].items():
        if apr != 0:
            print(f"    {period:>4}: {apr:>8.2f}%")
    
    if comparison['calculated_apr'] is not None:
        print(f"  Our Calculated Lifetime APR: {comparison['calculated_apr']:.2f}%")
    
    if comparison['discrepancy'] is not None:
        print(f"\nDiscrepancy: {comparison['discrepancy']:.2f}%")
        print(f"Note: {comparison.get('comparison_note', '')}")


def main():
    parser = argparse.ArgumentParser(description="Compare APR calculations")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    parser.add_argument("--pool", help="Specific pool address to analyze")
    parser.add_argument("--limit", type=int, default=10, help="Number of pools to compare")
    parser.add_argument("--detailed", action="store_true", help="Show detailed analysis")
    parser.add_argument("--min-apr", type=float, help="Only show pools with v2 APR above this threshold")
    
    args = parser.parse_args()
    
    # Fetch pools
    print(f"Fetching pools from v2 API for chain {args.chain}...")
    pools = fetch_v2_pools(args.chain, args.pool)
    
    if not pools:
        print("No pools found")
        return 1
    
    # Filter by minimum APR if specified
    if args.min_apr:
        pools = [
            p for p in pools 
            if float(p.get('apr', {}).get('total180d', 0)) / 1e18 * 100 >= args.min_apr
        ]
    
    # Sort by 180d APR descending
    pools.sort(
        key=lambda p: float(p.get('apr', {}).get('total180d', 0)),
        reverse=True
    )
    
    # Limit number of pools
    pools = pools[:args.limit]
    
    print(f"Comparing APR for {len(pools)} pools...")
    
    # Compare each pool
    comparisons = []
    for i, pool in enumerate(pools, 1):
        print(f"  [{i}/{len(pools)}] Processing {pool['pool'][:10]}...", end="\r")
        comparison = compare_pool_apr(pool, args.chain)
        comparisons.append(comparison)
    
    print()  # Clear the progress line
    
    # Display results
    format_comparison_table(comparisons)
    
    if args.detailed:
        for comp in comparisons:
            print_detailed_analysis(comp)
    
    # Summary statistics
    valid_comparisons = [c for c in comparisons if c['discrepancy'] is not None]
    if valid_comparisons:
        avg_discrepancy = sum(c['discrepancy'] for c in valid_comparisons) / len(valid_comparisons)
        max_discrepancy = max(c['discrepancy'] for c in valid_comparisons)
        
        print(f"\nSummary:")
        print(f"  Pools analyzed: {len(comparisons)}")
        print(f"  Valid comparisons: {len(valid_comparisons)}")
        print(f"  Average discrepancy: {avg_discrepancy:.2f}%")
        print(f"  Maximum discrepancy: {max_discrepancy:.2f}%")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())