import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from flask import Flask, request, render_template_string
import os
import uuid
import re
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
bot = telebot.TeleBot(os.getenv('BOT_TOKEN'))

# Environment variables
FORCE_JOIN_CHANNELS = os.getenv('FORCE_JOIN_CHANNELS', '@channel1,@channel2,@channel3').split(',')
ADMIN_IDS = [int(x.strip()) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
WEBHOOK_URL = os.getenv('WEBHOOK_URL', 'https://your-app.onrender.com/verify')
WITHDRAW_POINTS = 3
DB_PATH = 'referral_bot.db'

admin_states = {}
channel_id_cache = {}

def get_channel_id(channel_username):
    if channel_username in channel_id_cache:
        return channel_id_cache[channel_username]
    try:
        username = channel_username.strip().replace('@', '')
        chat = bot.get_chat(f"@{username}")
        channel_id_cache[channel_username] = chat.id
        return chat.id
    except:
        return None

def get_force_join_channels():
    return [get_channel_id(ch) for ch in FORCE_JOIN_CHANNELS if get_channel_id(ch)]

# Database
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
        referrals INTEGER DEFAULT 0, points INTEGER DEFAULT 0, verified BOOLEAN DEFAULT 0,
        referer_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS coupons (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE, used BOOLEAN DEFAULT 0,
        used_by INTEGER, redeemed_at TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS redeems_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, coupon_code TEXT,
        redeemed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS verification_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, token TEXT UNIQUE,
        used BOOLEAN DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def db_query(table, user_id=None, token=None):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users' and user_id:
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            r = c.fetchone()
            if r: return [dict(zip(['user_id','username','first_name','referrals','points','verified','referer_id'], r))]
        elif table == 'coupons':
            c.execute("SELECT * FROM coupons WHERE used = 0")
            return [dict(zip(['id','code','used','used_by','redeemed_at'], r)) for r in c.fetchall()]
        elif table == 'verification_tokens' and token:
            c.execute("SELECT * FROM verification_tokens WHERE token = ?", (token,))
            return c.fetchone()
    finally:
        conn.close()
    return []

def db_insert(table, **data):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users':
            c.execute("INSERT OR IGNORE INTO users (user_id, username, first_name, referer_id) VALUES (?, ?, ?, ?)",
                     (data['user_id'], data['username'], data['first_name'], data.get('referer_id')))
        elif table == 'coupons': c.execute("INSERT INTO coupons (code) VALUES (?)", (data['code'],))
        elif table == 'redeems_log': c.execute("INSERT INTO redeems_log (user_id, coupon_code) VALUES (?, ?)", (data['user_id'], data['coupon_code']))
        elif table == 'verification_tokens': c.execute("INSERT INTO verification_tokens (user_id, token) VALUES (?, ?)", (data['user_id'], data['token']))
        conn.commit()
    finally:
        conn.close()

def db_update(table, user_id=None, token=None, coupon_id=None, points=None, referrals=None):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    try:
        if table == 'users' and user_id:
            if points is not None: c.execute("UPDATE users SET points = ? WHERE user_id = ?", (points, user_id))
            elif referrals is not None: c.execute("UPDATE users SET referrals = ? WHERE user_id = ?", (referrals, user_id))
            else: c.execute("UPDATE users SET verified = 1 WHERE user_id = ?", (user_id,))
        elif table == 'coupons' and coupon_id: c.execute("UPDATE coupons SET used = 1 WHERE id = ?", (coupon_id,))
        elif table == 'verification_tokens' and token: c.execute("UPDATE verification_tokens SET used = 1 WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()

init_db()

def check_membership(user_id):
    for channel_id in get_force_join_channels():
        try:
            member = bot.get_chat_member(channel_id, user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

def get_channel_links():
    return [f"• [Channel {i+1}](https://t.me/{c.strip().replace('@','')})" for i, c in enumerate(FORCE_JOIN_CHANNELS)]

def get_referral_link(user_id):
    return f"https://t.me/{bot.get_me().username}?start=r{user_id}"

def main_menu(is_admin=False):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row('📊 Stats', '🔗 Referral Link')
    markup.row('💰 Withdraw')
    if is_admin: markup.row('🔧 Admin Panel')
    return markup

def admin_menu():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.row('➕ Add Coupon', '➖ Remove Coupon')
    markup.row('📦 Coupon Stock', '📋 Redeems Log')
    markup.row('⚙️ Change Withdraw Points', '🔙 Back to Main')
    return markup

def force_join_keyboard():
    return InlineKeyboardMarkup().add(InlineKeyboardButton('✅ Joined All Channels', callback_data='check_channels'))

def show_main_menu(chat_id, user_id):
    bot.send_message(chat_id, "🏠 *Main Menu*", reply_markup=main_menu(user_id in ADMIN_IDS), parse_mode='Markdown')

VERIFICATION_HTML = """
<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verification</title><style>*{margin:0;padding:0;box-sizing:border-box;}body{font-family:'Segoe UI',sans-serif;
background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;display:flex;align-items:center;justify-content:center;
padding:20px;}.container{background:rgba(255,255,255,0.95);backdrop-filter:blur(10px);border-radius:20px;padding:40px;max-width:400px;
width:100%;box-shadow:0 20px 40px rgba(0,0,0,0.1);text-align:center;}.logo{font-size:2.5em;margin-bottom:20px;background:linear-gradient(45deg,#667eea,#764ba2);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;}h1{color:#333;margin-bottom:20px;font-size:1.8em;}p{color:#666;line-height:1.6;margin-bottom:30px;}
.verify-btn{background:linear-gradient(45deg,#667eea,#764ba2);color:white;border:none;padding:15px 40px;font-size:1.1em;border-radius:50px;cursor:pointer;transition:all 0.3s;
width:100%;margin-bottom:20px;}.verify-btn:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(102,126,234,0.4);}.status{padding:15px;border-radius:10px;margin-top:20px;display:none;}
.success{background:#d4edda;color:#155724;border:1px solid #c3e6cb;}.error{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb;}</style></head>
<body><div class="container"><div class="logo">🔍</div><h1>Complete Verification</h1><p>Click to verify your account</p>
<button class="verify-btn" id="verifyBtn">Verify Now</button><div id="status" class="status"></div></div>
<script>const urlParams=new URLSearchParams(window.location.search);const token=urlParams.get('token');
document.getElementById('verifyBtn').addEventListener('click',async()=>{const btn=document.getElementById('verifyBtn');
const status=document.getElementById('status');btn.disabled=true;btn.innerHTML='Verifying...';try{const res=await fetch('/api/verify',{
method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:token})});const data=await res.json();
if(data.success){status.textContent='✅ Success! Returning...';status.className='status success';
setTimeout(()=>{window.location.href=`https://t.me/${data.bot_username}?start=verified_${token}`;},2000);}else{
status.textContent=data.message;status.className='status error';btn.disabled=false;btn.innerHTML='Verify Now';}}catch(e){
status.textContent='Network error';status.className='status error';btn.disabled=false;btn.innerHTML='Verify Now';}}); </script></body></html>
"""

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    args = message.text.split(' ', 1)
    referer_id = int(args[1][1:]) if len(args) > 1 and args[1].startswith('r') else None
    
    user = db_query('users', user_id)
    if not user:
        db_insert('users', user_id=user_id, username=message.from_user.username or '', 
                 first_name=message.from_user.first_name or '', referer_id=referer_id)
        bot.send_message(message.chat.id, f"""👋 *Welcome!* 🎉

📢 *Join our channels:*
{chr(10).join(get_channel_links())}

👇 *Click after joining:* 👇""", reply_markup=force_join_keyboard(), 
                       parse_mode='Markdown', disable_web_page_preview=True)
    elif user[0]['verified']:
        show_main_menu(message.chat.id, user_id)
    else:
        bot.send_message(message.chat.id, "🔄 *Complete verification first!*", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    if call.data == 'check_channels':
        if check_membership(call.from_user.id):
            token = str(uuid.uuid4())
            db_insert('verification_tokens', user_id=call.from_user.id, token=token)
            markup = InlineKeyboardMarkup().add(
                InlineKeyboardButton('🔍 Verify Now', url=f"{WEBHOOK_URL}?token={token}"),
                InlineKeyboardButton('📱 Complete Later', callback_data=f'verify_{token}')
            )
            bot.edit_message_text("✅ *Joined all channels!*\n\n*Complete verification:*", call.message.chat.id, 
                                call.message.message_id, reply_markup=markup, parse_mode='Markdown')
        else:
            bot.answer_callback_query(call.id, "❌ Join all channels first!")
    elif call.data.startswith('verify_'):
        token = call.data[7:]
        bot.send_message(call.from_user.id, f"🔗 *Verify:*\n\n{WEBHOOK_URL}?token={token}", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text in ['📊 Stats', '🔗 Referral Link', '💰 Withdraw'])
def user_menu(message):
    user_id = message.from_user.id
    user = db_query('users', user_id)
    if not user: return
    
    if m.text == '📊 Stats':
        bot.send_message(m.chat.id, f"📊 *Stats:*\n👥 *Referrals:* {user[0]['referrals']}\n⭐ *Points:* {user[0]['points']}", parse_mode='Markdown')
    elif m.text == '🔗 Referral Link':
        bot.send_message(m.chat.id, f"🔗 *Link:*\n\n`{get_referral_link(user_id)}`", parse_mode='Markdown')
    elif m.text == '💰 Withdraw':
        if user[0]['points'] < WITHDRAW_POINTS:
            bot.send_message(m.chat.id, f"❌ *Need {WITHDRAW_POINTS} points!*", parse_mode='Markdown')
        else:
            coupons = db_query('coupons')
            if not coupons:
                bot.send_message(m.chat.id, "❌ *No coupons available!*", parse_mode='Markdown')
            else:
                coupon = coupons[0]
                db_update('coupons', coupon_id=coupon['id'])
                db_insert('redeems_log', user_id=user_id, coupon_code=coupon['code'])
                db_update('users', user_id=user_id, points=user[0]['points']-WITHDRAW_POINTS)
                bot.send_message(m.chat.id, f"✅ *Coupon:* `{coupon['code']}`\n⭐ *- {WITHDRAW_POINTS} points*", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text == '🔧 Admin Panel' and m.from_user.id in ADMIN_IDS)
def admin_panel(message): bot.send_message(message.chat.id, "🔧 *Admin*", reply_markup=admin_menu(), parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.text in ['➕ Add Coupon', '📦 Coupon Stock'] and m.from_user.id in ADMIN_IDS)
def admin_actions(message):
    if m.text == '➕ Add Coupon':
        admin_states[m.from_user.id] = 'add_coupon'
        bot.send_message(m.chat.id, "📤 *Send coupon code:*", parse_mode='Markdown')
    else:
        coupons = db_query('coupons')
        bot.send_message(m.chat.id, f"📦 *Stock:* {len(coupons)}", parse_mode='Markdown')

@bot.message_handler(func=lambda m: m.from_user.id in ADMIN_IDS and m.from_user.id in admin_states)
def admin_input(message):
    if admin_states.get(m.from_user.id) == 'add_coupon':
        code = m.text.strip().upper()
        if re.match(r'^[A-Z0-9]{6,12}$', code):
            db_insert('coupons', code=code)
            bot.reply_to(m, f"✅ *Added:* `{code}`", parse_mode='Markdown')
        else:
            bot.reply_to(m, "❌ *6-12 uppercase letters/numbers only!*")
        del admin_states[m.from_user.id]

# Web Routes
@app.route(f'/{bot.token}', methods=['POST'])
def webhook():
    json_string = request.get_data().decode('utf-8')
    update = telebot.types.Update.de_json(json_string)
    bot.process_new_updates([update])
    return 'ok'

@app.route('/verify')
def verification_page(): return render_template_string(VERIFICATION_HTML)

@app.route('/api/verify', methods=['POST'])
def api_verify():
    data = request.json
    token_data = db_query('verification_tokens', token=data.get('token'))
    if not token_data or token_data[3]: return {'success': False, 'message': 'Invalid token'}
    
    user_id = token_data[1]
    user = db_query('users', user_id)
    if not user or user[0]['verified']: return {'success': False, 'message': 'Already verified'}
    
    db_update('verification_tokens', token=token_data[0])
    db_update('users', user_id=user_id)
    
    if user[0]['referer_id']:
        referer = db_query('users', user[0]['referer_id'])
        if referer:
            db_update('users', user_id=user[0]['referer_id'], points=referer[0]['points']+1, referrals=referer[0]['referrals']+1)
            try: bot.send_message(user[0]['referer_id'], "🎉 *New referral! +1 point*", parse_mode='Markdown')
            except: pass
    
    return {'success': True, 'bot_username': bot.get_me().username}

@app.route('/')
def home(): return "🤖 Referral Bot Active! 🚀"

# FIXED: Set webhook on first request
@app.before_first_request
def setup_webhook():
    bot.remove_webhook()
    webhook_url = f"https://{request.host}/{bot.token}"
    bot.set_webhook(url=webhook_url)
    print(f"✅ Webhook set: {webhook_url}")

if __name__ == '__main__':
    init_db()
    print("🤖 Bot starting...")
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
