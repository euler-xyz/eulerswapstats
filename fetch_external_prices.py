#!/usr/bin/env python3
"""
Fetch historical price data from external sources like DeFiLlama and CoinGecko.
"""
import argparse
import requests
from datetime import datetime, timedelta
import json
import time
from typing import Dict, List

# Token mappings for different APIs
DEFILLAMA_TOKENS = {
    'steth': 'ethereum:0xae7ab96520de3a18e5e111b5eaab095312d7fe84',
    'wsteth': 'ethereum:0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0',
    'weth': 'ethereum:0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2',
    'eth': 'ethereum:0x0000000000000000000000000000000000000000',
    'usdc': 'ethereum:0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48',
    'usdt': 'ethereum:0xdac17f958d2ee523a2206206994597c13d831ec7',
}

COINGECKO_IDS = {
    'steth': 'staked-ether',
    'wsteth': 'wrapped-steth',
    'eth': 'ethereum',
    'weth': 'weth',
    'usdc': 'usd-coin',
    'usdt': 'tether',
}


def fetch_defillama_historical(token: str, days: int = 30) -> List[Dict]:
    """Fetch historical prices from DeFiLlama."""
    
    # Get token identifier
    if token.lower() in DEFILLAMA_TOKENS:
        token_id = DEFILLAMA_TOKENS[token.lower()]
    else:
        # Assume it's an address, add ethereum: prefix
        if not token.startswith('ethereum:'):
            token_id = f'ethereum:{token.lower()}'
        else:
            token_id = token.lower()
    
    print(f"Fetching from DeFiLlama for {token_id}")
    
    # Calculate timestamps
    end_time = int(datetime.now().timestamp())
    start_time = int((datetime.now() - timedelta(days=days)).timestamp())
    
    # DeFiLlama historical endpoint
    url = f"https://coins.llama.fi/chart/{token_id}"
    params = {
        'period': '1d',  # Daily data
        'span': days  # Number of days
    }
    
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        if 'coins' in data and token_id in data['coins']:
            prices = data['coins'][token_id]['prices']
            
            daily_prices = []
            for price_point in prices:
                timestamp = price_point['timestamp']
                price = price_point['price']
                date = datetime.fromtimestamp(timestamp)
                
                daily_prices.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'timestamp': timestamp,
                    'price': price,
                    'source': 'defillama'
                })
            
            return daily_prices
        else:
            print(f"No data found for {token_id}")
            return []
            
    except Exception as e:
        print(f"Error fetching from DeFiLlama: {e}")
        return []


def fetch_coingecko_historical(token: str, days: int = 30) -> List[Dict]:
    """Fetch historical prices from CoinGecko (free tier)."""
    
    # Get CoinGecko ID
    if token.lower() in COINGECKO_IDS:
        coin_id = COINGECKO_IDS[token.lower()]
    else:
        print(f"Unknown token {token} for CoinGecko")
        return []
    
    print(f"Fetching from CoinGecko for {coin_id}")
    
    # CoinGecko market chart endpoint (free tier)
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
    params = {
        'vs_currency': 'usd',
        'days': days,
        'interval': 'daily'
    }
    
    try:
        r = requests.get(url, params=params, timeout=30)
        
        # Check rate limit
        if r.status_code == 429:
            print("Rate limited by CoinGecko, waiting 60 seconds...")
            time.sleep(60)
            r = requests.get(url, params=params, timeout=30)
        
        r.raise_for_status()
        data = r.json()
        
        if 'prices' in data:
            daily_prices = []
            for price_point in data['prices']:
                timestamp = price_point[0] / 1000  # Convert from ms to seconds
                price = price_point[1]
                date = datetime.fromtimestamp(timestamp)
                
                daily_prices.append({
                    'date': date.strftime('%Y-%m-%d'),
                    'timestamp': timestamp,
                    'price': price,
                    'source': 'coingecko'
                })
            
            return daily_prices
        else:
            print(f"No price data in response")
            return []
            
    except Exception as e:
        print(f"Error fetching from CoinGecko: {e}")
        return []


