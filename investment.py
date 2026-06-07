
# Let's also create a requirements.txt file for easy installation
requirements = """python-telegram-bot>=20.0
"""

with open('/mnt/agents/output/requirements.txt', 'w') as f:
    f.write(requirements)

# Create a setup guide
setup_guide = """
═══════════════════════════════════════════════════════════════════
INVESTMENT PRO BOT - SETUP GUIDE
═══════════════════════════════════════════════════════════════════

1. INSTALL DEPENDENCIES
───────────────────────────────────────────────────────────────────
pip install -r requirements.txt

2. CONFIGURE THE BOT
───────────────────────────────────────────────────────────────────
Open investment_bot.py and update these settings in the Config class:

   ADMIN_IDS = [123456789]  # Replace with your Telegram User ID
   
   To find your Telegram User ID:
   - Message @userinfobot on Telegram
   - It will reply with your User ID

3. RUN THE BOT
───────────────────────────────────────────────────────────────────
python investment_bot.py

4. SET UP BOT COMMANDS IN BOTFATHER
───────────────────────────────────────────────────────────────────
Message @BotFather and use /setcommands:

start - Start the bot
invest - Invest money
portfolio - View portfolio
withdraw - Withdraw money
referral - Get referral link
help - Show help
admin - Admin panel

5. FEATURES OVERVIEW
───────────────────────────────────────────────────────────────────
✅ 4 Investment Plans (Starter, Silver, Gold, Platinum)
✅ Daily Profit Calculation (1% - 2.5%)
✅ Portfolio Tracking
✅ Withdrawal System
✅ Referral System (5% bonus)
✅ Admin Dashboard
✅ Broadcast Messages
✅ SQLite Database
✅ Beautiful Interactive UI

6. INVESTMENT PLANS
───────────────────────────────────────────────────────────────────
Starter:    $10 - $500      | 1% daily  | 30 days
Silver:     $500 - $2,500   | 1.5% daily| 60 days
Gold:       $2,500 - $10,000| 2% daily  | 90 days
Platinum:   $10,000 - $100,000| 2.5% daily| 120 days

7. DATABASE
───────────────────────────────────────────────────────────────────
SQLite database is automatically created as 'investment_bot.db'
Tables: users, investments, transactions, referrals, daily_earnings

8. DAILY EARNINGS CALCULATION
───────────────────────────────────────────────────────────────────
Run calculate_daily_earnings() method daily via cron job:

Add to crontab (runs every day at midnight):
0 0 * * * cd /path/to/bot && python -c "from investment_bot import *; InvestmentManager(Database()).calculate_daily_earnings()"

Or use a scheduler in your hosting environment.

9. CUSTOMIZATION
───────────────────────────────────────────────────────────────────
- Currency: Change CURRENCY and CURRENCY_NAME in Config
- Plans: Modify PLANS dictionary in Config
- Rates: Adjust daily_rate for each plan
- Referral: Change REFERRAL_BONUS_PERCENT

═══════════════════════════════════════════════════════════════════
"""

with open('/mnt/agents/output/SETUP_GUIDE.txt', 'w') as f:
    f.write(setup_guide)

print("All files created successfully!")
print("\nFiles created:")
print("1. investment_bot.py - Main bot code")
print("2. requirements.txt - Python dependencies")
print("3. SETUP_GUIDE.txt - Setup instructions")
