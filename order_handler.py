import logging
from typing import Dict, List, Any, Optional

from order_execution.simple_orders import SimpleOrderExecutor
from order_execution.scaled_orders import ScaledOrderExecutor
from order_execution.twap_orders import TwapOrderExecutor
from order_execution.grid_trading import GridTrading

class OrderHandler:
    """
    Main order handler that coordinates all order execution methods
    for the Elysium Trading Platform.
    """
    
    def __init__(self, exchange=None, info=None):
        self.exchange = exchange
        self.info = info
        self.wallet_address = None
        self.api_connector = None
        self.logger = logging.getLogger(__name__)
        
        # Initialize order executors
        self.simple_executor = SimpleOrderExecutor(exchange, info)
        self.scaled_executor = ScaledOrderExecutor(exchange, info)
        self.twap_executor = TwapOrderExecutor(exchange, info)
        self.grid_trading = GridTrading(self)
    
    def set_exchange(self, exchange, info, api_connector=None):
        """
        Set the exchange and info objects for all executors
        
        Args:
            exchange: Exchange object
            info: Info object
            api_connector: API connector object
        """
        self.exchange = exchange
        self.info = info
        self.api_connector = api_connector
        
        # Update exchange in all executors
        self.simple_executor.set_exchange(exchange, info)
        self.scaled_executor.set_exchange(exchange, info, api_connector)
        self.twap_executor.set_exchange(exchange, info, api_connector)
        self.twap_executor.order_handler = self
    
    # ============================= Simple Order Methods =============================
    
    def market_buy(self, symbol: str, size: float, slippage: float = 0.05) -> Dict[str, Any]:
        """Execute a market buy order"""
        return self.simple_executor.market_buy(symbol, size, slippage)
    
    def market_sell(self, symbol: str, size: float, slippage: float = 0.05) -> Dict[str, Any]:
        """Execute a market sell order"""
        return self.simple_executor.market_sell(symbol, size, slippage)
    
    def limit_buy(self, symbol: str, size: float, price: float) -> Dict[str, Any]:
        """Place a limit buy order"""
        return self.simple_executor.limit_buy(symbol, size, price)
    
    def limit_sell(self, symbol: str, size: float, price: float) -> Dict[str, Any]:
        """Place a limit sell order"""
        return self.simple_executor.limit_sell(symbol, size, price)
    
    def perp_market_buy(self, symbol: str, size: float, leverage: int = 1, slippage: float = 0.05) -> Dict[str, Any]:
        """Execute a perpetual market buy order"""
        return self.simple_executor.perp_market_buy(symbol, size, leverage, slippage)
    
    def perp_market_sell(self, symbol: str, size: float, leverage: int = 1, slippage: float = 0.05) -> Dict[str, Any]:
        """Execute a perpetual market sell order"""
        return self.simple_executor.perp_market_sell(symbol, size, leverage, slippage)
    
    def perp_limit_buy(self, symbol: str, size: float, price: float, leverage: int = 1) -> Dict[str, Any]:
        """Place a perpetual limit buy order"""
        return self.simple_executor.perp_limit_buy(symbol, size, price, leverage)
    
    def perp_limit_sell(self, symbol: str, size: float, price: float, leverage: int = 1) -> Dict[str, Any]:
        """Place a perpetual limit sell order"""
        return self.simple_executor.perp_limit_sell(symbol, size, price, leverage)
    
    def close_position(self, symbol: str, slippage: float = 0.05) -> Dict[str, Any]:
        """Close an entire position for a symbol"""
        return self.simple_executor.close_position(symbol, slippage)
    
    def cancel_order(self, symbol: str, order_id: int) -> Dict[str, Any]:
        """Cancel a specific order"""
        return self.simple_executor.cancel_order(symbol, order_id)
    
    def cancel_all_orders(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Cancel all open orders, optionally filtered by symbol"""
        self.simple_executor.wallet_address = self.wallet_address
        return self.simple_executor.cancel_all_orders(symbol)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all open orders, optionally filtered by symbol"""
        self.simple_executor.wallet_address = self.wallet_address
        return self.simple_executor.get_open_orders(symbol)
    
    def _set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """Set leverage for a symbol"""
        return self.simple_executor._set_leverage(symbol, leverage)
    
    # ============================= Scaled Order Methods =============================
    
    def scaled_orders(self, symbol: str, is_buy: bool, total_size: float, num_orders: int,
                     start_price: float, end_price: float, skew: float = 0,
                     order_type: Dict = None, reduce_only: bool = False, check_market: bool = True) -> Dict[str, Any]:
        """Place multiple orders across a price range with an optional skew"""
        return self.scaled_executor.scaled_orders(
            symbol, is_buy, total_size, num_orders, 
            start_price, end_price, skew, 
            order_type, reduce_only, check_market
        )
    
    def perp_scaled_orders(self, symbol: str, is_buy: bool, total_size: float, num_orders: int,
                          start_price: float, end_price: float, leverage: int = 1, skew: float = 0,
                          order_type: Dict = None, reduce_only: bool = False) -> Dict[str, Any]:
        """Place multiple perpetual orders across a price range with an optional skew"""
        return self.scaled_executor.perp_scaled_orders(
            symbol, is_buy, total_size, num_orders, 
            start_price, end_price, leverage, skew, 
            order_type, reduce_only
        )
    
    def market_aware_scaled_buy(self, symbol: str, total_size: float, num_orders: int, 
                               price_percent: float = 3.0, skew: float = 0) -> Dict[str, Any]:
        """Place multiple buy orders across a price range with market awareness"""
        return self.scaled_executor.market_aware_scaled_buy(
            symbol, total_size, num_orders, price_percent, skew
        )
    
    def market_aware_scaled_sell(self, symbol: str, total_size: float, num_orders: int, 
                                price_percent: float = 3.0, skew: float = 0) -> Dict[str, Any]:
        """Place multiple sell orders across a price range with market awareness"""
        return self.scaled_executor.market_aware_scaled_sell(
            symbol, total_size, num_orders, price_percent, skew
        )
    
    # ============================= TWAP Order Methods =============================
    
    def create_twap(self, symbol: str, side: str, quantity: float, 
                   duration_minutes: int, num_slices: int, 
                   price_limit: Optional[float] = None,
                   is_perp: bool = False, leverage: int = 1) -> str:
        """Create a new TWAP execution"""
        return self.twap_executor.create_twap(
            symbol, side, quantity, duration_minutes, num_slices, 
            price_limit, is_perp, leverage
        )
    
    def start_twap(self, twap_id: str) -> bool:
        """Start a TWAP execution"""
        return self.twap_executor.start_twap(twap_id)
    
    def stop_twap(self, twap_id: str) -> bool:
        """Stop a TWAP execution"""
        return self.twap_executor.stop_twap(twap_id)
    
    def get_twap_status(self, twap_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a TWAP execution"""
        return self.twap_executor.get_twap_status(twap_id)
    
    def list_twaps(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all TWAP executions"""
        return self.twap_executor.list_twaps()
    
    def clean_completed_twaps(self) -> int:
        """Clean up completed TWAP executions"""
        return self.twap_executor.clean_completed_twaps()
    
    def stop_all_twaps(self) -> int:
        """Stop all active TWAP executions"""
        return self.twap_executor.stop_all_twaps()
    
    # ============================= Grid Trading Methods =============================
    
    def create_grid(self, symbol: str, upper_price: float, lower_price: float, 
                   num_grids: int, total_investment: float, is_perp: bool = False, 
                   leverage: int = 1, take_profit: Optional[float] = None,
                   stop_loss: Optional[float] = None) -> str:
        """Create a new grid trading strategy"""
        return self.grid_trading.create_grid(
            symbol, upper_price, lower_price, num_grids, total_investment,
            is_perp, leverage, take_profit, stop_loss
        )
    
    def start_grid(self, grid_id: str) -> Dict[str, Any]:
        """Start a grid trading strategy"""
        return self.grid_trading.start_grid(grid_id)
    
    def stop_grid(self, grid_id: str) -> Dict[str, Any]:
        """Stop a grid trading strategy"""
        return self.grid_trading.stop_grid(grid_id)
    
    def get_grid_status(self, grid_id: str) -> Dict[str, Any]:
        """Get the status of a grid trading strategy"""
        return self.grid_trading.get_grid_status(grid_id)
    
    def list_grids(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all grid trading strategies"""
        return self.grid_trading.list_grids()
    
    def clean_completed_grids(self) -> int:
        """Clean up completed grid strategies"""
        return self.grid_trading.clean_completed_grids()
    
    def stop_all_grids(self) -> int:
        """Stop all active grid strategies"""
        return self.grid_trading.stop_all_grids()
    
    def modify_grid(self, grid_id: str, take_profit: Optional[float] = None, 
                   stop_loss: Optional[float] = None) -> Dict[str, Any]:
        """Modify parameters of an existing grid strategy"""
        return self.grid_trading.modify_grid(grid_id, take_profit, stop_loss)
    
    # ============================= Utility Methods =============================
    
    def test_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        Test market data retrieval for a symbol before creating a grid
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dict with test results and market data if available
        """
        if not self.api_connector:
            return {
                "success": False,
                "message": "API connector not set. Please connect to exchange first."
            }
        
        if not self.exchange or not self.info:
            return {
                "success": False,
                "message": "Not connected to exchange. Please connect first."
            }
        
        try:
            # Try to get market data
            market_data = self.api_connector.get_market_data(symbol)
            
            if "error" in market_data:
                return {
                    "success": False,
                    "message": f"Could not get market data: {market_data['error']}"
                }
            
            # Check if we have the necessary price data
            if "mid_price" not in market_data and "best_bid" not in market_data and "best_ask" not in market_data:
                return {
                    "success": False,
                    "message": f"Could not determine price for {symbol}"
                }
            
            # If we have price data, consider it a success
            price = market_data.get("mid_price")
            if not price:
                if market_data.get("best_bid") and market_data.get("best_ask"):
                    price = (market_data["best_bid"] + market_data["best_ask"]) / 2
                elif market_data.get("best_bid"):
                    price = market_data["best_bid"]
                elif market_data.get("best_ask"):
                    price = market_data["best_ask"]
            
            return {
                "success": True,
                "message": f"Successfully retrieved market data for {symbol}",
                "price": price,
                "market_data": market_data
            }
        
        except Exception as e:
            return {
                "success": False,
                "message": f"Error testing market data: {str(e)}"
            }