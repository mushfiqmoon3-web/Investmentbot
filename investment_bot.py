"""
===================================================================
INVESTMENT PRO BOT - Professional Telegram Investment Bot
===================================================================
Built for: Client Project
Language: English
Features:
  - Portfolio Tracking & Management
  - Real-time Investment Plans
  - Profit/Loss Analysis
  - Multi-user Support
  - Admin Dashboard
  - Referral System
  - Withdrawal Management
  - Beautiful Interactive UI
  - .env Configuration Support

Requirements: python-telegram-bot v20+, python-dotenv, sqlite3
===================================================================
"""

import logging
import sqlite3
import asyncio
import random
import string
import os
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from dotenv import load_dotenv
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters
)

# Load environment variables from .env file
load_dotenv()

# ===================================================================
# CONFIGURATION (Reads from .env file)
# ===================================================================

class Config:
    # Bot Token (from .env)
    BOT_TOKEN = os.getenv("BOT_TOKEN", "")

    # Admin Configuration (from .env)
    ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "123456789").split(",") if x.strip()]

    # Database (from .env)
    DB_PATH = os.getenv("DB_PATH", "investment_bot.db")

    # Currency Settings (from .env)
    CURRENCY = os.getenv("CURRENCY", "$")
    CURRENCY_NAME = os.getenv("CURRENCY_NAME", "USD")

    # Investment Limits (from .env)
    MIN_INVESTMENT = float(os.getenv("MIN_INVESTMENT", 10))
    MAX_INVESTMENT = float(os.getenv("MAX_INVESTMENT", 100000))

    # Referral System (from .env)
    REFERRAL_BONUS_PERCENT = int(os.getenv("REFERRAL_BONUS_PERCENT", 5))
    ENABLE_REFERRAL = os.getenv("ENABLE_REFERRAL", "true").lower() == "true"
    ENABLE_WITHDRAWAL = os.getenv("ENABLE_WITHDRAWAL", "true").lower() == "true"

    # Support (from .env)
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@investmentpro.com")
    SUPPORT_TELEGRAM = os.getenv("SUPPORT_TELEGRAM", "@admin_username")

    # Debug (from .env)
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

    # Investment Plans (from .env)
    PLANS = {
        "starter": {
            "name": "Starter",
            "min": float(os.getenv("STARTER_MIN", 10)),
            "max": float(os.getenv("STARTER_MAX", 500)),
            "daily_rate": float(os.getenv("STARTER_RATE", 0.01)),
            "duration": int(os.getenv("STARTER_DURATION", 30)),
            "description": "Perfect for beginners"
        },
        "silver": {
            "name": "Silver",
            "min": float(os.getenv("SILVER_MIN", 500)),
            "max": float(os.getenv("SILVER_MAX", 2500)),
            "daily_rate": float(os.getenv("SILVER_RATE", 0.015)),
            "duration": int(os.getenv("SILVER_DURATION", 60)),
            "description": "Balanced growth plan"
        },
        "gold": {
            "name": "Gold",
            "min": float(os.getenv("GOLD_MIN", 2500)),
            "max": float(os.getenv("GOLD_MAX", 10000)),
            "daily_rate": float(os.getenv("GOLD_RATE", 0.02)),
            "duration": int(os.getenv("GOLD_DURATION", 90)),
            "description": "High return investment"
        },
        "platinum": {
            "name": "Platinum",
            "min": float(os.getenv("PLATINUM_MIN", 10000)),
            "max": float(os.getenv("PLATINUM_MAX", 100000)),
            "daily_rate": float(os.getenv("PLATINUM_RATE", 0.025)),
            "duration": int(os.getenv("PLATINUM_DURATION", 120)),
            "description": "Premium elite plan"
        },
    }

# ===================================================================
# DATABASE MANAGEMENT
# ===================================================================

