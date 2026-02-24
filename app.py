import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request, render_template_string
import os
import uuid
import re
import sqlite3
import json
from datetime import datetime
import threading
import time
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))

# Environment variables
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
FORCE_JOIN_CHANNELS = [int(x.strip()) for x in os.getenv('FORCE_JOIN_CHANNELS', '').split(',') if x.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.onrender.com/telegram_webhook')
WITHDRAW_POINTS = 3
DB_PATH = 'referral_bot.db'

# Admin states
admin_states = {}

# Initialize SQLite Database
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        referrals INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        verified BOOLEAN DEFAULT 0,
        referer_id INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE,
        used BOOLEAN DEFAULT 0,
        used_by INTEGER,
        redeemed_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS redeems_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        coupon_code TEXT,
        redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS verification_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        token TEXT UNIQUE,
        used BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

# Database functions
def db_query(table, filters=None):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users':
            if filters and 'user_id' in filters:
                c.execute("SELECT * FROM users WHERE user_id = ?", (filters['user_id'],))
            else:
                c.execute("SELECT * FROM users")
            result = c.fetchall()
            return [{'user_id': r[0], 'username': r[1], 'first_name': r[2], 'referrals': r[3], 
                     'points': r[4], 'verified': bool(r[5]), 'referer_id': r[6]} for r in result]
        elif table == 'coupons':
            if filters and 'used' in filters and not filters['used']:
                c.execute("SELECT * FROM coupons WHERE used = 0 LIMIT 1")
            else:
                c.execute("SELECT * FROM coupons WHERE used = 0")
            result = c.fetchall()
            return [{'id': r[0], 'code': r[1], 'used': bool(r[2]), 'used_by': r[3], 'redeemed_at': r[4]} for r in result]
        elif table == 'redeems_log':
            c.execute("SELECT * FROM redeems_log ORDER BY id DESC LIMIT 10")
            return c.fetchall()
        elif table == 'verification_tokens':
            if filters and 'token' in filters:
                c.execute("SELECT * FROM verification_tokens WHERE token = ?", (filters['token'],))
                return c.fetchone()
    except Exception as e:
        print(f"DB Query Error: {e}")
        return []
    finally:
        conn.close()

def db_insert(table, data):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users':
            c.execute('''INSERT OR IGNORE INTO users (user_id, username, first_name, referrals, points, verified, referer_id)
                      VALUES (?, ?, ?, ?, ?, ?, ?)''',
                      (data['user_id'], data['username'], data['first_name'], data.get('referrals', 0),
                       data.get('points', 0), int(data.get('verified', 0)), data.get('referer_id')))
        elif table == 'coupons':
            c.execute("INSERT INTO coupons (code, used, used_by, redeemed_at) VALUES (?, ?, ?, ?)",
                      (data['code'], 0, data.get('used_by'), data.get('redeemed_at')))
        elif table == 'redeems_log':
            c.execute("INSERT INTO redeems_log (user_id, coupon_code) VALUES (?, ?)",
                      (data['user_id'], data['coupon_code']))
        elif table == 'verification_tokens':
            c.execute("INSERT INTO verification_tokens (user_id, token, used) VALUES (?, ?, 0)",
                      (data['user_id'], data['token']))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Insert Error: {e}")
        return False
    finally:
        conn.close()

def db_update(table, data, condition):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users':
            if 'user_id' in condition:
                c.execute("UPDATE users SET points = ?, referrals = ? WHERE user_id = ?",
                          (data.get('points'), data.get('referrals'), condition['user_id']))
            else:
                c.execute("UPDATE users SET verified = ? WHERE user_id = ?",
                          (int(data['verified']), condition['user_id']))
        elif table == 'coupons':
            c.execute("UPDATE coupons SET used = 1, used_by = ?, redeemed_at = ? WHERE id = ?",
                      (data.get('used_by'), data.get('redeemed_at'), condition['id']))
        elif table == 'verification_tokens':
            c.execute("UPDATE verification_tokens SET used = 1 WHERE token = ?",
                      (condition['token'],))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Update Error: {e}")
        return False
    finally:
        conn.close()

def db_delete(table, condition):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'coupons':
            c.execute("DELETE FROM coupons WHERE id = ?", (condition['id'],))
        conn.commit()
        return True
    except Exception as e:
        print(f"DB Delete Error: {e}")
        return False
    finally:
        conn.close()

# Initialize database
init_db()

# Utility functions
def check_membership(user_id):
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

def get_referral_link(user_id):
    try:
        bot_info = bot.get_me()
        return f"https://t.me/{bot_info.username}?start=r{user_id}"
    except:
        return f"https://t.me/YOUR_BOT_USERNAME?start=r{user_id}"

# Keyboards
def main_menu(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton('📊 Stats'), KeyboardButton('🔗 Referral Link'))
    markup.add(KeyboardButton('💰 Withdraw'))
    if is_admin:
        markup.add(KeyboardButton('🔧 Admin Panel'))
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton('➕ Add Coupon'), KeyboardButton('➖ Remove Coupon'))
    markup.add(KeyboardButton('📦 Coupon Stock'), KeyboardButton('📋 Redeems Log'))
    markup.add(KeyboardButton('⚙️ Change Withdraw Points'))
    markup.add(KeyboardButton('🔙 Back to Main'))
    return markup

def force_join_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton('✅ Joined All Channels', callback_data='check_channels'))
    return markup

def show_main_menu(chat_id, user_id):
    is_admin = user_id in ADMIN_IDS
    bot.send_message(chat_id, "🏠 *Main Menu*", reply_markup=main_menu(is_admin), parse_mode='Markdown')

