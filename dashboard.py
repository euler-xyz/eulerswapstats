#!/usr/bin/env python3
"""
EulerSwap Lifetime PNL Dashboard
Minimal FastHTML app showing lifetime returns for all pools
"""
from fasthtml.common import *
import requests
from datetime import datetime, timedelta
from decimal import Decimal
import json
from typing import Dict, List, Optional, Tuple
import time
from utils import get_token_symbol, convert_apr_to_percentage, format_nav, format_reserves, calculate_net_interest

# API endpoints
V2_API = "https://index-dev.eul.dev/v2/swap/pools"
GRAPHQL_API = "https://index-dev.euler.finance/graphql"

# Cache for API responses (60 second TTL)
cache = {}
CACHE_TTL = 60

def cached_fetch(url: str, params: dict = None) -> dict:
    """Fetch with simple caching"""
    cache_key = f"{url}:{json.dumps(params or {})}"
    now = time.time()
    
    if cache_key in cache:
        data, timestamp = cache[cache_key]
        if now - timestamp < CACHE_TTL:
            return data
    
    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()
    cache[cache_key] = (data, now)
    return data

def fetch_creation_nav(pool_addr: str, chain: int = 1) -> Tuple[float, int, datetime]:
    """Fetch NAV at pool creation using cached pool data"""
    try:
        # Use cached pool creation block
        from pool_cache import get_pool_creation_block
        created_at, creation_block = get_pool_creation_block(pool_addr, chain)
        
        # Fetch historical NAV at creation block
        hist_data = cached_fetch(V2_API, {"chainId": chain, "blockNumber": creation_block})
        
        for p in hist_data:
            if p['pool'].lower() == pool_addr.lower():
                nav = format_nav(p.get('accountNav', {}))
                return nav, creation_block, datetime.fromtimestamp(created_at)
                
    except Exception as e:
        print(f"Error fetching creation NAV for {pool_addr}: {e}")
    
    return 0.0, 0, datetime.now()


def calculate_pool_metrics(pool: dict, fetch_historical: bool = False) -> dict:
    """Calculate lifetime PNL and other metrics for a pool"""
    pool_addr = pool['pool']
    chain = 1  # Mainnet
    
    # Current NAV
    current_nav = format_nav(pool.get('accountNav', {}))
    
    # For quick display, use simplified metrics from API
    # Only fetch historical data when specifically requested
    if fetch_historical:
        creation_nav, creation_block, created_at = fetch_creation_nav(pool_addr, chain)
        age_days = (datetime.now() - created_at).days if created_at else 0
    else:
        # Use approximations from API data
        creation_nav = current_nav  # Assume no change for quick display
        age_days = 30  # Default assumption
        
    # Use 30d APR from API as a proxy for lifetime return when not fetching historical
    if not fetch_historical:
        apr_30d = pool.get('apr', {}).get('total30d', '0')
        lifetime_return_pct = convert_apr_to_percentage(apr_30d)
        # Rough PNL estimate based on 30d APR (as monthly return)
        lifetime_pnl = current_nav * (lifetime_return_pct / 100) if lifetime_return_pct else 0
        annualized = lifetime_return_pct * 12  # Monthly to annual approximation
    else:
        # Calculate accurate lifetime metrics
        lifetime_pnl = current_nav - creation_nav if creation_nav > 0 else 0
        lifetime_return_pct = ((current_nav / creation_nav - 1) * 100) if creation_nav > 0 else 0
        
        # Annualized return
        if age_days > 0 and creation_nav > 0:
            years = age_days / 365.0
            annualized = ((current_nav / creation_nav) ** (1/years) - 1) * 100 if years > 0 else 0
        else:
            annualized = 0
    
    # Get token symbols
    token0 = get_token_symbol(pool.get('vault0', {}).get('asset', ''))
    token1 = get_token_symbol(pool.get('vault1', {}).get('asset', ''))
    
    return {
        'address': pool_addr,
        'pair': f"{token0}/{token1}",
        'current_nav': current_nav,
        'creation_nav': creation_nav,
        'lifetime_pnl': lifetime_pnl,
        'lifetime_return_pct': lifetime_return_pct,
        'annualized': annualized,
        'age_days': age_days,
        'active': pool.get('active', False),
        'volume_30d': format_nav(pool.get('volume', {}).get('total30d', 0)),
        'fees_30d': format_nav(pool.get('fees', {}).get('total30d', 0)),
        'apr_30d': convert_apr_to_percentage(pool.get('apr', {}).get('total30d', '0')),
    }

