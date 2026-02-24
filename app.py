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

# Environment variables - NOW USE CHANNEL USERNAMES!
FORCE_JOIN_CHANNELS = os.getenv('FORCE_JOIN_CHANNELS', '@channel1,@channel2,@channel3').split(',')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.onrender.com/verify')
WITHDRAW_POINTS = 3
DB_PATH = 'referral_bot.db'

# Admin states
admin_states = {}

# Cache for channel IDs (convert username to ID once)
channel_id_cache = {}

def get_channel_id(channel_username):
    """Convert channel username to chat ID"""
    if channel_username in channel_id_cache:
        return channel_id_cache[channel_username]
    
    try:
        # Remove @ if present
        username = channel_username.replace('@', '')
        chat = bot.get_chat(f"@{username}")
        channel_id_cache[channel_username] = chat.id
        return chat.id
    except:
        print(f"❌ Cannot access channel: {channel_username}")
        return None

def get_force_join_channels():
    """Get all valid channel IDs from usernames"""
    valid_channels = []
    for channel in FORCE_JOIN_CHANNELS:
        channel_id = get_channel_id(channel.strip())
        if channel_id:
            valid_channels.append(channel_id)
    return valid_channels

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

# Database functions (SAME AS BEFORE)
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
            c.execute('''INSERT OR IGNORE INTO users 
                        (user_id, username, first_name, referrals, points, verified, referer_id) 
                        VALUES (?, ?, ?, ?, ?, ?, ?)''',
                     (data['user_id'], data['username'], data['first_name'], 
                      data.get('referrals', 0), data.get('points', 0), 
                      int(data.get('verified', 0)), data.get('referer_id')))
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

# FIXED: Check membership using channel usernames
def check_membership(user_id):
    channels = get_force_join_channels()
    for channel_id in channels:
        try:
            member = bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except Exception as e:
            print(f"❌ Cannot check membership for channel {channel_id}: {e}")
            return False
    return True

def get_channel_links():
    """Generate channel links for welcome message"""
    links = []
    for i, channel_username in enumerate(FORCE_JOIN_CHANNELS, 1):
        username = channel_username.strip().replace('@', '')
        links.append(f"• [Channel {i}](https://t.me/{username})")
    return links

def get_referral_link(user_id):
    try:
        bot_info = bot.get_me()
        return f"https://t.me/{bot_info.username}?start=r{user_id}"
    except:
        return "https://t.me/YOUR_BOT_USERNAME?start=r{user_id}".format(user_id=user_id)

# Keyboards (SAME)
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

