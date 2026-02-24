import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request, render_template_string
import os
import uuid
import re
import sqlite3
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))

# Environment variables - USE CHANNEL USERNAMES ✅
FORCE_JOIN_CHANNELS = os.getenv('FORCE_JOIN_CHANNELS', '@channel1,@channel2,@channel3').split(',')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL', f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'your-app.onrender.com')}/verify")
WITHDRAW_POINTS = 3
DB_PATH = 'referral_bot.db'

# Global state
admin_states = {}
channel_id_cache = {}
first_run = True
webhook_set = False

print(f"🤖 Starting bot...")
print(f"📢 Channels: {FORCE_JOIN_CHANNELS}")
print(f"👥 Admins: {ADMIN_IDS}")

def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    
    # Users table
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
    
    # Coupons table
    c.execute('''CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        used BOOLEAN DEFAULT 0,
        used_by INTEGER,
        redeemed_at TIMESTAMP
    )''')
    
    # Redeems log
    c.execute('''CREATE TABLE IF NOT EXISTS redeems_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        coupon_code TEXT,
        redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Verification tokens
    c.execute('''CREATE TABLE IF NOT EXISTS verification_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        token TEXT UNIQUE NOT NULL,
        used BOOLEAN DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

# Channel functions
def get_channel_id(channel_username):
    if channel_username in channel_id_cache:
        return channel_id_cache[channel_username]
    
    try:
        username = channel_username.strip().replace('@', '')
        chat = bot.get_chat(f"@{username}")
        channel_id_cache[channel_username] = chat.id
        print(f"✅ Cached: {channel_username} -> {chat.id}")
        return chat.id
    except Exception as e:
        print(f"❌ Channel error {channel_username}: {e}")
        return None

def get_force_join_channels():
    return [get_channel_id(ch) for ch in FORCE_JOIN_CHANNELS if get_channel_id(ch)]

def check_membership(user_id):
    channels = get_force_join_channels()
    if not channels:
        print("❌ No valid channels found")
        return False
    
    for channel_id in channels:
        try:
            member = bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

def get_channel_links():
    return [f"• [Channel {i+1}](https://t.me/{c.strip().replace('@','')})" 
            for i, c in enumerate(FORCE_JOIN_CHANNELS)]

# Database functions
def db_query(table, user_id=None, token=None):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users' and user_id:
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            r = c.fetchone()
            if r:
                return [{
                    'user_id': r[0], 'username': r[1], 'first_name': r[2],
                    'referrals': r[3], 'points': r[4], 'verified': bool(r[5]),
                    'referer_id': r[6]
                }]
        elif table == 'coupons':
            c.execute("SELECT * FROM coupons WHERE used = 0 LIMIT 1")
            r = c.fetchone()
            if r:
                return [{
                    'id': r[0], 'code': r[1], 'used': bool(r[2]),
                    'used_by': r[3], 'redeemed_at': r[4]
                }]
            return []
        elif table == 'verification_tokens' and token:
            c.execute("SELECT * FROM verification_tokens WHERE token = ?", (token,))
            return c.fetchone()
        elif table == 'redeems_log':
            c.execute("SELECT * FROM redeems_log ORDER BY id DESC LIMIT 10")
            return c.fetchall()
    finally:
        conn.close()
    return []

def db_insert(table, **kwargs):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users':
            c.execute("""INSERT OR IGNORE INTO users 
                        (user_id, username, first_name, referrals, points, verified, referer_id) 
                        VALUES (?, ?, ?, 0, 0, 0, ?)""",
                     (kwargs['user_id'], kwargs['username'], kwargs['first_name'], kwargs.get('referer_id')))
        elif table == 'coupons':
            c.execute("INSERT INTO coupons (code, used) VALUES (?, 0)", (kwargs['code'],))
        elif table == 'redeems_log':
            c.execute("INSERT INTO redeems_log (user_id, coupon_code) VALUES (?, ?)", 
                     (kwargs['user_id'], kwargs['coupon_code']))
        elif table == 'verification_tokens':
            c.execute("INSERT INTO verification_tokens (user_id, token, used) VALUES (?, ?, 0)", 
                     (kwargs['user_id'], kwargs['token']))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Insert {table}: {e}")
        return False
    finally:
        conn.close()

def db_update(table, condition, **kwargs):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users' and 'user_id' in condition:
            if 'points' in kwargs:
                c.execute("UPDATE users SET points = ? WHERE user_id = ?", 
                         (kwargs['points'], condition['user_id']))
            elif 'verified' in kwargs:
                c.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (condition['user_id'],))
        elif table == 'coupons' and 'id' in condition:
            c.execute("UPDATE coupons SET used = 1, used_by = ?, redeemed_at = ? WHERE id = ?", 
                     (kwargs.get('used_by', 0), datetime.now().isoformat(), condition['id']))
        elif table == 'verification_tokens' and 'token' in condition:
            c.execute("UPDATE verification_tokens SET used = 1 WHERE token = ?", (condition['token'],))
        conn.commit()
        return True
    except Exception as e:
        print(f"❌ Update {table}: {e}")
        return False
    finally:
        conn.close()

# Keyboards
def main_menu(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(KeyboardButton('📊 Stats'), KeyboardButton('🔗 Referral Link'))
    markup.add(KeyboardButton('💰 Withdraw'))
    if is_admin:
        markup.add(KeyboardButton('🔧 Admin Panel'))
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row(KeyboardButton('➕ Add Coupon'), KeyboardButton('➖ Remove Coupon'))
    markup.row(KeyboardButton('📦 Coupon Stock'), KeyboardButton('📋 Redeems Log'))
    markup.row(KeyboardButton('⚙️ Change Withdraw Points'), KeyboardButton('🔙 Back to Main'))
    return markup

def force_join_keyboard():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(InlineKeyboardButton('✅ Joined All Channels', callback_data='check_channels'))
    return markup

def show_main_menu(chat_id, user_id):
    bot.send_message(chat_id, "🏠 *Main Menu*", reply_markup=main_menu(user_id in ADMIN_IDS), parse_mode='Markdown')

# Beautiful HTML Verification Page
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
        .error { background: #f8d7da