# FastHTML App
app, rt = fast_app(
    hdrs=[
        Script(src="https://unpkg.com/htmx.org@1.9.10"),
        Style("""
            .profit { color: #10b981; font-weight: 600; }
            .loss { color: #ef4444; font-weight: 600; }
            .neutral { color: #6b7280; }
            .pool-addr { font-family: monospace; font-size: 0.875rem; }
            .metric-card { 
                background: white; 
                padding: 1.5rem; 
                border-radius: 0.5rem; 
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                margin-bottom: 1rem;
            }
            .metric-value { font-size: 2rem; font-weight: bold; }
            .metric-label { color: #6b7280; font-size: 0.875rem; }
            table { margin-top: 1rem; }
            th { cursor: pointer; user-select: none; }
            th:hover { background: #f3f4f6; }
            .inactive { opacity: 0.6; }
            .loading { text-align: center; padding: 2rem; color: #6b7280; }
        """)
    ]
)

@rt("/")
def index():
    """Main dashboard page"""
    return Container(
        H1("EulerSwap Lifetime PNL Dashboard"),
        Div(id="stats", cls="stats-container"),
        Div(id="pools-table", cls="table-container"),
        Script("""
            // Auto-refresh every 60 seconds
            setInterval(() => {
                htmx.ajax('GET', '/stats', {target: '#stats'});
                htmx.ajax('GET', '/table', {target: '#pools-table'});
            }, 60000);
            
            // Initial load
            htmx.ajax('GET', '/stats', {target: '#stats'});
            htmx.ajax('GET', '/table', {target: '#pools-table'});
        """)
    )

@rt("/stats")
def stats():
    """Summary statistics"""
    try:
        pools_data = cached_fetch(V2_API, {"chainId": 1})
        
        # Calculate aggregate stats
        total_nav = 0
        total_profit_pools = 0
        total_loss_pools = 0
        active_pools = 0
        
        for pool in pools_data:
            if pool.get('active'):
                active_pools += 1
                nav = format_nav(pool.get('accountNav', {}))
                total_nav += nav
                
                # Use calculated lifetime return if available, else 30d APR
                if 'lifetime_return_pct' in pool:
                    return_pct = pool.get('lifetime_return_pct', 0)
                else:
                    apr_30d = pool.get('apr', {}).get('total30d', '0')
                    return_pct = convert_apr_to_percentage(apr_30d)
                
                if return_pct > 0:
                    total_profit_pools += 1
                elif return_pct < 0:
                    total_loss_pools += 1
        
        return Grid(
            Card(
                Div("Total Pools", cls="metric-label"),
                Div(f"{active_pools}", cls="metric-value"),
                cls="metric-card"
            ),
            Card(
                Div("Total NAV", cls="metric-label"),
                Div(f"${total_nav:,.0f}", cls="metric-value"),
                cls="metric-card"
            ),
            Card(
                Div("Profitable", cls="metric-label"),
                Div(f"{total_profit_pools}", cls="metric-value profit"),
                cls="metric-card"
            ),
            Card(
                Div("Loss Making", cls="metric-label"),
                Div(f"{total_loss_pools}", cls="metric-value loss"),
                cls="metric-card"
            )
        )
    except Exception as e:
        return Div(f"Error loading stats: {e}", cls="error")

