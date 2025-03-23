import os
import sys
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """
    Set up logging configuration
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file
        
    Returns:
        Logger instance
    """
    # Convert string log level to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Configure the root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    # Add file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(log_format))
        logging.getLogger().addHandler(file_handler)
    
    return logging.getLogger("elysium")

def format_number(number: float, decimal_places: int = 2) -> str:
    """
    Format a number with the specified decimal places
    
    Args:
        number: Number to format
        decimal_places: Number of decimal places
        
    Returns:
        Formatted number string
    """
    return f"{number:.{decimal_places}f}"

def format_price(price: float) -> str:
    """
    Format a price with appropriate decimal places
    
    Args:
        price: Price to format
        
    Returns:
        Formatted price string
    """
    if price < 0.001:
        return f"{price:.8f}"
    elif price < 1:
        return f"{price:.6f}"
    elif price < 10:
        return f"{price:.4f}"
    else:
        return f"{price:.2f}"

def format_size(size: float) -> str:
    """
    Format a size with appropriate decimal places
    
    Args:
        size: Size to format
        
    Returns:
        Formatted size string
    """
    if size < 0.001:
        return f"{size:.8f}"
    elif size < 1:
        return f"{size:.4f}"
    else:
        return f"{size:.2f}"

def format_timestamp(timestamp: int) -> str:
    """
    Format a timestamp to date time string
    
    Args:
        timestamp: Timestamp in milliseconds
        
    Returns:
        Formatted date time string
    """
    return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")

def print_table(headers: List[str], rows: List[List[Any]], title: Optional[str] = None) -> None:
    """
    Print a formatted table to the console
    
    Args:
        headers: List of column headers
        rows: List of rows, each containing data for each column
        title: Optional title for the table
    """
    # Calculate column widths
    col_widths = [len(str(h)) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    
    # Print title if provided
    if title:
        print(f"\n{title}")
        print("=" * len(title))
    
    # Print headers
    header_str = " | ".join(str(h).ljust(col_widths[i]) for i, h in enumerate(headers))
    print(header_str)
    print("-" * len(header_str))
    
    # Print rows
    for row in rows:
        row_str = " | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row))
        print(row_str)

def load_json_file(file_path: str, default: Any = None) -> Any:
    """
    Load JSON from a file
    
    Args:
        file_path: Path to the JSON file
        default: Value to return if file doesn't exist or loading fails
        
    Returns:
        Loaded JSON data or default value
    """
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                return json.load(f)
        return default
    except Exception as e:
        logging.error(f"Error loading JSON file {file_path}: {str(e)}")
        return default

def save_json_file(file_path: str, data: Any) -> bool:
    """
    Save data to a JSON file
    
    Args:
        file_path: Path to save the file
        data: Data to save
        
    Returns:
        True if successful, False otherwise
    """
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        logging.error(f"Error saving to JSON file {file_path}: {str(e)}")
        return False

def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert a value to float
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value or default
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def calculate_pnl_metrics(fills: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Calculate PnL metrics from trading history
    
    Args:
        fills: List of trade fills
        
    Returns:
        Dictionary with PnL metrics
    """
    if not fills:
        return {
            "total_trades": 0,
            "total_volume": 0,
            "total_pnl": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate": 0,
            "avg_win": 0,
            "avg_loss": 0
        }
    
    total_trades = len(fills)
    total_volume = sum(safe_float(fill.get("sz", 0)) * safe_float(fill.get("px", 0)) for fill in fills)
    total_pnl = sum(safe_float(fill.get("closedPnl", 0)) for fill in fills)
    
    # Separate wins and losses
    wins = [safe_float(fill.get("closedPnl", 0)) for fill in fills if safe_float(fill.get("closedPnl", 0)) > 0]
    losses = [safe_float(fill.get("closedPnl", 0)) for fill in fills if safe_float(fill.get("closedPnl", 0)) < 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    win_rate = (win_count / total_trades) * 100 if total_trades > 0 else 0
    
    avg_win = sum(wins) / win_count if win_count > 0 else 0
    avg_loss = sum(losses) / loss_count if loss_count > 0 else 0
    
    return {
        "total_trades": total_trades,
        "total_volume": total_volume,
        "total_pnl": total_pnl,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss
    }

class Colors:
    """ANSI color codes for terminal output"""
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

class StatusIcons:
    """Status icons for terminal output"""
    SUCCESS = f"{Colors.GREEN}✓{Colors.END}"
    ERROR = f"{Colors.RED}✗{Colors.END}"
    WARNING = f"{Colors.YELLOW}⚠{Colors.END}"
    INFO = f"{Colors.BLUE}ℹ{Colors.END}"
    RUNNING = f"{Colors.GREEN}●{Colors.END}"
    STOPPED = f"{Colors.RED}●{Colors.END}"
    LOADING = f"{Colors.YELLOW}◌{Colors.END}"
    ARROW = f"{Colors.CYAN}➜{Colors.END}"