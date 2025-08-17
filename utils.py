#!/usr/bin/env python3
"""
Shared utilities for EulerSwap stats tools
"""
from decimal import Decimal
from typing import Union, Optional

# Known token addresses -> symbols mapping
TOKEN_SYMBOLS = {
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0xdac17f958d2ee523a2206206994597c13d831ec7": "USDT",
    "0x6b175474e89094c44da98b954eedeac495271d0f": "DAI",
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": "WETH",
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": "WBTC",
    "0x66a1e37c9b0eaddca17d3662d6c05f4decf3e110": "USR",
    "0x4c9edd5852cd905f086c759e8383e09bff1e68b3": "USDe",
    "0x514910771af9ca656af840dff83e8264ecf986ca": "LINK",
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": "AAVE",
    "0xc18360217d8f7ab5e7c516566761ea12ce7f9d72": "ENS",
    "0x4d224452801aced8b2f0aebe155379bb5d594381": "APE",
    "0xc13919770b88e0ddebda0a0a9eedabeceefe4b8b": "RLUSD",
    "0x7f39c581f595b53c5cb19bd0b3f8da6c935e2ca0": "wstETH",
}

# Token decimals for known tokens
TOKEN_DECIMALS = {
    "USDC": 6,
    "USDT": 6,
    "DAI": 18,
    "WETH": 18,
    "WBTC": 8,
    "USR": 18,
    "USDe": 18,
    "LINK": 18,
    "AAVE": 18,
    "ENS": 18,
    "APE": 18,
    "RLUSD": 18,
    "wstETH": 18,
}


def get_token_symbol(address: str) -> str:
    """
    Get token symbol from address.
    Returns shortened address if token not found.
    """
    return TOKEN_SYMBOLS.get(address.lower(), address[:6].upper())


def get_token_decimals(symbol: str) -> int:
    """
    Get token decimals from symbol.
    Returns 18 as default if unknown.
    """
    return TOKEN_DECIMALS.get(symbol, 18)


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


def format_reserves(reserves: Union[str, int, float], token_symbol: str) -> float:
    """
    Format reserve value based on token decimals.
    
    Args:
        reserves: Raw reserves value
        token_symbol: Token symbol to determine decimals
    
    Returns:
        Formatted reserves
    """
    try:
        reserves_float = float(reserves)
        decimals = get_token_decimals(token_symbol)
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