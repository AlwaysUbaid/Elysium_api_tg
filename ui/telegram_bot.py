import os
import logging
import json
import time
import re
import threading
import queue
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

# Telegram imports
from telegram import Update, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, CallbackContext,
    Filters, CallbackQueryHandler, ConversationHandler
)

# States for conversation handlers
SELECTING_NETWORK, PASSWORD_AUTH, PASSWORD_SETUP, CONFIRM_PASSWORD = range(4)
SYMBOL, SIDE, AMOUNT, PRICE, CONFIRMATION = range(4, 9)

def notify_telegram_bot(bot, message, parse_mode=ParseMode.MARKDOWN):
    """
    Send a notification to all admin users of the bot
    
    Args:
        bot: The ElysiumTelegramBot instance
        message: Message to send
        parse_mode: Parsing mode for the message
    """
    if not bot or not hasattr(bot, 'admin_user_ids'):
        return
        
    for user_id in bot.admin_user_ids:
        try:
            if hasattr(bot, 'updater') and bot.updater and bot.updater.bot:
                bot.updater.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode=parse_mode
                )
        except Exception as e:
            logging.error(f"Error sending notification to {user_id}: {str(e)}")

class ElysiumTelegramBot:
    """Telegram bot for Elysium Trading Platform"""
    
    def __init__(self, api_connector, order_handler, config_manager, logger):
        self.api_connector = api_connector
        self.order_handler = order_handler
        self.config_manager = config_manager
        self.logger = logger
        
        # Bot state
        self.connected = False
        self.is_testnet = False
        self.authenticated_users = set()  # Track authenticated users
        self.connection_contexts = {}  # Store connection context per user
        self.trading_context = {}  # Store trading info per user
        
        # For thread safety and synchronization
        self.state_lock = threading.Lock()
        self.command_queue = queue.Queue()  # Queue for commands between CLI and Telegram
        
        # Initialize Telegram token
        try:
            import dontshareconfig as ds
            self.telegram_token = getattr(ds, 'telegram_token', None)
            self.admin_user_ids = getattr(ds, 'telegram_admin_ids', [])
        except ImportError:
            self.logger.warning("dontshareconfig.py not found. Telegram bot will use environment variables")
            self.telegram_token = os.environ.get('TELEGRAM_TOKEN')
            admin_ids_str = os.environ.get('ADMIN_USER_IDS', '')
            self.admin_user_ids = list(map(int, admin_ids_str.split(','))) if admin_ids_str else []
        
        if not self.telegram_token:
            self.logger.error("No Telegram token found! Telegram bot will not start.")
            return
        
        # Initialize Telegram updater
        self.updater = Updater(self.telegram_token)
        self.dispatcher = self.updater.dispatcher
        
        # Register handlers
        self._register_handlers()
        
        self.logger.info("Elysium Telegram Bot initialized")
    
    def _register_handlers(self):
        """Register all command and message handlers"""
        # Welcome handler
        self.dispatcher.add_handler(CommandHandler("start", self.cmd_start))
        
        # Authentication conversation
        auth_conv = ConversationHandler(
            entry_points=[CommandHandler("connect", self.select_network)],
            states={
                SELECTING_NETWORK: [
                    CallbackQueryHandler(self.select_network_callback, pattern='^network_')
                ],
                PASSWORD_AUTH: [
                    MessageHandler(Filters.text & ~Filters.command, self.password_auth)
                ],
                PASSWORD_SETUP: [
                    MessageHandler(Filters.text & ~Filters.command, self.password_setup)
                ],
                CONFIRM_PASSWORD: [
                    MessageHandler(Filters.text & ~Filters.command, self.confirm_password)
                ]
            },
            fallbacks=[CommandHandler("cancel", self.cancel_conversation)]
        )
        self.dispatcher.add_handler(auth_conv)
        
        # Account info commands
        self.dispatcher.add_handler(CommandHandler("balance", self.cmd_balance))
        self.dispatcher.add_handler(CommandHandler("positions", self.cmd_positions))
        self.dispatcher.add_handler(CommandHandler("orders", self.cmd_orders))
        
        # Help and status
        self.dispatcher.add_handler(CommandHandler("help", self.cmd_help))
        self.dispatcher.add_handler(CommandHandler("status", self.cmd_status))
        
        # Market data commands
        self.dispatcher.add_handler(CommandHandler("price", self.cmd_price))
        
        # Main menu
        self.dispatcher.add_handler(CommandHandler("menu", self.cmd_show_menu))
        
        # Add trade commands
        self.dispatcher.add_handler(CommandHandler("buy", self.cmd_buy))
        self.dispatcher.add_handler(CommandHandler("sell", self.cmd_sell))
        self.dispatcher.add_handler(CommandHandler("close", self.cmd_close))
        
        # Callback query handler
        self.dispatcher.add_handler(CallbackQueryHandler(self.button_callback))
        
        # Error handler
        self.dispatcher.add_error_handler(self.error_handler)
    
    def start(self):
        """Start the bot in a separate thread"""
        if not hasattr(self, 'updater'):
            self.logger.error("Telegram bot not properly initialized")
            return
        
        self.logger.info("Starting Elysium Telegram Bot")
        self.updater.start_polling()
        
        # Start the command processing thread
        self.command_processor_thread = threading.Thread(target=self._process_commands)
        self.command_processor_thread.daemon = True
        self.command_processor_thread.start()
    
    def stop(self):
        """Stop the bot"""
        if hasattr(self, 'updater'):
            self.logger.info("Stopping Elysium Telegram Bot")
            self.updater.stop()
    
    def _process_commands(self):
        """Process commands between CLI and Telegram"""
        while True:
            try:
                # Get command from queue (with timeout to allow checking for shutdown)
                try:
                    cmd, args = self.command_queue.get(timeout=1)
                    
                    # Process the command
                    if cmd == "update_connection":
                        connected, is_testnet = args
                        self._update_connection_status(connected, is_testnet)
                    
                    # Mark task as done
                    self.command_queue.task_done()
                except queue.Empty:
                    # Queue is empty, just continue the loop
                    pass
                    
                # Sleep a bit to prevent high CPU usage
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.error(f"Error in command processor: {str(e)}")
                time.sleep(1)  # Prevent tight loop in case of errors
    
    def update_connection_status(self, connected, is_testnet=False):
        """
        Update the connection status when the main app connects
        This is thread-safe and uses the command queue
        """
        self.command_queue.put(("update_connection", (connected, is_testnet)))
    
    def _update_connection_status(self, connected, is_testnet=False):
        """Internal method to update connection status with thread safety"""
        with self.state_lock:
            self.connected = connected
            self.is_testnet = is_testnet
    
    def _is_authorized(self, user_id):
        """Check if a user is authorized to use this bot"""
        return user_id in self.admin_user_ids
    
    def _is_authenticated(self, user_id):
        """Check if user is authenticated (after password)"""
        return user_id in self.authenticated_users
    
    def _check_auth(self, update: Update, context: CallbackContext):
        """Check if the user is authorized and authenticated"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            update.message.reply_text("⛔ You are not authorized to use this bot.")
            return False
            
        if not self._is_authenticated(user_id):
            update.message.reply_text(
                "You need to connect and authenticate first.\n"
                "Use /connect to start."
            )
            return False
            
        return True
    
    def _check_connection(self, update: Update, context: CallbackContext):
        """Check if the bot is connected to the exchange"""
        with self.state_lock:
            connected = self.connected
        
        if not connected:
            if hasattr(update, 'message') and update.message:
                update.message.reply_text("❌ Not connected to exchange. Use /connect first.")
                return False
            elif hasattr(update, 'callback_query') and update.callback_query:
                update.callback_query.answer("Not connected to exchange")
                update.callback_query.edit_message_text("❌ Not connected to exchange. Use /connect first.")
                return False
            return False
        return True
    
    # Command handlers
    def cmd_start(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        update.message.reply_text(
            f"🚀 *Welcome to Elysium Trading Bot!*\n\n"
            f"This bot allows you to control your trading platform remotely.\n\n"
            f"To get started:\n"
            f"1. Use /connect to connect to an exchange\n"
            f"2. Use /menu to see available commands\n"
            f"3. Use /help for detailed instructions",
            parse_mode=ParseMode.MARKDOWN
        )
    
    def select_network(self, update: Update, context: CallbackContext):
        """Start connection by selecting network"""
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            update.message.reply_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END
        
        keyboard = [
            [
                InlineKeyboardButton("Mainnet", callback_data="network_mainnet"),
                InlineKeyboardButton("Testnet", callback_data="network_testnet")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        update.message.reply_text(
            "Please select a network to connect to:",
            reply_markup=reply_markup
        )
        return SELECTING_NETWORK
    
    def select_network_callback(self, update: Update, context: CallbackContext):
        """Handle network selection"""
        query = update.callback_query
        query.answer()
        user_id = query.from_user.id
        
        if not self._is_authorized(user_id):
            query.edit_message_text("⛔ You are not authorized to use this bot.")
            return ConversationHandler.END
        
        network = query.data.split("_")[1]
        self.connection_contexts[user_id] = {"network": network}
        
        # Check if password is already set
        if self.config_manager.get('password_hash'):
            query.edit_message_text(
                f"Selected {network.upper()}. Please enter your password:"
            )
            return PASSWORD_AUTH
        else:
            query.edit_message_text(
                "First-time setup. Please create a password:"
            )
            return PASSWORD_SETUP
    
    def password_auth(self, update: Update, context: CallbackContext):
        """Authenticate with existing password"""
        user_id = update.effective_user.id
        password = update.message.text
        
        # Delete the message containing the password for security
        try:
            context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception as e:
            self.logger.warning(f"Could not delete password message: {str(e)}")
        
        if self.config_manager.verify_password(password):
            # Connect to the exchange
            network = self.connection_contexts[user_id]["network"]
            self._connect_to_exchange(update, context, network == "testnet")
            
            # Mark as authenticated
            self.authenticated_users.add(user_id)
            
            # Show main menu
            self.cmd_show_menu(update, context)
            return ConversationHandler.END
        else:
            update.message.reply_text(
                "❌ Incorrect password. Please try again:"
            )
            return PASSWORD_AUTH
    
    def password_setup(self, update: Update, context: CallbackContext):
        """Set up a new password"""
        user_id = update.effective_user.id
        password = update.message.text
        
        # Delete the message containing the password for security
        try:
            context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception as e:
            self.logger.warning(f"Could not delete password message: {str(e)}")
        
        self.connection_contexts[user_id]["new_password"] = password
        
        update.message.reply_text(
            "Please confirm your password:"
        )
        return CONFIRM_PASSWORD
    
    def confirm_password(self, update: Update, context: CallbackContext):
        """Confirm new password"""
        user_id = update.effective_user.id
        confirm_password = update.message.text
        new_password = self.connection_contexts[user_id]["new_password"]
        
        # Delete the message containing the password for security
        try:
            context.bot.delete_message(chat_id=update.message.chat_id, message_id=update.message.message_id)
        except Exception as e:
            self.logger.warning(f"Could not delete password message: {str(e)}")
        
        if confirm_password == new_password:
            # Set the password
            self.config_manager.set_password(new_password)
            
            # Connect to the exchange
            network = self.connection_contexts[user_id]["network"]
            self._connect_to_exchange(update, context, network == "testnet")
            
            # Mark as authenticated
            self.authenticated_users.add(user_id)
            
            # Show main menu
            self.cmd_show_menu(update, context)
            return ConversationHandler.END
        else:
            update.message.reply_text(
                "❌ Passwords don't match. Please start again with /connect"
            )
            return ConversationHandler.END
    
    def _connect_to_exchange(self, update, context, use_testnet=False):
        """Connect to the exchange with proper synchronization"""
        network_name = "testnet" if use_testnet else "mainnet"
        
        message = update.message if hasattr(update, 'message') and update.message else None
        user_id = update.effective_user.id
        
        if message:
            message.reply_text(f"🔄 Connecting to Hyperliquid {network_name}...")
        
        try:
            # Import credentials from dontshareconfig
            import dontshareconfig as ds
            
            if use_testnet:
                wallet_address = ds.testnet_wallet
                secret_key = ds.testnet_secret
            else:
                wallet_address = ds.mainnet_wallet
                secret_key = ds.mainnet_secret
            
            # Connect using API connector
            success = self.api_connector.connect_hyperliquid(wallet_address, secret_key, use_testnet)
            
            if success:
                # Update local state with thread safety
                with self.state_lock:
                    self.connected = True
                    self.is_testnet = use_testnet
                
                # Initialize order handler if needed
                self.order_handler.set_exchange(
                    self.api_connector.exchange, 
                    self.api_connector.info,
                    self.api_connector
                )
                self.order_handler.wallet_address = wallet_address
                
                if message:
                    message.reply_text(
                        f"✅ Successfully connected to Hyperliquid {network_name}\n"
                        f"Address: `{wallet_address[:6]}...{wallet_address[-4:]}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                return True
            else:
                if message:
                    message.reply_text(f"❌ Failed to connect to Hyperliquid {network_name}")
                return False
        except Exception as e:
            self.logger.error(f"Error connecting to {network_name}: {str(e)}")
            if message:
                message.reply_text(f"❌ Error connecting to {network_name}: {str(e)}")
            return False
    
    def cmd_show_menu(self, update: Update, context: CallbackContext):
        """Show the main menu with basic operations"""
        user_id = update.effective_user.id
        
        if not self._is_authorized(user_id):
            if hasattr(update, 'message') and update.message:
                update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        if not self._is_authenticated(user_id):
            if hasattr(update, 'message') and update.message:
                update.message.reply_text(
                    "Please connect and authenticate first.\n"
                    "Use /connect to start."
                )
            return
        
        keyboard = [
            [KeyboardButton("💰 Balance"), KeyboardButton("📊 Positions")],
            [KeyboardButton("📝 Orders"), KeyboardButton("📈 Price")],
            [KeyboardButton("🛒 Trade"), KeyboardButton("❌ Close Position")],
            [KeyboardButton("🔄 Status"), KeyboardButton("❔ Help")]
        ]
        reply_markup = ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True, one_time_keyboard=False
        )
        
        with self.state_lock:
            connection_status = "Connected" if self.connected else "Not connected"
            network = "testnet" if self.is_testnet else "mainnet"
            network_emoji = "🧪" if self.is_testnet else "🌐"
        
        message = (
            f"*Elysium Trading Bot - Main Menu*\n\n"
            f"Status: {connection_status}\n"
            f"Network: {network_emoji} {network.upper()}\n\n"
            f"Choose an option from the menu below:"
        )
        
        if hasattr(update, 'message') and update.message:
            update.message.reply_text(
                message,
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            query = update.callback_query
            query.edit_message_text(
                message,
                parse_mode=ParseMode.MARKDOWN
            )
            context.bot.send_message(
                chat_id=query.message.chat_id,
                text="Main menu activated.",
                reply_markup=reply_markup
            )
    
    def button_callback(self, update: Update, context: CallbackContext):
        """Handle button callbacks"""
        query = update.callback_query
        query.answer()
        data = query.data
        
        # Handle different button actions based on data
        if data == "action_main_menu":
            self.cmd_show_menu(update, context)
        elif data.startswith("action_"):
            # Handle action buttons
            action = data[7:]  # Remove "action_" prefix
            self.handle_action(action, update, context)
        elif data.startswith("close_"):
            # Handle close position button
            symbol = data[6:]  # Remove "close_" prefix
            self.handle_close_position(symbol, update, context)
    
    def handle_action(self, action: str, update: Update, context: CallbackContext):
        """Handle different menu actions"""
        if action == "balance":
            self.cmd_balance(update, context)
        elif action == "positions":
            self.cmd_positions(update, context)
        elif action == "orders":
            self.cmd_orders(update, context)
        elif action == "trade":
            # Show trade options
            keyboard = [
                [
                    InlineKeyboardButton("Market Buy", callback_data="action_market_buy"),
                    InlineKeyboardButton("Market Sell", callback_data="action_market_sell")
                ],
                [
                    InlineKeyboardButton("Limit Buy", callback_data="action_limit_buy"),
                    InlineKeyboardButton("Limit Sell", callback_data="action_limit_sell")
                ],
                [
                    InlineKeyboardButton("Close Position", callback_data="action_close_position")
                ],
                [
                    InlineKeyboardButton("« Back", callback_data="action_main_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.callback_query.edit_message_text(
                "Select a trading action:",
                reply_markup=reply_markup
            )
    
    def handle_close_position(self, symbol: str, update: Update, context: CallbackContext):
        """Handle closing a position"""
        if not self._check_connection(update, context):
            return
        
        query = update.callback_query
        
        try:
            # Confirm close
            keyboard = [
                [
                    InlineKeyboardButton("Yes, Close Position", callback_data=f"confirm_close_{symbol}"),
                    InlineKeyboardButton("No, Cancel", callback_data="action_main_menu")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            query.edit_message_text(
                f"Are you sure you want to close your {symbol} position?",
                reply_markup=reply_markup
            )
        except Exception as e:
            self.logger.error(f"Error preparing to close position: {str(e)}")
            query.edit_message_text(f"Error: {str(e)}")
    
    def handle_close_confirm(self, symbol: str, update: Update, context: CallbackContext):
        """Handle confirmation of position close"""
        if not self._check_connection(update, context):
            return
            
        query = update.callback_query
        
        try:
            query.edit_message_text(f"Closing {symbol} position...")
            
            # Close the position
            result = self.order_handler.close_position(symbol)
            
            if result["status"] == "ok":
                query.edit_message_text(f"✅ Successfully closed {symbol} position")
            else:
                query.edit_message_text(f"❌ Error closing position: {result.get('message', 'Unknown error')}")
        
        except Exception as e:
            self.logger.error(f"Error closing position: {str(e)}")
            query.edit_message_text(f"❌ Error: {str(e)}")
    
    def cancel_conversation(self, update: Update, context: CallbackContext):
        """Generic handler to cancel any conversation"""
        user_id = update.effective_user.id
        
        # Clear trading context
        if user_id in self.trading_context:
            del self.trading_context[user_id]
        
        # Remove keyboard if present
        update.message.reply_text(
            "Operation cancelled",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END
    
    def cmd_balance(self, update: Update, context: CallbackContext):
        """Handle /balance command"""
        if not self._check_auth(update, context):
            return
        
        if not self._check_connection(update, context):
            return
        
        try:
            update.message.reply_text("🔄 Fetching balance information...")
            
            balances = self.api_connector.get_balances()
            
            message = "*Account Balances:*\n\n"
            
            # Format spot balances
            if balances.get("spot"):
                message += "*Spot Balances:*\n"
                for balance in balances["spot"]:
                    if float(balance.get("total", 0)) > 0:
                        message += (
                            f"• {balance.get('asset')}: "
                            f"{balance.get('available', 0)} available, "
                            f"{balance.get('total', 0)} total\n"
                        )
                message += "\n"
            
            # Format perpetual account
            if balances.get("perp"):
                message += "*Perpetual Account:*\n"
                message += f"• Account Value: ${balances['perp'].get('account_value', 0)}\n"
                message += f"• Margin Used: ${balances['perp'].get('margin_used', 0)}\n"
                message += f"• Position Value: ${balances['perp'].get('position_value', 0)}\n"
            
            update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            self.logger.error(f"Error fetching balance: {str(e)}")
            update.message.reply_text(f"❌ Error fetching balance: {str(e)}")
    
    def cmd_positions(self, update: Update, context: CallbackContext):
        """Handle /positions command"""
        if not self._check_auth(update, context):
            return
        
        if not self._check_connection(update, context):
            return
        
        try:
            update.message.reply_text("🔄 Fetching position information...")
            
            positions = self.api_connector.get_positions()
            
            if not positions:
                update.message.reply_text("No open positions")
                return
            
            message = "*Open Positions:*\n\n"
            for pos in positions:
                symbol = pos.get("symbol", "")
                size = pos.get("size", 0)
                side = "Long" if size > 0 else "Short"
                entry = pos.get("entry_price", 0)
                mark = pos.get("mark_price", 0)
                pnl = pos.get("unrealized_pnl", 0)
                
                message += (
                    f"*{symbol}:*\n"
                    f"• Side: {side}\n"
                    f"• Size: {abs(size)}\n"
                    f"• Entry: {entry}\n"
                    f"• Mark: {mark}\n"
                    f"• Unrealized PnL: {pnl}\n\n"
                )
            
            # Add close buttons for positions
            keyboard = []
            for pos in positions:
                symbol = pos.get("symbol", "")
                keyboard.append([
                    InlineKeyboardButton(f"Close {symbol} Position", callback_data=f"close_{symbol}")
                ])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except Exception as e:
            self.logger.error(f"Error fetching positions: {str(e)}")
            update.message.reply_text(f"❌ Error fetching positions: {str(e)}")
    
    def cmd_orders(self, update: Update, context: CallbackContext):
        """Handle /orders command"""
        if not self._check_auth(update, context):
            return
            
        if not self._check_connection(update, context):
            return
        
        try:
            update.message.reply_text("🔄 Fetching open orders...")
            
            orders_result = self.order_handler.get_open_orders()
            
            if isinstance(orders_result, dict) and "data" in orders_result:
                orders = orders_result["data"]
            else:
                orders = orders_result
            
            if not orders:
                update.message.reply_text("No open orders")
                return
            
            message = "*Open Orders:*\n\n"
            keyboard = []
            
            for order in orders:
                symbol = order.get("coin", "")
                side = "Buy" if order.get("side", "") == "B" else "Sell"
                size = float(order.get("sz", 0))
                price = float(order.get("limitPx", 0))
                order_id = order.get("oid", 0)
                
                message += (
                    f"*{symbol}:*\n"
                    f"• Side: {side}\n"
                    f"• Size: {size}\n"
                    f"• Price: {price}\n"
                    f"• Order ID: {order_id}\n\n"
                )
                
                # Add a cancel button for this order
                keyboard.append([InlineKeyboardButton(f"Cancel Order #{order_id}", callback_data=f"cancel_{symbol}_{order_id}")])
            
            # Add a cancel all button
            keyboard.append([InlineKeyboardButton("Cancel All Orders", callback_data="action_cancel_all")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
        except Exception as e:
            self.logger.error(f"Error fetching orders: {str(e)}")
            update.message.reply_text(f"❌ Error fetching orders: {str(e)}")
    
    def cmd_price(self, update: Update, context: CallbackContext):
        """Handle /price command"""
        if not self._check_auth(update, context):
            return
            
        if not self._check_connection(update, context):
            return
        
        try:
            args = update.message.text.split()[1:] if len(update.message.text.split()) > 1 else []
            
            if not args:
                update.message.reply_text("Please specify a symbol. Usage: /price BTC")
                return
            
            symbol = args[0].upper()
            
            update.message.reply_text(f"🔄 Fetching price for {symbol}...")
            
            market_data = self.api_connector.get_market_data(symbol)
            
            if "error" in market_data:
                update.message.reply_text(f"❌ Error: {market_data['error']}")
                return
            
            message = f"*{symbol} Market Data:*\n\n"
            
            if "mid_price" in market_data:
                message += f"Mid Price: ${market_data['mid_price']}\n"
            
            if "best_bid" in market_data:
                message += f"Best Bid: ${market_data['best_bid']}\n"
            
            if "best_ask" in market_data:
                message += f"Best Ask: ${market_data['best_ask']}\n"
            
            update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            self.logger.error(f"Error fetching price: {str(e)}")
            update.message.reply_text(f"❌ Error fetching price: {str(e)}")
    
    def cmd_status(self, update: Update, context: CallbackContext):
        """Handle /status command"""
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        with self.state_lock:
            connection_status = "Connected" if self.connected else "Not connected"
            network = "testnet" if self.is_testnet else "mainnet"
            network_emoji = "🧪" if self.is_testnet else "🌐"
        
        message = f"*Elysium Bot Status:*\n\n"
        message += f"Status: {connection_status}\n"
        
        if self.connected:
            message += f"Network: {network_emoji} {network.upper()}\n"
            message += f"Address: `{self.api_connector.wallet_address[:6]}...{self.api_connector.wallet_address[-4:]}`\n"
            
            # Add position summary if available
            try:
                positions = self.api_connector.get_positions()
                if positions:
                    message += "\n*Open Positions:*\n"
                    for pos in positions:
                        symbol = pos.get("symbol", "")
                        size = pos.get("size", 0)
                        side = "Long" if size > 0 else "Short"
                        entry = pos.get("entry_price", 0)
                        pnl = pos.get("unrealized_pnl", 0)
                        message += f"• {symbol}: {side} {abs(size)} @ {entry} (PnL: {pnl})\n"
            except Exception as e:
                self.logger.error(f"Error getting positions for status: {str(e)}")
        
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    def cmd_help(self, update: Update, context: CallbackContext):
        """Handle /help command"""
        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            update.message.reply_text("⛔ You are not authorized to use this bot.")
            return
        
        update.message.reply_text(
            "*Elysium Trading Bot Commands:*\n\n"
            "*Basic Commands:*\n"
            "/connect - Connect to exchange\n"
            "/menu - Show main menu\n"
            "/help - Show this help message\n"
            "/status - Show connection status\n\n"
            
            "*Account Info:*\n"
            "/balance - Show account balance\n"
            "/positions - Show open positions\n"
            "/orders - Show open orders\n"
            "/price <symbol> - Check current price\n\n"
            
            "*Trading:*\n"
            "/buy <symbol> <size> - Execute a spot market buy\n"
            "/sell <symbol> <size> - Execute a spot market sell\n"
            "/close <symbol> - Close a position\n",
            parse_mode=ParseMode.MARKDOWN
        )
    
    def cmd_buy(self, update: Update, context: CallbackContext):
        """Handle /buy command"""
        if not self._check_auth(update, context) or not self._check_connection(update, context):
            return
            
        args = context.args
        if len(args) < 2:
            update.message.reply_text("Usage: /buy <symbol> <size> [slippage]")
            return
            
        symbol = args[0]
        size = float(args[1])
        slippage = float(args[2]) if len(args) > 2 else 0.05
        
        update.message.reply_text(f"🔄 Executing market buy: {size} {symbol}")
        result = self.order_handler.market_buy(symbol, size, slippage)
        
        if result["status"] == "ok":
            update.message.reply_text("✅ Buy order executed successfully")
            # Show details if available
            if "response" in result and "data" in result["response"] and "statuses" in result["response"]["data"]:
                for status in result["response"]["data"]["statuses"]:
                    if "filled" in status:
                        filled = status["filled"]
                        update.message.reply_text(f"Filled: {filled['totalSz']} @ {filled['avgPx']}")
        else:
            update.message.reply_text(f"❌ Order failed: {result.get('message', 'Unknown error')}")
    
    def cmd_sell(self, update: Update, context: CallbackContext):
        """Handle /sell command"""
        if not self._check_auth(update, context) or not self._check_connection(update, context):
            return
            
        args = context.args
        if len(args) < 2:
            update.message.reply_text("Usage: /sell <symbol> <size> [slippage]")
            return
            
        symbol = args[0]
        size = float(args[1])
        slippage = float(args[2]) if len(args) > 2 else 0.05
        
        update.message.reply_text(f"🔄 Executing market sell: {size} {symbol}")
        result = self.order_handler.market_sell(symbol, size, slippage)
        
        if result["status"] == "ok":
            update.message.reply_text("✅ Sell order executed successfully")
            # Show details if available
            if "response" in result and "data" in result["response"] and "statuses" in result["response"]["data"]:
                for status in result["response"]["data"]["statuses"]:
                    if "filled" in status:
                        filled = status["filled"]
                        update.message.reply_text(f"Filled: {filled['totalSz']} @ {filled['avgPx']}")
        else:
            update.message.reply_text(f"❌ Order failed: {result.get('message', 'Unknown error')}")
    
    def cmd_close(self, update: Update, context: CallbackContext):
        """Handle /close command"""
        if not self._check_auth(update, context) or not self._check_connection(update, context):
            return
            
        args = context.args
        if len(args) < 1:
            update.message.reply_text("Usage: /close <symbol> [slippage]")
            return
            
        symbol = args[0]
        slippage = float(args[1]) if len(args) > 1 else 0.05
        
        update.message.reply_text(f"🔄 Closing position for {symbol}")
        result = self.order_handler.close_position(symbol, slippage)
        
        if result["status"] == "ok":
            update.message.reply_text("✅ Position closed successfully")
            # Show details if available
            if "response" in result and "data" in result["response"] and "statuses" in result["response"]["data"]:
                for status in result["response"]["data"]["statuses"]:
                    if "filled" in status:
                        filled = status["filled"]
                        update.message.reply_text(f"Filled: {filled['totalSz']} @ {filled['avgPx']}")
        else:
            update.message.reply_text(f"❌ Failed to close position: {result.get('message', 'Unknown error')}")
    
    def error_handler(self, update: Update, context: CallbackContext):
        """Log errors and send a message to the user"""
        self.logger.error(f"Update {update} caused error {context.error}")
        
        try:
            if update.effective_message:
                update.effective_message.reply_text(
                    "❌ Sorry, an error occurred while processing your request."
                )
        except Exception as e:
            self.logger.error(f"Error in error handler: {str(e)}")