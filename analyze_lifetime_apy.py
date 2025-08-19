#!/usr/bin/env python3
"""
Analyze lifetime APY calculation for a specific pool.
Shows detailed breakdown of how the APY is calculated from NAV changes.
"""
import argparse
import requests
from datetime import datetime
from typing import Dict, Any
from netnav import get_pool_lifespan_return, calculate_net_nav, fetch_pool_data
from pool_cache import get_pool_creation_block
from utils import get_token_symbol

# API endpoints
V1_API = "https://index-dev.eul.dev/v1/swap/pools"
V2_API = "https://index-dev.eul.dev/v2/swap/pools"
DEFAULT_GRAPHQL = "https://index-dev.euler.finance/graphql"
DEFAULT_RPC_URL = "https://ethereum.publicnode.com"


def fetch_v2_pool_data(pool_address: str, chain_id: int = 1) -> Dict[str, Any]:
    """Fetch pool data from V2 API."""
    r = requests.get(V2_API, params={"chainId": chain_id}, timeout=30)
    r.raise_for_status()
    pools = r.json()
    
    for p in pools:
        if p['pool'].lower() == pool_address.lower():
            return p
    return None


def analyze_lifetime_apy(pool_address: str, chain_id: int = 1) -> None:
    """Analyze lifetime APY calculation for a pool."""
    
    print(f"\n{'='*80}")
    print(f"LIFETIME APY ANALYSIS FOR POOL: {pool_address[:10]}...")
    print(f"{'='*80}")
    
    # Get pool creation data
    created_at, creation_block = get_pool_creation_block(pool_address, chain_id)
    creation_date = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"\n1. POOL CREATION INFO:")
    print(f"   Created at: {creation_date} (timestamp: {created_at})")
    print(f"   Creation block: {creation_block}")
    
    # Get lifespan return data
    print(f"\n2. CALCULATING LIFETIME PERFORMANCE...")
    lifespan_data = get_pool_lifespan_return(pool_address, chain_id)
    
    if 'error' in lifespan_data:
        print(f"   ❌ Error: {lifespan_data['error']}")
        return
    
    print(f"\n3. NAV ANALYSIS:")
    print(f"   Starting NAV (at creation):  ${lifespan_data['start_nav']:,.2f}")
    print(f"   Current NAV:                 ${lifespan_data['end_nav']:,.2f}")
    print(f"   Absolute change:             ${lifespan_data['absolute_return']:+,.2f}")
    
    # Handle percentage calculation when start_nav is 0
    if lifespan_data['start_nav'] > 0:
        print(f"   Percentage change:           {lifespan_data['percent_return']:+.2f}%")
    else:
        print(f"   Percentage change:           N/A (started with $0)")
    
    print(f"\n4. TIME PERIOD:")
    days = lifespan_data['days']
    print(f"   Duration: {days:.1f} days")
    print(f"   From block: {lifespan_data['from_block']}")
    print(f"   To block: {lifespan_data['to_block']}")
    
    print(f"\n5. ANNUALIZED RETURN CALCULATION:")
    if days > 0 and lifespan_data['start_nav'] > 0:
        # Show the formula
        start_nav = lifespan_data['start_nav']
        end_nav = lifespan_data['end_nav']
        annual_return = lifespan_data['annualized_return']
        
        print(f"   Formula: ((end_nav / start_nav) ^ (365/days) - 1) * 100")
        print(f"   = (({end_nav:.2f} / {start_nav:.2f}) ^ (365/{days:.1f}) - 1) * 100")
        print(f"   = ({end_nav/start_nav:.4f} ^ {365/days:.4f} - 1) * 100")
        print(f"   = {annual_return:.2f}%")
    else:
        print(f"   Cannot calculate (insufficient data or time)")
    
    print(f"\n6. COMPARISON WITH V2 API APR:")
    v2_data = fetch_v2_pool_data(pool_address, chain_id)
    if v2_data:
        # Get V2 APR values
        apr_data = v2_data.get('apr', {})
        apr_30d = float(apr_data.get('total30d', 0)) / 1e18 * 100
        apr_180d = float(apr_data.get('total180d', 0)) / 1e18 * 100
        
        print(f"   V2 30d APR:  {apr_30d:.2f}% (fees only, no price appreciation)")
        print(f"   V2 180d APR: {apr_180d:.2f}% (fees only, no price appreciation)")
        print(f"   Lifetime APY: {lifespan_data['annualized_return']:.2f}% (includes everything)")
        
        # Get token info from vault data (V2 API structure)
        vault0 = v2_data.get('vault0', {})
        vault1 = v2_data.get('vault1', {})
        token0_addr = vault0.get('asset', '')
        token1_addr = vault1.get('asset', '')
        token0_symbol = get_token_symbol(token0_addr) if token0_addr else 'Unknown'
        token1_symbol = get_token_symbol(token1_addr) if token1_addr else 'Unknown'
        pair = f"{token0_symbol}/{token1_symbol}"
        
        print(f"\n7. TOKEN PAIR: {pair}")
        
        # Get current positions
        print(f"\n8. CURRENT POSITION BREAKDOWN:")
        
        # Try to fetch current pool data for detailed breakdown
        try:
            current_data = fetch_pool_data(V1_API, chain_id, pool_address, lifespan_data['to_block'])
            nav_result = calculate_net_nav(current_data, DEFAULT_GRAPHQL, chain_id, lifespan_data['to_block'])
            
            print(f"   Token 0 ({token0_symbol}):")
            print(f"     Reserve: {nav_result['reserve0']:,.4f}")
            print(f"     Collateral: {nav_result['collateral0']:,.4f}")
            print(f"     Debt: {nav_result['debt0']:,.4f}")
            print(f"     Net: {nav_result['net0']:,.4f}")
            print(f"     Price: ${nav_result['price0']:,.4f}")
            print(f"     Value: ${nav_result['value0']:,.2f}")
            
            print(f"\n   Token 1 ({token1_symbol}):")
            print(f"     Reserve: {nav_result['reserve1']:,.4f}")
            print(f"     Collateral: {nav_result['collateral1']:,.4f}")
            print(f"     Debt: {nav_result['debt1']:,.4f}")
            print(f"     Net: {nav_result['net1']:,.4f}")
            print(f"     Price: ${nav_result['price1']:,.4f}")
            print(f"     Value: ${nav_result['value1']:,.2f}")
            
            print(f"\n   Total NAV: ${nav_result['nav']:,.2f}")
        except Exception as e:
            print(f"   ⚠️  Unable to fetch detailed position data")
            print(f"   (Pool may be inactive at block {lifespan_data['to_block']})")
        
        # Show what contributes to lifetime APY
        print(f"\n9. WHAT CONTRIBUTES TO LIFETIME APY:")
        print(f"   ✓ Swap fees earned")
        print(f"   ✓ Interest earned on collateral")
        print(f"   ✓ Price appreciation of tokens")
        print(f"   ✓ Impermanent gain/loss")
        print(f"   - Interest paid on debt")
        
        print(f"\n10. WHY LIFETIME APY DIFFERS FROM V2 APR:")
        print(f"   • V2 APR only includes fees (and sometimes interest)")
        print(f"   • V2 APR uses current NAV for calculation (not historical)")
        print(f"   • Lifetime APY captures TOTAL return including price changes")
        print(f"   • Lifetime APY is calculated from actual NAV changes over time")
        
        # Check if pool is still active
        if lifespan_data['to_block'] < lifespan_data.get('current_block', lifespan_data['to_block']):
            print(f"\n⚠️  NOTE: Pool appears to be inactive (last data at block {lifespan_data['to_block']})")


def main():
    parser = argparse.ArgumentParser(description="Analyze lifetime APY calculation")
    parser.add_argument("--pool", required=True, help="Pool address")
    parser.add_argument("--chain", type=int, default=1, help="Chain ID (default: 1)")
    
    args = parser.parse_args()
    
    analyze_lifetime_apy(args.pool, args.chain)


if __name__ == "__main__":
    main()