from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator, confloat, constr
import re

from order_handler import OrderHandler
from api.api_connector import ApiConnector

router = APIRouter(prefix="/api/v1/spot", tags=["spot"])

# Constants for validation
MIN_ORDER_SIZE = 0.0001
MAX_ORDER_SIZE = 1000.0
MIN_PRICE = 0.0001
MAX_PRICE = 1000000.0
MIN_SLIPPAGE = 0.0
MAX_SLIPPAGE = 1.0

# These will be set by main.py
api_connector = None
order_handler = None

def set_instances(connector: ApiConnector, handler: OrderHandler):
    """Set the shared instances from main.py"""
    global api_connector, order_handler
    api_connector = connector
    order_handler = handler

def check_connection():
    """Check if connected to exchange and raise appropriate error if not"""
    if not api_connector.is_connected():
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": "Not connected to exchange. Please connect first using the /connect endpoint",
                "required_action": "Call POST /connect with your wallet credentials first",
                "current_network": api_connector.is_testnet() and "testnet" or "mainnet"
            }
        )
    
    # Ensure order handler is properly configured for current network
    if not order_handler.exchange or not order_handler.info:
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": f"Order handler not configured for {network}. Please reconnect.",
                "required_action": "Call POST /connect again to reconfigure the order handler",
                "current_network": network
            }
        )
    
    # Ensure wallet address is set
    if not order_handler.wallet_address:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": "Wallet address not set. Please reconnect.",
                "required_action": "Call POST /connect again to set the wallet address",
                "current_network": api_connector.is_testnet() and "testnet" or "mainnet"
            }
        )

# Request Models
class MarketOrderRequest(BaseModel):
    symbol: str = Field(
        ..., 
        description="Trading pair symbol (e.g., 'BTC/USDT')",
        example="BTC/USDT"
    )
    size: confloat(gt=MIN_ORDER_SIZE, le=MAX_ORDER_SIZE) = Field(
        ..., 
        description=f"Order size (between {MIN_ORDER_SIZE} and {MAX_ORDER_SIZE})",
        example=0.1
    )
    slippage: confloat(ge=MIN_SLIPPAGE, le=MAX_SLIPPAGE) = Field(
        default=0.05, 
        description=f"Maximum allowed slippage (between {MIN_SLIPPAGE} and {MAX_SLIPPAGE})",
        example=0.05
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        # Additional validation for common trading pairs
        common_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT']
        if v not in common_pairs:
            # If not a common pair, validate the format
            if not re.match(r'^[A-Z0-9]+/[A-Z0-9]+$', v):
                raise ValueError('Invalid trading pair format. Use format like "BTC/USDT"')
        return v

class LimitOrderRequest(BaseModel):
    symbol: str = Field(
        ..., 
        description="Trading pair symbol (e.g., 'BTC/USDT')",
        example="BTC/USDT"
    )
    size: confloat(gt=MIN_ORDER_SIZE, le=MAX_ORDER_SIZE) = Field(
        ..., 
        description=f"Order size (between {MIN_ORDER_SIZE} and {MAX_ORDER_SIZE})",
        example=0.1
    )
    price: confloat(gt=MIN_PRICE, le=MAX_PRICE) = Field(
        ..., 
        description=f"Order price (between {MIN_PRICE} and {MAX_PRICE})",
        example=50000.0
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        # Additional validation for common trading pairs
        common_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT']
        if v not in common_pairs:
            # If not a common pair, validate the format
            if not re.match(r'^[A-Z0-9]+/[A-Z0-9]+$', v):
                raise ValueError('Invalid trading pair format. Use format like "BTC/USDT"')
        return v

class CancelOrderRequest(BaseModel):
    symbol: str = Field(
        ..., 
        description="Trading pair symbol (e.g., 'BTC/USDT')",
        example="BTC/USDT"
    )
    order_id: int = Field(
        ..., 
        description="Order ID to cancel",
        gt=0,
        example=123456
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        # Additional validation for common trading pairs
        common_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT']
        if v not in common_pairs:
            # If not a common pair, validate the format
            if not re.match(r'^[A-Z0-9]+/[A-Z0-9]+$', v):
                raise ValueError('Invalid trading pair format. Use format like "BTC/USDT"')
        return v

class CancelAllOrdersRequest(BaseModel):
    symbol: Optional[str] = Field(
        None, 
        description="Optional trading pair symbol to cancel orders for",
        example="BTC/USDT"
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        if v is not None:
            # Additional validation for common trading pairs
            common_pairs = ['BTC/USDT', 'ETH/USDT', 'BNB/USDT', 'XRP/USDT']
            if v not in common_pairs:
                # If not a common pair, validate the format
                if not re.match(r'^[A-Z0-9]+/[A-Z0-9]+$', v):
                    raise ValueError('Invalid trading pair format. Use format like "BTC/USDT"')
        return v

# Response Models
class OrderResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")

class CancelAllOrdersResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    cancelled_orders: Optional[int] = Field(None, description="Number of orders cancelled")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")

@router.post("/market-buy", response_model=OrderResponse)
async def market_buy(request: MarketOrderRequest):
    """
    Execute a market buy order
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - size: Order size (0.0001-1000)
    - slippage: Maximum allowed slippage (0-1)
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.market_buy(
            symbol=request.symbol,
            size=request.size,
            slippage=request.slippage
        )
        return OrderResponse(
            success=True,
            message=f"Market buy order executed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/market-sell", response_model=OrderResponse)
async def market_sell(request: MarketOrderRequest):
    """
    Execute a market sell order
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - size: Order size (0.0001-1000)
    - slippage: Maximum allowed slippage (0-1)
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.market_sell(
            symbol=request.symbol,
            size=request.size,
            slippage=request.slippage
        )
        return OrderResponse(
            success=True,
            message=f"Market sell order executed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/limit-buy", response_model=OrderResponse)
async def limit_buy(request: LimitOrderRequest):
    """
    Place a limit buy order
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - size: Order size (0.0001-1000)
    - price: Order price (0.0001-1000000)
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.limit_buy(
            symbol=request.symbol,
            size=request.size,
            price=request.price
        )
        return OrderResponse(
            success=True,
            message=f"Limit buy order placed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/limit-sell", response_model=OrderResponse)
async def limit_sell(request: LimitOrderRequest):
    """
    Place a limit sell order
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - size: Order size (0.0001-1000)
    - price: Order price (0.0001-1000000)
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.limit_sell(
            symbol=request.symbol,
            size=request.size,
            price=request.price
        )
        return OrderResponse(
            success=True,
            message=f"Limit sell order placed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cancel-order", response_model=OrderResponse)
async def cancel_order(request: CancelOrderRequest):
    """
    Cancel a specific order
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - order_id: Order ID to cancel (must be positive)
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.cancel_order(
            symbol=request.symbol,
            order_id=request.order_id
        )
        return OrderResponse(
            success=True,
            message=f"Order cancelled successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/cancel-all-orders", response_model=CancelAllOrdersResponse)
async def cancel_all_orders(request: CancelAllOrdersRequest):
    """
    Cancel all open orders, optionally filtered by symbol
    
    Parameters:
    - symbol: Optional trading pair to cancel orders for (e.g., 'BTC/USDT')
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.cancel_all_orders(symbol=request.symbol)
        return CancelAllOrdersResponse(
            success=True,
            message=f"All orders cancelled successfully on {network}",
            cancelled_orders=result.get("cancelled_orders"),
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 