"""
===================================================================
INVESTMENT PRO BOT - DEPOSIT FLOW (Exact User Request)
===================================================================
Flow:
1. Invest -> Plans -> Amount
2. Bot shows: Admin wallet + Payment details + Amount + Deposit Request ID
3. User sends payment from app, gets Transaction ID
4. User enters Transaction ID in bot
5. Bot shows: Full payment details + Amount + Deposit Request ID + Transaction ID + [Confirm] [Cancel]
6. User clicks Confirm -> "Deposit accepted. Please wait for admin approval." + Back to Menu
7. Admin gets notification -> Approve/Reject
8. Admin approves -> User gets confirmation message
"""

import logging
import sqlite3
import random
import string
import os
from datetime import datetime, timedelta
from typing import List, Optional

from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ===================================================================
# CONFIGURATION
# ===================================================================

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x.strip()]
    DB_PATH = os.getenv("DB_PATH", "investment_bot.db")
    CURRENCY = os.getenv("CURRENCY", "$")
    CURRENCY_NAME = os.getenv("CURRENCY_NAME", "USD")
    MIN_INVESTMENT = float(os.getenv("MIN_INVESTMENT", 10))
    MAX_INVESTMENT = float(os.getenv("MAX_INVESTMENT", 100000))
    REFERRAL_BONUS_PERCENT = int(os.getenv("REFERRAL_BONUS_PERCENT", 5))
    ENABLE_REFERRAL = os.getenv("ENABLE_REFERRAL", "true").lower() == "true"
    ENABLE_WITHDRAWAL = os.getenv("ENABLE_WITHDRAWAL", "true").lower() == "true"
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@investmentpro.com")
    SUPPORT_TELEGRAM = os.getenv("SUPPORT_TELEGRAM", "@admin_username")

    # Payment Details (shown to user)
    WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0x1234567890abcdef1234567890abcdef12345678")
    PAYMENT_METHOD = os.getenv("PAYMENT_METHOD", "USDT (TRC20)")
    NETWORK = os.getenv("NETWORK", "TRC20")

    PLANS = {
        "starter": {"name": "Starter", "min": float(os.getenv("STARTER_MIN", 10)), "max": float(os.getenv("STARTER_MAX", 500)), "daily_rate": float(os.getenv("STARTER_RATE", 0.01)), "duration": int(os.getenv("STARTER_DURATION", 30)), "description": "Perfect for beginners"},
        "silver": {"name": "Silver", "min": float(os.getenv("SILVER_MIN", 500)), "max": float(os.getenv("SILVER_MAX", 2500)), "daily_rate": float(os.getenv("SILVER_RATE", 0.015)), "duration": int(os.getenv("SILVER_DURATION", 60)), "description": "Balanced growth plan"},
        "gold": {"name": "Gold", "min": float(os.getenv("GOLD_MIN", 2500)), "max": float(os.getenv("GOLD_MAX", 10000)), "daily_rate": float(os.getenv("GOLD_RATE", 0.02)), "duration": int(os.getenv("GOLD_DURATION", 90)), "description": "High return investment"},
        "platinum": {"name": "Platinum", "min": float(os.getenv("PLATINUM_MIN", 10000)), "max": float(os.getenv("PLATINUM_MAX", 100000)), "daily_rate": float(os.getenv("PLATINUM_RATE", 0.025)), "duration": int(os.getenv("PLATINUM_DURATION", 120)), "description": "Premium elite plan"},
    }

