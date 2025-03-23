# Elysium Trading Platform

A modular, extensible trading platform for Hyperliquid exchange supporting multiple order types, strategies, and interfaces.

## Features

- Connect to Hyperliquid exchange (both mainnet and testnet)
- Multiple order types:
  - Spot and perpetual market/limit orders
  - Scaled orders across price ranges
  - Time-Weighted Average Price (TWAP) execution
  - Grid trading strategies
- Interactive terminal UI
- Telegram bot interface
- Trading strategy framework

## Project Structure

The project is organized into several modules to enhance maintainability and extensibility:

```
elysium/
├── api/                  # API connectivity
│   ├── __init__.py
│   ├── api_connector.py  # Connect to exchange API
│   └── constants.py      # API URLs and constants
├── core/                 # Core functionality
│   ├── __init__.py
│   ├── config_manager.py # Handle configuration
│   └── utils.py          # Utility functions
├── order_execution/      # Order execution strategies
│   ├── __init__.py
│   ├── simple_orders.py  # Basic spot and perp orders
│   ├── scaled_orders.py  # Scaled order strategies
│   ├── twap_orders.py    # TWAP order execution
│   └── grid_trading.py   # Grid trading functionality
├── strategies/           # Trading strategies
│   ├── __init__.py
│   ├── strategy_selector.py   # Strategy selection system
│   └── pure_mm.py        # Pure market making strategy
├── ui/                   # User interfaces
│   ├── __init__.py
│   ├── terminal_ui.py    # CLI interface
│   └── telegram_bot.py   # Telegram bot interface
├── elysium.py            # Main entry point
├── order_handler.py      # Order coordination
└── README.md             # Project documentation
```

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/elysium.git
   cd elysium
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. For Telegram bot functionality (optional):
   ```
   pip install python-telegram-bot==13.7 urllib3==1.26.15 httpx==0.23.0
   ```

## Configuration

Create a file named `dontshareconfig.py` with your API keys:

```python
# Mainnet credentials
mainnet_wallet = "YOUR_MAINNET_WALLET_ADDRESS"
mainnet_secret = "YOUR_MAINNET_SECRET_KEY"

# Testnet credentials (optional)
testnet_wallet = "YOUR_TESTNET_WALLET_ADDRESS"
testnet_secret = "YOUR_TESTNET_SECRET_KEY"

# Telegram bot configuration (optional)
telegram_token = "YOUR_TELEGRAM_BOT_TOKEN"
telegram_admin_ids = [YOUR_TELEGRAM_USER_ID]
```

## Usage

### Running the Terminal UI

```
python elysium.py
```

Options:
- `-t, --testnet`: Connect to testnet instead of mainnet
- `-v, --verbose`: Enable verbose logging
- `--log-file PATH`: Specify a log file
- `--no-telegram`: Disable Telegram bot
- `--telegram-only`: Run only the Telegram bot (no terminal UI)

### Terminal UI Commands

Basic commands:
- `connect [mainnet|testnet]`: Connect to Hyperliquid exchange
- `balance`: Show account balance
- `positions`: Show open positions
- `orders`: List open orders
- `cancel <symbol> <order_id>`: Cancel a specific order
- `cancel_all [symbol]`: Cancel all orders, optionally for a specific symbol

Simple orders:
- `buy <symbol> <size> [slippage]`: Execute a market buy order
- `sell <symbol> <size> [slippage]`: Execute a market sell order
- `limit_buy <symbol> <size> <price>`: Place a limit buy order
- `limit_sell <symbol> <size> <price>`: Place a limit sell order

Perpetual orders:
- `perp_buy <symbol> <size> [leverage] [slippage]`: Execute a perpetual market buy
- `perp_sell <symbol> <size> [leverage] [slippage]`: Execute a perpetual market sell
- `perp_limit_buy <symbol> <size> <price> [leverage]`: Place a perpetual limit buy
- `perp_limit_sell <symbol> <size> <price> [leverage]`: Place a perpetual limit sell
- `close_position <symbol> [slippage]`: Close a position
- `set_leverage <symbol> <leverage>`: Set leverage for a symbol

Scaled orders:
- `scaled_buy <symbol> <total> <num> <start> <end> [skew]`: Place multiple buy orders
- `scaled_sell <symbol> <total> <num> <start> <end> [skew]`: Place multiple sell orders
- `market_scaled_buy <symbol> <total> <num> [percent] [skew]`: Place market-aware buy orders
- `market_scaled_sell <symbol> <total> <num> [percent] [skew]`: Place market-aware sell orders