class Database:
    def __init__(self):
        self.conn = sqlite3.connect(Config.DB_PATH, check_same_thread=False)
        self.create_tables()

    def create_tables(self):
        cursor = self.conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                phone TEXT,
                email TEXT,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                balance REAL DEFAULT 0,
                total_invested REAL DEFAULT 0,
                total_earned REAL DEFAULT 0,
                total_withdrawn REAL DEFAULT 0,
                joined_date TEXT,
                status TEXT DEFAULT 'active'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS investments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                plan_type TEXT,
                amount REAL,
                daily_rate REAL,
                duration INTEGER,
                start_date TEXT,
                end_date TEXT,
                total_return REAL,
                daily_earning REAL,
                status TEXT DEFAULT 'active',
                total_earned REAL DEFAULT 0,
                last_calculation TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount REAL,
                status TEXT,
                method TEXT,
                details TEXT,
                created_at TEXT,
                processed_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referred_id INTEGER,
                bonus_amount REAL,
                status TEXT DEFAULT 'pending',
                created_at TEXT,
                FOREIGN KEY (referrer_id) REFERENCES users (user_id),
                FOREIGN KEY (referred_id) REFERENCES users (user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_earnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                investment_id INTEGER,
                user_id INTEGER,
                amount REAL,
                date TEXT,
                FOREIGN KEY (investment_id) REFERENCES investments (id)
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
# USER MANAGEMENT
# ===================================================================

class UserManager:
    def __init__(self, db: Database):
        self.db = db

    def generate_referral_code(self) -> str:
        return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

    def get_or_create_user(self, user_id: int, username: str, first_name: str, 
                          last_name: str = None, referral_code: str = None) -> dict:
        user = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))

        if not user:
            ref_code = self.generate_referral_code()
            referred_by = None

            if referral_code and Config.ENABLE_REFERRAL:
                referrer = self.db.fetchone(
                    "SELECT user_id FROM users WHERE referral_code = ?", (referral_code,)
                )
                if referrer:
                    referred_by = referrer[0]

            self.db.execute("""
                INSERT INTO users (user_id, username, first_name, last_name, 
                                   referral_code, referred_by, joined_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, username, first_name, last_name, ref_code, referred_by, 
                  datetime.now().isoformat()))

            if referred_by and Config.ENABLE_REFERRAL:
                self.db.execute("""
                    INSERT INTO referrals (referrer_id, referred_id, bonus_amount, created_at)
                    VALUES (?, ?, ?, ?)
                """, (referred_by, user_id, 0, datetime.now().isoformat()))

            user = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))

        return {
            "user_id": user[0],
            "username": user[1],
            "first_name": user[2],
            "last_name": user[3],
            "phone": user[4],
            "balance": user[8],
            "total_invested": user[9],
            "total_earned": user[10],
            "total_withdrawn": user[11],
            "referral_code": user[7],
            "status": user[13]
        }

    def get_user(self, user_id: int) -> Optional[dict]:
        user = self.db.fetchone("SELECT * FROM users WHERE user_id = ?", (user_id,))
        if not user:
            return None
        return {
            "user_id": user[0],
            "username": user[1],
            "first_name": user[2],
            "balance": user[8],
            "total_invested": user[9],
            "total_earned": user[10],
            "referral_code": user[7],
            "status": user[13]
        }

    def update_balance(self, user_id: int, amount: float):
        self.db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", 
                       (amount, user_id))

    def get_stats(self) -> dict:
        total_users = self.db.fetchone("SELECT COUNT(*) FROM users")[0]
        total_investments = self.db.fetchone(
            "SELECT COALESCE(SUM(amount), 0) FROM investments WHERE status = 'active'"
        )[0]
        total_earned = self.db.fetchone(
            "SELECT COALESCE(SUM(total_earned), 0) FROM investments"
        )[0]
        pending_withdrawals = self.db.fetchone(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type = 'withdrawal' AND status = 'pending'"
        )[0]

        return {
            "total_users": total_users,
            "total_investments": total_investments,
            "total_earned": total_earned,
            "pending_withdrawals": pending_withdrawals
        }

# ===================================================================
# INVESTMENT MANAGEMENT
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
            INSERT INTO investments 
            (user_id, plan_type, amount, daily_rate, duration, start_date, 
             end_date, total_return, daily_earning, last_calculation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, plan_type, amount, plan["daily_rate"], plan["duration"], 
              start_date.isoformat(), end_date.isoformat(), total_return, 
              daily_earning, start_date.isoformat()))

        investment_id = cursor.lastrowid

        self.db.execute(
            "UPDATE users SET total_invested = total_invested + ? WHERE user_id = ?",
            (amount, user_id)
        )

        return {
            "success": True,
            "investment_id": investment_id,
            "plan": plan["name"],
            "amount": amount,
            "duration": plan["duration"],
            "daily_earning": daily_earning,
            "total_return": total_return
        }

    def get_user_investments(self, user_id: int) -> List[dict]:
        rows = self.db.fetchall(
            "SELECT * FROM investments WHERE user_id = ? ORDER BY start_date DESC", 
            (user_id,)
        )
        investments = []
        for row in rows:
            investments.append({
                "id": row[0],
                "plan_type": row[2],
                "amount": row[3],
                "daily_rate": row[4],
                "duration": row[5],
                "start_date": row[6],
                "end_date": row[7],
                "total_return": row[8],
                "daily_earning": row[9],
                "status": row[10],
                "total_earned": row[11]
            })
        return investments

    def calculate_daily_earnings(self):
        today = datetime.now().date().isoformat()

        active_investments = self.db.fetchall(
            "SELECT * FROM investments WHERE status = 'active' AND date(last_calculation) < ?",
            (today,)
        )

        for inv in active_investments:
            inv_id = inv[0]
            user_id = inv[1]
            daily_earning = inv[9]

            self.db.execute("""
                INSERT INTO daily_earnings (investment_id, user_id, amount, date)
                VALUES (?, ?, ?, ?)
            """, (inv_id, user_id, daily_earning, today))

            self.db.execute("""
                UPDATE investments 
                SET total_earned = total_earned + ?, last_calculation = ?
                WHERE id = ?
            """, (daily_earning, datetime.now().isoformat(), inv_id))

            self.db.execute("""
                UPDATE users 
                SET balance = balance + ?, total_earned = total_earned + ?
                WHERE user_id = ?
            """, (daily_earning, daily_earning, user_id))

            end_date = datetime.fromisoformat(inv[7])
            if datetime.now() >= end_date:
                self.db.execute(
                    "UPDATE investments SET status = 'completed' WHERE id = ?", 
                    (inv_id,)
                )

# ===================================================================
# KEYBOARD BUILDERS
# ===================================================================

class Keyboards:
    @staticmethod
    def main_menu() -> InlineKeyboardMarkup:
        keyboard = [
            [
                InlineKeyboardButton("Invest", callback_data="invest"),
                InlineKeyboardButton("Portfolio", callback_data="portfolio")
            ],
            [
                InlineKeyboardButton("Withdraw", callback_data="withdraw"),
                InlineKeyboardButton("Referral", callback_data="referral")
            ],
            [
                InlineKeyboardButton("Support", callback_data="support"),
                InlineKeyboardButton("Help", callback_data="help_menu")
            ],
            [
                InlineKeyboardButton("Statistics", callback_data="stats")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def plans_menu() -> InlineKeyboardMarkup:
        keyboard = []
        for key, plan in Config.PLANS.items():
            btn_text = f"{plan['name']} - {Config.CURRENCY}{plan['min']:,} to {Config.CURRENCY}{plan['max']:,}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"plan_{key}")])
        keyboard.append([InlineKeyboardButton("Back", callback_data="back_menu")])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def confirm_menu() -> InlineKeyboardMarkup:
        keyboard = [
            [
                InlineKeyboardButton("Confirm", callback_data="confirm_invest"),
                InlineKeyboardButton("Cancel", callback_data="cancel_invest")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def back_menu() -> InlineKeyboardMarkup:
        keyboard = [[InlineKeyboardButton("Back to Menu", callback_data="back_menu")]]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_menu() -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton("Statistics", callback_data="admin_stats")],
            [InlineKeyboardButton("Users List", callback_data="admin_users")],
            [InlineKeyboardButton("Pending Withdrawals", callback_data="admin_withdrawals")],
            [InlineKeyboardButton("Broadcast Message", callback_data="admin_broadcast")],
            [InlineKeyboardButton("Back", callback_data="back_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

# ===================================================================
# CONVERSATION STATES
# ===================================================================

SELECTING_PLAN, ENTERING_AMOUNT, CONFIRMING_INVESTMENT = range(3)
ENTERING_WITHDRAW_AMOUNT = 4

# ===================================================================
# BOT HANDLERS
# ===================================================================

class InvestmentBot:
    def __init__(self):
        self.db = Database()
        self.user_manager = UserManager(self.db)
        self.investment_manager = InvestmentManager(self.db)

    # ===================================================================
    # START COMMAND
    # ===================================================================
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        referral_code = context.args[0] if context.args else None

        user_data = self.user_manager.get_or_create_user(
            user.id, user.username, user.first_name, user.last_name, referral_code
        )

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

    # ===================================================================
    # BACK TO MENU - FIXED: Works from any state
    # ===================================================================
    async def back_to_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        user = self.user_manager.get_user(update.effective_user.id)

        welcome_text = (
            f"Main Menu\n"
            f"-------------------------\n\n"
            f"Balance: {Config.CURRENCY}{user['balance']:,.2f}\n"
            f"Total Invested: {Config.CURRENCY}{user['total_invested']:,.2f}\n"
            f"Total Earned: {Config.CURRENCY}{user['total_earned']:,.2f}\n"
            f"Total Withdrawn: {Config.CURRENCY}{user['total_withdrawn']:,.2f}\n\n"
            f"What would you like to do?"
        )

        await query.edit_message_text(welcome_text, reply_markup=Keyboards.main_menu())
        return ConversationHandler.END

    # ===================================================================
    # INVESTMENT FLOW
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
        user = self.user_manager.get_user(update.effective_user.id)

        try:
            amount = float(update.message.text.replace(",", "").replace(Config.CURRENCY, ""))
        except ValueError:
            await update.message.reply_text(
                "Invalid amount! Please enter a valid number.",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_AMOUNT

        plan_type = context.user_data.get("selected_plan")
        plan = Config.PLANS[plan_type]

        if amount < plan["min"]:
            await update.message.reply_text(
                f"Minimum investment is {Config.CURRENCY}{plan['min']:,}!",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_AMOUNT

        if amount > plan["max"]:
            await update.message.reply_text(
                f"Maximum investment is {Config.CURRENCY}{plan['max']:,}!",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_AMOUNT

        context.user_data["investment_amount"] = amount

        daily_earning = amount * plan["daily_rate"]
        total_return = daily_earning * plan["duration"]

        confirm_text = (
            f"Investment Confirmation\n"
            f"-------------------------\n"
            f"Amount: {Config.CURRENCY}{amount:,.2f}\n"
            f"Plan: {plan['name']}\n"
            f"Duration: {plan['duration']} days\n"
            f"Daily Earning: {Config.CURRENCY}{daily_earning:,.2f}\n"
            f"Total Return: {Config.CURRENCY}{total_return:,.2f}\n"
            f"-------------------------\n\n"
            f"Confirm this investment?"
        )

        await update.message.reply_text(
            confirm_text,
            reply_markup=Keyboards.confirm_menu()
        )
        return CONFIRMING_INVESTMENT

    async def confirm_investment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        plan_type = context.user_data.get("selected_plan")
        amount = context.user_data.get("investment_amount")

        result = self.investment_manager.create_investment(
            update.effective_user.id, plan_type, amount
        )

        if result["success"]:
            text = (
                f"Investment Successful!\n\n"
                f"Plan: {result['plan']}\n"
                f"Amount: {Config.CURRENCY}{result['amount']:,.2f}\n"
                f"Duration: {result['duration']} days\n"
                f"Daily Earning: {Config.CURRENCY}{result['daily_earning']:,.2f}\n"
                f"Total Return: {Config.CURRENCY}{result['total_return']:,.2f}\n\n"
                f"Your investment is now active!\n"
                f"Earnings are calculated daily."
            )
        else:
            text = "Investment failed. Please try again."

        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())
        return ConversationHandler.END

    async def cancel_investment(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        await query.edit_message_text(
            "Investment cancelled.",
            reply_markup=Keyboards.back_menu()
        )
        return ConversationHandler.END

    # ===================================================================
    # PORTFOLIO
    # ===================================================================
    async def portfolio(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        user = self.user_manager.get_user(update.effective_user.id)
        investments = self.investment_manager.get_user_investments(update.effective_user.id)

        if not investments:
            text = (
                f"Your Portfolio\n"
                f"-------------------------\n\n"
                f"You have no active investments.\n\n"
                f"Start investing today to earn daily profits!"
            )
        else:
            text = (
                f"Your Portfolio\n"
                f"-------------------------\n\n"
            )
            total_active = 0
            total_earned = 0

            for inv in investments:
                plan_name = Config.PLANS[inv["plan_type"]]["name"]
                status_emoji = "Active" if inv["status"] == "active" else "Completed"
                text += (
                    f"{plan_name} - {status_emoji}\n"
                    f"   Amount: {Config.CURRENCY}{inv['amount']:,.2f}\n"
                    f"   Earned: {Config.CURRENCY}{inv['total_earned']:,.2f}\n"
                    f"   {inv['start_date'][:10]} to {inv['end_date'][:10]}\n\n"
                )

                if inv["status"] == "active":
                    total_active += inv["amount"]
                total_earned += inv["total_earned"]

            text += (
                f"-------------------------\n"
                f"Active Investment: {Config.CURRENCY}{total_active:,.2f}\n"
                f"Total Earned: {Config.CURRENCY}{total_earned:,.2f}\n"
                f"Current Balance: {Config.CURRENCY}{user['balance']:,.2f}"
            )

        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    # ===================================================================
    # WITHDRAWAL
    # ===================================================================
    async def withdraw_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not Config.ENABLE_WITHDRAWAL:
            await query.edit_message_text(
                "Withdrawal system is currently disabled.",
                reply_markup=Keyboards.back_menu()
            )
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
        user = self.user_manager.get_user(update.effective_user.id)

        try:
            amount = float(update.message.text.replace(",", "").replace(Config.CURRENCY, ""))
        except ValueError:
            await update.message.reply_text(
                "Invalid amount! Please enter a valid number.",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_WITHDRAW_AMOUNT

        if amount > user["balance"]:
            await update.message.reply_text(
                f"Insufficient balance!\n"
                f"Available: {Config.CURRENCY}{user['balance']:,.2f}",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_WITHDRAW_AMOUNT

        if amount < Config.MIN_INVESTMENT:
            await update.message.reply_text(
                f"Minimum withdrawal is {Config.CURRENCY}{Config.MIN_INVESTMENT}!",
                reply_markup=Keyboards.back_menu()
            )
            return ENTERING_WITHDRAW_AMOUNT

        # Create withdrawal request
        self.db.execute("""
            INSERT INTO transactions (user_id, type, amount, status, method, details, created_at)
            VALUES (?, 'withdrawal', ?, 'pending', 'manual', ?, ?)
        """, (update.effective_user.id, amount, "Manual withdrawal request", 
              datetime.now().isoformat()))

        # Deduct balance
        self.db.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ?",
            (amount, update.effective_user.id)
        )

        text = (
            f"Withdrawal Request Submitted!\n\n"
            f"Amount: {Config.CURRENCY}{amount:,.2f}\n"
            f"Status: Pending\n"
            f"Will be processed within 24 hours.\n\n"
            f"You will receive a notification once processed."
        )

        await update.message.reply_text(text, reply_markup=Keyboards.back_menu())
        return ConversationHandler.END

    # ===================================================================
    # REFERRAL SYSTEM
    # ===================================================================
    async def referral(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        if not Config.ENABLE_REFERRAL:
            await query.edit_message_text(
                "Referral system is currently disabled.",
                reply_markup=Keyboards.back_menu()
            )
            return

        user = self.user_manager.get_user(update.effective_user.id)
        bot_info = await context.bot.get_me()

        ref_link = f"https://t.me/{bot_info.username}?start={user['referral_code']}"

        ref_count = self.db.fetchone(
            "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?",
            (update.effective_user.id,)
        )[0]

        ref_bonus = self.db.fetchone(
            "SELECT COALESCE(SUM(bonus_amount), 0) FROM referrals WHERE referrer_id = ?",
            (update.effective_user.id,)
        )[0]

        text = (
            f"Your Referral Program\n"
            f"-------------------------\n\n"
            f"Your Referral Link:\n"
            f"{ref_link}\n\n"
            f"Total Referrals: {ref_count}\n"
            f"Total Bonus Earned: {Config.CURRENCY}{ref_bonus:,.2f}\n\n"
            f"Earn {Config.REFERRAL_BONUS_PERCENT}% bonus on every referral investment!\n"
            f"Share your link with friends and start earning!"
        )

        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    # ===================================================================
    # SUPPORT
    # ===================================================================
    async def support(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        text = (
            f"Customer Support\n"
            f"-------------------------\n\n"
            f"Need help? Contact us:\n\n"
            f"Email: {Config.SUPPORT_EMAIL}\n"
            f"Telegram: {Config.SUPPORT_TELEGRAM}\n"
            f"Support Hours: 9 AM - 9 PM (UTC)\n\n"
            f"We typically respond within 2 hours."
        )

        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    # ===================================================================
    # HELP
    # ===================================================================
    async def help_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        text = (
            f"Help & Commands\n"
            f"-------------------------\n\n"
            f"Getting Started:\n"
            f"1. Click 'Invest' to choose a plan\n"
            f"2. Enter your investment amount\n"
            f"3. Confirm and start earning daily!\n\n"
            f"Commands:\n"
            f"/start - Start the bot\n"
            f"/invest - Invest money\n"
            f"/portfolio - View your portfolio\n"
            f"/withdraw - Withdraw earnings\n"
            f"/referral - Get referral link\n"
            f"/help - Show this help\n"
            f"/admin - Admin panel (admins only)\n\n"
            f"Tip: Use the menu buttons for easy navigation!"
        )

        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    # ===================================================================
    # STATISTICS
    # ===================================================================
    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        stats = self.user_manager.get_stats()

        text = (
            f"Platform Statistics\n"
            f"-------------------------\n\n"
            f"Total Users: {stats['total_users']}\n"
            f"Total Active Investments: {Config.CURRENCY}{stats['total_investments']:,.2f}\n"
            f"Total Earned by Users: {Config.CURRENCY}{stats['total_earned']:,.2f}\n"
            f"Pending Withdrawals: {Config.CURRENCY}{stats['pending_withdrawals']:,.2f}\n\n"
            f"Join thousands of investors earning daily!"
        )

        await query.edit_message_text(text, reply_markup=Keyboards.back_menu())

    # ===================================================================
    # ADMIN PANEL
    # ===================================================================
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("Access denied! You are not an admin.")
            return

        await update.message.reply_text(
            "Admin Panel\n-------------------------",
            reply_markup=Keyboards.admin_menu()
        )

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
            f"Pending Withdrawals: {Config.CURRENCY}{stats['pending_withdrawals']:,.2f}"
        )

        await query.edit_message_text(text, reply_markup=Keyboards.admin_menu())

    async def admin_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        users = self.db.fetchall(
            "SELECT user_id, username, first_name, balance, total_invested, joined_date "
            "FROM users ORDER BY joined_date DESC LIMIT 20"
        )

        text = f"Recent Users (Last 20)\n-------------------------\n\n"
        for user in users:
            text += (
                f"ID: {user[0]} | @{user[1] or 'N/A'}\n"
                f"Name: {user[2]}\n"
                f"Balance: {Config.CURRENCY}{user[3]:,.2f}\n"
                f"Invested: {Config.CURRENCY}{user[4]:,.2f}\n"
                f"Joined: {user[5][:10]}\n\n"
            )

        await query.edit_message_text(text, reply_markup=Keyboards.admin_menu())

    async def admin_withdrawals(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        withdrawals = self.db.fetchall(
            "SELECT t.id, t.user_id, u.username, t.amount, t.created_at "
            "FROM transactions t JOIN users u ON t.user_id = u.user_id "
            "WHERE t.type = 'withdrawal' AND t.status = 'pending' "
            "ORDER BY t.created_at DESC"
        )

        if not withdrawals:
            text = "No pending withdrawals!"
        else:
            text = f"Pending Withdrawals\n-------------------------\n\n"
            for w in withdrawals:
                text += (
                    f"ID: {w[0]} | User: {w[1]} (@{w[2] or 'N/A'})\n"
                    f"Amount: {Config.CURRENCY}{w[3]:,.2f}\n"
                    f"Date: {w[4][:10]}\n\n"
                )

        await query.edit_message_text(text, reply_markup=Keyboards.admin_menu())

    async def admin_broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        await query.edit_message_text(
            "Broadcast Feature\n\n"
            "To broadcast a message to all users, use:\n"
            "/broadcast Your message here",
            reply_markup=Keyboards.admin_menu()
        )

    async def broadcast_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id not in Config.ADMIN_IDS:
            await update.message.reply_text("Access denied!")
            return

        message = ' '.join(context.args)
        if not message:
            await update.message.reply_text("Please provide a message. Usage: /broadcast Your message")
            return

        users = self.db.fetchall("SELECT user_id FROM users")
        sent_count = 0
        failed_count = 0

        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user[0],
                    text=f"Announcement\n-------------------------\n\n{message}"
                )
                sent_count += 1
            except Exception:
                failed_count += 1

        await update.message.reply_text(
            f"Broadcast Complete!\n"
            f"Sent: {sent_count}\n"
            f"Failed: {failed_count}"
        )

# ===================================================================
# MAIN APPLICATION
# ===================================================================

def main():
    # Initialize bot
    bot = InvestmentBot()

    # Create application
    application = Application.builder().token(Config.BOT_TOKEN).build()

    # Set bot commands
    commands = [
        BotCommand("start", "Start the bot"),
        BotCommand("invest", "Invest money"),
        BotCommand("portfolio", "View portfolio"),
        BotCommand("withdraw", "Withdraw money"),
        BotCommand("referral", "Get referral link"),
        BotCommand("help", "Show help"),
        BotCommand("admin", "Admin panel")
    ]

    # ===================================================================
    # FIXED: Conversation handlers with back button in EVERY state
    # ===================================================================

    # Investment conversation handler
    invest_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.invest_callback, pattern="^invest$")],
        states={
            SELECTING_PLAN: [
                CallbackQueryHandler(bot.plan_selected, pattern="^plan_"),
                # FIXED: Back button handler in this state
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ],
            ENTERING_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.amount_entered),
                # FIXED: Back button handler in this state
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ],
            CONFIRMING_INVESTMENT: [
                CallbackQueryHandler(bot.confirm_investment, pattern="^confirm_invest$"),
                CallbackQueryHandler(bot.cancel_investment, pattern="^cancel_invest$"),
                # FIXED: Back button handler in this state
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$"),
            CommandHandler("start", bot.start)
        ],
        per_message=True  # FIXED: Track callbacks per message
    )

    # Withdrawal conversation handler
    withdraw_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(bot.withdraw_start, pattern="^withdraw$")],
        states={
            ENTERING_WITHDRAW_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.withdraw_amount_entered),
                # FIXED: Back button handler in this state
                CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$")
            ]
        },
        fallbacks=[
            CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$"),
            CommandHandler("start", bot.start)
        ],
        per_message=True  # FIXED: Track callbacks per message
    )

    # ===================================================================
    # GLOBAL HANDLERS (Outside conversation - always active)
    # ===================================================================

    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_menu))
    application.add_handler(CommandHandler("admin", bot.admin_panel))
    application.add_handler(CommandHandler("broadcast", bot.broadcast_message))

    # Add conversation handlers
    application.add_handler(invest_conv)
    application.add_handler(withdraw_conv)

    # Global callback handlers (must be AFTER conversation handlers)
    application.add_handler(CallbackQueryHandler(bot.portfolio, pattern="^portfolio$"))
    application.add_handler(CallbackQueryHandler(bot.referral, pattern="^referral$"))
    application.add_handler(CallbackQueryHandler(bot.support, pattern="^support$"))
    application.add_handler(CallbackQueryHandler(bot.help_menu, pattern="^help_menu$"))
    application.add_handler(CallbackQueryHandler(bot.stats, pattern="^stats$"))

    # Admin callbacks
    application.add_handler(CallbackQueryHandler(bot.admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(bot.admin_users, pattern="^admin_users$"))
    application.add_handler(CallbackQueryHandler(bot.admin_withdrawals, pattern="^admin_withdrawals$"))
    application.add_handler(CallbackQueryHandler(bot.admin_broadcast, pattern="^admin_broadcast$"))

    # Global back button (catch-all for any remaining back clicks)
    application.add_handler(CallbackQueryHandler(bot.back_to_menu, pattern="^back_menu$"))

    # Start bot
    print("=" * 60)
    print("INVESTMENT PRO BOT STARTED!")
    print("=" * 60)
    print(f"Token: {Config.BOT_TOKEN[:20]}...")
    print(f"Admins: {Config.ADMIN_IDS}")
    print(f"Currency: {Config.CURRENCY_NAME} ({Config.CURRENCY})")
    print(f"Investment Plans: {len(Config.PLANS)}")
    print(f"Referral: {'Enabled' if Config.ENABLE_REFERRAL else 'Disabled'}")
    print(f"Withdrawal: {'Enabled' if Config.ENABLE_WITHDRAWAL else 'Disabled'}")
    print("=" * 60)

    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
