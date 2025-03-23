from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, validator, confloat, conint

from order_handler import OrderHandler
from api.api_connector import ApiConnector

router = APIRouter(prefix="/api/v1/perp", tags=["perp"])

# Constants for validation
MIN_ORDER_SIZE = 0.0001
MAX_ORDER_SIZE = 1000.0
MIN_PRICE = 0.0001
MAX_PRICE = 1000000.0
MIN_SLIPPAGE = 0.0
MAX_SLIPPAGE = 1.0
MIN_LEVERAGE = 1
MAX_LEVERAGE = 100

# Shared instances
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
    
    network = "testnet" if api_connector.is_testnet() else "mainnet"
    
    if not order_handler.exchange or not order_handler.info:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": f"Order handler not configured for {network}. Please reconnect.",
                "required_action": "Call POST /connect again to reconfigure the order handler",
                "current_network": network
            }
        )
    
    if not order_handler.wallet_address:
        raise HTTPException(
            status_code=400,
            detail={
                "status": "error",
                "message": "Wallet address not set. Please reconnect.",
                "required_action": "Call POST /connect again to set the wallet address",
                "current_network": network
            }
        )
    
    return network

def create_order_response(result: Dict[str, Any], network: str, message: str) -> Dict[str, Any]:
    """Create a standardized order response"""
    return {
        "success": True,
        "message": message,
        "data": {
            **result,
            "network": network
        }
    }

# Base request model with common symbol validation
class BaseRequest(BaseModel):
    symbol: str = Field(
        ..., 
        description="Trading pair symbol (can be any arbitrary value)",
        example="BTC-PERP"
    )

    @validator('symbol')
    def validate_symbol(cls, v):
        if not v or not isinstance(v, str):
            raise ValueError('Symbol must be a non-empty string')
        return v

# Request Models
class MarketOrderRequest(BaseRequest):
    size: confloat(gt=MIN_ORDER_SIZE, le=MAX_ORDER_SIZE) = Field(
        ..., 
        description=f"Order size (between {MIN_ORDER_SIZE} and {MAX_ORDER_SIZE})",
        example=0.1
    )
    leverage: conint(ge=MIN_LEVERAGE, le=MAX_LEVERAGE) = Field(
        default=1,
        description=f"Leverage to use (between {MIN_LEVERAGE} and {MAX_LEVERAGE})",
        example=1
    )
    slippage: confloat(ge=MIN_SLIPPAGE, le=MAX_SLIPPAGE) = Field(
        default=0.05, 
        description=f"Maximum allowed slippage (between {MIN_SLIPPAGE} and {MAX_SLIPPAGE})",
        example=0.05
    )

class LimitOrderRequest(BaseRequest):
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
    leverage: conint(ge=MIN_LEVERAGE, le=MAX_LEVERAGE) = Field(
        default=1,
        description=f"Leverage to use (between {MIN_LEVERAGE} and {MAX_LEVERAGE})",
        example=1
    )

class ClosePositionRequest(BaseRequest):
    slippage: confloat(ge=MIN_SLIPPAGE, le=MAX_SLIPPAGE) = Field(
        default=0.05, 
        description=f"Maximum allowed slippage (between {MIN_SLIPPAGE} and {MAX_SLIPPAGE})",
        example=0.05
    )

class SetLeverageRequest(BaseRequest):
    leverage: conint(ge=MIN_LEVERAGE, le=MAX_LEVERAGE) = Field(
        ..., 
        description=f"Leverage to set (between {MIN_LEVERAGE} and {MAX_LEVERAGE})",
        example=1
    )

# Response Model
class OrderResponse(BaseModel):
    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional response data")

@router.post("/market-buy", response_model=OrderResponse)
async def perp_market_buy(request: MarketOrderRequest):
    """Execute a perpetual market buy order"""
    try:
        network = check_connection()
        result = order_handler.perp_market_buy(
            symbol=request.symbol,
            size=request.size,
            leverage=request.leverage,
            slippage=request.slippage
        )
        return OrderResponse(**create_order_response(
            result, 
            network, 
            f"Perpetual market buy order executed successfully on {network}"
        ))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/market-sell", response_model=OrderResponse)
async def perp_market_sell(request: MarketOrderRequest):
    """Execute a perpetual market sell order"""
    try:
        network = check_connection()
        result = order_handler.perp_market_sell(
            symbol=request.symbol,
            size=request.size,
            leverage=request.leverage,
            slippage=request.slippage
        )
        return OrderResponse(**create_order_response(
            result, 
            network, 
            f"Perpetual market sell order executed successfully on {network}"
        ))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/limit-buy", response_model=OrderResponse)
async def perp_limit_buy(request: LimitOrderRequest):
    """Place a perpetual limit buy order"""
    try:
        network = check_connection()
        result = order_handler.perp_limit_buy(
            symbol=request.symbol,
            size=request.size,
            price=request.price,
            leverage=request.leverage
        )
        return OrderResponse(**create_order_response(
            result, 
            network, 
            f"Perpetual limit buy order placed successfully on {network}"
        ))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/limit-sell", response_model=OrderResponse)
async def perp_limit_sell(request: LimitOrderRequest):
    """Place a perpetual limit sell order"""
    try:
        network = check_connection()
        result = order_handler.perp_limit_sell(
            symbol=request.symbol,
            size=request.size,
            price=request.price,
            leverage=request.leverage
        )
        return OrderResponse(**create_order_response(
            result, 
            network, 
            f"Perpetual limit sell order placed successfully on {network}"
        ))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/close-position", response_model=OrderResponse)
async def close_position(request: ClosePositionRequest):
    """Close an entire position for a symbol"""
    try:
        network = check_connection()
        result = order_handler.close_position(
            symbol=request.symbol,
            slippage=request.slippage
        )
        return OrderResponse(**create_order_response(
            result, 
            network, 
            f"Position closed successfully on {network}"
        ))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/set-leverage", response_model=OrderResponse)
async def set_leverage(request: SetLeverageRequest):
    """Set leverage for a symbol"""
    try:
        network = check_connection()
        result = order_handler._set_leverage(
            symbol=request.symbol,
            leverage=request.leverage
        )
        return OrderResponse(**create_order_response(
            result, 
            network, 
            f"Leverage set successfully on {network}"
        ))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) 