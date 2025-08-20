#!/usr/bin/env python3
"""
Generic pool analysis and visualization for any token pair.
Automatically detects pair type and generates appropriate charts.
"""
import re
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from enum import Enum

class PairType(Enum):
    """Classification of token pairs for appropriate analysis."""
    STABLE_STABLE = "stable_stable"      # USDC/USDT
    VOLATILE_STABLE = "volatile_stable"  # ETH/USDC
    VOLATILE_VOLATILE = "volatile_volatile"  # ETH/BTC
    LST_BASE = "lst_base"               # wstETH/WETH, rETH/WETH
    WRAPPED_UNWRAPPED = "wrapped"        # WETH/ETH, WBTC/BTC
    GENERIC = "generic"                  # Default fallback

class TokenRegistry:
    """Registry of known tokens and their characteristics."""
    
    STABLECOINS = {
        'USDC', 'USDT', 'DAI', 'BUSD', 'TUSD', 'USDP', 'GUSD', 'FRAX', 'LUSD', 'SUSD',
        'USDE'  # Ethena USD
    }
    
    LST_TOKENS = {
        'WSTETH': 'STETH',  # wstETH -> stETH
        'RETH': 'ETH',      # rETH -> ETH
        'SFRXETH': 'FRXETH', # sfrxETH -> frxETH
        'CBETH': 'ETH',     # cbETH -> ETH
    }
    
    WRAPPED_TOKENS = {
        'WETH': 'ETH',
        'WBTC': 'BTC',
        'WMATIC': 'MATIC',
        'WAVAX': 'AVAX',
    }
    
    VOLATILE_MAJORS = {
        'ETH', 'WETH', 'BTC', 'WBTC', 'BNB', 'SOL', 'AVAX', 'MATIC'
    }
    
    @classmethod
    def is_stablecoin(cls, symbol: str) -> bool:
        return symbol.upper() in cls.STABLECOINS
    
    @classmethod
    def is_lst(cls, symbol: str) -> bool:
        return symbol.upper() in cls.LST_TOKENS
    
    @classmethod
    def is_wrapped(cls, symbol: str) -> bool:
        return symbol.upper() in cls.WRAPPED_TOKENS
    
    @classmethod
    def is_volatile_major(cls, symbol: str) -> bool:
        return symbol.upper() in cls.VOLATILE_MAJORS or symbol.upper() in cls.WRAPPED_TOKENS

class PairAnalyzer:
    """Analyzes token pairs and determines appropriate visualizations."""
    
    def __init__(self, token0_symbol: str, token1_symbol: str):
        self.token0 = token0_symbol.upper()
        self.token1 = token1_symbol.upper()
        self.pair_type = self._classify_pair()
        
    def _classify_pair(self) -> PairType:
        """Classify the token pair for appropriate analysis."""
        
        # Check for stable/stable
        if TokenRegistry.is_stablecoin(self.token0) and TokenRegistry.is_stablecoin(self.token1):
            return PairType.STABLE_STABLE
        
        # Check for LST/base pairs
        if TokenRegistry.is_lst(self.token0) and (self.token1 in ['ETH', 'WETH']):
            return PairType.LST_BASE
        
        # Check for wrapped/unwrapped
        if (TokenRegistry.is_wrapped(self.token0) and 
            TokenRegistry.WRAPPED_TOKENS.get(self.token0) == self.token1):
            return PairType.WRAPPED_UNWRAPPED
        
        # Check for volatile/stable
        if TokenRegistry.is_volatile_major(self.token0) and TokenRegistry.is_stablecoin(self.token1):
            return PairType.VOLATILE_STABLE
        if TokenRegistry.is_stablecoin(self.token0) and TokenRegistry.is_volatile_major(self.token1):
            return PairType.VOLATILE_STABLE
        
        # Check for volatile/volatile
        if TokenRegistry.is_volatile_major(self.token0) and TokenRegistry.is_volatile_major(self.token1):
            return PairType.VOLATILE_VOLATILE
        
        return PairType.GENERIC
    
    def get_chart_config(self) -> Dict:
        """Get chart configuration based on pair type."""
        
        base_config = {
            'nav_usd': True,
            'nav_quote': True,
            'price_ratio': True,
            'net_positions': True,
            'performance': True,
            'volume': True,
            'swaps': True,
            'fee_analysis': True
        }
        
        if self.pair_type == PairType.STABLE_STABLE:
            base_config.update({
                'peg_deviation': True,
                'spread_analysis': True,
                'price_ratio_label': f'{self.token0}/{self.token1} Ratio (should be ~1.0)'
            })
        elif self.pair_type == PairType.LST_BASE:
            base_config.update({
                'staking_premium': True,
                'base_comparison': True,
                'price_ratio_label': f'{self.token0}/{self.token1} Staking Premium'
            })
        elif self.pair_type == PairType.VOLATILE_STABLE:
            base_config.update({
                'price_trend': True,
                'volatility_bands': True,
                'price_ratio_label': f'{self.token0} Price in {self.token1}'
            })
        else:
            base_config['price_ratio_label'] = f'{self.token0}/{self.token1} Ratio'
        
        return base_config

