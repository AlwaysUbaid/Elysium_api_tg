from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import uvicorn
import logging
from datetime import datetime

# Import core modules
from core.config_manager import ConfigManager
from core.utils import setup_logging
from api.api_connector import ApiConnector
from order_handler import OrderHandler
from api.spot_api import router as spot_router, set_instances as set_spot_instances
from api.perp_api import router as perp_router, set_instances as set_perp_instances
from api.scaled_api import router as scaled_router, set_instances as set_scaled_instances

# Setup logging
logger = setup_logging("INFO")
logger.info("Initializing Elysium Trading Platform API components")

# Initialize FastAPI app
app = FastAPI(
    title="Elysium Trading Platform API",
    description="API for the Elysium Trading Platform",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
config_manager = ConfigManager("elysium_config.json")
api_connector = ApiConnector()
order_handler = OrderHandler()

# Set instances in spot, perp, and scaled APIs
set_spot_instances(api_connector, order_handler)
set_perp_instances(api_connector, order_handler)
set_scaled_instances(api_connector, order_handler)

# Include routers in the requested order:
# 1. Default endpoints are already in main.py
# 2. Spot
# 3. Perp
# 4. Scaled
app.include_router(spot_router)
app.include_router(perp_router)
app.include_router(scaled_router)

# Request/Response Models
class Credentials(BaseModel):
    wallet_address: str = Field(
        ...,
        description="Your Ethereum wallet address (e.g., 0x123...)",
        example="0x4f7116a3B69b14480b0C0890d63bd4B3d0984EE6"
    )
    secret_key: str = Field(
        ...,
        description="Your wallet's private key",
        example="0x992df5cae22a4b8e3844f73e14756f11a2662b7f2e792ce78fd85abb63150d51"
    )

class ConnectionRequest(BaseModel):
    network: str = Field(
        default="testnet",
        description="Network to connect to (mainnet or testnet)",
        example="mainnet"
    )
    credentials: Credentials = Field(
        ...,
        description="Wallet credentials (required for both mainnet and testnet)"
    )

class ConnectionResponse(BaseModel):
    status: str = Field(..., description="Connection status")
    message: str = Field(..., description="Response message")
    network: str = Field(..., description="Connected network (testnet/mainnet)")
    timestamp: str = Field(..., description="Connection timestamp")

class SpotBalance(BaseModel):
    asset: str = Field(..., description="Asset symbol (e.g., BTC)")
    available: float = Field(..., description="Available balance")
    total: float = Field(..., description="Total balance")
    in_orders: float = Field(..., description="Balance in open orders")

class PerpBalance(BaseModel):
    account_value: float = Field(..., description="Total account value")
    margin_used: float = Field(..., description="Margin used for positions")
    position_value: float = Field(..., description="Total position value")

class BalancesResponse(BaseModel):
    spot: List[SpotBalance] = Field(..., description="List of spot balances")
    perp: PerpBalance = Field(..., description="Perpetual trading balances")

class OpenOrder(BaseModel):
    symbol: str = Field(..., description="Trading pair symbol (e.g., BTC)")
    order_id: int = Field(..., description="Unique order ID")
    side: str = Field(..., description="Order side (buy or sell)")
    order_type: str = Field(..., description="Order type (market or limit)")
    price: Optional[float] = Field(None, description="Order price (for limit orders)")
    quantity: float = Field(..., description="Order quantity")
    filled: float = Field(..., description="Amount already filled")
    remaining: float = Field(..., description="Amount remaining to be filled")
    status: str = Field(..., description="Order status (open, filled, cancelled, etc.)")
    created_at: str = Field(..., description="Order creation timestamp")

class OpenOrdersResponse(BaseModel):
    orders: List[OpenOrder] = Field(..., description="List of open orders")

# API Endpoints
@app.get("/")
async def root():
    """Health check endpoint"""
    return {"status": "online", "message": "Elysium Trading Platform API"}

@app.post("/connect", response_model=Dict[str, str])
async def connect(request: ConnectionRequest):
    """
    Connect to either mainnet or testnet of the exchange.
    
    For both mainnet and testnet:
    - Requires wallet credentials (wallet_address and secret_key)
    
    ⚠️ Security Note: Never share your secret_key with anyone!
    """
    try:
        success = api_connector.connect_hyperliquid(
            wallet_address=request.credentials.wallet_address,
            secret_key=request.credentials.secret_key,
            use_testnet=(request.network == "testnet")
        )
        
        if success:
            # Set up the OrderHandler with the exchange and API connector
            order_handler.set_exchange(
                exchange=api_connector.exchange,
                info=api_connector.info,
                api_connector=api_connector
            )
            order_handler.wallet_address = request.credentials.wallet_address
            
            return {"status": "success", "message": f"Connected to {request.network}"}
        raise HTTPException(status_code=400, detail="Connection failed")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/balances", response_model=BalancesResponse)
async def get_balances():
    """Get both spot and perpetual trading balances"""
    try:
        if not api_connector.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to exchange")
        
        balances = api_connector.get_balances()
        
        spot_balances = [
            SpotBalance(
                asset=balance["asset"],
                available=balance["available"],
                total=balance["total"],
                in_orders=balance["in_orders"]
            )
            for balance in balances["spot"]
        ]
        
        perp_balance = PerpBalance(
            account_value=balances["perp"]["account_value"],
            margin_used=balances["perp"]["margin_used"],
            position_value=balances["perp"]["position_value"]
        )
        
        return BalancesResponse(spot=spot_balances, perp=perp_balance)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/open-orders", response_model=OpenOrdersResponse)
async def get_open_orders(symbol: Optional[str] = None):
    """
    Get all open orders, optionally filtered by symbol.
    
    Args:
        symbol: Optional trading pair symbol to filter orders (e.g., "BTC")
        
    Returns:
        List of open orders with their details
    """
    try:
        if not api_connector.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to exchange")
        
        response = order_handler.get_open_orders(symbol)
        
        # Check if the response is an error
        if isinstance(response, dict) and response.get("status") == "error":
            raise HTTPException(
                status_code=500,
                detail=f"Error fetching orders: {response.get('message', 'Unknown error')}"
            )
        
        # Extract orders from the response
        orders = []
        if isinstance(response, dict):
            # Handle the case where orders are in a specific key
            if "orders" in response:
                orders = response["orders"]
            elif "data" in response and "orders" in response["data"]:
                orders = response["data"]["orders"]
            else:
                # If the response is a single order, wrap it in a list
                orders = [response] if response else []
        
        # Convert the orders to our Pydantic model format with safe access
        formatted_orders = []
        for order in orders:
            try:
                # Ensure order is a dictionary
                if not isinstance(order, dict):
                    continue
                    
                formatted_order = OpenOrder(
                    symbol=str(order.get("symbol", "")),
                    order_id=int(order.get("order_id", 0)),
                    side=str(order.get("side", "")),
                    order_type=str(order.get("order_type", "")),
                    price=float(order.get("price")) if order.get("price") is not None else None,
                    quantity=float(order.get("quantity", 0)),
                    filled=float(order.get("filled", 0)),
                    remaining=float(order.get("remaining", 0)),
                    status=str(order.get("status", "")),
                    created_at=str(order.get("created_at", ""))
                )
                formatted_orders.append(formatted_order)
            except (ValueError, TypeError) as e:
                # Log the error but continue processing other orders
                logger.error(f"Error formatting order: {e}")
                continue
        
        return OpenOrdersResponse(orders=formatted_orders)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching open orders: {str(e)}"
        )

if __name__ == "__main__":
    try:
        logger.info("Starting Elysium Trading Platform API")
        logger.info("Server will be available at http://0.0.0.0:8000")
        logger.info("API documentation available at http://0.0.0.0:8000/docs")
        
        # Run the server with more stable settings
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=8000,
            reload=False,  # Disable auto-reload for stability
            log_level="info",
            workers=1  # Use single worker for stability
        )
    except Exception as e:
        logger.error(f"Server crashed: {str(e)}")
        raise 