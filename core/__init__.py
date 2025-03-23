"""
Core package for Elysium Trading Platform.

This package contains core functionality:
- config_manager: Manages configuration settings
- utils: Utility functions
"""

from core.config_manager import ConfigManager
from core.utils import (
    setup_logging, format_number, format_price, 
    format_size, format_timestamp, print_table
)

__all__ = [
    'ConfigManager',
    'setup_logging',
    'format_number',
    'format_price',
    'format_size',
    'format_timestamp',
    'print_table',
]