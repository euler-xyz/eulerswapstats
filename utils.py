#!/usr/bin/env python3
"""
Shared utilities for EulerSwap stats tools
"""
from decimal import Decimal
from typing import Union, Optional

# Import dynamic token cache functions
try:
    from token_cache import (
        get_token_symbol as _get_token_symbol_cached,
        get_token_decimals as _get_token_decimals_cached
    )
    USE_TOKEN_CACHE = True
except ImportError:
    # Fallback if token_cache module not available
    USE_TOKEN_CACHE = False
    
    # Minimal fallback mapping for essential tokens only
    _FALLBACK_SYMBOLS = {
        "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
        "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
        "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    }


def get_token_symbol(address: str) -> str:
    """
    Get token symbol from address.
    Uses dynamic blockchain lookup with caching.
    Returns shortened address if token not found.
    """
    if USE_TOKEN_CACHE:
        return _get_token_symbol_cached(address)
    else:
        # Fallback to minimal mapping
        return _FALLBACK_SYMBOLS.get(address.lower(), address[:6].upper())


def get_token_decimals(address: str) -> int:
    """
    Get token decimals from address.
    Uses dynamic blockchain lookup with caching.
    Returns 18 as default if unknown.
    
    Note: This now takes an address, not a symbol.
    """
    if USE_TOKEN_CACHE:
        return _get_token_decimals_cached(address)
    else:
        # Known decimals for fallback tokens
        addr_lower = address.lower()
        if addr_lower in ["0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 
                          "0xdac17f958d2ee523a2206206994597c13d831ec7"]:
            return 6  # USDC, USDT
        return 18  # Default


def convert_apr_to_percentage(apr_value: Union[str, int, float]) -> float:
    """
    Convert APR value from API (in 1e18 format) to percentage.
    
    API returns APR values as integers scaled by 1e18.
    For example: 798049266657973740 = 79.80% APR
    
    Args:
        apr_value: Raw APR value from API (as string or number)
    
    Returns:
        APR as percentage (e.g., 79.80 for 79.80%)
    """
    try:
        if isinstance(apr_value, str):
            if apr_value == "0" or not apr_value:
                return 0.0
            apr_float = float(apr_value)
        else:
            apr_float = float(apr_value)
        
        # Divide by 1e18 to get decimal, multiply by 100 for percentage
        return (apr_float / 1e18) * 100
    except (ValueError, TypeError):
        return 0.0


def format_nav(nav_value: Union[str, int, float], scale: int = 1e8) -> float:
    """
    Format NAV value from API to USD.
    
    API returns NAV values scaled by 1e8 by default.
    
    Args:
        nav_value: Raw NAV value from API
        scale: Scale factor (default 1e8)
    
    Returns:
        NAV in USD
    """
    try:
        if isinstance(nav_value, dict):
            nav_value = nav_value.get('nav', 0)
        return float(nav_value) / scale
    except (ValueError, TypeError):
        return 0.0


def format_reserves(reserves: Union[str, int, float], token_address_or_symbol: str) -> float:
    """
    Format reserve value based on token decimals.
    
    Args:
        reserves: Raw reserves value
        token_address_or_symbol: Token address (preferred) or symbol for decimals lookup
    
    Returns:
        Formatted reserves
    """
    try:
        reserves_float = float(reserves)
        
        # Check if it's an address (starts with 0x and is 42 chars)
        if token_address_or_symbol.startswith('0x') and len(token_address_or_symbol) == 42:
            decimals = get_token_decimals(token_address_or_symbol)
        else:
            # It's a symbol - use default decimals based on common tokens
            if token_address_or_symbol in ['USDC', 'USDT']:
                decimals = 6
            elif token_address_or_symbol == 'WBTC':
                decimals = 8
            else:
                decimals = 18
        
        return reserves_float / (10 ** decimals)
    except (ValueError, TypeError):
        return 0.0


def calculate_net_interest(interest_earned: Union[str, int, float], 
                          interest_paid: Union[str, int, float],
                          scale: int = 1e8) -> float:
    """
    Calculate net interest (earned - paid).
    
    Args:
        interest_earned: Interest earned value
        interest_paid: Interest paid value
        scale: Scale factor (default 1e8)
    
    Returns:
        Net interest in USD
    """
    try:
        earned = float(interest_earned) / scale
        paid = float(interest_paid) / scale
        return earned - paid
    except (ValueError, TypeError):
        return 0.0