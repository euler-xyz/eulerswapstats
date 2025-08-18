#!/usr/bin/env python3
"""
Simplified EulerSwap Pool Dashboard (NetNAV Calculations)
Shows all pools with key metrics using custom net NAV calculations
"""
from fasthtml.common import *
import requests
from datetime import datetime
from decimal import Decimal
import json
from utils import get_token_symbol, convert_apr_to_percentage, format_reserves, calculate_net_interest
from netnav import calculate_net_nav, get_pool_lifespan_return, DEFAULT_REST_API, DEFAULT_GRAPHQL
from pool_cache import get_pool_creation_block

# API endpoints
V1_API = DEFAULT_REST_API  # "https://index-dev.eul.dev/v1/swap/pools"
V2_API = "https://index-dev.eul.dev/v2/swap/pools"  # For APR and other V2-only fields

# FastHTML App with minimal styling
app, rt = fast_app(
    hdrs=[
        Style("""
            body { font-family: -apple-system, system-ui, sans-serif; }
            .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
            h1 { color: #1f2937; margin-bottom: 10px; }
            .subtitle { color: #6b7280; margin-bottom: 30px; }
            table { 
                width: 100%; 
                border-collapse: collapse; 
                background: white;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            th { 
                background: #f9fafb; 
                padding: 12px; 
                text-align: left; 
                font-weight: 600;
                color: #374151;
                border-bottom: 2px solid #e5e7eb;
            }
            td { 
                padding: 12px; 
                border-bottom: 1px solid #f3f4f6;
            }
            tr:hover { background: #f9fafb; }
            .profit { color: #10b981; font-weight: 600; }
            .loss { color: #ef4444; font-weight: 600; }
            .neutral { color: #6b7280; }
            .pool-addr { 
                font-family: 'SF Mono', Monaco, monospace; 
                font-size: 0.875rem;
                color: #6366f1;
            }
            .pair-badge {
                background: #f3f4f6;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: 500;
            }
            .active { color: #10b981; }
            .inactive { color: #6b7280; opacity: 0.6; }
            .number { text-align: right; font-variant-numeric: tabular-nums; }
            .loading { 
                text-align: center; 
                padding: 40px; 
                color: #6b7280;
            }
            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .stat-card {
                background: white;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            }
            .stat-label {
                color: #6b7280;
                font-size: 0.875rem;
                margin-bottom: 4px;
            }
            .stat-value {
                font-size: 1.875rem;
                font-weight: bold;
                color: #1f2937;
            }
            .timestamp {
                color: #6b7280;
                font-size: 0.875rem;
                margin-top: 20px;
            }
        """)
    ]
)

