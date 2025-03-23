import cmd
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

from core.utils import Colors, StatusIcons

class ElysiumTerminalUI(cmd.Cmd):
    """
    Command-line interface for Elysium Trading Platform
    
    This class handles user interaction through a command-line interface
    and delegates all execution logic to the order_handler and other modules.
    """
    
    VERSION = "1.0.0"
    intro = None

    ASCII_ART = '''
    ███████╗██╗  ██╗   ██╗███████╗██╗██╗   ██╗███╗   ███╗
    ██╔════╝██║  ╚██╗ ██╔╝██╔════╝██║██║   ██║████╗ ████║
    █████╗  ██║   ╚████╔╝ ███████╗██║██║   ██║██╔████╔██║
    ██╔══╝  ██║    ╚██╔╝  ╚════██║██║██║   ██║██║╚██╔╝██║
    ███████╗███████╗██║   ███████║██║╚██████╔╝██║ ╚═╝ ██║
    ╚══════╝╚══════╝╚═╝   ╚══════╝╚═╝ ╚═════╝ ╚═╝     ╚═╝
    ===========================================================
    '''

    WELCOME_MSG = '''
    Welcome to Elysium Trading Bot - Type 'help' to see available commands

    BASIC COMMANDS:                ORDER EXECUTION:
    - connect [mainnet|testnet]    - buy, sell, limit_buy, limit_sell
    - balance                      - perp_buy, perp_sell
    - positions                    - scaled_buy, scaled_sell
    - orders                       - twap_create, twap_start
                                   - grid_create, grid_start
    
    STRATEGY COMMANDS:             ACCOUNT MANAGEMENT:
    - select_strategy              - help <command>
    - strategy_status              - status
    - stop_strategy                - exit
    '''

    def __init__(self, api_connector, order_handler, config_manager):
        super().__init__()
        self.prompt = 'elysium> '
        self.api_connector = api_connector
        self.order_handler = order_handler
        self.config_manager = config_manager
        self.authenticated = False
        self.logger = logging.getLogger(__name__)
        
        # Initialize strategy selector if needed
        from strategies.strategy_selector import StrategySelector
        self.strategy_selector = StrategySelector(api_connector, order_handler, config_manager)
        
    def preloop(self):
        """Setup before starting the command loop"""
        self.display_layout()
        
        # Authenticate user before proceeding
        auth_success = self.authenticate_user()
        if not auth_success:
            print("\nAuthentication failed. Exiting...")
            import sys
            sys.exit(1)
        
        self.authenticated = True
        print("\nAuthentication successful!")
        print("Initializing Elysium CLI...")
        time.sleep(1)
        print(f"{StatusIcons.SUCCESS} Ready to trade!\n")
        
    def authenticate_user(self) -> bool:
        """Authenticate user with password"""
        # Password is already stored in config
        if self.config_manager.get('password_hash'):
            for attempt in range(3):  # Allow 3 attempts
                password = input("Enter your password: ")
                if self.config_manager.verify_password(password):
                    return True
                else:
                    print(f"Incorrect password. {2-attempt} attempts remaining.")
            return False
        else:
            # First-time setup
            print("First-time setup. Please create a password:")
            password = input("Enter new password: ")
            confirm = input("Confirm password: ")
            
            if password == confirm:
                self.config_manager.set_password(password)
                return True
            else:
                print("Passwords don't match.")
                return False
    
    def display_layout(self):
        """Display the interface layout"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print(self.ASCII_ART)
        print(self.WELCOME_MSG)
    
    def _check_connection(self) -> bool:
        """Check if connected to exchange"""
        if not self.api_connector.exchange:
            print(f"{StatusIcons.ERROR} Not connected to exchange. Use 'connect' first.")
            return False
        return True
    
    def _process_order_result(self, result: Dict[str, Any]) -> None:
        """Process and display the result of an order execution"""
        if result["status"] == "ok":
            print(f"{StatusIcons.SUCCESS} Order executed successfully")
            # Display order details if available
            if "response" in result and "data" in result["response"] and "statuses" in result["response"]["data"]:
                for status in result["response"]["data"]["statuses"]:
                    if "filled" in status:
                        filled = status["filled"]
                        print(f"Filled: {filled['totalSz']} @ {filled['avgPx']}")
                    elif "resting" in status:
                        resting = status["resting"]
                        print(f"Order ID: {resting['oid']}")
                    elif "error" in status:
                        print(f"Error: {status['error']}")
        else:
            print(f"{StatusIcons.ERROR} Order failed: {result.get('message', 'Unknown error')}")
    
    def _parse_bool(self, value: str) -> bool:
        """Parse a string to boolean value"""
        return value.lower() in ['true', 't', 'yes', 'y', '1']
    
    # ============================= Connection Commands =============================
    
    def do_connect(self, arg):
        """
        Connect to Hyperliquid exchange
        Usage: connect [mainnet|testnet]
        """
        try:
            # Parse network type from arguments
            use_testnet = "testnet" in arg.lower()
            network_name = "testnet" if use_testnet else "mainnet"
            
            # Import credentials from dontshareconfig.py
            import dontshareconfig as ds
            
            # Select the appropriate credentials based on network
            wallet_address = ds.testnet_wallet if use_testnet else ds.mainnet_wallet
            secret_key = ds.testnet_secret if use_testnet else ds.mainnet_secret
            
            print(f"\n{StatusIcons.LOADING} Connecting to Hyperliquid ({network_name})...")
            success = self.api_connector.connect_hyperliquid(wallet_address, secret_key, use_testnet)
            
            if success:
                print(f"{StatusIcons.SUCCESS} Successfully connected to {wallet_address}")
                # Initialize order handler with the connected exchange and info objects
                self.order_handler.set_exchange(
                    self.api_connector.exchange, 
                    self.api_connector.info,
                    self.api_connector
                )
                self.order_handler.wallet_address = wallet_address
            else:
                print(f"{StatusIcons.ERROR} Failed to connect to exchange")
                    
        except Exception as e:
            print(f"{StatusIcons.ERROR} Error connecting to exchange: {str(e)}")
    
    # ============================= Simple Order Commands =============================
    
    def do_buy(self, arg):
        """
        Execute a market buy order
        Usage: buy <symbol> <size> [slippage]
        """
        if not self._check_connection():
            return
            
        args = arg.split()
        if len(args) < 2:
            print("Invalid arguments. Usage: buy <symbol> <size> [slippage]")
            return
            
        symbol = args[0]
        size = float(args[1])
        slippage = float(args[2]) if len(args) > 2 else 0.05
        
        print(f"\n{StatusIcons.LOADING} Executing market buy: {size} {symbol}")
        result = self.order_handler.market_buy(symbol, size, slippage)
        self._process_order_result(result)
    
    def do_sell(self, arg):
        """
        Execute a market sell order
        Usage: sell <symbol> <size> [slippage]
        """
        if not self._check_connection():
            return
            
        args = arg.split()
        if len(args) < 2:
            print("Invalid arguments. Usage: sell <symbol> <size> [slippage]")
            return
            
        symbol = args[0]
        size = float(args[1])
        slippage = float(args[2]) if len(args) > 2 else 0.05
        
        print(f"\n{StatusIcons.LOADING} Executing market sell: {size} {symbol}")
        result = self.order_handler.market_sell(symbol, size, slippage)
        self._process_order_result(result)
    
    def do_limit_buy(self, arg):
        """
        Place a limit buy order
        Usage: limit_buy <symbol> <size> <price>
        """
        if not self._check_connection():
            return
            
        args = arg.split()
        if len(args) < 3:
            print("Invalid arguments. Usage: limit_buy <symbol> <size> <price>")
            return
            
        symbol = args[0]
        size = float(args[1])
        price = float(args[2])
        
        print(f"\n{StatusIcons.LOADING} Placing limit buy: {size} {symbol} @ {price}")
        result = self.order_handler.limit_buy(symbol, size, price)
        self._process_order_result(result)
    
    def do_limit_sell(self, arg):
        """
        Place a limit sell order
        Usage: limit_sell <symbol> <size> <price>
        """
        if not self._check_connection():
            return
            
        args = arg.split()
        if len(args) < 3:
            print("Invalid arguments. Usage: limit_sell <symbol> <size> <price>")
            return
            
        symbol = args[0]
        size = float(args[1])
        price = float(args[2])
        
        print(f"\n{StatusIcons.LOADING} Placing limit sell: {size} {symbol} @ {price}")
        result = self.order_handler.limit_sell(symbol, size, price)
        self._process_order_result(result)
    
    # ============================= Information Commands =============================
    
    def do_balance(self, arg):
        """Show account balance"""
        if not self._check_connection():
            return
            
        print(f"\n{StatusIcons.LOADING} Fetching balance information...")
        balances = self.api_connector.get_balances()
        
        # Display spot balances
        print("\n=== Account Balances ===")
        if balances.get("spot"):
            print("\nSpot Balances:")
            for balance in balances["spot"]:
                if float(balance.get("total", 0)) > 0:
                    print(f"• {balance['asset']}: {balance['available']} available, {balance['total']} total")
        
        # Display perpetual balances
        if balances.get("perp"):
            print("\nPerpetual Account:")
            print(f"• Account Value: ${balances['perp']['account_value']}")
            print(f"• Margin Used: ${balances['perp']['margin_used']}")
            print(f"• Position Value: ${balances['perp']['position_value']}")
    
    def do_positions(self, arg):
        """Show open positions"""
        if not self._check_connection():
            return
            
        print(f"\n{StatusIcons.LOADING} Fetching position information...")
        positions = self.api_connector.get_positions()
        
        if not positions:
            print("No open positions")
            return
        
        print("\n=== Open Positions ===")
        for pos in positions:
            symbol = pos.get("symbol", "")
            size = pos.get("size", 0)
            side = "Long" if size > 0 else "Short"
            print(f"\n{symbol} ({side}):")
            print(f"• Size: {abs(size)}")
            print(f"• Entry Price: {pos.get('entry_price', 0)}")
            print(f"• Mark Price: {pos.get('mark_price', 0)}")
            print(f"• Unrealized PnL: {pos.get('unrealized_pnl', 0)}")
    
    def do_orders(self, arg):
        """Show open orders"""
        if not self._check_connection():
            return
            
        print(f"\n{StatusIcons.LOADING} Fetching open orders...")
        orders_result = self.order_handler.get_open_orders()
        
        if isinstance(orders_result, dict) and "data" in orders_result:
            orders = orders_result["data"]
        else:
            orders = orders_result
            
        if not orders:
            print("No open orders")
            return
        
        print("\n=== Open Orders ===")
        for order in orders:
            print(f"\n{order.get('coin', '')}")
            print(f"• Side: {'Buy' if order.get('side', '') == 'B' else 'Sell'}")
            print(f"• Size: {float(order.get('sz', 0))}")
            print(f"• Price: {float(order.get('limitPx', 0))}")
            print(f"• Order ID: {order.get('oid', 0)}")
    
    # ============================= Strategy Commands =============================
    
    def do_select_strategy(self, arg):
        """
        Select and configure a trading strategy
        Usage: select_strategy [strategy_name]
        """
        if not self._check_connection():
            return
            
        # Delegate to strategy selector
        strategies = self.strategy_selector.list_strategies()
        
        # If no strategy specified, list available strategies
        if not arg:
            print("\n=== Available Trading Strategies ===")
            for strategy in strategies:
                print(f"\n{strategy['name']} ({strategy['module']})")
                print(f"  {strategy['description']}")
            return
        
        # Try to load the specified strategy
        strategy_name = arg.strip()
        if not any(s['module'] == strategy_name for s in strategies):
            print(f"{StatusIcons.ERROR} Strategy '{strategy_name}' not found")
            return
            
        # Get strategy parameters for customization
        params = self.strategy_selector.get_strategy_params(strategy_name)
        custom_params = {}
        
        print(f"\n=== Configuring {strategy_name} ===")
        for name, param in params.items():
            if isinstance(param, dict) and "value" in param:
                default = param["value"]
                desc = param.get("description", "")
                prompt = f"{name} ({desc}) [{default}]: "
                user_input = input(prompt)
                
                if user_input.strip():
                    if isinstance(default, bool):
                        custom_params[name] = {"value": self._parse_bool(user_input)}
                    elif isinstance(default, int):
                        custom_params[name] = {"value": int(user_input)}
                    elif isinstance(default, float):
                        custom_params[name] = {"value": float(user_input)}
                    else:
                        custom_params[name] = {"value": user_input}
                else:
                    custom_params[name] = {"value": default}
        
        # Start the strategy
        print(f"\n{StatusIcons.LOADING} Starting {strategy_name}...")
        success = self.strategy_selector.start_strategy(strategy_name, custom_params)
        
        if success:
            print(f"{StatusIcons.SUCCESS} Strategy started successfully")
        else:
            print(f"{StatusIcons.ERROR} Failed to start strategy")
    
    def do_strategy_status(self, arg):
        """Show the status of the current strategy"""
        active_strategy = self.strategy_selector.get_active_strategy()
        
        if not active_strategy:
            print("No active trading strategy")
            return
            
        print(f"\n=== Active Strategy: {active_strategy['name']} ===")
        print(f"Module: {active_strategy['module']}")
        print(f"Status: {'Running' if active_strategy['running'] else 'Stopped'}")
        
        # Get and display parameters
        if active_strategy.get('params'):
            print("\nParameters:")
            for key, value in active_strategy['params'].items():
                if isinstance(value, dict) and "value" in value:
                    print(f"• {key}: {value['value']}")
                else:
                    print(f"• {key}: {value}")
    
    def do_stop_strategy(self, arg):
        """Stop the current strategy"""
        success = self.strategy_selector.stop_strategy()
        
        if success:
            print(f"{StatusIcons.SUCCESS} Strategy stopped successfully")
        else:
            print(f"{StatusIcons.ERROR} No active strategy to stop")
    
    # ============================= Utility Commands =============================
    
    def do_clear(self, arg):
        """Clear the terminal screen"""
        self.display_layout()
    
    def do_exit(self, arg):
        """Exit the Elysium CLI"""
        print("\nThank you for using Elysium Trading Bot!")
        return True
        
    def do_EOF(self, arg):
        """Exit on Ctrl+D"""
        return self.do_exit(arg)