# ===================================================================
# DATABASE
# ===================================================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT, last_name TEXT,
                phone TEXT, email TEXT, referral_code TEXT UNIQUE, referred_by INTEGER,
                balance REAL DEFAULT 0, total_invested REAL DEFAULT 0, total_earned REAL DEFAULT 0,
                total_withdrawn REAL DEFAULT 0, joined_date TEXT, status TEXT DEFAULT 'active'
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_type TEXT,
                amount REAL, daily_rate REAL, duration INTEGER, start_date TEXT,
                end_date TEXT, total_return REAL, daily_earning REAL, status TEXT DEFAULT 'active',
                total_earned REAL DEFAULT 0, last_calculation TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT,
                amount REAL, status TEXT, method TEXT, details TEXT, created_at TEXT, processed_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT, referrer_id INTEGER, referred_id INTEGER,
                bonus_amount REAL, status TEXT DEFAULT 'pending', created_at TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS deposit_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_type TEXT,
                amount REAL,
                transaction_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                processed_at TEXT,
                processed_by INTEGER
            )
        """)
        self.conn.commit()

    def execute(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        self.conn.commit()
        return cursor

    def fetchone(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()

    def fetchall(self, query, params=()):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()

# ===================================================================
# USER MANAGER
# ===================================================================

class UserManager:
    def __init__(self, db: Database):
        self.db = db

    def generate_referral_code(self) -> str:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def get_or_create_user(self, user_id: int, username: str, first_name: str, last_name: str = None, referral_code: str = None) -> dict:
        user = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not user:
            ref_code = self.generate_referral_code()
            referred_by = None
            if referral_code and Config.ENABLE_REFERRAL:
                referrer = self.db.fetchone("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
                if referrer:
                    referred_by = referrer[0]
            self.db.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, referral_code, referred_by, joined_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, ref_code, referred_by, datetime.now().isoformat()))
            if referred_by and Config.ENABLE_REFERRAL:
                self.db.execute("""
                    INSERT INTO referrals (referrer_id, referred_id, bonus_amount, created_at)
                    VALUES (?, ?, ?, ?)
                """, (referred_by, user_id, 0, datetime.now().isoformat()))
            user = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return {
            "user_id": user[0], "username": user[1], "first_name": user[2],
            "balance": user[8], "total_invested": user[9], "total_earned": user[10],
            "total_withdrawn": user[11], "referral_code": user[7], "status": user[13]
        }

    def get_user(self, user_id: int) -> Optional[dict]:
        user = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not user:
            return None
        return {
            "user_id": user[0], "username": user[1], "first_name": user[2],
            "balance": user[8], "total_invested": user[9], "total_earned": user[10],
            "referral_code": user[7], "status": user[13]
        }

    def get_stats(self) -> dict:
        total_users = self.db.fetchone("SELECT COUNT(*) FROM users")[0]
        total_investments = self.db.fetchone("SELECT COALESCE(SUM(amount), 0) FROM investments WHERE status = 'active'")[0]
        total_earned = self.db.fetchone("SELECT COALESCE(SUM(total_earned), 0) FROM investments")[0]
        pending_withdrawals = self.db.fetchone("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'withdrawal' AND status = 'pending'")[0]
        pending_deposits = self.db.fetchone("SELECT COUNT(*) FROM deposit_requests WHERE status = 'pending'")[0]
        return {"total_users": total_users, "total_investments": total_investments, 
                "total_earned": total_earned, "pending_withdrawals": pending_withdrawals,
                "pending_deposits": pending_deposits}

# ===================================================================
# INVESTMENT MANAGER
# ===================================================================

class InvestmentManager:
    def __init__(self, db: Database):
        self.db = db

    def create_investment(self, user_id: int, plan_type: str, amount: float) -> dict:
        plan = Config.PLANS[plan_type]
        if amount < plan["min"] or amount > plan["max"]:
            return {"success": False, "message": "Amount out of range"}
        daily_earning = amount * plan["daily_rate"]
        total_return = daily_earning * plan["duration"]
        start_date = datetime.now()
        end_date = start_date + timedelta(days=plan["duration"])
        cursor = self.db.execute("""
            INSERT INTO investments (user_id, plan_type, amount, daily_rate, duration, start_date, 
             end_date, total_return, daily_earning, last_calculation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, plan_type, amount, plan["daily_rate"], plan["duration"], 
              start_date.isoformat(), end_date.isoformat(), total_return, daily_earning, start_date.isoformat()))
        self.db.execute("UPDATE users SET total_invested = total_invested + ? WHERE user_id = ?", (amount, user_id))
        return {
            "success": True, "investment_id": cursor.lastrowid, "plan": plan["name"],
            "amount": amount, "duration": plan["duration"], "daily_earning": daily_earning, "total_return": total_return
        }

    def get_user_investments(self, user_id: int) -> List[dict]:
        rows = self.db.fetchall("SELECT * FROM investments WHERE user_id = ? ORDER BY start_date DESC", (user_id,))
        return [{"id": r[0], "plan_type": r[2], "amount": r[3], "daily_rate": r[4], "duration": r[5],
                 "start_date": r[6], "end_date": r[7], "total_return": r[8], "daily_earning": r[9],
                 "status": r[10], "total_earned": r[11]} for r in rows]

# ===================================================================
# KEYBOARDS
# ===================================================================

