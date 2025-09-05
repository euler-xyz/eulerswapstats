#!/usr/bin/env python3
"""
Minimal test script for Etherscan API - getblocknobytime endpoint
Tests getting block numbers from timestamps
"""

import requests
import json
from datetime import datetime, timedelta

def get_block_by_timestamp(timestamp, closest="before"):
    """
    Get block number by Unix timestamp using Etherscan API
    
    Args:
        timestamp: Unix timestamp (seconds since epoch)
        closest: "before" or "after" - whether to get block before or after timestamp
    """
    url = "https://api.etherscan.io/api"
    params = {
        "module": "block",
        "action": "getblocknobytime",
        "timestamp": timestamp,
        "closest": closest,
        "apikey": "K1HVQX1QC8WU2W8RZUC6PXQJH9I3IDGFUQ"
    }
    
    print(f"\n📡 Fetching block for timestamp {timestamp}")
    print(f"   Date: {datetime.fromtimestamp(timestamp).isoformat()}")
    print(f"   Closest: {closest}")
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if data["status"] == "1":
            block_number = data["result"]
            print(f"   ✅ Block found: #{block_number}")
            return int(block_number)
        else:
            print(f"   ❌ Error: {data.get('message', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"   ❌ Request failed: {e}")
        return None

def main():
    print("=" * 60)
    print("ETHERSCAN API TEST - Get Block Number by Timestamp")
    print("=" * 60)
    
    # Test cases
    test_cases = [
        {
            "name": "Recent block (1 hour ago)",
            "timestamp": int((datetime.now() - timedelta(hours=1)).timestamp())
        },
        {
            "name": "Yesterday",
            "timestamp": int((datetime.now() - timedelta(days=1)).timestamp())
        },
        {
            "name": "One week ago",
            "timestamp": int((datetime.now() - timedelta(weeks=1)).timestamp())
        },
        {
            "name": "Specific date (Aug 11, 2025 19:30:23 UTC)",
            "timestamp": 1723403423  # Unix timestamp for 2025-08-11T19:30:23Z
        },
        {
            "name": "Ethereum genesis block",
            "timestamp": 1438269973  # July 30, 2015
        }
    ]
    
    # Test each case
    for test in test_cases:
        print(f"\n🧪 Test: {test['name']}")
        print("-" * 40)
        
        # Get block BEFORE timestamp
        before_block = get_block_by_timestamp(test["timestamp"], "before")
        
        # Get block AFTER timestamp
        after_block = get_block_by_timestamp(test["timestamp"], "after")
        
        if before_block and after_block:
            diff = after_block - before_block
            print(f"\n   📊 Block difference: {diff} blocks")
            print(f"   ⏱️  Time span: ~{diff * 12} seconds (~{diff * 12 / 60:.1f} minutes)")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)
    
    # Additional test: Verify accuracy
    print("\n🔍 Accuracy Test: Comparing manual calculation vs Etherscan")
    print("-" * 60)
    
    # Use a known reference point
    reference_block = 20500000
    reference_time = 1723500000  # Approximate timestamp for block 20500000
    
    # Test timestamp (1 day after reference)
    test_time = reference_time + 86400  # +1 day
    
    # Manual calculation (12 second blocks)
    manual_estimate = reference_block + (86400 // 12)
    print(f"Manual estimate: Block #{manual_estimate}")
    
    # Etherscan API
    api_result = get_block_by_timestamp(test_time, "before")
    if api_result:
        print(f"Etherscan API:   Block #{api_result}")
        print(f"Difference:      {abs(api_result - manual_estimate)} blocks")

if __name__ == "__main__":
    main()