# HTML Template (SAME AS BEFORE)
VERIFICATION_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Verification - Referral Bot</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 40px;
            max-width: 400px;
            width: 100%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            text-align: center;
        }
        .logo { font-size: 2.5em; margin-bottom: 20px; background: linear-gradient(45deg, #667eea, #764ba2); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        h1 { color: #333; margin-bottom: 20px; font-size: 1.8em; }
        p { color: #666; line-height: 1.6; margin-bottom: 30px; }
        .verify-btn {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 15px 40px;
            font-size: 1.1em;
            border-radius: 50px;
            cursor: pointer;
            transition: all 0.3s ease;
            width: 100%;
            margin-bottom: 20px;
        }
        .verify-btn:hover { transform: translateY(-2px); box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4); }
        .status { padding: 15px; border-radius: 10px; margin-top: 20px; display: none; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">🔍</div>
        <h1>Complete Verification</h1>
        <p>Click the button below to verify your account. This ensures one device per user.</p>
        <button class="verify-btn" id="verifyBtn">Verify Now</button>
        <div id="status" class="status"></div>
    </div>
    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');
        const verifyBtn = document.getElementById('verifyBtn');
        const status = document.getElementById('status');
        
        verifyBtn.addEventListener('click', async function() {
            verifyBtn.disabled = true;
            verifyBtn.innerHTML = 'Verifying...';
            try {
                const response = await fetch('/api/verify', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({token: token})
                });
                const data = await response.json();
                if (data.success) {
                    status.textContent = '✅ Verification successful! Returning to Telegram...';
                    status.className = 'status success';
                    setTimeout(() => {
                        window.location.href = `https://t.me/${data.bot_username}?start=verified_${token}`;
                    }, 2000);
                } else {
                    status.textContent = data.message || 'Verification failed';
                    status.className = 'status error';
                    verifyBtn.disabled = false;
                    verifyBtn.innerHTML = 'Verify Now';
                }
            } catch (error) {
                status.textContent = 'Network error. Please try again.';
                status.className = 'status error';
                verifyBtn.disabled = false;
                verifyBtn.innerHTML = 'Verify Now';
            }
        });
    </script>
</body>
</html>
"""

# ALL OTHER HANDLERS REMAIN THE SAME (start, callback, stats, withdraw, admin, etc.)
# ... [Copy all handlers from previous version exactly as they are]

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split(' ', 1)
    
    referer_id = None
    if len(args) > 1 and args[1].startswith('r'):
        try:
            referer_id = int(args[1][1:])
        except:
            pass
    
    user = db_query('users', {'user_id': user_id})
    
    if not user:
        db_insert('users', {
            'user_id': user_id,
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'referer_id': referer_id
        })
        
        markup = force_join_keyboard()
        channel_links = get_channel_links()
        
        message_text = f"""👋 *Welcome to Referral Bot!* 🎉

📢 *Please join our channels first:*

{chr(10).join(channel_links)}

👇 *Click the button after joining all channels* 👇"""
        
        bot.send_message(
            message.chat.id, 
            message_text,
            reply_markup=markup, 
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
    else:
        if user[0]['verified']:
            show_main_menu(message.chat.id, user_id)
        else:
            bot.send_message(message.chat.id, "🔄 *Please complete verification first!*", parse_mode='Markdown')

# [Include ALL other handlers from previous version - stats, withdraw, admin panel, etc.]
# ... Copy everything from previous file handlers section ...

# Web Routes (SAME)
@app.route('/verify')
def verification_page():
    return render_template_string(VERIFICATION_HTML)

@app.route('/api/verify', methods=['POST'])
def api_verify():
    try:
        data = request.json
        token = data.get('token')
        
        token_data = db_query('verification_tokens', {'token': token})
        if not token_data or token_data[3] == 1:
            return {'success': False, 'message': 'Invalid or used token'}
        
        user_id = token_data[1]
        user = db_query('users', {'user_id': user_id})
        
        if not user or user[0]['verified']:
            return {'success': False, 'message': 'User already verified'}
        
        db_update('verification_tokens', {}, {'token': token})
        db_update('users', {'verified': True}, {'user_id': user_id})
        
        user_data = user[0]
        referer_id = user_data['referer_id']
        if referer_id:
            referer = db_query('users', {'user_id': referer_id})
            if referer:
                new_referrals = referer[0]['referrals'] + 1
                new_points = referer[0]['points'] + 1
                db_update('users', {
                    'referrals': new_referrals,
                    'points': new_points
                }, {'user_id': referer_id})
                
                try:
                    bot.send_message(referer_id, 
                                   f"🎉 *New referral!*\n👤 New user: @{user_data['username']}\n⭐ *+1 point* (Total: {new_points})",
                                   parse_mode='Markdown')
                except:
                    pass
        
        bot_info = bot.get_me()
        return {
            'success': True,
            'bot_username': bot_info.username,
            'message': 'Verified successfully!'
        }
    except Exception as e:
        print(f"Verification error: {e}")
        return {'success': False, 'message': 'Server error'}

@app.route('/')
def health_check():
    return "🤖 Referral Bot is running perfectly! 🚀"

if __name__ == '__main__':
    print("🤖 Starting Referral Bot...")
    print(f"👥 Admins: {ADMIN_IDS}")
    print(f"📢 Channels: {FORCE_JOIN_CHANNELS}")
    
    def run_bot():
        bot.infinity_polling()
    
    threading.Thread(target=run_bot, daemon=True).start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
