import logging
from typing import Dict, Optional, Any, List
import hyperliquid

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from api.constants import MAINNET_API_URL, TESTNET_API_URL

class ApiConnector:
    """Handles connections to trading APIs and exchanges"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.wallet: Optional[LocalAccount] = None
        self.wallet_address: Optional[str] = None
        self.exchange: Optional[Exchange] = None
        self.info: Optional[Info] = None
        self._is_testnet: bool = False  # Track which network we're connected to
        
    def connect_testnet(self) -> bool:
        """
        Connect to Hyperliquid testnet
        
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self._is_testnet = True
            api_url = TESTNET_API_URL
            
            # Initialize exchange and info for testnet
            self.exchange = Exchange(
                None,  # No wallet needed for testnet
                api_url
            )
            self.info = Info(api_url)
            
            self.logger.info("Successfully connected to Hyperliquid testnet")
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Hyperliquid testnet: {str(e)}")
            return False

    def connect(self, credentials: Dict[str, str]) -> bool:
        """
        Connect to Hyperliquid mainnet
        
        Args:
            credentials: Dictionary containing wallet_address and secret_key
            
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self._is_testnet = False
            return self.connect_hyperliquid(
                wallet_address=credentials["wallet_address"],
                secret_key=credentials["secret_key"],
                use_testnet=False
            )
        except Exception as e:
            self.logger.error(f"Error connecting to Hyperliquid mainnet: {str(e)}")
            return False

    def connect_hyperliquid(self, wallet_address: str, secret_key: str, 
                           use_testnet: bool = False) -> bool:
        """
        Connect to Hyperliquid exchange
        
        Args:
            wallet_address: Wallet address for authentication
            secret_key: Secret key for authentication 
            use_testnet: Whether to use testnet (default is mainnet)
            
        Returns:
            True if connected successfully, False otherwise
        """
        try:
            self.wallet_address = wallet_address
            self._is_testnet = use_testnet  # Store the network type
            api_url = TESTNET_API_URL if use_testnet else MAINNET_API_URL
            
            # Initialize wallet
            self.wallet = eth_account.Account.from_key(secret_key)
            
            # Initialize exchange and info
            self.exchange = Exchange(
                self.wallet,
                api_url,
                account_address=self.wallet_address
            )
            self.info = Info(api_url)
            
            # Test connection by getting balances
            user_state = self.info.user_state(self.wallet_address)
            
            self.logger.info(f"Successfully connected to Hyperliquid {'(testnet)' if use_testnet else ''}")
            return True
        except Exception as e:
            self.logger.error(f"Error connecting to Hyperliquid: {str(e)}")
            return False
    
    def is_testnet(self) -> bool:
        """
        Check if currently connected to testnet
        
        Returns:
            bool: True if connected to testnet, False if connected to mainnet
        """
        return self._is_testnet

    def is_connected(self) -> bool:
        """
        Check if currently connected to any network
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self.exchange is not None and self.info is not None
    
    def get_balances(self) -> Dict[str, Any]:
        """Get all balances (spot and perpetual)"""
        if not self.info or not self.wallet_address:
            self.logger.error("Not connected to exchange")
            return {
                "spot": [],
                "perp": {
                    "account_value": 0.0,
                    "margin_used": 0.0,
                    "position_value": 0.0
                }
            }
        
        try:
            # Get spot balances
            spot_balances = []
            try:
                spot_state = self.info.spot_user_state(self.wallet_address)
                for balance in spot_state.get("balances", []):
                    spot_balances.append({
                        "asset": balance.get("coin", ""),
                        "available": float(balance.get("available", 0)),
                        "total": float(balance.get("total", 0)),
                        "in_orders": float(balance.get("total", 0)) - float(balance.get("available", 0))
                    })
            except Exception as e:
                self.logger.error(f"Error fetching spot balances: {str(e)}")
            
            # Get perpetual balances
            perp_balances = {
                "account_value": 0.0,
                "margin_used": 0.0,
                "position_value": 0.0
            }
            try:
                perp_state = self.info.user_state(self.wallet_address)
                if perp_state and isinstance(perp_state, dict):
                    margin_summary = perp_state.get("marginSummary", {})
                    if margin_summary and isinstance(margin_summary, dict):
                        perp_balances = {
                            "account_value": float(margin_summary.get("accountValue", 0)),
                            "margin_used": float(margin_summary.get("totalMarginUsed", 0)),
                            "position_value": float(margin_summary.get("totalNtlPos", 0))
                        }
            except Exception as e:
                self.logger.error(f"Error fetching perpetual balances: {str(e)}")
            
            # Log the response for debugging
            self.logger.debug(f"Spot balances: {spot_balances}")
            self.logger.debug(f"Perp balances: {perp_balances}")
            
            return {
                "spot": spot_balances,
                "perp": perp_balances
            }
        except Exception as e:
            self.logger.error(f"Error in get_balances: {str(e)}")
            return {
                "spot": [],
                "perp": {
                    "account_value": 0.0,
                    "margin_used": 0.0,
                    "position_value": 0.0
                }
            }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions"""
        if not self.info or not self.wallet_address:
            self.logger.error("Not connected to exchange")
            return []
        
        try:
            perp_state = self.info.user_state(self.wallet_address)
            positions = []
            
            for asset_position in perp_state.get("assetPositions", []):
                position = asset_position.get("position", {})
                if float(position.get("szi", 0)) != 0:
                    positions.append({
                        "symbol": position.get("coin", ""),
                        "size": float(position.get("szi", 0)),
                        "entry_price": float(position.get("entryPx", 0)),
                        "mark_price": float(position.get("markPx", 0)),
                        "liquidation_price": float(position.get("liquidationPx", 0) or 0),
                        "unrealized_pnl": float(position.get("unrealizedPnl", 0)),
                        "margin_used": float(position.get("marginUsed", 0))
                    })
            
            return positions
        except Exception as e:
            self.logger.error(f"Error fetching positions: {str(e)}")
            return []
    
    def get_market_data(self, symbol: str) -> Dict[str, Any]:
        """
        Get market data for a specific symbol with robust error handling
        
        Args:
            symbol: Trading pair symbol
            
        Returns:
            Dict with market data including mid_price, best_bid, best_ask
        """
        if not self.info:
            self.logger.error(f"Not connected to exchange when getting market data for {symbol}")
            return {}
        
        try:
            # Try multiple methods to get price data for maximum reliability
            market_data = {}
            
            # Method 1: Get order book
            try:
                order_book = self.info.l2_snapshot(symbol)
                
                if order_book and "levels" in order_book and len(order_book["levels"]) >= 2:
                    bid_levels = order_book["levels"][0]
                    ask_levels = order_book["levels"][1]
                    
                    if bid_levels and len(bid_levels) > 0:
                        market_data["best_bid"] = float(bid_levels[0]["px"])
                    
                    if ask_levels and len(ask_levels) > 0:
                        market_data["best_ask"] = float(ask_levels[0]["px"])
                    
                    # Calculate mid price if we have both bid and ask
                    if "best_bid" in market_data and "best_ask" in market_data:
                        market_data["mid_price"] = (market_data["best_bid"] + market_data["best_ask"]) / 2
                        self.logger.info(f"Got price for {symbol} from order book: {market_data['mid_price']}")
                
                market_data["order_book"] = order_book
            except Exception as e:
                self.logger.warning(f"Error getting order book for {symbol}: {str(e)}")
            
            # Method 2: Try all_mids if we don't have mid_price yet
            if "mid_price" not in market_data:
                try:
                    all_mids = self.info.all_mids()
                    mid_price = all_mids.get(symbol, None)
                    if mid_price is not None:
                        market_data["mid_price"] = float(mid_price)
                        self.logger.info(f"Got price for {symbol} from all_mids: {market_data['mid_price']}")
                except Exception as e:
                    self.logger.warning(f"Error getting all_mids for {symbol}: {str(e)}")
            
            # Method 3: Try metadata and last price if we still don't have a price
            if "mid_price" not in market_data:
                try:
                    meta = self.info.meta()
                    for asset in meta.get("universe", []):
                        if asset.get("name") == symbol:
                            last_price = asset.get("lastPrice")
                            if last_price:
                                market_data["mid_price"] = float(last_price)
                                self.logger.info(f"Got price for {symbol} from meta: {market_data['mid_price']}")
                                break
                except Exception as e:
                    self.logger.warning(f"Error getting meta for {symbol}: {str(e)}")
            
            # If we still don't have a price, try symbol info directly
            if "mid_price" not in market_data:
                try:
                    if hasattr(self.info, "ticker") and callable(self.info.ticker):
                        ticker = self.info.ticker(symbol)
                        if ticker and "last" in ticker:
                            market_data["mid_price"] = float(ticker["last"])
                            self.logger.info(f"Got price for {symbol} from ticker: {market_data['mid_price']}")
                except Exception as e:
                    self.logger.warning(f"Error getting ticker for {symbol}: {str(e)}")
            
            # Log if we still couldn't get a price
            if "mid_price" not in market_data:
                self.logger.error(f"Could not determine price for {symbol} using any method")
                return {"error": f"Could not determine price for {symbol}"}
            
            return market_data
        
        except Exception as e:
            self.logger.error(f"Error fetching market data for {symbol}: {str(e)}")
            return {"error": str(e)}