# HTML Template for verification
VERIFICATION_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Verify Account</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; max-width: 400px; margin: 50px auto; padding: 20px; text-align: center; }
        .container { background: #f5f5f5; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        button { background: #0088cc; color: white; padding: 12px 24px; border: none; border-radius: 5px; font-size: 16px; cursor: pointer; }
        button:hover { background: #006da3; }
        .token { font-family: monospace; background: #333; color: #0f0; padding: 10px; border-radius: 5px; word-break: break-all; margin: 20px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h2>🔐 Verify Your Account</h2>
        <p>Click the button below to verify your account. This ensures one device per user.</p>
        <button onclick="verify()">✅ Verify Now</button>
        <div id="status"></div>
    </div>
    <script>
        function verify() {
            const token = "{{ token }}";
            fetch('/verify/{{ token }}', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    document.getElementById('status').innerHTML = 
                        data.success ? '<p style="color: green;">✅ Verified! Returning to Telegram...</p>' : 
                        '<p style="color: red;">❌ Verification failed. Try again.</p>';
                    if (data.success) setTimeout(() => window.close(), 2000);
                });
        }
    </script>
</body>
</html>
"""

# Telegram Bot Handlers
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    # Check referral
    referer_id = None
    if len(message.text.split()) > 1:
        try:
            referer_id = int(message.text.split()[1].replace('r', ''))
            db_insert('users', {'user_id': referer_id, 'username': '', 'first_name': ''})
        except:
            referer_id = None
    
    # Create/update user
    db_insert('users', {
        'user_id': user_id, 'username': username, 'first_name': first_name,
        'referer_id': referer_id
    })
    
    if referer_id and referer_id != user_id:
        user_data = db_query('users', {'user_id': referer_id})[0]
        new_points = user_data['points'] + 1
        new_referrals = user_data['referrals'] + 1
        db_update('users', {'points': new_points, 'referrals': new_referrals}, {'user_id': referer_id})
    
    if check_membership(user_id):
        db_update('users', {'verified': True}, {'user_id': user_id})
        show_main_menu(message.chat.id, user_id)
    else:
        bot.send_message(message.chat.id, 
                        "👋 Welcome!\n\nPlease join our channels first:", 
                        reply_markup=force_join_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == 'check_channels':
        if check_membership(call.from_user.id):
            db_update('users', {'verified': True}, {'user_id': call.from_user.id})
            bot.edit_message_text("✅ Verified! Welcome!", call.message.chat.id, call.message.message_id)
            show_main_menu(call.message.chat.id, call.from_user.id)
        else:
            bot.answer_callback_query(call.id, "❌ Please join all channels first!")

@bot.message_handler(func=lambda message: message.text == '📊 Stats')
def stats_handler(message):
    user_data = db_query('users', {'user_id': message.from_user.id})[0]
    stats_text = f"""
📊 *Your Stats*
👤 Name: {user_data['first_name']}
⭐ Points: {user_data['points']}
👥 Referrals: {user_data['referrals']}
"""
    bot.send_message(message.chat.id, stats_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '🔗 Referral Link')
def referral_handler(message):
    link = get_referral_link(message.from_user.id)
    bot.send_message(message.chat.id, f"🔗 *Your Referral Link*\n\n`{link}`\n\nShare this to earn points!", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '💰 Withdraw')
def withdraw_handler(message):
    user_data = db_query('users', {'user_id': message.from_user.id})[0]
    if user_data['points'] >= WITHDRAW_POINTS:
        coupons = db_query('coupons', {'used': False})
        if coupons:
            coupon = coupons[0]
            db_update('coupons', {'used_by': message.from_user.id, 'redeemed_at': str(datetime.now())}, {'id': coupon['id']})
            db_update('users', {'points': user_data['points'] - WITHDRAW_POINTS}, {'user_id': message.from_user.id})
            db_insert('redeems_log', {'user_id': message.from_user.id, 'coupon_code': coupon['code']})
            bot.send_message(message.chat.id, f"🎉 Coupon Redeemed!\n\n`{coupon['code']}`", parse_mode='Markdown')
        else:
            bot.send_message(message.chat.id, "❌ No coupons available!")
    else:
        bot.send_message(message.chat.id, f"❌ Need {WITHDRAW_POINTS} points to withdraw!")

# Admin handlers
@bot.message_handler(func=lambda message: message.text == '🔧 Admin Panel' and message.from_user.id in ADMIN_IDS)
def admin_panel(message):
    bot.send_message(message.chat.id, "🔧 *Admin Panel*", reply_markup=admin_menu(), parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '🔙 Back to Main' and message.from_user.id in ADMIN_IDS)
def back_to_main(message):
    show_main_menu(message.chat.id, message.from_user.id)

# Flask Routes
@app.route('/')
def index():
    return "Bot is running! 🚀"

@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    try:
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return 'OK', 200
    except Exception as e:
        print(f"Webhook error: {e}")
        return 'Error', 500

@app.route('/verify/<token>')
def verify_page(token):
    token_data = db_query('verification_tokens', {'token': token})
    if token_data and not token_data[3]:  # not used
        return render_template_string(VERIFICATION_HTML, token=token)
    return "Invalid or used token", 404

@app.route('/verify/<token>', methods=['POST'])
def verify_token(token):
    token_data = db_query('verification_tokens', {'token': token})
    if token_data and not token_data[3]:
        user_id = token_data[1]
        db_update('verification_tokens', {}, {'token': token})
        db_update('users', {'verified': True}, {'user_id': user_id})
        return {'success': True}
    return {'success': False}

# Setup webhook on startup
def setup_webhook():
    print("Setting up webhook...")
    bot.delete_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"Webhook set to: {WEBHOOK_URL}")

@app.before_first_request
def before_first_request():
    setup_webhook()

if __name__ == '__main__':
    # Setup webhook
    setup_webhook()
    # Start Flask app
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False)