class Keyboards:
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Invest", callback_data="invest"), InlineKeyboardButton("Portfolio", callback_data="portfolio")],
            [InlineKeyboardButton("Withdraw", callback_data="withdraw"), InlineKeyboardButton("Referral", callback_data="referral")],
            [InlineKeyboardButton("Support", callback_data="support"), InlineKeyboardButton("Help", callback_data="help_menu")],
            [InlineKeyboardButton("Statistics", callback_data="stats")]
        ])

    @staticmethod
    def plans_menu() -> InlineKeyboardMarkup:
        keyboard = []
        for key, plan in Config.PLANS.items():
            btn_text = f"{plan['name']} - {Config.CURRENCY}{plan['min']:,} to {Config.CURRENCY}{plan['max']:,}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"plan_{key}")])
        keyboard.append([InlineKeyboardButton("Back to Menu", callback_data="back_menu")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def confirm_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Confirm", callback_data="confirm_deposit"), InlineKeyboardButton("Cancel", callback_data="cancel_deposit")]
        ])

    @staticmethod
    def back_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([[InlineKeyboardButton("Back to Menu", callback_data="back_menu")]])

    @staticmethod
    def admin_menu() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton("Users List", callback_data="admin_users")],
            [InlineKeyboardButton("Pending Deposits", callback_data="admin_deposits")],
            [InlineKeyboardButton("Pending Withdrawals", callback_data="admin_withdrawals")],
            [InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("Back to Menu", callback_data="back_menu")]
        ])

    @staticmethod
    def admin_deposit_approval(deposit_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Approve", callback_data=f"approve_deposit_{deposit_id}"),
             InlineKeyboardButton("Reject", callback_data=f"reject_deposit_{deposit_id}")]
        ])

# ===================================================================
# STATES
# ===================================================================

SELECTING_PLAN, ENTERING_AMOUNT, ENTERING_TRANSACTION_ID, CONFIRMING_DEPOSIT = range(4)
ENTERING_WITHDRAW_AMOUNT = 5

# ===================================================================
# BOT CLASS
# ===================================================================

