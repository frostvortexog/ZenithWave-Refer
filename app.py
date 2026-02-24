import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request, render_template_string
import supabase
import os
import uuid
import re
from datetime import datetime
from dotenv import load_dotenv
import json

# Load environment variables
load_dotenv()

app = Flask(__name__)
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))

# Safe Supabase initialization
supabase_client = None
try:
    supabase_client = supabase.create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
    print("✅ Supabase connected successfully!")
except Exception as e:
    print(f"❌ Supabase connection failed: {e}")

# Environment variables
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
FORCE_JOIN_CHANNELS = [int(x.strip()) for x in os.getenv('FORCE_JOIN_CHANNELS', '').split(',') if x.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.onrender.com/verify')
WITHDRAW_POINTS = 3

# FIXED Safe database functions - NO **kwargs syntax error
def safe_db_query(table, filters=None):
    """Safe database query with filters dict"""
    if not supabase_client:
        return {'data': []}
    try:
        query = supabase_client.table(table).select('*')
        if filters:
            for key, value in filters.items():
                query = query.eq(key, value)
        result = query.execute()
        return result
    except Exception as e:
        print(f"❌ DB Query Error {table}: {e}")
        return {'data': []}

def safe_db_insert(table, data):
    """Safe database insert"""
    if not supabase_client:
        return False
    try:
        supabase_client.table(table).insert(data).execute()
        return True
    except Exception as e:
        print(f"❌ Insert Error {table}: {e}")
        return False

def safe_db_update(table, data, filters):
    """Safe database update with filters dict"""
    if not supabase_client:
        return False
    try:
        query = supabase_client.table(table).update(data)
        for key, value in filters.items():
            query = query.eq(key, value)
        query.execute()
        return True
    except Exception as e:
        print(f"❌ Update Error {table}: {e}")
        return False

def safe_db_delete(table, filters):
    """Safe database delete with filters dict"""
    if not supabase_client:
        return False
    try:
        query = supabase_client.table(table).delete()
        for key, value in filters.items():
            query = query.eq(key, value)
        query.execute()
        return True
    except Exception as e:
        print(f"❌ Delete Error {table}: {e}")
        return False

# Check if user joined all channels
def check_membership(user_id):
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = bot.get_chat_member(channel, user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            return False
    return True

# Generate unique referral link
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

# Show main menu
def show_main_menu(chat_id, user_id):
    is_admin = user_id in ADMIN_IDS
    bot.send_message(chat_id, "🏠 *Main Menu*", reply_markup=main_menu(is_admin), parse_mode='Markdown')

# HTML Template for verification
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

# Bot Handlers
@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split(' ', 1)
    
    # Handle referral
    referer_id = None
    if len(args) > 1 and args[1].startswith('r'):
        try:
            referer_id = int(args[1][1:])
            referer = safe_db_query('users', {'user_id': referer_id})
            if referer.data and referer.data[0].get('verified', False):
                referer_id = referer_id
        except:
            pass
    
    # Check if user exists
    user = safe_db_query('users', {'user_id': user_id})
    
    if not user.data:
        # Create new user
        safe_db_insert('users', {
            'user_id': user_id,
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'referrals': 0,
            'points': 0,
            'verified': False,
            'referer_id': referer_id
        })
        
        # Perfect start message
        markup = force_join_keyboard()
        channel_links = []
        for i, channel_id in enumerate(FORCE_JOIN_CHANNELS, 1):
            clean_id = str(channel_id)[4:] if str(channel_id).startswith('-100') else str(channel_id)
            channel_links.append(f"• [Channel {i}](https://t.me/c/{clean_id}/1)")
        
        message_text = f"""👋 *Welcome to Referral Bot!* 🎉

📢 *Please join our 3 channels first:*

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
        user_data = user.data[0]
        if user_data.get('verified', False):
            show_main_menu(message.chat.id, user_id)
        else:
            bot.send_message(message.chat.id, "🔄 *Please complete verification first!*", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == 'check_channels':
        if check_membership(call.from_user.id):
            # Generate verification token
            token = str(uuid.uuid4())
            safe_db_insert('verification_tokens', {
                'user_id': call.from_user.id,
                'token': token
            })
            
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(InlineKeyboardButton('🔍 Verify Now', url=f"{WEBHOOK_URL}?token={token}"))
            markup.add(InlineKeyboardButton('✅ Complete Verification', callback_data=f'verify_complete_{token}'))
            
            bot.edit_message_text(
                "✅ *All channels joined!*\n\n*Please complete web verification:*", 
                call.message.chat.id, 
                call.message.message_id, 
                reply_markup=markup,
                parse_mode='Markdown'
            )
        else:
            bot.answer_callback_query(call.id, "❌ Please join all channels first!")
    
    elif call.data.startswith('verify_complete_'):
        token = call.data.split('_', 2)[2]
        bot.send_message(call.from_user.id, f"🔗 *Complete verification:*\n\n{WEBHOOK_URL}?token={token}", parse_mode='Markdown')

# User menu handlers
@bot.message_handler(func=lambda message: message.text == '📊 Stats')
def show_stats(message):
    user = safe_db_query('users', {'user_id': message.from_user.id})
    if user.data:
        user_data = user.data[0]
        bot.send_message(message.chat.id, 
                        f"📊 *Your Stats:*\n\n"
                        f"👥 *Referrals:* {user_data.get('referrals', 0)}\n"
                        f"⭐ *Points:* {user_data.get('points', 0)}", 
                        parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '🔗 Referral Link')
def referral_link(message):
    link = get_referral_link(message.from_user.id)
    bot.send_message(message.chat.id, f"🔗 *Your referral link:*\n\n`{link}`\n\n*Share this link to earn points!*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text == '💰 Withdraw')
def withdraw(message):
    user = safe_db_query('users', {'user_id': message.from_user.id})
    if not user.data:
        bot.send_message(message.chat.id, "❌ Please start the bot first!")
        return
    
    user_data = user.data[0]
    
    if user_data.get('points', 0) < WITHDRAW_POINTS:
        bot.send_message(message.chat.id, f"❌ *Not enough points!* Need {WITHDRAW_POINTS} points.", parse_mode='Markdown')
        return
    
    # Check coupon stock
    coupons = safe_db_query('coupons', {'used': False})
    if not coupons.data:
        bot.send_message(message.chat.id, "❌ *Coupons are out of stock!*", parse_mode='Markdown')
        return
    
    # Send coupon
    coupon = coupons.data[0]
    safe_db_update('coupons', {
        'used': True,
        'used_by': message.from_user.id,
        'redeemed_at': datetime.now().isoformat()
    }, {'id': coupon['id']})
    
    safe_db_insert('redeems_log', {
        'user_id': message.from_user.id,
        'coupon_code': coupon['code']
    })
    
    # Deduct points
    new_points = user_data['points'] - WITHDRAW_POINTS
    safe_db_update('users', {'points': new_points}, {'user_id': message.from_user.id})
    
    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, 
                           f"✅ *User redeemed coupon!*\n"
                           f"👤 @{message.from_user.username}\n"
                           f"🎫 `{coupon['code']}`\n"
                           f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 
                           parse_mode='Markdown')
        except:
            pass
    
    bot.send_message(message.chat.id, 
                    f"✅ *Coupon sent!*\n"
                    f"🎫 `{coupon['code']}`\n"
                    f"⭐ *{WITHDRAW_POINTS} points deducted.*", 
                    parse_mode='Markdown')

# Admin handlers
admin_states = {}

@bot.message_handler(func=lambda m: m.text == '🔧 Admin Panel' and m.from_user.id in ADMIN_IDS)
def admin_panel(message):
    bot.send_message(message.chat.id, "🔧 *Admin Panel*", reply_markup=admin_menu(), parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '🔙 Back to Main' and m.from_user.id in ADMIN_IDS)
def back_to_main(message):
    show_main_menu(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda m: m.text == '➕ Add Coupon' and m.from_user.id in ADMIN_IDS)
def admin_add_coupon(message):
    admin_states[message.from_user.id] = 'add_coupon'
    bot.send_message(message.chat.id, "📤 *Send coupons line by line*\n\n*Format:* `ABC123`\n*6-12 uppercase letters/numbers*", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '➖ Remove Coupon' and m.from_user.id in ADMIN_IDS)
def admin_remove_coupon(message):
    admin_states[message.from_user.id] = 'remove_coupon'
    bot.send_message(message.chat.id, "🔢 *Send number of coupons to remove:*")

@bot.message_handler(func=lambda m: m.text == '📦 Coupon Stock' and m.from_user.id in ADMIN_IDS)
def coupon_stock(message):
    coupons = safe_db_query('coupons', {'used': False})
    total = len(coupons.data)
    bot.send_message(message.chat.id, f"📦 *Coupon Stock:* {total}", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '📋 Redeems Log' and m.from_user.id in ADMIN_IDS)
def redeems_log(message):
    logs = safe_db_query('redeems_log')
    if logs.data:
        log_text = "📋 *Recent Redeems (Last 10):*\n\n"
        for log in logs.data[-10:]:
            user = safe_db_query('users', {'user_id': log['user_id']})
            username = user.data[0]['username'] if user.data else 'Unknown'
            log_text += f"• @{username} - `{log['coupon_code']}`\n"
        bot.send_message(message.chat.id, log_text, parse_mode='Markdown')
    else:
        bot.send_message(message.chat.id, "📋 *No redeems yet!*", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '⚙️ Change Withdraw Points' and m.from_user.id in ADMIN_IDS)
def change_withdraw_points(message):
    admin_states[message.from_user.id] = 'change_points'
    bot.send_message(message.chat.id, "🔢 *Send new withdraw points (current: 3):*", parse_mode='Markdown')

# Handle admin input states
@bot.message_handler(func=lambda message: message.from_user.id in ADMIN_IDS)
def handle_admin_input(message):
    user_id = message.from_user.id
    state = admin_states.get(user_id)
    
    if state == 'add_coupon':
        coupon_code = message.text.strip().upper()
        if re.match(r'^[A-Z0-9]{6,12}$', coupon_code):
            safe_db_insert('coupons', {
                'code': coupon_code,
                'used': False
            })
            bot.reply_to(message, f"✅ *Added coupon:* `{coupon_code}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ *Invalid format!* Use 6-12 uppercase letters/numbers.", parse_mode='Markdown')
        del admin_states[user_id]
    
    elif state == 'remove_coupon':
        try:
            count = int(message.text.strip())
            coupons = safe_db_query('coupons', {'used': False})
            for coupon in coupons.data[:count]:
                safe_db_delete('coupons', {'id': coupon['id']})
            bot.reply_to(message, f"✅ *Removed {count} coupons.*", parse_mode='Markdown')
        except:
            bot.reply_to(message, "❌ *Invalid number!*", parse_mode='Markdown')
        del admin_states[user_id]
    
    elif state == 'change_points':
        try:
            global WITHDRAW_POINTS
            WITHDRAW_POINTS = int(message.text.strip())
            bot.reply_to(message, f"✅ *Withdraw points updated:* {WITHDRAW_POINTS}", parse_mode='Markdown')
        except:
            bot.reply_to(message, "❌ *Invalid number!*", parse_mode='Markdown')
        del admin_states[user_id]

# Web verification routes
@app.route('/verify')
def verification_page():
    token = request.args.get('token')
    return render_template_string(VERIFICATION_HTML)

@app.route('/api/verify', methods=['POST'])
def api_verify():
    try:
        data = request.json
        token = data.get('token')
        
        # Verify token
        token_data = safe_db_query('verification_tokens', {'token': token})
        if not token_data.data or token_data.data[0].get('used', True):
            return {'success': False, 'message': 'Invalid or used token'}
        
        user_id = token_data.data[0]['user_id']
        user = safe_db_query('users', {'user_id': user_id})
        
        if not user.data or user.data[0].get('verified', True):
            return {'success': False, 'message': 'User already verified'}
        
        # Mark as verified
        safe_db_update('verification_tokens', {'used': True}, {'token': token})
        safe_db_update('users', {'verified': True}, {'user_id': user_id})
        
        # Check for referer and award points
        user_data = user.data[0]
        referer_id = user_data.get('referer_id')
        if referer_id:
            referer = safe_db_query('users', {'user_id': referer_id})
            if referer.data:
                new_referrals = referer.data[0].get('referrals', 0) + 1
                new_points = referer.data[0].get('points', 0) + 1
                safe_db_update('users', {
                    'referrals': new_referrals,
                    'points': new_points
                }, {'user_id': referer_id})
                
                # Notify referer
                try:
                    bot.send_message(referer_id, 
                                   f"🎉 *New referral!*\n"
                                   f"👤 New user: @{user_data.get('username', 'Unknown')}\n"
                                   f"⭐ *+1 point* (Total: {new_points})",
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

# Health check
@app.route('/')
def health_check():
    return "🤖 Referral Bot is running perfectly! 🚀"

if __name__ == '__main__':
    print("🤖 Starting Referral Bot...")
    print(f"👥 Admins: {ADMIN_IDS}")
    print(f"📢 Force join channels: {len(FORCE_JOIN_CHANNELS)}")
    print(f"🌐 Webhook URL: {WEBHOOK_URL}")
    
    # Start bot polling in background
    def start_polling():
        while True:
            try:
                bot.polling(none_stop=True, interval=0, timeout=20)
            except Exception as e:
                print(f"Polling error: {e}")
                time.sleep(15)
    
    import threading
    threading.Thread(target=start_polling, daemon=True).start()
    
    # Start Flask
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