@rt("/")
def index():
    """Main page that loads pool data directly"""
    try:
        # Fetch pool data from V1 API for net NAV calculations
        r_v1 = requests.get(V1_API, params={"chainId": 1}, timeout=10)
        r_v1.raise_for_status()
        pools_v1 = r_v1.json()
        
        # Fetch V2 data for APR and additional metrics
        r_v2 = requests.get(V2_API, params={"chainId": 1}, timeout=10)
        r_v2.raise_for_status()
        pools_v2 = r_v2.json()
        
        # Create lookup for V2 data
        v2_lookup = {p['pool'].lower(): p for p in pools_v2}
        
        # Process pools with net NAV calculation
        active_pools = []
        total_net_nav = 0
        total_volume = 0
        
        for pool_v1 in pools_v1:
            if not pool_v1.get('active'):
                continue
                
            pool_addr = pool_v1['pool']
            
            # Calculate net NAV using netnav module
            try:
                nav_result = calculate_net_nav(pool_v1, DEFAULT_GRAPHQL, 1)
                net_nav = nav_result["nav"]
                positions = nav_result["positions"]
            except Exception as e:
                print(f"Error calculating NAV for {pool_addr}: {e}")
                net_nav = 0
                positions = None
            
            # Get V2 data for this pool
            v2_data = v2_lookup.get(pool_addr.lower(), {})
            
            # Calculate lifetime APY for all active pools to show alongside V2 APR
            calculated_apy = None
            
            try:
                # Use the lifespan return function which handles all edge cases
                lifespan_data = get_pool_lifespan_return(pool_addr, 1, use_cache=True)
                
                if 'error' not in lifespan_data and lifespan_data.get('annualized_return') is not None:
                    calculated_apy = lifespan_data['annualized_return']
                    
                    # If APY is 0 but NAV exists and pool is young, it might just be stable
                    if calculated_apy == 0 and net_nav > 0 and lifespan_data.get('days', 0) < 7:
                        # For very young pools, show — instead of 0%
                        calculated_apy = None
            except Exception as e:
                # Pool doesn't have creation data or other error - silently skip
                calculated_apy = None
            
            active_pools.append({
                'pool': pool_addr,
                'net_nav': net_nav,
                'positions': positions,
                'v1_data': pool_v1,
                'v2_data': v2_data,
                'calculated_apy': calculated_apy
            })
            
            total_net_nav += net_nav
            total_volume += float(v2_data.get('volume', {}).get('total30d', 0)) / 1e8 if v2_data else 0
        
        # Sort by net NAV descending
        active_pools.sort(key=lambda x: x['net_nav'], reverse=True)
        
        # Build pool rows
        rows = []
        for p in active_pools[:100]:  # Limit to 100 most active pools
            pool_addr = p['pool']
            net_nav = p['net_nav']
            positions = p['positions']
            v1_data = p['v1_data']
            v2_data = p['v2_data']
            
            # Get token pair
            token0 = get_token_symbol(v1_data.get('vault0', {}).get('asset', ''))
            token1 = get_token_symbol(v1_data.get('vault1', {}).get('asset', ''))
            pair = f"{token0}/{token1}"
            
            # Get reserves from positions if available
            if positions:
                reserve0 = positions['asset0']['net']
                reserve1 = positions['asset1']['net']
            else:
                # Fallback to raw reserves
                reserve0 = format_reserves(v1_data.get('vault0', {}).get('reserves', 0), token0)
                reserve1 = format_reserves(v1_data.get('vault1', {}).get('reserves', 0), token1)
            
            # APR from V2 data
            apr_30d = v2_data.get('apr', {}).get('total30d', '0') if v2_data else '0'
            apr_val = convert_apr_to_percentage(apr_30d)
            apr_class = "profit" if apr_val > 0 else "loss" if apr_val < 0 else "neutral"
            
            # Calculated APY
            calc_apy = p.get('calculated_apy')
            calc_apy_str = f"{calc_apy:.2f}%" if calc_apy is not None else "—"
            calc_apy_class = "profit" if calc_apy and calc_apy > 0 else "loss" if calc_apy and calc_apy < 0 else "neutral"
            
            # Volume and fees from V2 data
            volume_30d = float(v2_data.get('volume', {}).get('total30d', 0)) / 1e8 if v2_data else 0
            fees_30d = float(v2_data.get('fees', {}).get('total30d', 0)) / 1e8 if v2_data else 0
            
            # Net interest from V2 data
            if v2_data:
                net_interest = calculate_net_interest(
                    v2_data.get('interestEarned', {}).get('total30d', 0),
                    v2_data.get('interestPaid', {}).get('total30d', 0)
                )
            else:
                net_interest = 0
            
            rows.append(
                Tr(
                    Td(A(Code(pool_addr[:8] + "...", cls="pool-addr"), 
                         href=f"https://etherscan.io/address/{pool_addr}", 
                         target="_blank")),
                    Td(Span(pair, cls="pair-badge")),
                    Td(f"${net_nav:,.2f}", cls="number"),
                    Td(f"{reserve0:,.2f}", cls="number"),
                    Td(f"{reserve1:,.2f}", cls="number"),
                    Td(f"{apr_val:.2f}%", cls=f"number {apr_class}"),
                    Td(calc_apy_str, cls=f"number {calc_apy_class}"),
                    Td(f"${volume_30d:,.0f}", cls="number"),
                    Td(f"${fees_30d:,.2f}", cls="number"),
                    Td(f"${net_interest:+,.2f}", cls=f"number {'profit' if net_interest > 0 else 'loss' if net_interest < 0 else 'neutral'}")
                )
            )
        
        return Div(
            H1("EulerSwap Pools (Net NAV)"),
            P(f"Active pools on Ethereum Mainnet using custom NAV calculations", cls="subtitle"),
            
            # Summary stats
            Div(
                Div(
                    Div("Active Pools", cls="stat-label"),
                    Div(f"{len(active_pools)}", cls="stat-value"),
                    cls="stat-card"
                ),
                Div(
                    Div("Total Net NAV", cls="stat-label"),
                    Div(f"${total_net_nav:,.0f}", cls="stat-value"),
                    cls="stat-card"
                ),
                Div(
                    Div("30d Volume", cls="stat-label"),
                    Div(f"${total_volume:,.0f}", cls="stat-value"),
                    cls="stat-card"
                ),
                cls="stats-grid"
            ),
            
            # Pools table
            Table(
                Thead(
                    Tr(
                        Th("Pool"),
                        Th("Pair"),
                        Th("Net NAV"),
                        Th("Net Position 0"),
                        Th("Net Position 1"),
                        Th("V2 30d APR"),
                        Th("Lifetime APY"),
                        Th("30d Volume"),
                        Th("30d Fees"),
                        Th("30d Net Interest")
                    )
                ),
                Tbody(*rows)
            ),
            
            P(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}", cls="timestamp"),
            cls="container"
        )
        
    except Exception as e:
        return Div(
            H1("EulerSwap Pools (Net NAV)"),
            Div(f"Error loading data: {str(e)}", cls="loading"),
            cls="container"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)