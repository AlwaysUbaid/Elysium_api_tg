from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator, confloat, conint
import re

from order_handler import OrderHandler
from api.api_connector import ApiConnector

router = APIRouter(prefix="/api/v1/scaled", tags=["scaled"])

# Constants for validation
MIN_ORDER_SIZE = 0.0001
MAX_ORDER_SIZE = 1000.0
MIN_PRICE = 0.0001
MAX_PRICE = 1000000.0
MIN_LEVERAGE = 1
MAX_LEVERAGE = 100
MIN_NUM_ORDERS = 1
MAX_NUM_ORDERS = 100
MIN_SKEW = -1.0
MAX_SKEW = 1.0

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
class ScaledOrdersRequest(BaseModel):
    symbol: str = Field(
        ..., 
        description="Trading pair symbol (e.g., 'BTC/USDT', 'ETH/USDC', 'SOL/BTC', etc.)",
        example="BTC/USDT"
    )
    is_buy: bool = Field(
        ...,
        description="True for buy orders, False for sell orders",
        example=True
    )
    total_size: confloat(gt=MIN_ORDER_SIZE, le=MAX_ORDER_SIZE) = Field(
        ...,
        description=f"Total order size (between {MIN_ORDER_SIZE} and {MAX_ORDER_SIZE})",
        example=0.1
    )
    num_orders: conint(ge=MIN_NUM_ORDERS, le=MAX_NUM_ORDERS) = Field(
        ...,
        description=f"Number of orders to place (between {MIN_NUM_ORDERS} and {MAX_NUM_ORDERS})",
        example=5
    )
    start_price: confloat(gt=MIN_PRICE, le=MAX_PRICE) = Field(
        ...,
        description=f"Starting price for the order range (between {MIN_PRICE} and {MAX_PRICE})",
        example=50000.0
    )
    end_price: confloat(gt=MIN_PRICE, le=MAX_PRICE) = Field(
        ...,
        description=f"Ending price for the order range (between {MIN_PRICE} and {MAX_PRICE})",
        example=51000.0
    )
    skew: confloat(ge=MIN_SKEW, le=MAX_SKEW) = Field(
        default=0.0,
        description=f"Order size skew factor (between {MIN_SKEW} and {MAX_SKEW})",
        example=0.0
    )
    reduce_only: bool = Field(
        default=False,
        description="Whether orders should only reduce positions",
        example=False
    )
    check_market: bool = Field(
        default=True,
        description="Whether to check market conditions before placing orders",
        example=True
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        # Accept any valid trading pair format
        if not re.match(r'^[A-Z0-9]+/[A-Z0-9]+$', v):
            raise ValueError('Invalid trading pair format. Use format like "BTC/USDT" or "ETH/USDC"')
        return v

class PerpScaledOrdersRequest(ScaledOrdersRequest):
    leverage: conint(ge=MIN_LEVERAGE, le=MAX_LEVERAGE) = Field(
        default=1,
        description=f"Leverage to use (between {MIN_LEVERAGE} and {MAX_LEVERAGE})",
        example=1
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        # Accept any symbol format
        return v

class MarketAwareScaledRequest(BaseModel):
    symbol: str = Field(
        ..., 
        description="Trading pair symbol (e.g., 'BTC/USDT', 'ETH/USDC', 'SOL/BTC', etc.)",
        example="BTC/USDT"
    )
    total_size: confloat(gt=MIN_ORDER_SIZE, le=MAX_ORDER_SIZE) = Field(
        ...,
        description=f"Total order size (between {MIN_ORDER_SIZE} and {MAX_ORDER_SIZE})",
        example=0.1
    )
    num_orders: conint(ge=MIN_NUM_ORDERS, le=MAX_NUM_ORDERS) = Field(
        ...,
        description=f"Number of orders to place (between {MIN_NUM_ORDERS} and {MAX_NUM_ORDERS})",
        example=5
    )
    price_percent: confloat(gt=0.0, le=100.0) = Field(
        default=3.0,
        description="Price range as percentage of current market price",
        example=3.0
    )
    skew: confloat(ge=MIN_SKEW, le=MAX_SKEW) = Field(
        default=0.0,
        description=f"Order size skew factor (between {MIN_SKEW} and {MAX_SKEW})",
        example=0.0
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        # Accept any symbol format
        return v

# Response Models
class OrderResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")

@router.post("/scaled-orders", response_model=OrderResponse)
async def scaled_orders(request: ScaledOrdersRequest):
    """
    Place multiple orders across a price range with an optional skew
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - is_buy: True for buy orders, False for sell orders
    - total_size: Total order size (0.0001-1000)
    - num_orders: Number of orders to place (1-100)
    - start_price: Starting price for the order range (0.0001-1000000)
    - end_price: Ending price for the order range (0.0001-1000000)
    - skew: Order size skew factor (-1.0 to 1.0)
    - reduce_only: Whether orders should only reduce positions
    - check_market: Whether to check market conditions before placing orders
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.scaled_orders(
            symbol=request.symbol,
            is_buy=request.is_buy,
            total_size=request.total_size,
            num_orders=request.num_orders,
            start_price=request.start_price,
            end_price=request.end_price,
            skew=request.skew,
            reduce_only=request.reduce_only,
            check_market=request.check_market
        )
        return OrderResponse(
            success=True,
            message=f"Scaled orders placed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/perp-scaled-orders", response_model=OrderResponse)
async def perp_scaled_orders(request: PerpScaledOrdersRequest):
    """
    Place multiple perpetual orders across a price range with an optional skew
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - is_buy: True for buy orders, False for sell orders
    - total_size: Total order size (0.0001-1000)
    - num_orders: Number of orders to place (1-100)
    - start_price: Starting price for the order range (0.0001-1000000)
    - end_price: Ending price for the order range (0.0001-1000000)
    - leverage: Leverage to use (1-100)
    - skew: Order size skew factor (-1.0 to 1.0)
    - reduce_only: Whether orders should only reduce positions
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.perp_scaled_orders(
            symbol=request.symbol,
            is_buy=request.is_buy,
            total_size=request.total_size,
            num_orders=request.num_orders,
            start_price=request.start_price,
            end_price=request.end_price,
            leverage=request.leverage,
            skew=request.skew,
            reduce_only=request.reduce_only
        )
        return OrderResponse(
            success=True,
            message=f"Perpetual scaled orders placed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/market-aware-scaled-buy", response_model=OrderResponse)
async def market_aware_scaled_buy(request: MarketAwareScaledRequest):
    """
    Place multiple buy orders across a price range with market awareness
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - total_size: Total order size (0.0001-1000)
    - num_orders: Number of orders to place (1-100)
    - price_percent: Price range as percentage of current market price
    - skew: Order size skew factor (-1.0 to 1.0)
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.market_aware_scaled_buy(
            symbol=request.symbol,
            total_size=request.total_size,
            num_orders=request.num_orders,
            price_percent=request.price_percent,
            skew=request.skew
        )
        return OrderResponse(
            success=True,
            message=f"Market-aware scaled buy orders placed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/market-aware-scaled-sell", response_model=OrderResponse)
async def market_aware_scaled_sell(request: MarketAwareScaledRequest):
    """
    Place multiple sell orders across a price range with market awareness
    
    Parameters:
    - symbol: Trading pair (e.g., 'BTC/USDT')
    - total_size: Total order size (0.0001-1000)
    - num_orders: Number of orders to place (1-100)
    - price_percent: Price range as percentage of current market price
    - skew: Order size skew factor (-1.0 to 1.0)
    """
    try:
        check_connection()
        network = "testnet" if api_connector.is_testnet() else "mainnet"
        result = order_handler.market_aware_scaled_sell(
            symbol=request.symbol,
            total_size=request.total_size,
            num_orders=request.num_orders,
            price_percent=request.price_percent,
            skew=request.skew
        )
        return OrderResponse(
            success=True,
            message=f"Market-aware scaled sell orders placed successfully on {network}",
            data={
                **result,
                "network": network
            }
        )
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 