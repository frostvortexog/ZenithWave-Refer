import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request, render_template_string
import supabase
import os
import uuid
import requests
import re
from datetime import datetime
import threading
import time

# Initialize
app = Flask(__name__)
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))
supabase_client = supabase.create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))

ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS').split(',')]
FORCE_JOIN_CHANNELS = [int(x) for x in os.getenv('FORCE_JOIN_CHANNELS').split(',')]
WEBHOOK_URL = os.getenv('WEBHOOK_URL')

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
        <button class="verify-btn" onclick="verifyUser()">Verify Now</button>
        <div id="status" class="status"></div>
    </div>

    <script>
        const urlParams = new URLSearchParams(window.location.search);
        const token = urlParams.get('token');
        
        async function verifyUser() {
            const btn = document.querySelector('.verify-btn');
            const status = document.getElementById('status');
            
            btn.disabled = true;
            btn.textContent = 'Verifying...';
            
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
                    btn.disabled = false;
                    btn.textContent = 'Verify Now';
                }
            } catch (error) {
                status.textContent = 'Network error. Please try again.';
                status.className = 'status error';
                btn.disabled = false;
                btn.textContent = 'Verify Now';
            }
        }
    </script>
</body>
</html>
"""

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
    return f"https://t.me/{bot.get_me().username}?start=r{user_id}"

# Main menu keyboard
def main_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton('📊 Stats'), KeyboardButton('🔗 Referral Link'))
    markup.add(KeyboardButton('💰 Withdraw'))
    return markup

# Admin menu keyboard
def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(KeyboardButton('➕ Add Coupon'), KeyboardButton('➖ Remove Coupon'))
    markup.add(KeyboardButton('📦 Coupon Stock'), KeyboardButton('📋 Redeems Log'))
    markup.add(KeyboardButton('⚙️ Change Withdraw Points'))
    markup.add(KeyboardButton('🔙 Back to Main'))
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split(' ', 1)
    
    # Handle referral
    referer_id = None
    if len(args) > 1 and args[1].startswith('r'):
        try:
            referer_id = int(args[1][1:])
            # Check if referer exists and is verified
            referer = supabase_client.table('users').select('*').eq('user_id', referer_id).execute()
            if referer.data and referer.data[0]['verified']:
                referer_id = referer_id
        except:
            pass
    
    # Check if user exists
    user = supabase_client.table('users').select('*').eq('user_id', user_id).execute()
    
    if not user.data:
        # Create new user
        supabase_client.table('users').insert({
            'user_id': user_id,
            'username': message.from_user.username,
            'first_name': message.from_user.first_name,
            'referer_id': referer_id
        }).execute()
        
        # Force join channels
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton('✅ Joined All Channels', callback_data='check_channels'))
        bot.send_message(message.chat.id, 
                        "👋 Welcome!\n\nPlease join our channels first:\n\n"
                        + "\n".join([f"• [Channel {i+1}](https://t.me/c/{str(ch)[4:]}/1)" for i, ch in enumerate(FORCE_JOIN_CHANNELS)]),
                        reply_markup=markup, parse_mode='Markdown', disable_web_page_preview=True)
    else:
        if user.data[0]['verified']:
            show_main_menu(message)
        else:
            show_verification_step(message)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data == 'check_channels':
        if check_membership(call.from_user.id):
            # Generate verification token
            token = str(uuid.uuid4())
            supabase_client.table('verification_tokens').insert({
                'user_id': call.from_user.id,
                'token': token
            }).execute()
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton('🔍 Verify Now', url=f"{WEBHOOK_URL}?token={token}"))
            markup.add(InlineKeyboardButton('✅ Complete Verification', callback_data=f'verify_complete_{token}'))
            
            bot.edit_message_text("✅ All channels joined!\n\nPlease complete web verification:", 
                                call.message.chat.id, call.message.message_id, reply_markup=markup)
        else:
            bot.answer_callback_query(call.id, "❌ Please join all channels first!")
    
    elif call.data.startswith('verify_complete_'):
        token = call.data.split('_', 2)[2]
        bot.send_message(call.from_user.id, 
                        "🔗 Please complete verification:\n" +
                        f"https://your-domain.onrender.com/verify.html?token={token}")

def show_main_menu(message):
    bot.send_message(message.chat.id, "🏠 Main Menu:", reply_markup=main_menu())

def show_admin_menu(message):
    bot.send_message(message.chat.id, "🔧 Admin Panel:", reply_markup=admin_menu())

@bot.message_handler(func=lambda message: message.text == '📊 Stats')
def show_stats(message):
    user = supabase_client.table('users').select('*').eq('user_id', message.from_user.id).execute()
    if user.data:
        bot.send_message(message.chat.id, 
                        f"📊 Your Stats:\n\n"
                        f"👥 Referrals: {user.data[0]['referrals']}\n"
                        f"⭐ Points: {user.data[0]['points']}")

@bot.message_handler(func=lambda message: message.text == '🔗 Referral Link')
def referral_link(message):
    link = get_referral_link(message.from_user.id)
    bot.send_message(message.chat.id, f"🔗 Your referral link:\n\n{link}")

@bot.message_handler(func=lambda message: message.text == '💰 Withdraw')
def withdraw(message):
    user = supabase_client.table('users').select('*').eq('user_id', message.from_user.id).execute()
    if not user.data:
        bot.send_message(message.chat.id, "❌ Please start the bot first!")
        return
    
    user_data = user.data[0]
    
    # Get withdraw points requirement
    withdraw_points_res = supabase_client.table('settings').select('withdraw_points').eq('key', 'withdraw_points').execute()
    withdraw_points = withdraw_points_res.data[0]['withdraw_points'] if withdraw_points_res.data else 3
    
    if user_data['points'] < withdraw_points:
        bot.send_message(message.chat.id, f"❌ Not enough points! Need {withdraw_points} points.")
        return
    
    # Check coupon stock
    coupons = supabase_client.table('coupons').select('id').eq('used', False).execute()
    if not coupons.data:
        bot.send_message(message.chat.id, "❌ Coupons are out of stock!")
        return
    
    # Send coupon
    coupon = coupons.data[0]
    supabase_client.table('coupons').update({
        'used': True,
        'used_by': message.from_user.id,
        'redeemed_at': datetime.now().isoformat()
    }).eq('id', coupon['id']).execute()
    
    supabase_client.table('redeems_log').insert({
        'user_id': message.from_user.id,
        'coupon_code': coupon['code']
    }).execute()
    
    # Deduct points
    supabase_client.table('users').update({'points': user_data['points'] - withdraw_points}).eq('user_id', message.from_user.id).execute()
    
    # Notify admin
    for admin_id in ADMIN_IDS:
        try:
            bot.send_message(admin_id, f"✅ User @{message.from_user.username} redeemed coupon `{coupon['code']}` at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", parse_mode='Markdown')
        except:
            pass
    
    bot.send_message(message.chat.id, f"✅ Coupon `{coupon['code']}` sent!\n⭐ {withdraw_points} points deducted.")

# Admin handlers
@bot.message_handler(func=lambda m: m.from_user.id in ADMIN_IDS and m.text == '➕ Add Coupon')
def admin_add_coupon(message):
    bot.send_message(message.chat.id, "📤 Send coupons line by line:")

@bot.message_handler(func=lambda m: m.from_user.id in ADMIN_IDS)
def handle_admin_input(message):
    if message.reply_to_message and "Send coupons line by line" in message.reply_to_message.text:
        coupon_code = message.text.strip().upper()
        if re.match(r'^[A-Z0-9]{6,12}$', coupon_code):
            supabase_client.table('coupons').insert({
                'code': coupon_code,
                'used': False
            }).execute()
            bot.reply_to(message, f"✅ Added coupon: `{coupon_code}`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Invalid format! Use 6-12 uppercase letters/numbers.")
        return
    
    # Handle other admin commands similarly...

def handle_web_verification():
    @app.route('/verify.html')
    def verification_page():
        token = request.args.get('token')
        return render_template_string(VERIFICATION_HTML)
    
    @app.route('/api/verify', methods=['POST'])
    def api_verify():
        data = request.json
        token = data.get('token')
        
        # Verify token and user
        token_data = supabase_client.table('verification_tokens').select('*').eq('token', token).execute()
        if not token_data.data or token_data.data[0]['used']:
            return {'success': False, 'message': 'Invalid or used token'}
        
        user_id = token_data.data[0]['user_id']
        user = supabase_client.table('users').select('*').eq('user_id', user_id).eq('verified', False).execute()
        
        if not user.data:
            return {'success': False, 'message': 'User already verified or not found'}
        
        # Mark as verified
        supabase_client.table('verification_tokens').update({'used': True}).eq('token', token).execute()
        supabase_client.table('users').update({'verified': True}).eq('user_id', user_id).execute()
        
        bot_info = bot.get_me()
        return {
            'success': True,
            'bot_username': bot_info.username,
            'message': 'Verified successfully!'
        }
    
    return app

# Run bot
if __name__ == '__main__':
    # Initialize settings
    supabase_client.table('settings').upsert({'key': 'withdraw_points', 'value': 3}, on_conflict='key').execute()
    
    print("Bot started!")
    handle_web_verification().run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