class InvestmentBot:
    def __init__(self):
        self.db = Database()
        self.user_manager = UserManager(self.db)
        self.investment_manager = InvestmentManager(self.db)

    async def send_main_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
        user = self.user_manager.get_user(update.effective_user.id)
        text = (
            f"Main Menu\n"
            f"-------------------------\n\n"
            f"Balance: {Config.CURRENCY}{user['balance']:,.2f}\n"
            f"Total Invested: {Config.CURRENCY}{user['total_invested']:,.2f}\n"
            f"Total Earned: {Config.CURRENCY}{user['total_earned']:,.2f}\n"
            f"Total Withdrawn: {Config.CURRENCY}{user['total_withdrawn']:,.2f}\n\n"
            f"What would you like to do?"
        )
        if edit and update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=Keyboards.main_menu())
        else:
            await update.message.reply_text(text, reply_markup=Keyboards.main_menu())

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        referral_code = context.args[0] if context.args else None
        user_data = self.user_manager.get_or_create_user(user.id, user.username, user.first_name, user.last_name, referral_code)
        welcome_text = (
            f"Welcome, {user.first_name}!\n\n"
            f"Welcome to Investment Pro Bot.\n"
            f"Invest your money and earn daily profits.\n\n"
            f"Your Dashboard:\n"
            f"Balance: {Config.CURRENCY}{user_data['balance']:,.2f}\n"
            f"Total Invested: {Config.CURRENCY}{user_data['total_invested']:,.2f}\n"
            f"Total Earned: {Config.CURRENCY}{user_data['total_earned']:,.2f}\n"
            f"Total Withdrawn: {Config.CURRENCY}{user_data['total_withdrawn']:,.2f}"
        )
        await update.message.reply_text(welcome_text, reply_markup=Keyboards.main_menu())

    async def back_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        context.user_data.clear()
        await self.send_main_menu(update, context, edit=True)
        return ConversationHandler.END

    # ===================================================================
    # INVEST FLOW - EXACT USER REQUEST
    # ===================================================================
    async def invest_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        text = (
            "Choose an Investment Plan:\n\n"
            "Starter: 1% daily for 30 days\n"
            "Silver: 1.5% daily for 60 days\n"
            "Gold: 2% daily for 90 days\n"
            "Platinum: 2.5% daily for 120 days\n\n"
            "Select a plan below:"
        )
        await query.edit_message_text(text, reply_markup=Keyboards.plans_menu())
        return SELECTING_PLAN

    async def plan_selected(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        plan_type = query.data.replace("plan_", "")
        context.user_data["selected_plan"] = plan_type
        plan = Config.PLANS[plan_type]
        text = (
            f"{plan['name']} Plan\n"
            f"-------------------------\n"
            f"Minimum: {Config.CURRENCY}{plan['min']:,}\n"
            f"Maximum: {Config.CURRENCY}{plan['max']:,}\n"
            f"Daily Rate: {plan['daily_rate']*100}%\n"
            f"Duration: {plan['duration']} days\n"
            f"{plan['description']}\n\n"
            f"Enter the amount you want to invest ({Config.CURRENCY}):"
        )
        await query.edit_message_text(text)
        return ENTERING_AMOUNT

    async def amount_entered(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        try:
            text = update.message.text.strip()
            text = text.replace(Config.CURRENCY, "").replace("$", "").replace("€", "").replace("£", "")
            text = text.replace(",", "")
            amount = float(text)
        except ValueError:
            await update.message.reply_text(
                "Invalid amount! Please enter a valid number like: 40 or 50\n\n"
                f"Try again or click Back to Menu:",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_AMOUNT

        plan_type = context.user_data.get("selected_plan")
        if not plan_type:
            await update.message.reply_text("Session expired. Please start again.", reply_markup=Keyboards.back_menu())
            return ConversationHandler.END

        plan = Config.PLANS[plan_type]
        if amount < plan["min"]:
            await update.message.reply_text(f"Minimum investment is {Config.CURRENCY}{plan['min']:,}!\n\nTry again:", reply_markup=Keyboards.back_menu())
            return ENTERING_AMOUNT
        if amount > plan["max"]:
            await update.message.reply_text(f"Maximum investment is {Config.CURRENCY}{plan['max']:,}!\n\nTry again:", reply_markup=Keyboards.back_menu())
            return ENTERING_AMOUNT

        context.user_data["investment_amount"] = amount

        # Create deposit request in database (pending)
        cursor = self.db.execute("""
            INSERT INTO deposit_requests (user_id, plan_type, amount, status, created_at)
            VALUES (?, ?, ?, 'pending', ?)
        """, (update.effective_user.id, plan_type, amount, datetime.now().isoformat()))
        deposit_id = cursor.lastrowid
        context.user_data["deposit_id"] = deposit_id

        # Show payment details with wallet address
        payment_text = (
            f"Payment Details\n"
            f"-------------------------\n\n"
            f"Amount: {Config.CURRENCY}{amount:,.2f}\n"
            f"Plan: {plan['name']}\n"
            f"Deposit Request ID: #{deposit_id}\n\n"
            f"-------------------------\n"
            f"Send Payment To:\n\n"
            f"Method: {Config.PAYMENT_METHOD}\n"
            f"Network: {Config.NETWORK}\n"
            f"Wallet Address:\n"
            f"{Config.WALLET_ADDRESS}\n\n"
            f"-------------------------\n"
            f"Please copy the wallet address above,\n"
            f"send payment from your app, then enter\n"
            f"the Transaction ID (TXID) below:\n\n"
            f"Enter Transaction ID:"
        )
        await update.message.reply_text(payment_text)
        return ENTERING_TRANSACTION_ID

    async def transaction_id_entered(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()

        transaction_id = update.message.text.strip()

        if not transaction_id or len(transaction_id) < 5:
            await update.message.reply_text(
                "Invalid Transaction ID! Please enter a valid transaction ID.\n\n"
                "Try again or click Back to Menu:",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_TRANSACTION_ID

        deposit_id = context.user_data.get("deposit_id")
        amount = context.user_data.get("investment_amount")
        plan_type = context.user_data.get("selected_plan")

        if not deposit_id or not amount or not plan_type:
            await update.message.reply_text("Session expired. Please start again.", reply_markup=Keyboards.back_menu())
            return ConversationHandler.END

        # Save transaction ID
        context.user_data["transaction_id"] = transaction_id
        self.db.execute("UPDATE deposit_requests SET transaction_id = ? WHERE id = ?", (transaction_id, deposit_id))

        plan = Config.PLANS[plan_type]
        daily_earning = amount * plan["daily_rate"]
        total_return = daily_earning * plan["duration"]

        # Show full payment details with Confirm/Cancel buttons
        confirm_text = (
            f"Deposit Confirmation\n"
            f"-------------------------\n\n"
            f"Payment Details:\n"
            f"Method: {Config.PAYMENT_METHOD}\n"
            f"Network: {Config.NETWORK}\n"
            f"Wallet: {Config.WALLET_ADDRESS}\n\n"
            f"Amount: {Config.CURRENCY}{amount:,.2f}\n"
            f"Plan: {plan['name']}\n"
            f"Deposit Request ID: #{deposit_id}\n"
            f"Transaction ID: {transaction_id}\n\n"
            f"Daily Earning: {Config.CURRENCY}{daily_earning:,.2f}\n"
            f"Total Return: {Config.CURRENCY}{total_return:,.2f}\n"
            f"-------------------------\n\n"
            f"Please confirm your deposit:"
        )
        await update.message.reply_text(confirm_text, reply_markup=Keyboards.confirm_menu())
        return CONFIRMING_DEPOSIT

    async def confirm_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        deposit_id = context.user_data.get("deposit_id")
        amount = context.user_data.get("investment_amount")
        plan_type = context.user_data.get("selected_plan")
        transaction_id = context.user_data.get("transaction_id")

        if not deposit_id:
            await query.edit_message_text("Session expired. Please start again.", reply_markup=Keyboards.back_menu())
            return ConversationHandler.END

        # Update deposit status to 'awaiting_approval'
        self.db.execute("UPDATE deposit_requests SET status = 'awaiting_approval' WHERE id = ?", (deposit_id,))

        # Notify admin
        await self.notify_admin_deposit(update, context, deposit_id, plan_type, amount, transaction_id)

        # Show user confirmation message
        await query.edit_message_text(
            f"Deposit Accepted!\n\n"
            f"Deposit Request ID: #{deposit_id}\n"
            f"Transaction ID: {transaction_id}\n\n"
            f"Your deposit has been accepted.\n"
            f"Please wait for admin approval.\n\n"
            f"You will receive a confirmation message\n"
            f"once your deposit is approved.",
            reply_markup=Keyboards.back_menu()
        )

        context.user_data.clear()
        return ConversationHandler.END

    async def cancel_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        deposit_id = context.user_data.get("deposit_id")
        if deposit_id:
            self.db.execute("UPDATE deposit_requests SET status = 'cancelled' WHERE id = ?", (deposit_id,))

        context.user_data.clear()
        await query.edit_message_text("Deposit cancelled.", reply_markup=Keyboards.back_menu())
        return ConversationHandler.END

    # ===================================================================
    # ADMIN NOTIFICATION
    # ===================================================================
    async def notify_admin_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE, deposit_id: int, plan_type: str, amount: float, transaction_id: str):
        user = update.effective_user
        plan = Config.PLANS.get(plan_type, {"name": "Unknown"})

        admin_text = (
            f"New Deposit Request!\n\n"
            f"User: {user.first_name} (@{user.username or 'N/A'})\n"
            f"User ID: {user.id}\n\n"
            f"Deposit Details:\n"
            f"Request ID: #{deposit_id}\n"
            f"Plan: {plan['name']}\n"
            f"Amount: {Config.CURRENCY}{amount:,.2f}\n"
            f"Transaction ID: {transaction_id}\n\n"
            f"Status: Awaiting Approval"
        )

        for admin_id in Config.ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=admin_text,
                    reply_markup=Keyboards.admin_deposit_approval(deposit_id)
                )
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

    # ===================================================================
    # ADMIN APPROVE/REJECT
    # ===================================================================
    async def approve_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if update.effective_user.id not in Config.ADMIN_IDS:
            await query.edit_message_text("Access denied!")
            return

        deposit_id = int(query.data.replace("approve_deposit_", ""))
        deposit = self.db.fetchone("SELECT * FROM deposit_requests WHERE id = ?", (deposit_id,))

        if not deposit:
            await query.edit_message_text("Deposit request not found!")
            return

        if deposit[5] != 'awaiting_approval':
            await query.edit_message_text(f"Deposit already {deposit[5]}!")
            return

        user_id = deposit[1]
        plan_type = deposit[2]
        amount = deposit[3]
        transaction_id = deposit[4] or "N/A"

        # Create investment
        result = self.investment_manager.create_investment(user_id, plan_type, amount)

        if result["success"]:
            # Update deposit status
            self.db.execute("""
                UPDATE deposit_requests 
                SET status = 'approved', processed_at = ?, processed_by = ?
                WHERE id = ?
            """, (datetime.now().isoformat(), update.effective_user.id, deposit_id))

            # Notify user
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"Deposit Approved!\n\n"
                        f"Your deposit has been approved by admin.\n\n"
                        f"Deposit Request ID: #{deposit_id}\n"
                        f"Transaction ID: {transaction_id}\n"
                        f"Plan: {result['plan']}\n"
                        f"Amount: {Config.CURRENCY}{result['amount']:,.2f}\n"
                        f"Duration: {result['duration']} days\n"
                        f"Daily Earning: {Config.CURRENCY}{result['daily_earning']:,.2f}\n"
                        f"Total Return: {Config.CURRENCY}{result['total_return']:,.2f}\n\n"
                        f"Your investment is now active!\n"
                        f"Start earning daily profits!"
                    ),
                    reply_markup=Keyboards.back_menu()
                )
            except Exception as e:
                logger.error(f"Failed to notify user {user_id}: {e}")

            await query.edit_message_text(
                f"Deposit #{deposit_id} APPROVED!\n\n"
                f"User ID: {user_id}\n"
                f"Transaction ID: {transaction_id}\n"
                f"Amount: {Config.CURRENCY}{amount:,.2f}\n"
                f"Investment created successfully."
            )
        else:
            await query.edit_message_text("Failed to create investment!")

    async def reject_deposit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if update.effective_user.id not in Config.ADMIN_IDS:
            await query.edit_message_text("Access denied!")
            return

        deposit_id = int(query.data.replace("reject_deposit_", ""))
        deposit = self.db.fetchone("SELECT * FROM deposit_requests WHERE id = ?", (deposit_id,))

        if not deposit:
            await query.edit_message_text("Deposit request not found!")
            return

        user_id = deposit[1]
        amount = deposit[3]
        transaction_id = deposit[4] or "N/A"

        self.db.execute("""
            UPDATE deposit_requests 
            SET status = 'rejected', processed_at = ?, processed_by = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), update.effective_user.id, deposit_id))

        # Notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"Deposit Rejected\n\n"
                    f"Your deposit has been rejected by admin.\n\n"
                    f"Deposit Request ID: #{deposit_id}\n"
                    f"Transaction ID: {transaction_id}\n"
                    f"Amount: {Config.CURRENCY}{amount:,.2f}\n\n"
                    f"Please contact support for more information."
                ),
                reply_markup=Keyboards.back_menu()
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")

        await query.edit_message_text(
            f"Deposit #{deposit_id} REJECTED!\n\n"
            f"User ID: {user_id}\n"
            f"Transaction ID: {transaction_id}\n"
            f"Amount: {Config.CURRENCY}{amount:,.2f}"
        )

    # ===================================================================
    # OTHER HANDLERS
    # ===================================================================
    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        user = self.user_manager.get_user(update.effective_user.id)
        investments = self.investment_manager.get_user_investments(update.effective_user.id)
        pending_deposits = self.db.fetchall(
            "SELECT id, plan_type, amount, status, transaction_id, created_at FROM deposit_requests WHERE user_id = ? AND status IN ('pending', 'awaiting_approval')",
            (update.effective_user.id,)
        )

        text = f"Your Portfolio\n-------------------------\n\n"

        if pending_deposits:
            text += "Pending Deposits:\n"
            for dep in pending_deposits:
                plan_name = Config.PLANS[dep[1]]["name"]
                tx_id = dep[4] or "N/A"
                text += f"  #{dep[0]} - {plan_name} - {Config.CURRENCY}{dep[2]:,.2f}\n  TXID: {tx_id} ({dep[3]})\n\n"

        if not investments and not pending_deposits:
            text += "You have no active investments.\n\nStart investing today!"
        elif investments:
            total_active = total_earned = 0
            for inv in investments:
                plan_name = Config.PLANS[inv["plan_type"]]["name"]
                status = "Active" if inv["status"] == "active" else "Completed"
                text += (
                    f"{plan_name} - {status}\n"
                    f"   Amount: {Config.CURRENCY}{inv['amount']:,.2f}\n"
                    f"   Earned: {Config.CURRENCY}{inv['total_earned']:,.2f}\n"
                    f"   {inv['start_date'][:10]} to {inv['end_date'][:10]}\n\n"
                )
                if inv["status"] == "active":
                    total_active += inv["amount"]
                total_earned += inv["total_earned"]
            text += (
                f"-------------------------\n"
                f"Active: {Config.CURRENCY}{total_active:,.2f}\n"
                f"Earned: {Config.CURRENCY}{total_earned:,.2f}\n"
                f"Balance: {Config.CURRENCY}{user['balance']:,.2f}"
            )

        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    async def withdraw_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not Config.ENABLE_WITHDRAWAL:
            await query.edit_message_text("Withdrawal system is currently disabled.", reply_markup=Keyboards.back_menu())
            return ConversationHandler.END
        user = self.user_manager.get_user(update.effective_user.id)
        text = (
            f"Withdrawal Request\n"
            f"-------------------------\n"
            f"Available Balance: {Config.CURRENCY}{user['balance']:,.2f}\n\n"
            f"Enter the amount you want to withdraw ({Config.CURRENCY}):"
        )
        await query.edit_message_text(text)
        return ENTERING_WITHDRAW_AMOUNT

    async def withdraw_amount_entered(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.callback_query:
            await update.callback_query.answer()
        user = self.user_manager.get_user(update.effective_user.id)
        try:
            text = update.message.text.strip()
            text = text.replace(Config.CURRENCY, "").replace("$", "").replace("€", "").replace("£", "")
            text = text.replace(",", "")
            amount = float(text)
        except ValueError:
            await update.message.reply_text("Invalid amount! Please enter a valid number.", reply_markup=Keyboards.back_menu())
            return ENTERING_WITHDRAW_AMOUNT
        if amount > user["balance"]:
            await update.message.reply_text(f"Insufficient balance! Available: {Config.CURRENCY}{user['balance']:,.2f}", reply_markup=Keyboards.back_menu())
            return ENTERING_WITHDRAW_AMOUNT
        if amount < Config.MIN_INVESTMENT:
            await update.message.reply_text(f"Minimum withdrawal is {Config.CURRENCY}{Config.MIN_INVESTMENT}!", reply_markup=Keyboards.back_menu())
            return ENTERING_WITHDRAW_AMOUNT

        self.db.execute("""
            INSERT INTO transactions (user_id, type, amount, status, method, details, created_at)
            VALUES (?, 'withdrawal', ?, 'pending', 'manual', ?, ?)
        """, (update.effective_user.id, amount, "Manual withdrawal request", datetime.now().isoformat()))
        self.db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, update.effective_user.id))

        text = (
            f"Withdrawal Request Submitted!\n\n"
            f"Amount: {Config.CURRENCY}{amount:,.2f}\n"
            f"Status: Pending\n"
            f"Will be processed within 24 hours."
        )
        await update.message.reply_text(text, reply_markup=Keyboards.back_menu())
        return ConversationHandler.END

    async def referral(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if not Config.ENABLE_REFERRAL:
            await query.edit_message_text("Referral system is currently disabled.", reply_markup=Keyboards.back_menu())
            return
        user = self.user_manager.get_user(update.effective_user.id)
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user['referral_code']}"
        ref_count = self.db.fetchone("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (update.effective_user.id,))[0]
        ref_bonus = self.db.fetchone("SELECT COALESCE(SUM(bonus_amount), 0) FROM referrals WHERE referrer_id = ?", (update.effective_user.id,))[0]
        text = (
            f"Your Referral Program\n"
            f"-------------------------\n\n"
            f"Your Referral Link:\n{ref_link}\n\n"
            f"Total Referrals: {ref_count}\n"
            f"Total Bonus Earned: {Config.CURRENCY}{ref_bonus:,.2f}\n\n"
            f"Earn {Config.REFERRAL_BONUS_PERCENT}% bonus on every referral investment!"
        )
        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    async def support(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        text = (
            f"Customer Support\n"
            f"-------------------------\n\n"
            f"Email: {Config.SUPPORT_EMAIL}\n"
            f"Telegram: {Config.SUPPORT_TELEGRAM}\n"
            f"Support Hours: 9 AM - 9 PM (UTC)"
        )
        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    async def help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        text = (
            f"Help & Commands\n"
            f"-------------------------\n\n"
            f"/start - Start the bot\n"
            f"/invest - Invest money\n"
            f"/portfolio - View portfolio\n"
            f"/withdraw - Withdraw earnings\n"
            f"/referral - Get referral link\n"
            f"/help - Show this help\n"
            f"/admin - Admin panel (admins only)"
        )
        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        stats = self.user_manager.get_stats()
        text = (
            f"Platform Statistics\n"
            f"-------------------------\n\n"
            f"Total Users: {stats['total_users']}\n"
            f"Total Active Investments: {Config.CURRENCY}{stats['total_investments']:,.2f}\n"
            f"Total Earned: {Config.CURRENCY}{stats['total_earned']:,.2f}\n"
            f"Pending Deposits: {stats['pending_deposits']}\n"
            f"Pending Withdrawals: {Config.CURRENCY}{stats['pending_withdrawals']:,.2f}"
        )
        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("Access denied! You are not an admin.")
            return
        await update.message.reply_text("Admin Panel\n-------------------------", reply_markup=Keyboards.admin_menu())

    async def admin_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        stats = self.user_manager.get_stats()
        text = (
            f"Admin Statistics\n"
            f"-------------------------\n\n"
            f"Total Users: {stats['total_users']}\n"
            f"Total Investments: {Config.CURRENCY}{stats['total_investments']:,.2f}\n"
            f"Total Earned: {Config.CURRENCY}{stats['total_earned']:,.2f}\n"
            f"Pending Deposits: {stats['pending_deposits']}\n"
            f"Pending Withdrawals: {Config.CURRENCY}{stats['pending_withdrawals']:,.2f}"
        )
        await query.edit_message_text(text, reply_markup=Keyboards.admin_menu())

    async def admin_deposits(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        deposits = self.db.fetchall("""
            SELECT d.id, d.user_id, u.username, u.first_name, d.plan_type, d.amount, d.status, d.transaction_id, d.created_at 
            FROM deposit_requests d 
            JOIN users u ON d.user_id = u.user_id 
            WHERE d.status IN ('pending', 'awaiting_approval') 
            ORDER BY d.created_at DESC
        """)
        if not deposits:
            text = "No pending deposits!"
        else:
            text = f"Pending Deposits\n-------------------------\n\n"
            for dep in deposits:
                plan_name = Config.PLANS[dep[4]]["name"]
                tx_id = dep[7] or "N/A"
                text += (
                    f"ID: #{dep[0]}\n"
                    f"User: {dep[3]} (@{dep[2] or 'N/A'})\n"
                    f"Plan: {plan_name}\n"
                    f"Amount: {Config.CURRENCY}{dep[5]:,.2f}\n"
                    f"TXID: {tx_id}\n"
                    f"Status: {dep[6]}\n"
                    f"Date: {dep[8][:10]}\n\n"
                )
        await query.edit_message_text(text, reply_markup=Keyboards.admin_menu())

    async def admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        users = self.db.fetchall("SELECT user_id, username, first_name, balance, total_invested, joined_date FROM users ORDER BY joined_date DESC LIMIT 20")
        text = f"Recent Users (Last 20)\n-------------------------\n\n"
        for user in users:
            text += f"ID: {user[0]} | @{user[1] or 'N/A'}\nName: {user[2]}\nBalance: {Config.CURRENCY}{user[3]:,.2f}\nInvested: {Config.CURRENCY}{user[4]:,.2f}\nJoined: {user[5][:10]}\n\n"
        await query.edit_message_text(text, reply_markup=Keyboards.admin_menu())

    async def admin_withdrawals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        withdrawals = self.db.fetchall("SELECT t.id, t.user_id, u.username, t.amount, t.created_at FROM transactions t JOIN users u ON t.user_id = u.user_id WHERE t.type = 'withdrawal' AND t.status = 'pending' ORDER BY t.created_at DESC")
        if not withdrawals:
            text = "No pending withdrawals!"
        else:
            text = f"Pending Withdrawals\n-------------------------\n\n"
            for w in withdrawals:
                text += f"ID: {w[0]} | User: {w[1]} (@{w[2] or 'N/A'})\nAmount: {Config.CURRENCY}{w[3]:,.2f}\nDate: {w[4][:10]}\n\n"
        await query.edit_message_text(text, reply_markup=Keyboards.admin_menu())

    async def admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("Broadcast Feature\n\nTo broadcast: /broadcast Your message here", reply_markup=Keyboards.admin_menu())

    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("Access denied!")
            return
        message = ' '.join(context.args)
        if not message:
            await update.message.reply_text("Usage: /broadcast Your message")
            return
        users = self.db.fetchall("SELECT user_id FROM users")
        sent_count = failed_count = 0
        for user in users:
            try:
                await context.bot.send_message(chat_id=user[0], text=f"Announcement\n-------------------------\n\n{message}")
                sent_count += 1
            except Exception:
                failed_count += 1
        await update.message.reply_text(f"Broadcast Complete!\nSent: {sent_count}\nFailed: {failed_count}")

# ===================================================================
# MAIN
# ===================================================================

def main():
    bot = InvestmentBot()
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Global commands
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_menu))
    application.add_handler(CommandHandler("admin", bot.admin_panel))
    application.add_handler(CommandHandler("broadcast", bot.broadcast_message))

    # Global callbacks
    application.add_handler(CallbackQueryHandler(bot.portfolio, pattern="^portfolio$"))
    application.add_handler(CallbackQueryHandler(bot.referral, pattern="^referral$"))
    application.add_handler(CallbackQueryHandler(bot.support, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(bot.help_menu, pattern="^help_menu$"))
    application.add_handler(CallbackQueryHandler(bot.stats, pattern="^stats$"))

    # Admin callbacks
    application.add_handler(CallbackQueryHandler(bot.admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(bot.admin_users, pattern="^admin_users$"))
    application.add_handler(CallbackQueryHandler(bot.admin_deposits, pattern="^admin_deposits$"))
    application.add_handler(CallbackQueryHandler(bot.admin_withdrawals, pattern="^admin_withdrawals$"))
    application.add_handler(CallbackQueryHandler(bot.admin_broadcast, pattern="^admin_broadcast$"))
    application.add_handler(CallbackQueryHandler(bot.approve_deposit, pattern="^approve_deposit_"))
    application.add_handler(CallbackQueryHandler(bot.reject_deposit, pattern="^reject_deposit_"))

    # Global back button
    application.add_handler(CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$"))

    # Investment conversation
    invest_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.invest_callback, pattern="^invest$")],
        states={
            SELECTING_PLAN: [
                CallbackQueryHandler(bot.plan_selected, pattern="^plan_"),
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ],
            ENTERING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.amount_entered),
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ],
            ENTERING_TRANSACTION_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.transaction_id_entered),
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ],
            CONFIRMING_DEPOSIT: [
                CallbackQueryHandler(bot.confirm_deposit, pattern="^confirm_deposit$"),
                CallbackQueryHandler(bot.cancel_deposit, pattern="^cancel_deposit$"),
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ]
        },
        fallbacks=[
            CommandHandler("start", bot.start),
            CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Please use the buttons or type /start to go back to menu.", reply_markup=Keyboards.back_menu()))
        ]
    )

    # Withdrawal conversation
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.withdraw_start, pattern="^withdraw$")],
        states={
            ENTERING_WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.withdraw_amount_entered),
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ]
        },
        fallbacks=[
            CommandHandler("start", bot.start),
            CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u, c: u.message.reply_text("Please use the buttons or type /start to go back to menu.", reply_markup=Keyboards.back_menu()))
        ]
    )

    application.add_handler(invest_conv)
    application.add_handler(withdraw_conv)

    print("=" * 60)
    print("INVESTMENT PRO BOT - DEPOSIT FLOW READY")
    print("=" * 60)
    print(f"Token: {Config.BOT_TOKEN[:20]}...")
    print(f"Admins: {Config.ADMIN_IDS}")
    print(f"Wallet: {Config.WALLET_ADDRESS[:20]}...")
    print("=" * 60)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
