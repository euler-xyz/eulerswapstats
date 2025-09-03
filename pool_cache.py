#!/usr/bin/env python3
"""
Pool creation block cache with CSV persistence.
Avoids repeated GraphQL and RPC calls for the same pool creation data.
"""
import csv
import os
from typing import Dict, Optional, Tuple
from datetime import datetime
import requests
from netnav import (
    fetch_pool_created_at as _original_fetch_pool_created_at,
    block_at_or_after_timestamp as _original_block_at_or_after_timestamp,
    DEFAULT_GRAPHQL,
    DEFAULT_RPC_URL
)

# Cache file path
CACHE_FILE = "pool_creation_blocks.csv"
CACHE_FIELDS = ["pool_address", "chain_id", "created_at", "creation_block", "last_available_block", "last_updated"]

# In-memory cache for this session
_memory_cache: Dict[str, Dict] = {}


def _load_cache() -> Dict[str, Dict]:
    """Load cache from CSV file into memory."""
    cache = {}
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    # Key is pool_address:chain_id (lowercase)
                    key = f"{row['pool_address'].lower()}:{row['chain_id']}"
                    cache[key] = {
                        'created_at': int(row['created_at']),
                        'creation_block': int(row['creation_block']),
                        'last_available_block': int(row.get('last_available_block', 0)) if row.get('last_available_block') else None,
                        'last_updated': row['last_updated']
                    }
        except Exception as e:
            print(f"Warning: Could not load cache file: {e}")
    return cache


def _save_cache_entry(pool_address: str, chain_id: int, created_at: int, creation_block: int, last_available_block: int = None):
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
    key = f"{pool_address.lower()}:{chain_id}"
    entry_found = False
    
    for row in existing_data:
        if f"{row['pool_address'].lower()}:{row['chain_id']}" == key:
            # Update existing entry
            row['created_at'] = str(created_at)
            row['creation_block'] = str(creation_block)
            if last_available_block is not None:
                row['last_available_block'] = str(last_available_block)
            row['last_updated'] = datetime.now().isoformat()
            entry_found = True
            break
    
    if not entry_found:
        # Add new entry
        new_entry = {
            'pool_address': pool_address.lower(),
            'chain_id': str(chain_id),
            'created_at': str(created_at),
            'creation_block': str(creation_block),
            'last_updated': datetime.now().isoformat()
        }
        if last_available_block is not None:
            new_entry['last_available_block'] = str(last_available_block)
        existing_data.append(new_entry)
    
    # Write back to file
    with open(CACHE_FILE, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CACHE_FIELDS)
        writer.writeheader()
        writer.writerows(existing_data)
    
    # Update memory cache
    cache_entry = {
        'created_at': created_at,
        'creation_block': creation_block,
        'last_updated': datetime.now().isoformat()
    }
    if last_available_block is not None:
        cache_entry['last_available_block'] = last_available_block
    _memory_cache[key] = cache_entry


def get_pool_creation_block(pool_address: str, 
                           chain_id: int = 1,
                           use_cache: bool = True) -> Tuple[int, int, Optional[int]]:
    """
    Get pool creation timestamp and block number with caching.
    
    Args:
        pool_address: Pool address
        chain_id: Chain ID (default: 1 for mainnet)
        use_cache: Whether to use cache (default: True)
    
    Returns:
        Tuple of (created_at_timestamp, creation_block_number, last_available_block)
        Note: third value is last_available_block from cache (may be None)
    """
    global _memory_cache
    
    # Initialize memory cache if needed
    if not _memory_cache and use_cache:
        _memory_cache = _load_cache()
    
    # Check cache first
    cache_key = f"{pool_address.lower()}:{chain_id}"
    
    if use_cache and cache_key in _memory_cache:
        cached = _memory_cache[cache_key]
        print(f"Using cached creation block for {pool_address[:10]}...")
        # Note: We're returning last_available_block as third value for backward compatibility
        # TODO: This should be refactored to return a proper structure
        last_available = cached.get('last_available_block')
        return cached['created_at'], cached['creation_block'], last_available
    
    # Not in cache, fetch from GraphQL and estimate block
    print(f"Fetching creation block for {pool_address[:10]}... (not in cache)")
    
    try:
        # Get creation timestamp from GraphQL
        created_at = _original_fetch_pool_created_at(DEFAULT_GRAPHQL, chain_id, pool_address)
        
        # Estimate block number from timestamp (much faster than binary search)
        # Using ~12 second block time on Ethereum
        import os
        etherscan_api_key = os.getenv('ETHERSCAN_API_KEY')
        
        if etherscan_api_key:
            # Try Etherscan API for accurate block
            try:
                import requests
                url = "https://api.etherscan.io/api"
                params = {
                    'module': 'block',
                    'action': 'getblocknobytime',
                    'timestamp': created_at,
                    'closest': 'after',
                    'apikey': etherscan_api_key
                }
                r = requests.get(url, params=params, timeout=10)
                data = r.json()
                if data.get('status') == '1' and data.get('result'):
                    creation_block = int(data['result'])
                else:
                    raise Exception("Etherscan API failed")
            except:
                # Fallback to estimation
                reference_block = 23179760
                reference_timestamp = 1755715200  # 2025-08-20 12:00:00 UTC
                blocks_diff = (created_at - reference_timestamp) // 12
                creation_block = reference_block + blocks_diff
        else:
            # Direct estimation without Etherscan
            reference_block = 23179760
            reference_timestamp = 1755715200  # 2025-08-20 12:00:00 UTC
            blocks_diff = (created_at - reference_timestamp) // 12
            creation_block = reference_block + blocks_diff
        
        # Save to cache
        if use_cache:
            _save_cache_entry(pool_address, chain_id, created_at, creation_block)
            print(f"Cached creation data for {pool_address[:10]}...")
        
        return created_at, creation_block, None
        
    except Exception as e:
        print(f"Error fetching creation data for {pool_address}: {e}")
        raise