Grid trading:
- `grid_create <symbol> <upper> <lower> <num> <investment> [is_perp] [leverage] [tp] [sl]`: Create grid
- `grid_start <grid_id>`: Start a grid strategy
- `grid_stop <grid_id>`: Stop a grid strategy
- `grid_status <grid_id>`: Check grid status
- `grid_list`: List all grid strategies
- `grid_stop_all`: Stop all active grid strategies
- `grid_clean`: Clean up completed grid strategies

TWAP execution:
- `twap_create <symbol> <side> <quantity> <duration> <slices> [price] [is_perp] [leverage]`: Create TWAP
- `twap_start <twap_id>`: Start TWAP execution
- `twap_stop <twap_id>`: Stop TWAP execution
- `twap_status <twap_id>`: Check TWAP status
- `twap_list`: List all TWAP executions
- `twap_stop_all`: Stop all active TWAP executions

### Telegram Bot Commands

- `/start`: Start the bot
- `/help`: Show help menu
- `/connect`: Connect to the exchange
- `/status`: Show connection status
- `/balance`: Show account balance
- `/positions`: Show positions
- `/orders`: Show open orders
- `/price <symbol>`: Check price
- `/trade`: Start trading dialog
- `/menu`: Show commands menu

## Trading Strategies

The platform includes a strategy framework that allows you to create and run custom strategies:

- Pure Market Making: Places buy and sell orders around the mid price to capture the spread

To implement your own strategy:
1. Create a new file in the `strategies` directory
2. Inherit from `TradingStrategy` class
3. Implement the required methods

## License

[MIT License](LICENSE)

## Disclaimer

This software is for educational purposes only. Use at your own risk. Trading cryptocurrency carries significant financial risk.

# Elysium Trading Platform Telegram Bot

A Telegram bot for interacting with the Elysium Trading Platform API.

## Features

- Connect to Elysium Trading Platform (mainnet or testnet)
- Check account balances (spot and perpetual)
- View open orders
- Execute trades:
  - Spot market and limit orders
  - Perpetual market and limit orders
  - Advanced scaled orders

## Prerequisites

- Python 3.9+
- Elysium Trading Platform API running locally or hosted somewhere
- Telegram Bot Token (obtained from [@BotFather](https://t.me/botfather))

## Installation

1. Clone this repository or download the files
2. Install required packages:

```bash
pip install python-telegram-bot requests
```

3. Update the `TOKEN` variable in `tg_bot_example.py` with your Telegram bot token
4. Update the `BASE_URL` in `api_urls.py` if your API is not running on the default `http://0.0.0.0:8000`

## Usage

1. Start the Elysium Trading Platform API:

```bash
python main.py
```

2. Start the Telegram bot:

```bash
python tg_bot_example.py
```

3. Open your Telegram app and start a conversation with your bot
4. Use `/connect` command with your wallet credentials to establish a connection:

```
/connect your_wallet_address your_secret_key [testnet|mainnet]
```

## Available Commands

### Basic Commands
- `/start` - Start the bot
- `/help` - Show available commands
- `/connect` - Connect to the trading platform
- `/balance` - View your balances
- `/orders` - View open orders

### Spot Trading Commands
- `/spot_buy [symbol] [quantity]` - Execute a spot market buy
- `/spot_sell [symbol] [quantity]` - Execute a spot market sell
- `/spot_limit_buy [symbol] [quantity] [price]` - Place a spot limit buy
- `/spot_limit_sell [symbol] [quantity] [price]` - Place a spot limit sell
- `/cancel_order [order_id]` - Cancel a specific order
- `/cancel_all` - Cancel all open orders

### Perpetual Trading Commands
- `/perp_buy [symbol] [quantity]` - Execute a perpetual market buy
- `/perp_sell [symbol] [quantity]` - Execute a perpetual market sell
- `/perp_limit_buy [symbol] [quantity] [price]` - Place a perpetual limit buy
- `/perp_limit_sell [symbol] [quantity] [price]` - Place a perpetual limit sell
- `/close_position [symbol]` - Close a perpetual position
- `/set_leverage [symbol] [leverage]` - Set leverage for a symbol

### Scaled Order Commands
- `/scaled_orders` - Create scaled orders
- `/perp_scaled_orders` - Create perpetual scaled orders
- `/market_aware_buy` - Create market-aware scaled buy orders
- `/market_aware_sell` - Create market-aware scaled sell orders

## Security Notice

- Never share your private keys
- The bot stores credentials in memory only
- Consider implementing more secure authentication for production use

## API Structure

The Elysium Trading Platform API is organized in the following categories:

1. Default - Basic account and connection APIs
2. Spot - Spot trading APIs
3. Perp - Perpetual trading APIs
4. Scaled - Advanced scaling order APIs

## Extending the Bot

To add more functionality:

1. Add new command handlers in `tg_bot_example.py`
2. Use the appropriate endpoints from `api_urls.py`
3. Follow the pattern of existing command handlers