@rt("/table") 
def table(sort: str = "nav", order: str = "desc", show_inactive: bool = False):
    """Pools table with lifetime PNL"""
    try:
        pools_data = cached_fetch(V2_API, {"chainId": 1})
        
        # Calculate metrics for each pool
        pools = []
        for pool in pools_data:
            if not show_inactive and not pool.get('active'):
                continue
            pools.append(calculate_pool_metrics(pool))
        
        # Sort pools
        reverse = (order == "desc")
        if sort == "nav":
            pools.sort(key=lambda x: x['current_nav'], reverse=reverse)
        elif sort == "pnl":
            pools.sort(key=lambda x: x['lifetime_pnl'], reverse=reverse)
        elif sort == "return":
            pools.sort(key=lambda x: x['lifetime_return_pct'], reverse=reverse)
        elif sort == "apy":
            pools.sort(key=lambda x: x['annualized'], reverse=reverse)
        elif sort == "apr30d":
            pools.sort(key=lambda x: x.get('apr_30d', 0), reverse=reverse)
        elif sort == "age":
            pools.sort(key=lambda x: x['age_days'], reverse=reverse)
        elif sort == "volume":
            pools.sort(key=lambda x: x['volume_30d'], reverse=reverse)
        
        # Create table rows
        rows = []
        for p in pools[:50]:  # Limit to top 50 for performance
            pnl_class = "profit" if p['lifetime_pnl'] > 0 else "loss" if p['lifetime_pnl'] < 0 else "neutral"
            row_class = "" if p['active'] else "inactive"
            
            rows.append(
                Tr(
                    Td(Code(p['address'][:10] + "...", cls="pool-addr")),
                    Td(p['pair']),
                    Td(f"${p['current_nav']:,.2f}"),
                    Td(f"${p['creation_nav']:,.2f}"),
                    Td(f"${p['lifetime_pnl']:,.2f}", cls=pnl_class),
                    Td(f"{p['lifetime_return_pct']:.2f}%", cls=pnl_class),
                    Td(f"{p['annualized']:.2f}%"),
                    Td(f"{p.get('apr_30d', 0):.2f}%", cls="neutral" if p.get('apr_30d', 0) == 0 else "profit" if p.get('apr_30d', 0) > 0 else "loss"),
                    Td(f"{p['age_days']}d"),
                    Td(f"${p['volume_30d']:,.0f}"),
                    cls=row_class
                )
            )
        
        return Div(
            Div(
                Label(
                    Input(type="checkbox", 
                          checked=show_inactive,
                          hx_get="/table",
                          hx_target="#pools-table",
                          hx_trigger="change",
                          hx_include="[name='sort'],[name='order']",
                          name="show_inactive"),
                    " Show inactive pools"
                ),
                P(f"Showing {len(rows)} pools", cls="metric-label"),
                style="margin: 1rem 0;"
            ),
            Table(
                Thead(
                    Tr(
                        Th("Pool", hx_get="/table?sort=address", hx_target="#pools-table"),
                        Th("Pair", hx_get="/table?sort=pair", hx_target="#pools-table"),
                        Th("Current NAV", hx_get="/table?sort=nav", hx_target="#pools-table"),
                        Th("Initial NAV", hx_get="/table?sort=creation", hx_target="#pools-table"),
                        Th("Lifetime PNL", hx_get="/table?sort=pnl", hx_target="#pools-table"),
                        Th("Return %", hx_get="/table?sort=return", hx_target="#pools-table"),
                        Th("Calc APY", hx_get="/table?sort=apy", hx_target="#pools-table"),
                        Th("V2 30d APR", hx_get="/table?sort=apr30d", hx_target="#pools-table"),
                        Th("Age", hx_get="/table?sort=age", hx_target="#pools-table"),
                        Th("Volume 30d", hx_get="/table?sort=volume", hx_target="#pools-table"),
                    )
                ),
                Tbody(*rows)
            ),
            P(f"Last updated: {datetime.now().strftime('%H:%M:%S')}", 
              cls="metric-label", 
              style="margin-top: 1rem;")
        )
    except Exception as e:
        return Div(f"Error loading pools: {e}", cls="error")

@rt("/pool/{pool_addr}")
def pool_detail(pool_addr: str):
    """Detailed view for a single pool"""
    try:
        pools_data = cached_fetch(V2_API, {"chainId": 1})
        
        for pool in pools_data:
            if pool['pool'].lower() == pool_addr.lower():
                # Fetch full historical data for detail view
                metrics = calculate_pool_metrics(pool, fetch_historical=True)
                
                return Container(
                    H2(f"Pool: {pool_addr}"),
                    Grid(
                        Card(
                            H3("Lifetime Performance"),
                            P(f"Initial NAV: ${metrics['creation_nav']:,.2f}"),
                            P(f"Current NAV: ${metrics['current_nav']:,.2f}"),
                            P(f"Lifetime PNL: ${metrics['lifetime_pnl']:,.2f}", 
                              cls="profit" if metrics['lifetime_pnl'] > 0 else "loss"),
                            P(f"Return: {metrics['lifetime_return_pct']:.2f}%"),
                            P(f"Annualized: {metrics['annualized']:.2f}%"),
                        ),
                        Card(
                            H3("Pool Details"),
                            P(f"Pair: {metrics['pair']}"),
                            P(f"Age: {metrics['age_days']} days"),
                            P(f"Status: {'Active' if metrics['active'] else 'Inactive'}"),
                            P(f"30d Volume: ${metrics['volume_30d']:,.0f}"),
                            P(f"30d Fees: ${metrics['fees_30d']:,.2f}"),
                        )
                    ),
                    A("← Back to Dashboard", href="/")
                )
        
        return Container(P("Pool not found"), A("← Back to Dashboard", href="/"))
    except Exception as e:
        return Container(
            P(f"Error: {e}"),
            A("← Back to Dashboard", href="/")
        )

if __name__ == "__main__":
    serve(port=5001)