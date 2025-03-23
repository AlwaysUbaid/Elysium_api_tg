import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional

# Import the base strategy class
from strategies.strategy_selector import TradingStrategy

class PureMarketMaking(TradingStrategy):
    """
    Pure Market Making Strategy
    
    This strategy places buy and sell orders around the mid price,
    aiming to profit from the spread between bids and asks.
    """
    
    # Strategy metadata
    STRATEGY_NAME = "Pure Market Making"
    STRATEGY_DESCRIPTION = "Places buy and sell orders around the mid price to earn the spread"
    
    # Default parameters with descriptions
    STRATEGY_PARAMS = {
        "symbol": {
            "value": "BTC",
            "type": "str",
            "description": "Trading pair symbol"
        },
        "bid_spread": {
            "value": 0.0005,  # 0.05%
            "type": "float",
            "description": "Spread below mid price for buy orders (as a decimal)"
        },
        "ask_spread": {
            "value": 0.0005,  # 0.05%
            "type": "float",
            "description": "Spread above mid price for sell orders (as a decimal)"
        },
        "order_amount": {
            "value": 0.001,  # 0.001 BTC
            "type": "float",
            "description": "Size of each order"
        },
        "refresh_time": {
            "value": 30,  # 30 seconds
            "type": "int",
            "description": "Time in seconds between order refresh"
        },
        "is_perp": {
            "value": False,
            "type": "bool",
            "description": "Whether to trade perpetual contracts (True) or spot (False)"
        },
        "leverage": {
            "value": 1,
            "type": "int",
            "description": "Leverage to use for perpetual trading (if is_perp is True)"
        }
    }
    
    def __init__(self, api_connector, order_handler, config_manager, params=None):
        """Initialize the market making strategy with custom parameters"""
        super().__init__(api_connector, order_handler, config_manager, params)
        
        # Extract parameter values
        self.symbol = self._get_param_value("symbol")
        self.bid_spread = self._get_param_value("bid_spread")
        self.ask_spread = self._get_param_value("ask_spread")
        self.order_amount = self._get_param_value("order_amount")
        self.refresh_time = self._get_param_value("refresh_time")
        self.is_perp = self._get_param_value("is_perp")
        self.leverage = self._get_param_value("leverage")
        
        # Runtime variables
        self.last_tick_time = 0
        self.mid_price = 0
        self.active_buy_order_id = None
        self.active_sell_order_id = None
        self.status_message = "Initialized"
        self.status_lock = threading.Lock()
        
    def _get_param_value(self, param_name):
        """Helper method to extract parameter values"""
        if param_name in self.params:
            if isinstance(self.params[param_name], dict) and "value" in self.params[param_name]:
                return self.params[param_name]["value"]
            return self.params[param_name]
        
        # Fallback to default params
        if param_name in self.STRATEGY_PARAMS:
            if isinstance(self.STRATEGY_PARAMS[param_name], dict) and "value" in self.STRATEGY_PARAMS[param_name]:
                return self.STRATEGY_PARAMS[param_name]["value"]
            return self.STRATEGY_PARAMS[param_name]
        
        self.logger.warning(f"Parameter {param_name} not found, using None")
        return None
    
    def set_status(self, message):
        """Thread-safe status update"""
        with self.status_lock:
            self.status_message = message
            self.logger.info(f"Status: {message}")
    
    def get_status(self):
        """Get current strategy status"""
        with self.status_lock:
            return self.status_message
    
    def _run_strategy(self):
        """Main strategy execution loop"""
        self.set_status("Starting market making strategy")
        
        # Verify exchange connection
        if not self.api_connector.exchange or not self.order_handler.exchange:
            self.set_status("Error: Exchange connection is not active. Please connect first.")
            self.logger.error("Exchange connection not active when starting strategy")
            self.running = False
            return
        
        # Set leverage if using perpetual
        if self.is_perp and self.leverage > 1:
            try:
                self.order_handler._set_leverage(self.symbol, self.leverage)
                self.logger.info(f"Set leverage to {self.leverage}x for {self.symbol}")
            except Exception as e:
                self.logger.error(f"Failed to set leverage: {str(e)}")
        
        self.running = True
        
        # Main strategy loop
        try:
            while not self.stop_requested and self.running:
                current_time = time.time()
                
                # Check if it's time to refresh orders
                if (current_time - self.last_tick_time) >= self.refresh_time:
                    self.logger.info(f"Refreshing orders for {self.symbol}")
                    
                    # 1. Get market data
                    market_data = self.api_connector.get_market_data(self.symbol)
                    
                    if "error" in market_data:
                        self.set_status(f"Error getting market data: {market_data['error']}")
                        time.sleep(5)
                        continue
                    
                    # 2. Update mid price
                    if "mid_price" in market_data:
                        self.mid_price = market_data["mid_price"]
                    elif "best_bid" in market_data and "best_ask" in market_data:
                        self.mid_price = (market_data["best_bid"] + market_data["best_ask"]) / 2
                    else:
                        self.set_status("No price data available")
                        time.sleep(5)
                        continue
                    
                    # 3. Cancel existing orders
                    self._cancel_active_orders()
                    
                    # 4. Place new orders
                    success = self._place_orders()
                    
                    if success:
                        self.set_status(f"Placed orders around mid price {self.mid_price}")
                    else:
                        self.set_status("Failed to place orders")
                    
                    self.last_tick_time = current_time
                
                # Sleep to avoid excessive CPU usage
                time.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error in strategy loop: {str(e)}")
            self.set_status(f"Error: {str(e)}")
        
        finally:
            # Clean up when stopping
            self._cancel_active_orders()
            self.running = False
            self.set_status("Market making strategy stopped")
    
    def _cancel_active_orders(self):
        """Cancel active buy and sell orders"""
        try:
            if self.active_buy_order_id:
                self.order_handler.cancel_order(self.symbol, self.active_buy_order_id)
                self.logger.info(f"Cancelled buy order {self.active_buy_order_id}")
                self.active_buy_order_id = None
                
            if self.active_sell_order_id:
                self.order_handler.cancel_order(self.symbol, self.active_sell_order_id)
                self.logger.info(f"Cancelled sell order {self.active_sell_order_id}")
                self.active_sell_order_id = None
                
        except Exception as e:
            self.logger.error(f"Error cancelling orders: {str(e)}")
    
    def _place_orders(self):
        """Place new buy and sell orders"""
        try:
            # Get tick size for proper price formatting
            tick_size = self._get_tick_size()
            self.logger.info(f"Using tick size {tick_size} for {self.symbol}")
            
            # Calculate bid and ask prices
            bid_price = self.mid_price * (1 - self.bid_spread)
            ask_price = self.mid_price * (1 + self.ask_spread)
            
            # Format prices to comply with tick size
            bid_price = self._format_price(bid_price, tick_size)
            ask_price = self._format_price(ask_price, tick_size)
            
            self.logger.info(f"Placing orders - Buy: {self.order_amount} @ {bid_price}, Sell: {self.order_amount} @ {ask_price}")
            
            # Place buy order
            if self.is_perp:
                bid_result = self.order_handler.perp_limit_buy(self.symbol, self.order_amount, bid_price, self.leverage)
            else:
                bid_result = self.order_handler.limit_buy(self.symbol, self.order_amount, bid_price)
            
            if bid_result and bid_result["status"] == "ok":
                if "response" in bid_result and "data" in bid_result["response"] and "statuses" in bid_result["response"]["data"]:
                    for status in bid_result["response"]["data"]["statuses"]:
                        if "resting" in status:
                            self.active_buy_order_id = status["resting"]["oid"]
                            self.logger.info(f"Placed buy order: ID {self.active_buy_order_id} at {bid_price}")
            else:
                self.logger.error(f"Failed to place buy order: {bid_result}")
            
            # Place sell order
            if self.is_perp:
                ask_result = self.order_handler.perp_limit_sell(self.symbol, self.order_amount, ask_price, self.leverage)
            else:
                ask_result = self.order_handler.limit_sell(self.symbol, self.order_amount, ask_price)
            
            if ask_result and ask_result["status"] == "ok":
                if "response" in ask_result and "data" in ask_result["response"] and "statuses" in ask_result["response"]["data"]:
                    for status in ask_result["response"]["data"]["statuses"]:
                        if "resting" in status:
                            self.active_sell_order_id = status["resting"]["oid"]
                            self.logger.info(f"Placed sell order: ID {self.active_sell_order_id} at {ask_price}")
            else:
                self.logger.error(f"Failed to place sell order: {ask_result}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error placing orders: {str(e)}")
            return False
    
    def _get_tick_size(self):
        """Get tick size (minimum price increment) for the symbol"""
        try:
            # Try to get from exchange metadata
            if self.api_connector and self.api_connector.info:
                meta = self.api_connector.info.meta()
                
                for asset_info in meta.get("universe", []):
                    if asset_info.get("name") == self.symbol:
                        if "tickSize" in asset_info:
                            return float(asset_info["tickSize"])
            
            # Fallback to checking from market data
            market_data = self.api_connector.get_market_data(self.symbol)
            if "best_bid" in market_data:
                # Try to infer tick size from price
                bid_str = str(market_data["best_bid"])
                if '.' in bid_str:
                    decimal_places = len(bid_str.split('.')[1])
                    return 1 / (10 ** decimal_places)
            
            # Conservative defaults based on price ranges
            if self.mid_price >= 10000:  # BTC-like
                return 0.5
            elif self.mid_price >= 1000:
                return 0.1
            elif self.mid_price >= 100:
                return 0.01
            elif self.mid_price >= 10:
                return 0.001
            elif self.mid_price >= 1:
                return 0.0001
            else:
                return 0.00001
                
        except Exception as e:
            self.logger.warning(f"Error determining tick size: {str(e)}. Using conservative default.")
            return 0.00001  # Very conservative default
    
    def _format_price(self, price, tick_size):
        """Format price to comply with exchange tick size"""
        if tick_size <= 0:
            return round(price, 8)  # Default to 8 decimal places
        
        # Round to nearest tick size
        rounded_price = round(price / tick_size) * tick_size
        
        # Ensure proper string formatting without trailing zeros
        price_str = str(rounded_price)
        if '.' in price_str:
            decimal_places = len(price_str.split('.')[1])
            return round(rounded_price, decimal_places)
        
        return rounded_price
    
    def get_performance_metrics(self):
        """Get basic strategy performance metrics"""
        return {
            "symbol": self.symbol,
            "mid_price": self.mid_price,
            "bid_price": self.mid_price * (1 - self.bid_spread) if self.mid_price else 0,
            "ask_price": self.mid_price * (1 + self.ask_spread) if self.mid_price else 0,
            "has_buy_order": self.active_buy_order_id is not None,
            "has_sell_order": self.active_sell_order_id is not None,
            "last_refresh": datetime.fromtimestamp(self.last_tick_time).strftime('%Y-%m-%d %H:%M:%S') if self.last_tick_time else "Never"
        }