def parse_json_data(filename: str) -> Tuple[pd.DataFrame, float, Dict]:
    """Parse data from JSON file, auto-detecting field format.
    Returns: (DataFrame, fee_rate, metadata)
    """
    with open(filename, 'r') as f:
        json_data = json.load(f)
    
    # Check if it's the new format with metadata
    fee_rate = 0.0001  # Default 1bp
    metadata = {}
    if isinstance(json_data, dict) and 'metadata' in json_data:
        metadata = json_data['metadata']
        fee_rate = metadata.get('fee_rate', 0.0001)
        json_data = json_data['daily_data']
    
    if not json_data:
        return pd.DataFrame(), fee_rate, metadata
    
    first_entry = json_data[0]
    
    # Auto-detect format and token symbols
    if 'token0_symbol' in first_entry:
        # Generic format from daily_nav_history.py --output
        token0_symbol = first_entry['token0_symbol']
        token1_symbol = first_entry['token1_symbol']
        # Check which field names are used
        if 'net0' in first_entry:
            # Format: net0, net1, price0, price1
            token0_net_field = 'net0'
            token1_net_field = 'net1'
            token0_price_field = 'price0'
            token1_price_field = 'price1'
        else:
            # Format: token0_net, token1_net, token0_price, token1_price
            token0_net_field = 'token0_net'
            token1_net_field = 'token1_net'
            token0_price_field = 'token0_price'
            token1_price_field = 'token1_price'
    elif 'wsteth_net' in first_entry:
        # Specific format for wstETH/WETH
        token0_symbol = 'WSTETH'
        token1_symbol = 'WETH'
        token0_net_field = 'wsteth_net'
        token1_net_field = 'weth_net'
        token0_price_field = 'wsteth_price'
        token1_price_field = 'weth_price'
    elif 'usdc_net' in first_entry:
        # Example: USDC/USDT format
        token0_symbol = 'USDC'
        token1_symbol = 'USDT'
        token0_net_field = 'usdc_net'
        token1_net_field = 'usdt_net'
        token0_price_field = 'usdc_price'
        token1_price_field = 'usdt_price'
    else:
        # Fallback to generic
        token0_symbol = 'TOKEN0'
        token1_symbol = 'TOKEN1'
        token0_net_field = 'token0_net'
        token1_net_field = 'token1_net'
        token0_price_field = 'token0_price'
        token1_price_field = 'token1_price'
    
    data = []
    for entry in json_data:
        # Parse with detected field names
        token0_price = entry.get(token0_price_field, 0)
        token1_price = entry.get(token1_price_field, 0)
        
        data.append({
            'date': datetime.strptime(entry['date'], '%Y-%m-%d'),
            'block': entry.get('block', 0),
            'nav_usd': entry.get('nav_usd', entry.get('nav', 0)),  # Support both field names
            'token0_net': entry.get(token0_net_field, 0),
            'token1_net': entry.get(token1_net_field, 0),
            'token0_price': token0_price,
            'token1_price': token1_price,
            'nav_quote': entry.get('nav_in_quote', entry.get('nav_weth', entry.get('nav_quote', 0))),
            'price_ratio': token0_price / token1_price if token1_price > 0 else 0,
            'daily_volume': entry.get('daily_volume', entry.get('volume_usd', 0)),  # Support both field names
            'swaps': entry.get('swaps', entry.get('swap_count', 0)),  # Support both field names
            'token0_symbol': token0_symbol,
            'token1_symbol': token1_symbol
        })
    
    return pd.DataFrame(data), fee_rate, metadata

