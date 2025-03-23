"""
Elysium Trading Platform API URLs
Organized in the requested order:
1. Default
2. Spot
3. Perp
4. Scaled
"""

# Base URL (when running locally)
BASE_URL = "http://0.0.0.0:8000"

# 1. Default API Endpoints
DEFAULT_ENDPOINTS = {
    "root": f"{BASE_URL}/",
    "connect": f"{BASE_URL}/connect",
    "balances": f"{BASE_URL}/balances",
    "open_orders": f"{BASE_URL}/open-orders"
}

# 2. Spot API Endpoints
SPOT_ENDPOINTS = {
    "market_buy": f"{BASE_URL}/api/v1/spot/market-buy",
    "market_sell": f"{BASE_URL}/api/v1/spot/market-sell",
    "limit_buy": f"{BASE_URL}/api/v1/spot/limit-buy",
    "limit_sell": f"{BASE_URL}/api/v1/spot/limit-sell",
    "cancel_order": f"{BASE_URL}/api/v1/spot/cancel-order",
    "cancel_all_orders": f"{BASE_URL}/api/v1/spot/cancel-all-orders"
}

# 3. Perpetual Trading API Endpoints
PERP_ENDPOINTS = {
    "market_buy": f"{BASE_URL}/api/v1/perp/market-buy",
    "market_sell": f"{BASE_URL}/api/v1/perp/market-sell",
    "limit_buy": f"{BASE_URL}/api/v1/perp/limit-buy",
    "limit_sell": f"{BASE_URL}/api/v1/perp/limit-sell",
    "close_position": f"{BASE_URL}/api/v1/perp/close-position",
    "set_leverage": f"{BASE_URL}/api/v1/perp/set-leverage"
}

# 4. Scaled Order API Endpoints
SCALED_ENDPOINTS = {
    "scaled_orders": f"{BASE_URL}/api/v1/scaled/scaled-orders",
    "perp_scaled_orders": f"{BASE_URL}/api/v1/scaled/perp-scaled-orders",
    "market_aware_scaled_buy": f"{BASE_URL}/api/v1/scaled/market-aware-scaled-buy",
    "market_aware_scaled_sell": f"{BASE_URL}/api/v1/scaled/market-aware-scaled-sell"
}

# Helper function to get all endpoints as a flat dictionary
def get_all_endpoints():
    """Return all endpoints as a single dictionary"""
    all_endpoints = {}
    all_endpoints.update(DEFAULT_ENDPOINTS)
    all_endpoints.update(SPOT_ENDPOINTS)
    all_endpoints.update(PERP_ENDPOINTS)
    all_endpoints.update(SCALED_ENDPOINTS)
    return all_endpoints

# Helper function for creating a connection request payload
def create_connection_payload(wallet_address, secret_key, network="testnet"):
    """
    Create a properly formatted connection request payload
    
    Args:
        wallet_address: Ethereum wallet address
        secret_key: Wallet's private key
        network: 'testnet' or 'mainnet'
        
    Returns:
        Dict with properly formatted connection payload
    """
    return {
        "network": network,
        "credentials": {
            "wallet_address": wallet_address,
            "secret_key": secret_key
        }
    }
