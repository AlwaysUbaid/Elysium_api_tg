import logging
import threading
import time
import json
from datetime import datetime
from typing import Dict, List, Optional, Any, Union

class GridTrading:
    """
    Implements sequential grid trading strategy for the Elysium Trading Platform.
    This approach places buy orders first, then places sell orders only after buys are filled.
    """
    
    def __init__(self, order_handler):
        """
        Initialize the grid trading module
        
        Args:
            order_handler: The order handler object to execute orders
        """
        self.order_handler = order_handler
        self.active_grids = {}  # Dictionary to store active grid strategies
        self.completed_grids = {}  # Dictionary to store completed grid strategies
        self.grid_id_counter = 1
        self.grid_lock = threading.Lock()  # Lock for thread safety
        self.logger = logging.getLogger(__name__)
    
    def create_grid(self, symbol: str, upper_price: float, lower_price: float, 
                    num_grids: int, total_investment: float, is_perp: bool = False, 
                    leverage: int = 1, take_profit: Optional[float] = None,
                    stop_loss: Optional[float] = None) -> str:
        """
        Create a new grid trading strategy
        
        Args:
            symbol: Trading pair symbol
            upper_price: Upper price boundary of the grid
            lower_price: Lower price boundary of the grid
            num_grids: Number of grid levels
            total_investment: Total amount to invest in the grid
            is_perp: Whether to use perpetual contracts
            leverage: Leverage to use for perpetual orders
            take_profit: Optional take profit level as percentage
            stop_loss: Optional stop loss level as percentage
            
        Returns:
            str: Unique grid ID
        """
        if upper_price <= lower_price:
            self.logger.error("Upper price must be greater than lower price")
            return {"status": "error", "message": "Upper price must be greater than lower price"}
        
        if num_grids < 2:
            self.logger.error("Number of grids must be at least 2")
            return {"status": "error", "message": "Number of grids must be at least 2"}
        
        with self.grid_lock:
            grid_id = f"grid_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self.grid_id_counter}"
            self.grid_id_counter += 1
            
            # Calculate grid parameters
            price_interval = (upper_price - lower_price) / (num_grids - 1)
            investment_per_grid = total_investment / num_grids
            
            grid_config = {
                "id": grid_id,
                "symbol": symbol,
                "upper_price": upper_price,
                "lower_price": lower_price,
                "num_grids": num_grids,
                "price_interval": price_interval,
                "total_investment": total_investment,
                "investment_per_grid": investment_per_grid,
                "is_perp": is_perp,
                "leverage": leverage,
                "take_profit": take_profit,
                "stop_loss": stop_loss,
                "created_at": datetime.now(),
                "active": False,
                "orders": [],
                "filled_orders": [],
                "profit_loss": 0,
                "status": "created",
                "error": None,
                "current_price": None,
                "buy_only_mode": True  # New flag to indicate we're only placing buy orders initially
            }
            
            self.active_grids[grid_id] = grid_config
            self.logger.info(f"Created grid trading strategy {grid_id} for {symbol}")
            
            return grid_id
    
    def start_grid(self, grid_id: str) -> Dict[str, Any]:
        """
        Start a grid trading strategy in buy-only mode
        
        Args:
            grid_id: The ID of the grid to start
            
        Returns:
            Dict: Status information
        """
        with self.grid_lock:
            if grid_id not in self.active_grids:
                self.logger.error(f"Grid {grid_id} not found")
                return {"status": "error", "message": f"Grid {grid_id} not found"}
            
            grid = self.active_grids[grid_id]
            
            if grid["active"]:
                self.logger.warning(f"Grid {grid_id} is already active")
                return {"status": "warning", "message": f"Grid {grid_id} is already active"}
            
            try:
                warning_msg = None
                
                # Verify API connector is properly set
                if not hasattr(self.order_handler, 'api_connector') or self.order_handler.api_connector is None:
                    self.logger.error(f"API connector not properly set for grid {grid_id}")
                    return {"status": "error", "message": "API connector not properly set. Please reconnect to the exchange."}
                    
                # Get market data with proper error handling
                self.logger.info(f"Retrieving market data for {grid['symbol']}")
                market_data = self.order_handler.api_connector.get_market_data(grid["symbol"])
                
                # Check for error in market data
                if "error" in market_data:
                    self.logger.error(f"Error getting market data: {market_data['error']}")
                    grid["error"] = f"Could not get current price: {market_data['error']}"
                    return {"status": "error", "message": f"Could not get current price for {grid['symbol']}: {market_data['error']}"}
                
                # Get current price from market data
                current_price = market_data.get("mid_price")
                
                if not current_price:
                    # Try to use best_bid and best_ask if mid_price is not available
                    best_bid = market_data.get("best_bid")
                    best_ask = market_data.get("best_ask")
                    
                    if best_bid and best_ask:
                        current_price = (best_bid + best_ask) / 2
                        self.logger.info(f"Using average of bid/ask as current price: {current_price}")
                    elif best_bid:
                        current_price = best_bid
                        self.logger.info(f"Using best bid as current price: {current_price}")
                    elif best_ask:
                        current_price = best_ask
                        self.logger.info(f"Using best ask as current price: {current_price}")
                    else:
                        self.logger.error(f"Could not determine current price for {grid['symbol']}")
                        grid["error"] = "Could not determine current price"
                        return {"status": "error", "message": f"Could not determine current price for {grid['symbol']}"}
                
                self.logger.info(f"Current price for {grid['symbol']}: {current_price}")
                grid["current_price"] = current_price
                
                # Check if current price is within grid range
                if current_price < grid["lower_price"] or current_price > grid["upper_price"]:
                    self.logger.warning(f"Current price ({current_price}) is outside grid range ({grid['lower_price']} - {grid['upper_price']})")
                    warning_msg = f"Current price ({current_price}) is outside grid range. Consider adjusting grid boundaries."
                
                # Calculate grid levels
                grid_levels = []
                for i in range(grid["num_grids"]):
                    price = grid["lower_price"] + (i * grid["price_interval"])
                    grid_levels.append(price)
                
                # Place only buy orders (below current price)
                buy_orders = []
                
                # Use a simple fixed size to start
                base_quantity = 1.0
                
                # Place only buy orders below current price
                for price in grid_levels:
                    if price < current_price:
                        try:
                            # Place a buy order
                            self.logger.info(f"Placing buy order at {price} for {grid['symbol']}")
                            
                            # Try to use a simple fixed size that won't cause precision issues
                            if grid["is_perp"]:
                                # Set leverage first
                                self.order_handler._set_leverage(grid["symbol"], grid["leverage"])
                                order_result = self.order_handler.perp_limit_buy(
                                    grid["symbol"], base_quantity, price, grid["leverage"]
                                )
                            else:
                                order_result = self.order_handler.limit_buy(
                                    grid["symbol"], base_quantity, price
                                )
                            
                            # Process the result
                            if order_result["status"] == "ok":
                                if "response" in order_result and "data" in order_result["response"] and "statuses" in order_result["response"]["data"]:
                                    status = order_result["response"]["data"]["statuses"][0]
                                    if "resting" in status:
                                        order_id = status["resting"]["oid"]
                                        buy_orders.append({
                                            "id": order_id,
                                            "price": price,
                                            "quantity": base_quantity,
                                            "side": "buy",
                                            "status": "open"
                                        })
                                        self.logger.info(f"Successfully placed buy order at {price}")
                                    elif "error" in status:
                                        self.logger.error(f"Error placing buy order at {price}: {status['error']}")
                            else:
                                self.logger.error(f"Failed to place buy order at {price}: {order_result}")
                            
                            # Add a delay between orders to avoid rate limiting
                            time.sleep(0.5)
                            
                        except Exception as e:
                            self.logger.error(f"Exception placing buy order at {price}: {str(e)}")
                
                # Update grid with orders
                grid["orders"] = buy_orders
                grid["active"] = True
                grid["status"] = "active"
                grid["buy_only_mode"] = True  # We're only placing buy orders initially
                
                self.logger.info(f"Started grid {grid_id} with {len(buy_orders)} buy orders")
                
                # Start monitoring thread for this grid
                monitor_thread = threading.Thread(target=self._monitor_grid, args=(grid_id,))
                monitor_thread.daemon = True
                monitor_thread.start()
                
                return {
                    "status": "ok", 
                    "message": f"Grid {grid_id} started successfully in buy-only mode",
                    "warning": warning_msg,
                    "buy_orders": len(buy_orders),
                    "sell_orders": 0,  # No sell orders yet
                    "current_price": current_price
                }
            except Exception as e:
                error_msg = f"Error starting grid {grid_id}: {str(e)}"
                self.logger.error(error_msg)
                grid["error"] = error_msg
                grid["status"] = "error"
                return {"status": "error", "message": error_msg}
    
    def stop_grid(self, grid_id: str) -> Dict[str, Any]:
        """
        Stop a grid trading strategy and cancel all open orders
        
        Args:
            grid_id: The ID of the grid to stop
            
        Returns:
            Dict: Status information
        """
        with self.grid_lock:
            if grid_id not in self.active_grids:
                self.logger.error(f"Grid {grid_id} not found")
                return {"status": "error", "message": f"Grid {grid_id} not found"}
            
            grid = self.active_grids[grid_id]
            
            if not grid["active"]:
                self.logger.warning(f"Grid {grid_id} is not active")
                return {"status": "warning", "message": f"Grid {grid_id} is not active"}
            
            # Cancel all open orders
            try:
                symbol = grid["symbol"]
                cancelled = 0
                
                # Get all open orders for this grid
                open_orders = [order for order in grid["orders"] if order["status"] == "open"]
                
                for order in open_orders:
                    try:
                        result = self.order_handler.cancel_order(symbol, order["id"])
                        if result["status"] == "ok":
                            order["status"] = "cancelled"
                            cancelled += 1
                    except Exception as e:
                        self.logger.error(f"Error cancelling order {order['id']}: {str(e)}")
                
                grid["active"] = False
                grid["status"] = "stopped"
                
                # Move to completed grids
                self.completed_grids[grid_id] = grid
                del self.active_grids[grid_id]
                
                self.logger.info(f"Stopped grid {grid_id}, cancelled {cancelled}/{len(open_orders)} orders")
                
                return {
                    "status": "ok", 
                    "message": f"Grid {grid_id} stopped successfully",
                    "cancelled_orders": cancelled,
                    "total_orders": len(open_orders),
                    "profit_loss": grid["profit_loss"]
                }
            
            except Exception as e:
                error_msg = f"Error stopping grid {grid_id}: {str(e)}"
                self.logger.error(error_msg)
                grid["error"] = error_msg
                return {"status": "error", "message": error_msg}
    
    def get_grid_status(self, grid_id: str) -> Dict[str, Any]:
        """
        Get the status of a grid trading strategy
        
        Args:
            grid_id: The ID of the grid
            
        Returns:
            Dict: Grid status information
        """
        with self.grid_lock:
            if grid_id in self.active_grids:
                grid = self.active_grids[grid_id]
                status = grid.copy()
                status["status"] = "active" if grid["active"] else "created"
                return status
            elif grid_id in self.completed_grids:
                grid = self.completed_grids[grid_id]
                status = grid.copy()
                status["status"] = "completed"
                return status
            else:
                self.logger.error(f"Grid {grid_id} not found")
                return {"status": "error", "message": f"Grid {grid_id} not found"}
    
    def list_grids(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all grid trading strategies
        
        Returns:
            Dict: Dictionary with active and completed grids
        """
        with self.grid_lock:
            active = list(self.active_grids.values())
            completed = list(self.completed_grids.values())
            
            return {
                "active": active,
                "completed": completed
            }