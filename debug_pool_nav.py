#!/usr/bin/env python3
"""Debug NAV calculations for a specific pool"""
from netnav import (
    get_pool_nav, 
    get_pool_lifespan_return,
    DEFAULT_RPC_URL,
    DEFAULT_GRAPHQL
)
# Use cached version for pool creation lookups
from pool_cache import get_pool_creation_block
import json

pool_address = "0x0811dB938FfB1EE151db9E8186b390fe2a5FA8A8"
chain_id = 1

print(f"Analyzing pool: {pool_address}")
print("=" * 60)

# Get lifespan return data
print("\n1. Getting lifespan return data...")
lifespan_data = get_pool_lifespan_return(pool_address, chain_id)

print("\nLifespan Return Data:")
for key, value in lifespan_data.items():
    if key != 'error':
        print(f"  {key}: {value}")

# Get creation timestamp and block (using cache)
print("\n2. Getting creation details...")
created_at, created_block = get_pool_creation_block(pool_address, chain_id)

print(f"  Created at timestamp: {created_at}")
print(f"  Created at block: {created_block}")

# Get NAV at creation
print("\n3. Getting NAV at creation block {created_block}...")
creation_nav = get_pool_nav(pool_address, chain_id, created_block)
print(f"  Creation NAV: ${creation_nav:,.2f}")

# Get current NAV
print("\n4. Getting current NAV...")
current_nav = get_pool_nav(pool_address, chain_id)
print(f"  Current NAV: ${current_nav:,.2f}")

# Calculate return manually
print("\n5. Manual calculation:")
if creation_nav > 0 and lifespan_data['days'] > 0:
    total_return = (current_nav - creation_nav) / creation_nav
    print(f"  Total return: {total_return * 100:.2f}%")
    
    # Annualized return calculation
    days = lifespan_data['days']
    
    # Method 1: Simple annualization (what the code might be doing)
    annual_simple = (1 + total_return) ** (365/days) - 1
    print(f"  Annualized (compound): {annual_simple * 100:.2f}%")
    
    # Method 2: If negative, this might be happening
    if total_return < 0:
        # Some implementations handle negative returns differently
        annual_negative = total_return * (365/days)
        print(f"  Annualized (linear for negative): {annual_negative * 100:.2f}%")
    
    print(f"\n  Days elapsed: {days:.2f}")
    print(f"  Years elapsed: {days/365:.4f}")
    
print("\n6. Checking the calculation in get_pool_lifespan_return:")
print(f"  Function returned annualized_return: {lifespan_data['annualized_return']:.2f}%")

# Let's also check what the function actually does
print("\n7. Step-by-step from the function values:")
start_nav = lifespan_data['start_nav']
end_nav = lifespan_data['end_nav']
days = lifespan_data['days']

print(f"  start_nav: ${start_nav:,.2f}")
print(f"  end_nav: ${end_nav:,.2f}")
print(f"  days: {days:.2f}")

if days > 0 and start_nav > 0:
    # This is what the function does (from netnav.py line 494):
    # annual_return = ((end_nav / start_nav) ** (365/days) - 1) * 100
    calc_return = ((end_nav / start_nav) ** (365/days) - 1) * 100
    print(f"  Calculated: ((${end_nav:.2f} / ${start_nav:.2f}) ** (365/{days:.2f}) - 1) * 100")
    print(f"  = (({end_nav/start_nav:.6f}) ** {365/days:.6f} - 1) * 100")
    print(f"  = ({(end_nav/start_nav) ** (365/days):.6f} - 1) * 100")
    print(f"  = {calc_return:.2f}%")