def fetch_defillama_current(tokens: List[str]) -> Dict[str, float]:
    """Fetch current prices for multiple tokens from DeFiLlama."""
    
    # Build token list
    token_ids = []
    for token in tokens:
        if token.lower() in DEFILLAMA_TOKENS:
            token_ids.append(DEFILLAMA_TOKENS[token.lower()])
        else:
            if not token.startswith('ethereum:'):
                token_ids.append(f'ethereum:{token.lower()}')
            else:
                token_ids.append(token.lower())
    
    # DeFiLlama current prices endpoint
    url = "https://coins.llama.fi/prices/current/" + ','.join(token_ids)
    
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        prices = {}
        if 'coins' in data:
            for token_id, info in data['coins'].items():
                # Extract token symbol or address
                if ':' in token_id:
                    chain, address = token_id.split(':')
                    # Find original token name
                    for name, mapped_id in DEFILLAMA_TOKENS.items():
                        if mapped_id == token_id:
                            prices[name] = info['price']
                            break
                    else:
                        prices[address] = info['price']
                else:
                    prices[token_id] = info['price']
        
        return prices
        
    except Exception as e:
        print(f"Error fetching current prices: {e}")
        return {}


def compare_sources(token: str, days: int = 7):
    """Compare prices from different sources."""
    
    print(f"\nComparing prices for {token.upper()} over {days} days")
    print("=" * 60)
    
    # Fetch from both sources
    defillama_prices = fetch_defillama_historical(token, days)
    time.sleep(1)  # Be nice to APIs
    coingecko_prices = fetch_coingecko_historical(token, days)
    
    # Create date-indexed dicts
    defillama_dict = {p['date']: p['price'] for p in defillama_prices}
    coingecko_dict = {p['date']: p['price'] for p in coingecko_prices}
    
    # Get all dates
    all_dates = sorted(set(list(defillama_dict.keys()) + list(coingecko_dict.keys())))
    
    # Compare
    print(f"{'Date':<12} {'DeFiLlama':<12} {'CoinGecko':<12} {'Difference':<12}")
    print("-" * 48)
    
    for date in all_dates[-7:]:  # Show last 7 days
        dl_price = defillama_dict.get(date, 0)
        cg_price = coingecko_dict.get(date, 0)
        
        if dl_price and cg_price:
            diff = abs(dl_price - cg_price)
            diff_pct = (diff / dl_price * 100) if dl_price > 0 else 0
            print(f"{date:<12} ${dl_price:<11.2f} ${cg_price:<11.2f} {diff_pct:.2f}%")
        elif dl_price:
            print(f"{date:<12} ${dl_price:<11.2f} {'N/A':<12} -")
        elif cg_price:
            print(f"{date:<12} {'N/A':<12} ${cg_price:<11.2f} -")


def main():
    parser = argparse.ArgumentParser(description="Fetch historical prices from external sources")
    parser.add_argument("token", help="Token symbol (steth, wsteth, eth, etc.)")
    parser.add_argument("--days", type=int, default=30, help="Number of days of history")
    parser.add_argument("--source", choices=['defillama', 'coingecko', 'both'], default='defillama',
                       help="Data source to use")
    parser.add_argument("--output", help="Output filename")
    parser.add_argument("--compare", action="store_true", help="Compare prices from different sources")
    
    args = parser.parse_args()
    
    if args.compare:
        compare_sources(args.token, args.days)
        return
    
    # Fetch prices based on source
    if args.source == 'defillama' or args.source == 'both':
        prices = fetch_defillama_historical(args.token, args.days)
        
        if prices:
            print(f"\nFetched {len(prices)} days of data from DeFiLlama")
            
            # Show recent prices
            print("\nRecent prices:")
            for p in prices[-7:]:
                print(f"  {p['date']}: ${p['price']:.2f}")
            
            # Save if requested
            if args.output:
                with open(args.output, 'w') as f:
                    json.dump(prices, f, indent=2)
                print(f"\nSaved to {args.output}")
    
    if args.source == 'coingecko' or args.source == 'both':
        prices = fetch_coingecko_historical(args.token, args.days)
        
        if prices:
            print(f"\nFetched {len(prices)} days of data from CoinGecko")
            
            # Show recent prices
            print("\nRecent prices:")
            for p in prices[-7:]:
                print(f"  {p['date']}: ${p['price']:.2f}")
            
            # Save if requested
            if args.output and args.source == 'coingecko':
                with open(args.output, 'w') as f:
                    json.dump(prices, f, indent=2)
                print(f"\nSaved to {args.output}")
    
    # Test current prices for multiple tokens
    if args.source == 'both':
        print("\n" + "=" * 60)
        print("Current prices for multiple tokens:")
        tokens = ['steth', 'wsteth', 'eth', 'usdc']
        current_prices = fetch_defillama_current(tokens)
        for token, price in current_prices.items():
            print(f"  {token.upper()}: ${price:.2f}")


if __name__ == "__main__":
    main()