def get_pool_deployment_info(pool_address: str, chain_id: int = 1) -> Dict:
    """
    Get complete pool deployment information from GraphQL.
    
    Returns:
        Dict with pool, createdAt, eulerAccount, asset0, asset1
    """
    import requests
    
    query = f"""
    query {{
      eulerSwapFactoryPoolDeployed(chainId: {chain_id}, pool: "{pool_address.lower()}") {{
        pool
        createdAt
        eulerAccount
        asset0
        asset1
      }}
    }}
    """
    
    try:
        r = requests.post(DEFAULT_GRAPHQL, json={"query": query}, timeout=30)
        r.raise_for_status()
        data = r.json()
        
        deployment = data.get("data", {}).get("eulerSwapFactoryPoolDeployed")
        if deployment:
            return {
                'pool': deployment.get('pool', ''),
                'created_at': int(deployment.get('createdAt', 0)),
                'euler_account': deployment.get('eulerAccount', ''),
                'asset0': deployment.get('asset0', ''),
                'asset1': deployment.get('asset1', '')
            }
    except Exception as e:
        print(f"Error fetching deployment info: {e}")
    
    return {}


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
            'oldest_entry': min((e['last_updated'] for e in entries), default=None),
            'newest_entry': max((e['last_updated'] for e in entries), default=None)
        }
    except:
        return {'exists': True, 'entries': 0, 'error': 'Could not read cache file'}


# Convenience wrapper that matches the original function signatures
def fetch_pool_created_at(graphql: str, chain: int, pool: str) -> int:
    """
    Cached version of fetch_pool_created_at.
    Ignores graphql parameter and uses DEFAULT_GRAPHQL.
    """
    created_at, _, _ = get_pool_creation_block(pool, chain)
    return created_at


def block_at_or_after_timestamp(rpc_url: str, ts: int) -> int:
    """
    Pass-through to original function (timestamps to blocks don't need caching).
    """
    return _original_block_at_or_after_timestamp(rpc_url, ts)


def get_last_available_block(pool_address: str, chain_id: int = 1) -> Optional[int]:
    """
    Get cached last available block for a pool.
    
    Args:
        pool_address: Pool address
        chain_id: Chain ID (default: 1 for mainnet)
    
    Returns:
        Last available block number or None if not cached
    """
    global _memory_cache
    
    # Initialize memory cache if needed
    if not _memory_cache:
        _memory_cache = _load_cache()
    
    cache_key = f"{pool_address.lower()}:{chain_id}"
    
    if cache_key in _memory_cache:
        return _memory_cache[cache_key].get('last_available_block')
    
    return None


def set_last_available_block(pool_address: str, chain_id: int, last_block: int):
    """
    Update the last available block for a pool in cache.
    
    Args:
        pool_address: Pool address
        chain_id: Chain ID
        last_block: Last available block number
    """
    global _memory_cache
    
    # Initialize memory cache if needed
    if not _memory_cache:
        _memory_cache = _load_cache()
    
    cache_key = f"{pool_address.lower()}:{chain_id}"
    
    # Get existing entry or create minimal one
    if cache_key in _memory_cache:
        created_at = _memory_cache[cache_key].get('created_at', 0)
        creation_block = _memory_cache[cache_key].get('creation_block', 0)
    else:
        # If pool not in cache, we can't update just last_available_block
        # Need creation data first
        return
    
    # Save to cache with updated last_available_block
    _save_cache_entry(pool_address, chain_id, created_at, creation_block, last_block)


if __name__ == "__main__":
    # Test the cache
    import sys
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "stats":
            print("Cache statistics:")
            stats = get_cache_stats()
            for key, value in stats.items():
                print(f"  {key}: {value}")
        elif sys.argv[1] == "clear":
            clear_cache()
            print("Cache cleared")
        elif sys.argv[1] == "test":
            # Test with a known pool
            pool = "0x0811dB938FfB1EE151db9E8186b390fe2a5FA8A8"
            print(f"Testing with pool: {pool}")
            
            # First call (will fetch from API)
            print("\nFirst call (should fetch from API):")
            ts1, block1, last1 = get_pool_creation_block(pool)
            print(f"  Timestamp: {ts1}, Block: {block1}, Last Available: {last1}")
            
            # Second call (should use cache)
            print("\nSecond call (should use cache):")
            ts2, block2, last2 = get_pool_creation_block(pool)
            print(f"  Timestamp: {ts2}, Block: {block2}, Last Available: {last2}")
            
            assert ts1 == ts2 and block1 == block2, "Cache inconsistency!"
            print("\nCache test passed!")
    else:
        print("Usage:")
        print("  python pool_cache.py stats   - Show cache statistics")
        print("  python pool_cache.py clear   - Clear the cache")
        print("  python pool_cache.py test    - Test cache functionality")