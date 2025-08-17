#!/usr/bin/env python3
"""
Simplified EulerSwap Pool Dashboard (V2 API)
Shows all pools with key metrics using the V2 API
"""
from fasthtml.common import *
import requests
from datetime import datetime
from decimal import Decimal
import json
from utils import get_token_symbol, convert_apr_to_percentage, format_nav, format_reserves, calculate_net_interest

# API endpoint
V2_API = "https://index-dev.eul.dev/v2/swap/pools"

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
        # Fetch pool data
        r = requests.get(V2_API, params={"chainId": 1}, timeout=10)
        r.raise_for_status()
        pools = r.json()
        
        # Calculate summary stats
        active_pools = [p for p in pools if p.get('active')]
        total_nav = sum(format_nav(p.get('accountNav', {})) for p in active_pools)
        total_volume = sum(format_nav(p.get('volume', {}).get('total30d', 0)) for p in active_pools)
        
        # Build pool rows
        rows = []
        for p in active_pools[:100]:  # Limit to 100 most active pools
            # Extract data
            pool_addr = p['pool']
            nav = format_nav(p.get('accountNav', {}))
            
            # Get token pair
            token0 = get_token_symbol(p.get('vault0', {}).get('asset', ''))
            token1 = get_token_symbol(p.get('vault1', {}).get('asset', ''))
            pair = f"{token0}/{token1}"
            
            # Get reserves with proper decimal formatting
            reserve0 = format_reserves(p.get('vault0', {}).get('reserves', 0), token0)
            reserve1 = format_reserves(p.get('vault1', {}).get('reserves', 0), token1)
            
            # APR conversion from 1e18 format to percentage
            apr_30d = p.get('apr', {}).get('total30d', '0')
            apr_val = convert_apr_to_percentage(apr_30d)
            apr_class = "profit" if apr_val > 0 else "loss" if apr_val < 0 else "neutral"
            
            # Volume and fees
            volume_30d = format_nav(p.get('volume', {}).get('total30d', 0))
            fees_30d = format_nav(p.get('fees', {}).get('total30d', 0))
            
            # Net interest calculation
            net_interest = calculate_net_interest(
                p.get('interestEarned', {}).get('total30d', 0),
                p.get('interestPaid', {}).get('total30d', 0)
            )
            
            rows.append(
                Tr(
                    Td(A(Code(pool_addr[:8] + "...", cls="pool-addr"), 
                         href=f"https://etherscan.io/address/{pool_addr}", 
                         target="_blank")),
                    Td(Span(pair, cls="pair-badge")),
                    Td(f"${nav:,.2f}", cls="number"),
                    Td(f"{reserve0:,.2f}", cls="number"),
                    Td(f"{reserve1:,.2f}", cls="number"),
                    Td(f"{apr_val:.2f}%", cls=f"number {apr_class}"),
                    Td(f"${volume_30d:,.0f}", cls="number"),
                    Td(f"${fees_30d:,.2f}", cls="number"),
                    Td(f"${net_interest:+,.2f}", cls=f"number {'profit' if net_interest > 0 else 'loss' if net_interest < 0 else 'neutral'}")
                )
            )
        
        return Div(
            H1("EulerSwap Pools"),
            P(f"Active pools on Ethereum Mainnet", cls="subtitle"),
            
            # Summary stats
            Div(
                Div(
                    Div("Active Pools", cls="stat-label"),
                    Div(f"{len(active_pools)}", cls="stat-value"),
                    cls="stat-card"
                ),
                Div(
                    Div("Total NAV", cls="stat-label"),
                    Div(f"${total_nav:,.0f}", cls="stat-value"),
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
                        Th("NAV"),
                        Th("Reserve 0"),
                        Th("Reserve 1"),
                        Th("30d APR"),
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
            H1("EulerSwap Pools"),
            Div(f"Error loading data: {str(e)}", cls="loading"),
            cls="container"
        )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)