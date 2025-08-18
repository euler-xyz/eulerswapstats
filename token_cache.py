#!/usr/bin/env python3
"""
Token symbol and decimals cache with RPC lookup.
Dynamically fetches and caches token information from the blockchain.
"""
import csv
import os
import requests
from typing import Dict, Optional, Tuple
from datetime import datetime

# Cache file path
CACHE_FILE = "token_metadata.csv"
CACHE_FIELDS = ["address", "symbol", "decimals", "last_updated"]

# In-memory cache for this session
_memory_cache: Dict[str, Dict] = {}

# RPC endpoint
DEFAULT_RPC_URL = "https://ethereum.publicnode.com"


def _load_cache() -> Dict[str, Dict]:
    """Load cache from CSV file into memory."""
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Key is lowercase address
                    key = row['address'].lower()
                    cache[key] = {
                        'symbol': row['symbol'],
                        'decimals': int(row['decimals']),
                        'last_updated': row['last_updated']
                    }
        except Exception as e:
            print(f"Warning: Could not load token cache: {e}")
    return cache


def _save_cache_entry(address: str, symbol: str, decimals: int):
    """Save a single cache entry to CSV file."""
    # Check if file exists and has headers
    file_exists = os.path.exists(CACHE_FILE)
    
    # Read existing data
    existing_data = []
    if file_exists:
        try:
            with open(CACHE_FILE, 'r') as f:
                reader = csv.DictReader(f)
                existing_data = list(reader)
        except:
            pass
    
    # Update or add entry
    key = address.lower()
    entry_found = False
    
    for row in existing_data:
        if row['address'].lower() == key:
            # Update existing entry
            row['symbol'] = symbol
            row['decimals'] = str(decimals)
            row['last_updated'] = datetime.now().isoformat()
            entry_found = True
            break
    
    if not entry_found:
        # Add new entry
        new_entry = {
            'address': address.lower(),
            'symbol': symbol,
            'decimals': str(decimals),
            'last_updated': datetime.now().isoformat()
        }
        existing_data.append(new_entry)
    
    # Write back to file
    with open(CACHE_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CACHE_FIELDS)
        writer.writeheader()
        writer.writerows(existing_data)
    
    # Update memory cache
    _memory_cache[key] = {
        'symbol': symbol,
        'decimals': decimals,
        'last_updated': datetime.now().isoformat()
    }


def _fetch_token_metadata_from_chain(address: str) -> Tuple[Optional[str], Optional[int]]:
    """
    Fetch token symbol and decimals from blockchain via RPC.
    
    Returns:
        Tuple of (symbol, decimals) or (None, None) if fetch fails
    """
    # ERC20 function signatures
    symbol_sig = '0x95d89b41'    # symbol()
    decimals_sig = '0x313ce567'  # decimals()
    
    def call_contract(to_addr: str, data: str) -> Optional[str]:
        payload = {
            'jsonrpc': '2.0',
            'method': 'eth_call',
            'params': [{
                'to': to_addr,
                'data': data
            }, 'latest'],
            'id': 1
        }
        
        try:
            r = requests.post(DEFAULT_RPC_URL, json=payload, timeout=5)
            result = r.json().get('result', '0x')
            if result and result != '0x':
                return result
        except:
            pass
        return None
    
    # Fetch symbol
    symbol = None
    symbol_result = call_contract(address, symbol_sig)
    if symbol_result:
        try:
            hex_str = symbol_result[2:]  # Remove 0x
            if len(hex_str) >= 128:
                # ABI encoded string: offset (32 bytes) + length (32 bytes) + data
                length = int(hex_str[64:128], 16)
                symbol_hex = hex_str[128:128+length*2]
                symbol = bytes.fromhex(symbol_hex).decode('utf-8', errors='ignore').strip()
        except:
            pass
    
    # Fetch decimals
    decimals = 18  # Default
    decimals_result = call_contract(address, decimals_sig)
    if decimals_result:
        try:
            decimals = int(decimals_result, 16)
        except:
            pass
    
    return symbol, decimals


def get_token_symbol(address: str, use_cache: bool = True) -> str:
    """
    Get token symbol from address.
    
    Args:
        address: Token contract address
        use_cache: Whether to use cache (default: True)
    
    Returns:
        Token symbol or shortened address if lookup fails
    """
    global _memory_cache
    
    # Normalize address
    addr_lower = address.lower()
    
    # Initialize memory cache if needed
    if not _memory_cache and use_cache:
        _memory_cache = _load_cache()
    
    # Check cache first
    if use_cache and addr_lower in _memory_cache:
        return _memory_cache[addr_lower]['symbol']
    
    # Not in cache, fetch from chain
    symbol, decimals = _fetch_token_metadata_from_chain(address)
    
    if symbol:
        # Save to cache
        if use_cache:
            _save_cache_entry(address, symbol, decimals)
        return symbol
    
    # Fallback to shortened address
    return address[:6].upper()


def get_token_decimals(address: str, use_cache: bool = True) -> int:
    """
    Get token decimals from address.
    
    Args:
        address: Token contract address
        use_cache: Whether to use cache (default: True)
    
    Returns:
        Token decimals (default: 18)
    """
    global _memory_cache
    
    # Normalize address
    addr_lower = address.lower()
    
    # Initialize memory cache if needed
    if not _memory_cache and use_cache:
        _memory_cache = _load_cache()
    
    # Check cache first
    if use_cache and addr_lower in _memory_cache:
        return _memory_cache[addr_lower]['decimals']
    
    # Not in cache, fetch from chain
    symbol, decimals = _fetch_token_metadata_from_chain(address)
    
    if symbol and decimals is not None:
        # Save to cache
        if use_cache:
            _save_cache_entry(address, symbol, decimals)
        return decimals
    
    # Default to 18 decimals
    return 18


def clear_cache():
    """Clear the cache file and memory cache."""
    global _memory_cache
    _memory_cache = {}
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
        print(f"Cleared cache file: {CACHE_FILE}")


def get_cache_stats() -> Dict:
    """Get statistics about the cache."""
    if not os.path.exists(CACHE_FILE):
        return {'exists': False, 'entries': 0}
    
    try:
        with open(CACHE_FILE, 'r') as f:
            reader = csv.DictReader(f)
            entries = list(reader)
            
        return {
            'exists': True,
            'entries': len(entries),
            'file_size': os.path.getsize(CACHE_FILE),
            'tokens': [e['symbol'] for e in entries]
        }
    except:
        return {'exists': True, 'entries': 0, 'error': 'Could not read cache file'}


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "stats":
            print("Token cache statistics:")
            stats = get_cache_stats()
            for key, value in stats.items():
                if key == 'tokens' and value:
                    print(f"  {key}: {', '.join(value[:10])}...")
                else:
                    print(f"  {key}: {value}")
        elif sys.argv[1] == "clear":
            clear_cache()
            print("Cache cleared")
        elif sys.argv[1] == "test":
            # Test with some known tokens
            test_addrs = [
                "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",  # USDC
                "0xdac17f958d2ee523a2206206994597c13d831ec7",  # USDT
                "0x8292bb45bf1ee4d140127049757c2e0ff06317ed",  # Unknown
            ]
            
            for addr in test_addrs:
                symbol = get_token_symbol(addr)
                decimals = get_token_decimals(addr)
                print(f"{addr[:10]}...: {symbol} ({decimals} decimals)")
    else:
        print("Usage:")
        print("  python token_cache.py stats   - Show cache statistics")
        print("  python token_cache.py clear   - Clear the cache")
        print("  python token_cache.py test    - Test token lookups")