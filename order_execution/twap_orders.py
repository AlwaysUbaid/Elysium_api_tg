import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

class TwapExecution:
    """
    Time-Weighted Average Price (TWAP) execution strategy
    Splits a large order into smaller slices executed over time
    """
    
    def __init__(self, order_handler, symbol: str, side: str, total_quantity: float, 
                duration_minutes: int, num_slices: int, price_limit: Optional[float] = None,
                is_perp: bool = False, leverage: int = 1):
        """
        Initialize TWAP execution
        
        Args:
            order_handler: The order handler object that executes orders
            symbol: Trading pair symbol
            side: 'buy' or 'sell'
            total_quantity: Total quantity to execute
            duration_minutes: Total duration in minutes
            num_slices: Number of slices to divide the order into
            price_limit: Optional price limit for each slice
            is_perp: Whether this is a perpetual futures order
            leverage: Leverage to use for perpetual orders
        """
        self.order_handler = order_handler
        self.symbol = symbol
        self.side = side.lower()
        self.total_quantity = total_quantity
        self.duration_minutes = duration_minutes
        self.num_slices = num_slices
        self.price_limit = price_limit
        self.is_perp = is_perp
        self.leverage = leverage
        
        # Calculate parameters
        self.quantity_per_slice = total_quantity / num_slices
        self.interval_seconds = (duration_minutes * 60) / num_slices
        
        # Initialize tracking variables
        self.is_running = False
        self.start_time = None
        self.end_time = None
        self.slices_executed = 0
        self.total_executed = 0.0
        self.average_price = 0.0
        self.execution_prices = []
        self.errors = []
        self.thread = None
        self.stop_event = threading.Event()
        
        self.logger = logging.getLogger(__name__)
    
    def start(self) -> bool:
        """Start the TWAP execution"""
        if self.is_running:
            self.logger.warning("TWAP execution already running")
            return False
        
        self.start_time = datetime.now()
        self.end_time = self.start_time + timedelta(minutes=self.duration_minutes)
        self.is_running = True
        self.stop_event.clear()
        
        self.logger.info(f"Starting TWAP execution for {self.total_quantity} {self.symbol} "
                        f"over {self.duration_minutes} minutes in {self.num_slices} slices")
        
        # Start execution thread
        self.thread = threading.Thread(target=self._execute_strategy)
        self.thread.daemon = True
        self.thread.start()
        
        return True
    
    def stop(self) -> bool:
        """Stop the TWAP execution"""
        if not self.is_running:
            self.logger.warning("TWAP execution not running")
            return False
        
        self.logger.info("Stopping TWAP execution")
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
        
        self.is_running = False
        return True
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the TWAP execution"""
        return {
            "symbol": self.symbol,
            "side": self.side,
            "is_perp": self.is_perp,
            "total_quantity": self.total_quantity,
            "duration_minutes": self.duration_minutes,
            "num_slices": self.num_slices,
            "quantity_per_slice": self.quantity_per_slice,
            "interval_seconds": self.interval_seconds,
            "is_running": self.is_running,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "slices_executed": self.slices_executed,
            "total_executed": self.total_executed,
            "average_price": self.average_price,
            "remaining_quantity": self.total_quantity - self.total_executed,
            "completion_percentage": (self.slices_executed / self.num_slices) * 100 if self.num_slices > 0 else 0,
            "errors": self.errors
        }
    
    def _execute_strategy(self) -> None:
        """Execute the TWAP strategy - runs in a separate thread"""
        try:
            for slice_num in range(self.num_slices):
                # Check if we should stop
                if self.stop_event.is_set():
                    self.logger.info("TWAP execution stopped by user")
                    break
                
                # Execute slice
                slice_start_time = time.time()
                self._execute_slice(slice_num + 1)
                self.slices_executed += 1
                
                # Wait until the next interval, unless it's the last slice
                if slice_num < self.num_slices - 1:
                    # Calculate time to wait
                    elapsed = time.time() - slice_start_time
                    wait_time = max(0, self.interval_seconds - elapsed)
                    
                    # Wait, but check for stop event every second
                    for _ in range(int(wait_time)):
                        if self.stop_event.is_set():
                            self.logger.info("TWAP execution stopped during interval wait")
                            break
                        time.sleep(1)
                    
                    # Sleep any remaining fraction of a second
                    time.sleep(wait_time - int(wait_time))
            
            if self.slices_executed == self.num_slices:
                self.logger.info("TWAP execution completed successfully")
            else:
                self.logger.info(f"TWAP execution stopped after {self.slices_executed}/{self.num_slices} slices")
        
        except Exception as e:
            self.logger.error(f"Error in TWAP execution: {str(e)}")
            self.errors.append(str(e))
        
        finally:
            self.is_running = False
    
    def _execute_slice(self, slice_num: int) -> None:
        """Execute a single slice of the TWAP order"""
        try:
            self.logger.info(f"Executing TWAP slice {slice_num}/{self.num_slices} for {self.quantity_per_slice} {self.symbol}")
            
            # Execute the slice based on side and type (spot or perp)
            result = None
            
            if self.is_perp:
                # Perpetual order
                if self.side == 'buy':
                    if self.price_limit:
                        result = self.order_handler.perp_limit_buy(self.symbol, self.quantity_per_slice, 
                                                                self.price_limit, self.leverage)
                    else:
                        result = self.order_handler.perp_market_buy(self.symbol, self.quantity_per_slice, 
                                                                self.leverage)
                else:  # sell
                    if self.price_limit:
                        result = self.order_handler.perp_limit_sell(self.symbol, self.quantity_per_slice, 
                                                                self.price_limit, self.leverage)
                    else:
                        result = self.order_handler.perp_market_sell(self.symbol, self.quantity_per_slice, 
                                                                    self.leverage)
            else:
                # Spot order
                if self.side == 'buy':
                    if self.price_limit:
                        result = self.order_handler.limit_buy(self.symbol, self.quantity_per_slice, self.price_limit)
                    else:
                        result = self.order_handler.market_buy(self.symbol, self.quantity_per_slice)
                else:  # sell
                    if self.price_limit:
                        result = self.order_handler.limit_sell(self.symbol, self.quantity_per_slice, self.price_limit)
                    else:
                        result = self.order_handler.market_sell(self.symbol, self.quantity_per_slice)
            
            # Process the result
            if result and result["status"] == "ok":
                if "response" in result and "data" in result["response"] and "statuses" in result["response"]["data"]:
                    for status in result["response"]["data"]["statuses"]:
                        if "filled" in status:
                            filled = status["filled"]
                            executed_qty = float(filled["totalSz"])
                            executed_price = float(filled["avgPx"])
                            
                            self.total_executed += executed_qty
                            self.execution_prices.append(executed_price)
                            
                            # Update average price
                            if self.execution_prices:
                                self.average_price = sum(self.execution_prices) / len(self.execution_prices)
                            
                            self.logger.info(f"TWAP slice {slice_num} executed: {executed_qty} @ {executed_price}")
            else:
                error_msg = result.get("message", "Unknown error") if result else "No result returned"
                self.logger.error(f"TWAP slice {slice_num} failed: {error_msg}")
                self.errors.append(f"Slice {slice_num}: {error_msg}")
        
        except Exception as e:
            self.logger.error(f"Error executing TWAP slice {slice_num}: {str(e)}")
            self.errors.append(f"Slice {slice_num}: {str(e)}")


class TwapOrderExecutor:
    """Manages TWAP executions for the Elysium Trading Platform"""
    
    def __init__(self, exchange=None, info=None, api_connector=None):
        self.exchange = exchange
        self.info = info
        self.api_connector = api_connector
        self.wallet_address = None
        self.logger = logging.getLogger(__name__)
        
        # TWAP tracking
        self.active_twaps = {}
        self.completed_twaps = {}
        self.twap_id_counter = 1
        self.twap_lock = threading.Lock()
    
    def set_exchange(self, exchange, info, api_connector=None):
        """Set the exchange and info objects"""
        self.exchange = exchange
        self.info = info
        self.api_connector = api_connector
    
    def create_twap(self, symbol: str, side: str, quantity: float, 
                  duration_minutes: int, num_slices: int, 
                  price_limit: Optional[float] = None,
                  is_perp: bool = False, leverage: int = 1) -> str:
        """
        Create a new TWAP execution
        
        Args:
            symbol: Trading pair symbol
            side: 'buy' or 'sell'
            quantity: Total quantity to execute
            duration_minutes: Total duration in minutes
            num_slices: Number of slices to divide the order into
            price_limit: Optional price limit for each slice
            is_perp: Whether this is a perpetual futures order
            leverage: Leverage to use for perpetual orders
            
        Returns:
            str: A unique ID for the TWAP execution
        """
        with self.twap_lock:
            twap_id = f"twap_{datetime.now().strftime('%Y%m%d%H%M%S')}_{self.twap_id_counter}"
            self.twap_id_counter += 1
            
            twap = TwapExecution(
                self,
                symbol,
                side,
                quantity,
                duration_minutes,
                num_slices,
                price_limit,
                is_perp,
                leverage
            )
            
            self.active_twaps[twap_id] = twap
            self.logger.info(f"Created TWAP {twap_id} for {quantity} {symbol}")
            
            return twap_id
    
    def start_twap(self, twap_id: str) -> bool:
        """
        Start a TWAP execution
        
        Args:
            twap_id: The ID of the TWAP execution to start
            
        Returns:
            bool: True if started successfully, False otherwise
        """
        with self.twap_lock:
            if twap_id not in self.active_twaps:
                self.logger.error(f"Cannot start TWAP {twap_id} - not found")
                return False
            
            twap = self.active_twaps[twap_id]
            success = twap.start()
            
            if success:
                self.logger.info(f"Started TWAP {twap_id}")
            else:
                self.logger.warning(f"Failed to start TWAP {twap_id}")
            
            return success
    
    def stop_twap(self, twap_id: str) -> bool:
        """
        Stop a TWAP execution
        
        Args:
            twap_id: The ID of the TWAP execution to stop
            
        Returns:
            bool: True if stopped successfully, False otherwise
        """
        with self.twap_lock:
            if twap_id not in self.active_twaps:
                self.logger.error(f"Cannot stop TWAP {twap_id} - not found")
                return False
            
            twap = self.active_twaps[twap_id]
            success = twap.stop()
            
            if success:
                self.logger.info(f"Stopped TWAP {twap_id}")
                
                # Move to completed if it's no longer running
                if not twap.is_running:
                    self.completed_twaps[twap_id] = twap
                    del self.active_twaps[twap_id]
            else:
                self.logger.warning(f"Failed to stop TWAP {twap_id}")
            
            return success
    
    def get_twap_status(self, twap_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the status of a TWAP execution
        
        Args:
            twap_id: The ID of the TWAP execution
            
        Returns:
            Dict or None: The status of the TWAP execution, or None if not found
        """
        with self.twap_lock:
            if twap_id in self.active_twaps:
                twap = self.active_twaps[twap_id]
                status = twap.get_status()
                status["id"] = twap_id
                status["status"] = "active"
                return status
            elif twap_id in self.completed_twaps:
                twap = self.completed_twaps[twap_id]
                status = twap.get_status()
                status["id"] = twap_id
                status["status"] = "completed"
                return status
            else:
                self.logger.error(f"Cannot get status for TWAP {twap_id} - not found")
                return None
    
    def list_twaps(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        List all TWAP executions
        
        Returns:
            Dict: A dictionary with 'active' and 'completed' lists of TWAP executions
        """
        with self.twap_lock:
            active = []
            for twap_id, twap in self.active_twaps.items():
                status = twap.get_status()
                status["id"] = twap_id
                status["status"] = "active"
                active.append(status)
            
            completed = []
            for twap_id, twap in self.completed_twaps.items():
                status = twap.get_status()
                status["id"] = twap_id
                status["status"] = "completed"
                completed.append(status)
            
            return {
                "active": active,
                "completed": completed
            }
    
    def clean_completed_twaps(self) -> int:
        """
        Clean up completed TWAP executions
        
        Returns:
            int: The number of completed TWAP executions that were cleaned up
        """
        with self.twap_lock:
            count = len(self.completed_twaps)
            self.completed_twaps.clear()
            self.logger.info(f"Cleaned up {count} completed TWAP executions")
            return count
    
    def stop_all_twaps(self) -> int:
        """
        Stop all active TWAP executions
        
        Returns:
            int: The number of TWAP executions that were stopped
        """
        with self.twap_lock:
            count = 0
            twap_ids = list(self.active_twaps.keys())
            
            for twap_id in twap_ids:
                if self.stop_twap(twap_id):
                    count += 1
            
            self.logger.info(f"Stopped {count} TWAP executions")
            return count
    
    # Forward order handler methods to TWAP execution
    
    def market_buy(self, symbol: str, size: float, slippage: float = 0.05):
        """Forward market_buy to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.market_buy(symbol, size, slippage)
        return {"status": "error", "message": "No order handler available"}
    
    def market_sell(self, symbol: str, size: float, slippage: float = 0.05):
        """Forward market_sell to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.market_sell(symbol, size, slippage)
        return {"status": "error", "message": "No order handler available"}
    
    def limit_buy(self, symbol: str, size: float, price: float):
        """Forward limit_buy to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.limit_buy(symbol, size, price)
        return {"status": "error", "message": "No order handler available"}
    
    def limit_sell(self, symbol: str, size: float, price: float):
        """Forward limit_sell to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.limit_sell(symbol, size, price)
        return {"status": "error", "message": "No order handler available"}
    
    def perp_market_buy(self, symbol: str, size: float, leverage: int = 1, slippage: float = 0.05):
        """Forward perp_market_buy to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.perp_market_buy(symbol, size, leverage, slippage)
        return {"status": "error", "message": "No order handler available"}
    
    def perp_market_sell(self, symbol: str, size: float, leverage: int = 1, slippage: float = 0.05):
        """Forward perp_market_sell to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.perp_market_sell(symbol, size, leverage, slippage)
        return {"status": "error", "message": "No order handler available"}
    
    def perp_limit_buy(self, symbol: str, size: float, price: float, leverage: int = 1):
        """Forward perp_limit_buy to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.perp_limit_buy(symbol, size, price, leverage)
        return {"status": "error", "message": "No order handler available"}
    
    def perp_limit_sell(self, symbol: str, size: float, price: float, leverage: int = 1):
        """Forward perp_limit_sell to order handler"""
        if hasattr(self, 'order_handler') and self.order_handler:
            return self.order_handler.perp_limit_sell(symbol, size, price, leverage)
        return {"status": "error", "message": "No order handler available"}