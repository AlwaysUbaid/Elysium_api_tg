import logging
import requests
import json
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler

# Import API URLs
from api_urls import (
    DEFAULT_ENDPOINTS, 
    SPOT_ENDPOINTS, 
    PERP_ENDPOINTS, 
    SCALED_ENDPOINTS,
    create_connection_payload
)

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token (replace with your actual token)
TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# Store user session data
user_sessions = {}

# Bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_text(
        f"Welcome to Elysium Trading Bot, {user.first_name}! 🚀\n\n"
        "Use /connect to connect to the trading platform\n"
        "Use /help to see available commands"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = (
        "🤖 *Elysium Trading Bot Commands* 🤖\n\n"
        "*Basic Commands:*\n"
        "/start - Start the bot\n"
        "/connect - Connect to trading platform\n"
        "/balance - View your balances\n"
        "/orders - View open orders\n\n"
        
        "*Spot Trading:*\n"
        "/spot_buy - Market buy\n"
        "/spot_sell - Market sell\n"
        "/spot_limit_buy - Limit buy\n"
        "/spot_limit_sell - Limit sell\n"
        "/cancel_order - Cancel specific order\n"
        "/cancel_all - Cancel all orders\n\n"
        
        "*Perpetual Trading:*\n"
        "/perp_buy - Perp market buy\n"
        "/perp_sell - Perp market sell\n"
        "/perp_limit_buy - Perp limit buy\n"
        "/perp_limit_sell - Perp limit sell\n"
        "/close_position - Close position\n"
        "/set_leverage - Set leverage\n\n"
        
        "*Scaled Orders:*\n"
        "/scaled_orders - Create scaled orders\n"
        "/perp_scaled_orders - Create perp scaled orders\n"
        "/market_aware_buy - Market-aware scaled buy\n"
        "/market_aware_sell - Market-aware scaled sell"
    )
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Connect to Elysium Trading Platform."""
    user_id = update.effective_user.id
    
    # Check if arguments provided (wallet and key)
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Please provide your wallet address and secret key like this:\n"
            "/connect wallet_address secret_key [testnet|mainnet]"
        )
        return
    
    wallet_address = context.args[0]
    secret_key = context.args[1]
    network = context.args[2] if len(context.args) > 2 else "testnet"
    
    if network not in ["testnet", "mainnet"]:
        network = "testnet"
    
    # Create connection payload
    payload = create_connection_payload(wallet_address, secret_key, network)
    
    try:
        # Send connection request to API
        response = requests.post(DEFAULT_ENDPOINTS["connect"], json=payload)
        response_data = response.json()
        
        if response.status_code == 200 and response_data.get("status") == "success":
            # Store user session data
            user_sessions[user_id] = {
                "connected": True,
                "wallet_address": wallet_address,
                "network": network
            }
            
            await update.message.reply_text(
                f"✅ Successfully connected to {network}!"
            )
        else:
            await update.message.reply_text(
                f"❌ Connection failed: {response_data.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Error connecting to API: {str(e)}")
        await update.message.reply_text(f"❌ Error connecting to API: {str(e)}")

async def check_balances(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check user balances."""
    user_id = update.effective_user.id
    
    # Check if user is connected
    if user_id not in user_sessions or not user_sessions[user_id].get("connected"):
        await update.message.reply_text("⚠️ You are not connected. Use /connect first.")
        return
    
    try:
        # Send balance request to API
        response = requests.get(DEFAULT_ENDPOINTS["balances"])
        response_data = response.json()
        
        if response.status_code == 200:
            # Format balance data
            spot_balances = response_data.get("spot", [])
            perp_balance = response_data.get("perp", {})
            
            balance_text = "*Your Balances*\n\n"
            
            # Spot balances
            if spot_balances:
                balance_text += "*Spot Balances:*\n"
                for balance in spot_balances:
                    balance_text += f"• {balance['asset']}: {balance['available']} available, {balance['total']} total\n"
            else:
                balance_text += "*Spot Balances:* None\n"
            
            balance_text += "\n*Perpetual Balances:*\n"
            balance_text += f"• Account Value: {perp_balance.get('account_value', 0)}\n"
            balance_text += f"• Margin Used: {perp_balance.get('margin_used', 0)}\n"
            balance_text += f"• Position Value: {perp_balance.get('position_value', 0)}\n"
            
            await update.message.reply_text(balance_text, parse_mode='Markdown')
        else:
            await update.message.reply_text(
                f"❌ Failed to fetch balances: {response_data.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Error fetching balances: {str(e)}")
        await update.message.reply_text(f"❌ Error fetching balances: {str(e)}")

async def spot_market_buy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Execute a spot market buy."""
    user_id = update.effective_user.id
    
    # Check if user is connected
    if user_id not in user_sessions or not user_sessions[user_id].get("connected"):
        await update.message.reply_text("⚠️ You are not connected. Use /connect first.")
        return
    
    # Check if arguments provided
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Please provide symbol and quantity:\n"
            "/spot_buy BTC 0.01"
        )
        return
    
    symbol = context.args[0].upper()
    quantity = context.args[1]
    
    try:
        # Create request payload
        payload = {
            "symbol": symbol,
            "quantity": float(quantity)
        }
        
        # Send market buy request to API
        response = requests.post(SPOT_ENDPOINTS["market_buy"], json=payload)
        response_data = response.json()
        
        if response.status_code == 200:
            await update.message.reply_text(
                f"✅ Market buy order placed successfully!\n"
                f"Symbol: {symbol}\n"
                f"Quantity: {quantity}"
            )
        else:
            await update.message.reply_text(
                f"❌ Failed to place order: {response_data.get('detail', 'Unknown error')}"
            )
    except Exception as e:
        logger.error(f"Error placing market buy: {str(e)}")
        await update.message.reply_text(f"❌ Error placing market buy: {str(e)}")

# Main function to start the bot
def main() -> None:
    """Start the bot."""
    # Create the Application
    application = ApplicationBuilder().token(TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("connect", connect))
    application.add_handler(CommandHandler("balance", check_balances))
    application.add_handler(CommandHandler("spot_buy", spot_market_buy))
    
    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main() 