def create_generic_charts(df: pd.DataFrame, analyzer: PairAnalyzer, fee_rate: float = 0.0001, metadata: Dict = None) -> plt.Figure:
    """Create charts appropriate for the token pair type."""
    
    if metadata is None:
        metadata = {}
    
    config = analyzer.get_chart_config()
    token0 = analyzer.token0
    token1 = analyzer.token1
    
    # Determine number of subplots based on config
    active_charts = sum(1 for v in config.values() if v is True)
    rows = (active_charts + 1) // 2
    
    fig, axes = plt.subplots(rows, 2, figsize=(15, 4*rows))
    axes = axes.flatten() if rows > 1 else [axes[0], axes[1]]
    
    fig.suptitle(f'{token0}/{token1} Pool Performance Analysis\n(Type: {analyzer.pair_type.value})', 
                 fontsize=16, fontweight='bold')
    
    date_format = mdates.DateFormatter('%m/%d')
    chart_idx = 0
    
    # 1. NAV in USD
    if config.get('nav_usd'):
        ax = axes[chart_idx]
        # Auto-scale based on NAV size
        nav_scale = 1e6 if df['nav_usd'].max() > 1e6 else 1e3
        scale_label = 'M' if nav_scale == 1e6 else 'K'
        ax.plot(df['date'], df['nav_usd'] / nav_scale, 'b-', linewidth=2)
        ax.set_title('Net NAV in USD')
        ax.set_ylabel(f'NAV (${scale_label})')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=df['nav_usd'].iloc[0] / nav_scale, color='r', linestyle='--', alpha=0.5, label='Starting NAV')
        ax.legend()
        ax.xaxis.set_major_formatter(date_format)
        
        # Add USD APR annotation
        initial_nav_usd = df['nav_usd'].iloc[0]
        final_nav_usd = df['nav_usd'].iloc[-1]
        days = len(df)
        usd_return_pct = ((final_nav_usd/initial_nav_usd - 1) * 100) if initial_nav_usd > 0 else 0
        usd_apr = usd_return_pct * (365 / days) if days > 0 else 0
        
        ax.text(0.02, 0.98, f'USD APR: {usd_apr:.1f}%', 
                transform=ax.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.7))
        
        chart_idx += 1
    
    # 2. NAV in Quote Token
    if config.get('nav_quote'):
        ax = axes[chart_idx]
        # Use the same scaling as NAV USD for consistency
        nav_scale = 1e6 if df['nav_quote'].max() > 1e6 else 1e3
        scale_label = 'M' if nav_scale == 1e6 else 'K'
        
        ax.plot(df['date'], df['nav_quote'] / nav_scale, 'g-', linewidth=2)
        ax.set_title(f'Net NAV in {token1} Terms')
        ax.set_ylabel(f'NAV ({token1} {scale_label})')
        ax.grid(True, alpha=0.3)
        ax.axhline(y=df['nav_quote'].iloc[0] / nav_scale, color='r', linestyle='--', alpha=0.5, label='Starting NAV')
        ax.legend()
        ax.xaxis.set_major_formatter(date_format)
        
        # Add Quote Token APR annotation
        initial_nav_quote = df['nav_quote'].iloc[0]
        final_nav_quote = df['nav_quote'].iloc[-1]
        days = len(df)
        quote_return_pct = ((final_nav_quote/initial_nav_quote - 1) * 100) if initial_nav_quote > 0 else 0
        quote_apr = quote_return_pct * (365 / days) if days > 0 else 0
        
        ax.text(0.02, 0.98, f'{token1} APR: {quote_apr:.1f}%', 
                transform=ax.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.7))
        
        chart_idx += 1
    
    # 3. Price Ratio
    if config.get('price_ratio'):
        ax = axes[chart_idx]
        
        # For stable pairs, show deviation from 1.0
        if analyzer.pair_type == PairType.STABLE_STABLE:
            # Show ratio centered around 1.0
            ax.plot(df['date'], df['price_ratio'], 'purple', linewidth=2)
            ax.axhline(y=1.0, color='gray', linestyle='--', alpha=0.5, label='Parity')
            # Better y-axis limits for stable pairs
            ratio_min = df['price_ratio'].min()
            ratio_max = df['price_ratio'].max()
            margin = (ratio_max - ratio_min) * 0.1
            if margin < 0.0002:
                margin = 0.0002
            ax.set_ylim([ratio_min - margin, ratio_max + margin])
            # Force proper y-axis formatting to show values around 1.0
            from matplotlib.ticker import FormatStrFormatter
            ax.yaxis.set_major_formatter(FormatStrFormatter('%.4f'))
            ax.legend()
        else:
            ax.plot(df['date'], df['price_ratio'], 'purple', linewidth=2)
        
        ax.set_title(config.get('price_ratio_label', f'{token0}/{token1} Ratio'))
        ax.set_ylabel('Ratio')
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(date_format)
        chart_idx += 1
    
    # 4. Net Positions
    if config.get('net_positions'):
        ax = axes[chart_idx]
        
        # Scale large positions for better visualization
        max_pos = max(df['token0_net'].abs().max(), df['token1_net'].abs().max())
        if max_pos > 1e6:
            # Use millions for large positions
            scale_factor = 1e6
            scale_label = 'M'
        elif max_pos > 1e3:
            # Use thousands for medium positions
            scale_factor = 1e3
            scale_label = 'K'
        else:
            scale_factor = 1
            scale_label = ''
        
        ax.plot(df['date'], df['token0_net'] / scale_factor, 'orange', 
                label=f'{token0}', linewidth=2)
        ax.plot(df['date'], df['token1_net'] / scale_factor, 'blue', 
                label=f'{token1}', linewidth=2)
        ax.set_title('Net Token Positions')
        ax.set_ylabel(f'Amount ({scale_label})' if scale_label else 'Amount')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax.xaxis.set_major_formatter(date_format)
        chart_idx += 1
    
    # 5. Performance Comparison
    if config.get('performance'):
        ax = axes[chart_idx]
        initial_nav_usd = df['nav_usd'].iloc[0]
        initial_nav_quote = df['nav_quote'].iloc[0]
        
        nav_return = ((df['nav_usd'] / initial_nav_usd) - 1) * 100
        quote_return = ((df['nav_quote'] / initial_nav_quote) - 1) * 100
        
        ax.plot(df['date'], nav_return, 'b-', label='NAV (USD)', linewidth=2)
        ax.plot(df['date'], quote_return, 'g-', label=f'NAV ({token1})', linewidth=2)
        
        # Add price return for volatile pairs
        if analyzer.pair_type in [PairType.VOLATILE_STABLE, PairType.VOLATILE_VOLATILE]:
            initial_price = df['token1_price'].iloc[0]
            price_return = ((df['token1_price'] / initial_price) - 1) * 100
            ax.plot(df['date'], price_return, 'r--', label=f'{token1} Price', linewidth=2)
        
        ax.set_title('Cumulative Returns')
        ax.set_ylabel('Return (%)')
        ax.legend()
        ax.grid(True, alpha=0.3)
        ax.axhline(y=0, color='black', linestyle='-', alpha=0.3)
        ax.xaxis.set_major_formatter(date_format)
        chart_idx += 1
    
    # 6. Daily Volume
    if config.get('volume'):
        ax = axes[chart_idx]
        ax.bar(df['date'], df['daily_volume'] / 1e6, color='steelblue', alpha=0.7)
        ax.set_title('Daily Trading Volume')
        ax.set_ylabel('Volume ($M)')
        ax.grid(True, alpha=0.3)
        
        if len(df) >= 7:
            ma7 = df['daily_volume'].rolling(window=7).mean() / 1e6
            ax.plot(df['date'], ma7, 'r-', label='7-day MA', linewidth=2)
            ax.legend()
        
        ax.xaxis.set_major_formatter(date_format)
        chart_idx += 1
    
    # 7. Swap Count
    if config.get('swaps') and chart_idx < len(axes):
        ax = axes[chart_idx]
        ax.bar(df['date'], df['swaps'], color='darkgreen', alpha=0.7)
        ax.set_title('Daily Swap Count')
        ax.set_ylabel('Number of Swaps')
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(date_format)
        chart_idx += 1
    
    # 8. Fee Analysis
    if config.get('fee_analysis') and chart_idx < len(axes):
        ax = axes[chart_idx]
        
        # Calculate cumulative fees using actual fee rate
        df['daily_fees'] = df['daily_volume'] * fee_rate
        df['cumulative_fees'] = df['daily_fees'].cumsum()
        
        ax.plot(df['date'], df['cumulative_fees'] / 1e3, 'gold', linewidth=2)
        ax.set_title('Cumulative Fees Earned')
        ax.set_ylabel('Fees ($K)')
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(date_format)
        
        # Add fee APR annotation
        total_fees = df['cumulative_fees'].iloc[-1]
        avg_nav = df['nav_usd'].mean()
        days = len(df)
        fee_apr = (total_fees / avg_nav) * (365 / days) * 100
        
        # Show fee rate and APR
        fee_bps = fee_rate * 10000
        
        # Calculate total annualized returns
        initial_nav_usd = df['nav_usd'].iloc[0]
        final_nav_usd = df['nav_usd'].iloc[-1]
        initial_nav_quote = df['nav_quote'].iloc[0]
        final_nav_quote = df['nav_quote'].iloc[-1]
        
        usd_return_pct = ((final_nav_usd/initial_nav_usd - 1) * 100) if initial_nav_usd > 0 else 0
        quote_return_pct = ((final_nav_quote/initial_nav_quote - 1) * 100) if initial_nav_quote > 0 else 0
        usd_apr = usd_return_pct * (365 / days) if days > 0 else 0
        quote_apr = quote_return_pct * (365 / days) if days > 0 else 0
        
        token1 = analyzer.token1
        text = f'Fee Rate: {fee_bps:.2f}bps\nFee APR: {fee_apr:.2f}%\n\nTotal Returns:\nUSD APR: {usd_apr:.2f}%\n{token1} APR: {quote_apr:.2f}%'
            
        ax.text(0.02, 0.98, text, 
                transform=ax.transAxes, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        chart_idx += 1
    
    # Hide unused subplots
    for idx in range(chart_idx, len(axes)):
        axes[idx].set_visible(False)
    
    plt.tight_layout()
    
    # Save the figure with pool address prefix in data directory
    import os
    os.makedirs('data', exist_ok=True)
    
    # Extract pool address from metadata if available
    pool_prefix = ""
    if 'pool_address' in metadata:
        pool_addr = metadata['pool_address']
        # Get first 6 chars of address (0x + 4 chars)
        pool_prefix = f"_{pool_addr[:6]}" if pool_addr.startswith('0x') else ""
    
    output_file = f'data/{token0}_{token1}_analysis{pool_prefix}.png'
    plt.savefig(output_file, dpi=150, bbox_inches='tight')
    print(f"Graph saved as '{output_file}'")
    
    return fig

def print_summary_statistics(df: pd.DataFrame, analyzer: PairAnalyzer, fee_rate: float = 0.0001):
    """Print summary statistics appropriate for the pair type."""
    
    token0 = analyzer.token0
    token1 = analyzer.token1
    
    print("\n" + "="*60)
    print("SUMMARY STATISTICS")
    print("="*60)
    print(f"Pool: {token0}/{token1}")
    print(f"Type: {analyzer.pair_type.value}")
    print(f"Period: {df['date'].iloc[0].strftime('%Y-%m-%d')} to {df['date'].iloc[-1].strftime('%Y-%m-%d')}")
    print(f"Days: {len(df)}")
    
    # NAV Performance
    initial_nav_usd = df['nav_usd'].iloc[0]
    final_nav_usd = df['nav_usd'].iloc[-1]
    initial_nav_quote = df['nav_quote'].iloc[0]
    final_nav_quote = df['nav_quote'].iloc[-1]
    
    print(f"\nNAV Performance:")
    print(f"  Starting NAV (USD): ${initial_nav_usd:,.0f}")
    print(f"  Ending NAV (USD): ${final_nav_usd:,.0f}")
    print(f"  USD Return: {((final_nav_usd/initial_nav_usd - 1) * 100):.2f}%")
    
    print(f"\n  Starting NAV ({token1}): {initial_nav_quote:.2f}")
    print(f"  Ending NAV ({token1}): {final_nav_quote:.2f}")
    print(f"  {token1} Return: {((final_nav_quote/initial_nav_quote - 1) * 100):.2f}%")
    
    # Calculate annualized returns
    days = len(df)
    usd_return_pct = ((final_nav_usd/initial_nav_usd - 1) * 100)
    quote_return_pct = ((final_nav_quote/initial_nav_quote - 1) * 100)
    usd_apr = usd_return_pct * (365 / days)
    quote_apr = quote_return_pct * (365 / days)
    
    print(f"\nAnnualized Returns:")
    print(f"  USD APR: {usd_apr:.2f}%")
    print(f"  {token1} APR: {quote_apr:.2f}%")
    
    # Position changes
    print(f"\nPosition Evolution:")
    print(f"  Initial {token0}: {df['token0_net'].iloc[0]:,.2f}")
    print(f"  Final {token0}: {df['token0_net'].iloc[-1]:,.2f}")
    print(f"  Initial {token1}: {df['token1_net'].iloc[0]:,.2f}")
    print(f"  Final {token1}: {df['token1_net'].iloc[-1]:,.2f}")
    
    # Volume and fees
    total_volume = df['daily_volume'].sum()
    total_swaps = df['swaps'].sum()
    total_fees = total_volume * fee_rate
    fee_return = (total_fees / initial_nav_usd) * 100
    days = len(df)
    fee_apr = fee_return * (365 / days)
    fee_bps = fee_rate * 10000
    
    print(f"\nVolume & Fees:")
    print(f"  Total Volume: ${total_volume:,.0f}")
    print(f"  Total Swaps: {total_swaps:,}")
    print(f"  Pool Fee Rate: {fee_bps:.2f} bps ({fee_rate*100:.3f}%)")
    print(f"  Fees Earned: ${total_fees:,.0f}")
    print(f"  Fee Return: {fee_return:.2f}%")
    print(f"  Fee APR: {fee_apr:.2f}%")
    
    
    # Pair-specific metrics
    if analyzer.pair_type == PairType.STABLE_STABLE:
        avg_ratio = df['price_ratio'].mean()
        ratio_std = df['price_ratio'].std()
        print(f"\nStable Pair Metrics:")
        print(f"  Average Ratio: {avg_ratio:.6f}")
        print(f"  Ratio Std Dev: {ratio_std:.6f}")
        print(f"  Max Deviation from Parity: {abs(df['price_ratio'] - 1).max():.4f}")
    
    elif analyzer.pair_type == PairType.LST_BASE:
        avg_ratio = df['price_ratio'].mean()
        print(f"\nLST Metrics:")
        print(f"  Average {token0}/{token1} Ratio: {avg_ratio:.4f}")
        print(f"  Implied Staking Premium: {(avg_ratio - 1) * 100:.2f}%")
    
    elif analyzer.pair_type == PairType.VOLATILE_STABLE:
        price_change = ((df['token0_price'].iloc[-1] / df['token0_price'].iloc[0]) - 1) * 100
        print(f"\nPrice Metrics:")
        print(f"  {token0} Price Change: {price_change:.2f}%")
        print(f"  Average {token0} Price: ${df['token0_price'].mean():,.2f}")
        print(f"  Price Volatility (std): ${df['token0_price'].std():,.2f}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Generic pool analysis for any token pair")
    parser.add_argument("--input", required=True, help="Input JSON file from daily_nav_history.py")
    parser.add_argument("--pair-type", help="Override automatic pair type detection", 
                       choices=[t.value for t in PairType])
    
    args = parser.parse_args()
    
    # Load data
    df, fee_rate, metadata = parse_json_data(args.input)
    
    if df.empty:
        print(f"No data parsed from {args.input}")
        return
    
    # Get token symbols
    token0_symbol = df['token0_symbol'].iloc[0] if 'token0_symbol' in df.columns else 'TOKEN0'
    token1_symbol = df['token1_symbol'].iloc[0] if 'token1_symbol' in df.columns else 'TOKEN1'
    
    print(f"Analyzing {token0_symbol}/{token1_symbol} pool")
    print(f"Parsed {len(df)} days of data")
    
    # Analyze pair type
    analyzer = PairAnalyzer(token0_symbol, token1_symbol)
    
    # Override pair type if specified
    if args.pair_type:
        analyzer.pair_type = PairType(args.pair_type)
        print(f"Using override pair type: {args.pair_type}")
    else:
        print(f"Detected pair type: {analyzer.pair_type.value}")
    
    # Create appropriate charts
    fig = create_generic_charts(df, analyzer, fee_rate, metadata)
    
    # Print summary
    print_summary_statistics(df, analyzer, fee_rate)
    
    # Show plot
    plt.show()

if __name__ == "__main__":
    main()