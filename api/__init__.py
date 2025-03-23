"""
API package for Elysium Trading Platform.

This package contains modules for connecting to exchange APIs:
- api_connector: Handles connections to trading APIs and exchanges
- constants: API URLs and constants
"""

from api.api_connector import ApiConnector
from api.constants import MAINNET_API_URL, TESTNET_API_URL

__all__ = [
    'ApiConnector',
    'MAINNET_API_URL',
    'TESTNET_API_URL',
]