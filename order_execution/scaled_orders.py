import logging
import time
from typing import Dict, List, Any, Optional

class ScaledOrderExecutor:
    """
    Handles scaled order execution for Elysium Trading Platform
    Scaled orders place multiple orders across a price range with optional skew.
    """
    
    def __init__(self, exchange=None, info=None, api_connector=None):
        self.exchange = exchange
        self.info = info
        self.api_connector = api_connector
        self.wallet_address = None
        self.logger = logging.getLogger(__name__)
    
    def set_exchange(self, exchange, info, api_connector=None):
        """Set the exchange and info objects"""
        self.exchange = exchange
        self.info = info
        self.api_connector = api_connector
    
    def _calculate_order_distribution(self, total_size: float, num_orders: int, skew: float) -> List[float]:
        """
        Calculate the size distribution across orders based on skew
        
        Args:
            total_size: Total order size
            num_orders: Number of orders to place
            skew: Skew factor (0 = linear, >0 = exponential)
            
        Returns:
            List of order sizes
        """
        if num_orders <= 0:
            return [total_size]
            
        if skew == 0:
            # Linear distribution - equal sizes
            return [total_size / num_orders] * num_orders
            
        # Exponential distribution based on skew
        # Higher skew = more weight on earlier orders
        weights = [pow(i+1, skew) for i in range(num_orders)]
        total_weight = sum(weights)
        
        return [total_size * (weight / total_weight) for weight in weights]
    
    def _calculate_price_levels(self, is_buy: bool, num_orders: int, start_price: float, end_price: float) -> List[float]:
        """
        Calculate price levels for orders
        
        Args:
            is_buy: True for buy orders, False for sell orders
            num_orders: Number of orders to place
            start_price: Starting price (highest for buys, lowest for sells)
            end_price: Ending price (lowest for buys, highest for sells)
            
        Returns:
            List of prices for each order
        """
        if num_orders <= 1:
            return [start_price]
            
        # Calculate step size
        step = (end_price - start_price) / (num_orders - 1)
        
        # Generate prices
        prices = []
        for i in range(num_orders):
            price = start_price + step * i
            prices.append(price)
        
        return prices
    
    def _format_size(self, symbol: str, size: float) -> float:
        """
        Format the order size according to exchange requirements
        
        Args:
            symbol: Trading pair symbol
            size: Order size
            
        Returns:
            Properly formatted size
        """
        try:
            # Get the metadata for the symbol
            meta = self.info.meta()
            
            # Find the symbol's info
            symbol_info = None
            for asset_info in meta["universe"]:
                if asset_info["name"] == symbol:
                    symbol_info = asset_info
                    break
                
            if symbol_info:
                # Format size based on symbol's decimal places
                sz_decimals = symbol_info.get("szDecimals", 2)
                return round(size, sz_decimals)
            
            # Default to 2 decimal places if symbol info not found
            return round(size, 2)
            
        except Exception as e:
            self.logger.warning(f"Error formatting size: {str(e)}. Using original size.")
            return size
    
    def _format_price(self, symbol: str, price: float) -> float:
        """
        Format the price according to exchange requirements
        
        Args:
            symbol: Trading pair symbol
            price: Price
            
        Returns:
            Properly formatted price
        """
        try:
            # Special handling for very large prices to avoid precision errors
            if price > 100_000:
                return round(price)
                
            # First round to 5 significant figures
            price_str = f"{price:.5g}"
            price_float = float(price_str)
            
            # Then apply additional rounding based on coin type
            coin = self.info.name_to_coin.get(symbol, symbol)
            if coin:
                asset_idx = self.info.coin_to_asset.get(coin)
                if asset_idx is not None:
                    is_spot = asset_idx >= 10_000
                    max_decimals = 8 if is_spot else 6
                    return round(price_float, max_decimals)
                
            # Default to 6 decimal places if we can't determine
            return round(price_float, 6)
            
        except Exception as e:
            self.logger.warning(f"Error formatting price: {str(e)}. Using original price.")
            return price
    
    def scaled_orders(self, symbol: str, is_buy: bool, total_size: float, num_orders: int,
                    start_price: float, end_price: float, skew: float = 0,
                    order_type: Dict = None, reduce_only: bool = False, check_market: bool = True) -> Dict[str, Any]:
        """
        Place multiple orders across a price range with an optional skew
        
        Args:
            symbol: Trading pair symbol
            is_buy: True for buy, False for sell
            total_size: Total order size
            num_orders: Number of orders to place
            start_price: Starting price (higher for buys, lower for sells)
            end_price: Ending price (lower for buys, higher for sells)
            skew: Skew factor (0 = linear, >0 = exponential)
            order_type: Order type dict, defaults to GTC limit orders
            reduce_only: Whether orders should be reduce-only
            check_market: Whether to check market prices and adjust if needed
            
        Returns:
            Dict containing status and order responses
        """
        if not self.exchange:
            return {"status": "error", "message": "Not connected to exchange"}
        
        try:
            # Validate inputs
            if total_size <= 0:
                return {"status": "error", "message": "Total size must be greater than 0"}
                
            if num_orders <= 0:
                return {"status": "error", "message": "Number of orders must be greater than 0"}
                
            if start_price <= 0 or end_price <= 0:
                return {"status": "error", "message": "Prices must be greater than 0"}
                
            if skew < 0:
                return {"status": "error", "message": "Skew must be non-negative"}
                
            # Validate/adjust price direction based on order side
            if is_buy and start_price < end_price:
                self.logger.warning("For buy orders, start_price should be higher than end_price. Swapping values.")
                start_price, end_price = end_price, start_price
            elif not is_buy and start_price > end_price:
                self.logger.warning("For sell orders, start_price should be lower than end_price. Swapping values.")
                start_price, end_price = end_price, start_price
            
            # Default order type if not provided
            if order_type is None:
                order_type = {"limit": {"tif": "Gtc"}}
                
            # If check_market is true, get the current market data to validate prices
            if check_market:
                try:
                    # Get order book
                    order_book = self.info.l2_snapshot(symbol)
                    
                    if order_book and "levels" in order_book and len(order_book["levels"]) >= 2:
                        bid_levels = order_book["levels"][0]
                        ask_levels = order_book["levels"][1]
                        
                        if bid_levels and ask_levels:
                            best_bid = float(bid_levels[0]["px"])
                            best_ask = float(ask_levels[0]["px"])
                            
                            self.logger.info(f"Current market for {symbol}: Bid: {best_bid}, Ask: {best_ask}")
                            
                            # For buy orders, ensure we're not buying above the ask
                            if is_buy:
                                if start_price > best_ask * 1.05:  # Allow 5% above ask as maximum
                                    self.logger.warning(f"Start price {start_price} is too high. Limiting to 5% above ask: {best_ask * 1.05}")
                                    start_price = min(start_price, best_ask * 1.05)
                                
                                # Make sure end price is not above best ask
                                if end_price > best_ask:
                                    self.logger.warning(f"End price {end_price} is above best ask. Setting to best bid.")
                                    end_price = best_bid
                                    
                            # For sell orders, ensure we're not selling below the bid
                            else:
                                if start_price < best_bid * 0.95:  # Allow 5% below bid as minimum
                                    self.logger.warning(f"Start price {start_price} is too low. Limiting to 5% below bid: {best_bid * 0.95}")
                                    start_price = max(start_price, best_bid * 0.95)
                                    
                                # Make sure end price is not below best bid
                                if end_price < best_bid:
                                    self.logger.warning(f"End price {end_price} is below best bid. Setting to best ask.")
                                    end_price = best_ask
                except Exception as e:
                    self.logger.warning(f"Error checking market data: {str(e)}. Continuing with provided prices.")
                    
            # Calculate size and price for each order
            order_sizes = self._calculate_order_distribution(total_size, num_orders, skew)
            price_levels = self._calculate_price_levels(is_buy, num_orders, start_price, end_price)
            
            # Format sizes and prices to correct precision
            formatted_sizes = [self._format_size(symbol, s) for s in order_sizes]
            formatted_prices = [self._format_price(symbol, p) for p in price_levels]
            
            # Place orders
            self.logger.info(f"Placing {num_orders} {'buy' if is_buy else 'sell'} orders for {symbol} from {start_price} to {end_price} with total size {total_size}")
            
            order_results = []
            successful_orders = 0
            
            for i in range(num_orders):
                try:
                    result = self.exchange.order(
                        symbol, 
                        is_buy, 
                        formatted_sizes[i], 
                        formatted_prices[i], 
                        order_type, 
                        reduce_only
                    )
                    
                    order_results.append(result)
                    
                    if result["status"] == "ok":
                        successful_orders += 1
                        self.logger.info(f"Order {i+1}/{num_orders} placed: {formatted_sizes[i]} @ {formatted_prices[i]}")
                    else:
                        self.logger.error(f"Order {i+1}/{num_orders} failed: {result}")
                        
                    # Small delay to avoid rate limiting
                    time.sleep(0.1)
                    
                except Exception as e:
                    error_msg = f"Error placing order {i+1}/{num_orders}: {str(e)}"
                    self.logger.error(error_msg)
                    order_results.append({"status": "error", "message": error_msg})
            
            return {
                "status": "ok" if successful_orders > 0 else "error",
                "message": f"Successfully placed {successful_orders}/{num_orders} orders",
                "successful_orders": successful_orders,
                "total_orders": num_orders,
                "results": order_results,
                "sizes": formatted_sizes,
                "prices": formatted_prices
            }
        except Exception as e:
            self.logger.error(f"Error in scaled orders: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def perp_scaled_orders(self, symbol: str, is_buy: bool, total_size: float, num_orders: int,
                         start_price: float, end_price: float, leverage: int = 1, skew: float = 0,
                         order_type: Dict = None, reduce_only: bool = False) -> Dict[str, Any]:
        """
        Place multiple perpetual orders across a price range with an optional skew
        
        Args:
            symbol: Trading pair symbol
            is_buy: True for buy, False for sell
            total_size: Total order size
            num_orders: Number of orders to place
            start_price: Starting price (higher for buys, lower for sells)
            end_price: Ending price (lower for buys, higher for sells)
            leverage: Leverage multiplier (default 1x)
            skew: Skew factor (0 = linear, >0 = exponential)
            order_type: Order type dict, defaults to GTC limit orders
            reduce_only: Whether orders should be reduce-only
            
        Returns:
            Dict containing status and order responses
        """
        if not self.exchange:
            return {"status": "error", "message": "Not connected to exchange"}
            
        try:
            # Set leverage first
            self._set_leverage(symbol, leverage)
            
            # Use the standard scaled orders implementation
            return self.scaled_orders(
                symbol, is_buy, total_size, num_orders, 
                start_price, end_price, skew, 
                order_type, reduce_only
            )
        except Exception as e:
            self.logger.error(f"Error in perpetual scaled orders: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def _set_leverage(self, symbol: str, leverage: int) -> Dict[str, Any]:
        """
        Set leverage for a symbol
        
        Args:
            symbol: Trading pair symbol
            leverage: Leverage multiplier
            
        Returns:
            Response dictionary
        """
        if not self.exchange:
            return {"status": "error", "message": "Not connected to exchange"}
            
        try:
            self.logger.info(f"Setting {leverage}x leverage for {symbol}")
            result = self.exchange.update_leverage(leverage, symbol)
            return result
        except Exception as e:
            self.logger.error(f"Error setting leverage: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def market_aware_scaled_buy(self, symbol: str, total_size: float, num_orders: int, 
                               price_percent: float = 3.0, skew: float = 0) -> Dict[str, Any]:
        """
        Place multiple buy orders across a price range with market awareness
        
        Args:
            symbol: Trading pair symbol
            total_size: Total order size
            num_orders: Number of orders to place
            price_percent: How far below the best ask to start (default 3%)
            skew: Skew factor (0 = linear, >0 = exponential)
            
        Returns:
            Dict containing status and order responses
        """
        if not self.exchange or not self.info:
            return {"status": "error", "message": "Not connected to exchange"}
            
        try:
            # Get order book
            order_book = self.info.l2_snapshot(symbol)
            
            if not order_book or "levels" not in order_book or len(order_book["levels"]) < 2:
                return {"status": "error", "message": f"Could not fetch order book for {symbol}"}
                
            bid_levels = order_book["levels"][0]
            ask_levels = order_book["levels"][1]
            
            if not bid_levels or not ask_levels:
                return {"status": "error", "message": f"Order book for {symbol} has no bids or asks"}
            
            best_bid = float(bid_levels[0]["px"])
            best_ask = float(ask_levels[0]["px"])
            
            # Calculate price range
            start_price = best_ask * (1 - price_percent / 100)  # Start price is below ask
            end_price = best_bid  # End price is at best bid
            
            # Place scaled orders (don't check market again since we just did)
            return self.scaled_orders(
                symbol, True, total_size, num_orders, 
                start_price, end_price, skew, 
                check_market=False
            )
            
        except Exception as e:
            self.logger.error(f"Error in market-aware scaled buy: {str(e)}")
            return {"status": "error", "message": str(e)}
    
    def market_aware_scaled_sell(self, symbol: str, total_size: float, num_orders: int, 
                                price_percent: float = 3.0, skew: float = 0) -> Dict[str, Any]:
        """
        Place multiple sell orders across a price range with market awareness
        
        Args:
            symbol: Trading pair symbol
            total_size: Total order size
            num_orders: Number of orders to place
            price_percent: How far above the best bid to end (default 3%)
            skew: Skew factor (0 = linear, >0 = exponential)
            
        Returns:
            Dict containing status and order responses
        """
        if not self.exchange or not self.info:
            return {"status": "error", "message": "Not connected to exchange"}
            
        try:
            # Get order book
            order_book = self.info.l2_snapshot(symbol)
            
            if not order_book or "levels" not in order_book or len(order_book["levels"]) < 2:
                return {"status": "error", "message": f"Could not fetch order book for {symbol}"}
                
            bid_levels = order_book["levels"][0]
            ask_levels = order_book["levels"][1]
            
            if not bid_levels or not ask_levels:
                return {"status": "error", "message": f"Order book for {symbol} has no bids or asks"}
            
            best_bid = float(bid_levels[0]["px"])
            best_ask = float(ask_levels[0]["px"])
            
            # Calculate price range
            start_price = best_ask  # Start price is at best ask
            end_price = best_bid * (1 + price_percent / 100)  # End price is above bid
            
            # Place scaled orders (don't check market again since we just did)
            return self.scaled_orders(
                symbol, False, total_size, num_orders, 
                start_price, end_price, skew, 
                check_market=False
            )
            
        except Exception as e:
            self.logger.error(f"Error in market-aware scaled sell: {str(e)}")
            return {"status": "error", "message": str(e)}