import os
import requests
from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

CHANNELS = ["@ZenithWave_Shein", "@ZenithWaveLoots", "@ZenithWave_Shein_Backup"]
ADMINS = [8537079657]  # replace with your telegram id

user_states = {}

# ---------------- TELEGRAM ----------------
def send(chat_id, text, keyboard=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    requests.post(url, json=data)

# ---------------- SUPABASE ----------------
def sb(table, method="get", data=None, params=""):
    url = f"{SUPABASE_URL}/rest/v1/{table}{params}"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json"
    }
    if method == "get":
        return requests.get(url, headers=headers).json()
    elif method == "post":
        return requests.post(url, headers=headers, json=data)
    elif method == "patch":
        return requests.patch(url, headers=headers, json=data)
    elif method == "delete":
        return requests.delete(url, headers=headers)

# ---------------- FORCE JOIN ----------------
def check_join(user_id):
    for ch in CHANNELS:
        res = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember",
            params={"chat_id": ch, "user_id": user_id}
        ).json()

        if res["result"]["status"] not in ["member", "administrator", "creator"]:
            return False
    return True

# ---------------- MENUS ----------------
def user_menu():
    return {
        "keyboard": [
            ["📊 Stats", "🔗 Referral Link"],
            ["💸 Withdraw"]
        ],
        "resize_keyboard": True
    }

def admin_menu():
    return {
        "keyboard": [
            ["➕ Add Coupon", "➖ Remove Coupon"],
            ["📦 Coupon Stock", "📜 Redeems Log"],
            ["⚙ Change Withdraw Points"]
        ],
        "resize_keyboard": True
    }

# ---------------- BOT ----------------
@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def bot():
    data = request.json

    if "message" not in data:
        return "ok"

    msg = data["message"]
    user_id = msg["from"]["id"]
    text = msg.get("text", "")

    # create user
    user = sb("users", params=f"?user_id=eq.{user_id}")
    if not user:
        sb("users", "post", {
            "user_id": user_id,
            "points": 0,
            "verified": False
        })

    # ---------------- START ----------------
    if text.startswith("/start"):
        ref = None
        if " " in text:
            ref = text.split()[1]

        if ref and str(ref) != str(user_id):
            sb("users", "patch", {"referrer_id": int(ref)}, f"?user_id=eq.{user_id}")

        if not check_join(user_id):
            keyboard = {
                "inline_keyboard": [
                    [{"text": "Join Channel 1", "url": "https://t.me/ZenithWave_Shein"}],
                    [{"text": "Join Channel 2", "url": "https://t.me/ZenithWaveLoots"}],
                    [{"text": "Join Channel 3", "url": "https://t.me/ZenithWave_Shein_Backup"}]
                ]
            }
            send(user_id, "Join all channels first then press /start again", keyboard)
            return "ok"

        keyboard = {
            "inline_keyboard": [
                [{"text": "Verify Now", "url": f"https://yourapp.onrender.com/verify?uid={user_id}"}]
            ]
        }
        send(user_id, "Complete verification", keyboard)

    # ---------------- STATS ----------------
    elif text == "📊 Stats":
        u = sb("users", params=f"?user_id=eq.{user_id}")[0]
        refs = sb("users", params=f"?referrer_id=eq.{user_id}")
        send(user_id, f"Points: {u['points']}\nReferrals: {len(refs)}")

    # ---------------- REF LINK ----------------
    elif text == "🔗 Referral Link":
        send(user_id, f"https://t.me/ZenithWave_Refer_Bot?start={user_id}")

    # ---------------- WITHDRAW ----------------
    elif text == "💸 Withdraw":
        u = sb("users", params=f"?user_id=eq.{user_id}")[0]
        setting = sb("settings")[0]
        need = setting["withdraw_points"]

        if u["points"] < need:
            send(user_id, "Not enough points")
            return "ok"

        coupons = sb("coupons", params="?used=eq.false")
        if not coupons:
            send(user_id, "Coupons out of stock")
            return "ok"

        c = coupons[0]

        sb("coupons", "patch", {"used": True}, f"?id=eq.{c['id']}")
        sb("users", "patch", {"points": u["points"] - need}, f"?user_id=eq.{user_id}")

        send(user_id, f"Coupon: {c['code']}")

        sb("logs", "post", {
            "user_id": user_id,
            "coupon": c["code"]
        })

        for a in ADMINS:
            send(a, f"User {user_id} redeemed {c['code']}")

    # ---------------- ADMIN ----------------
    elif text == "/admin" and user_id in ADMINS:
        send(user_id, "Admin Panel", admin_menu())

    elif text == "➕ Add Coupon" and user_id in ADMINS:
        send(user_id, "Send coupons line by line")
        user_states[user_id] = "add"

    elif text == "➖ Remove Coupon" and user_id in ADMINS:
        send(user_id, "Send number to remove")
        user_states[user_id] = "remove"

    elif text == "📦 Coupon Stock" and user_id in ADMINS:
        coupons = sb("coupons", params="?used=eq.false")
        send(user_id, f"Stock: {len(coupons)}")

    elif text == "📜 Redeems Log" and user_id in ADMINS:
        logs = sb("logs", params="?select=*&order=id.desc&limit=10")
        txt = ""
        for l in logs:
            txt += f"{l['user_id']} -> {l['coupon']}\n"
        send(user_id, txt or "No logs")

    elif text == "⚙ Change Withdraw Points" and user_id in ADMINS:
        send(user_id, "Send new points")
        user_states[user_id] = "points"

    # ---------------- STATES ----------------
    else:
        state = user_states.get(user_id)

        if state == "add":
            codes = text.split("\n")
            for c in codes:
                if c.strip():
                    sb("coupons", "post", {"code": c.strip(), "used": False})
            send(user_id, "Coupons added")
            user_states[user_id] = None

        elif state == "remove":
            n = int(text)
            coupons = sb("coupons", params="?used=eq.false")
            for c in coupons[:n]:
                sb("coupons", "delete", params=f"?id=eq.{c['id']}")
            send(user_id, "Removed")
            user_states[user_id] = None

        elif state == "points":
            sb("settings", "patch", {"withdraw_points": int(text)}, "?id=eq.1")
            send(user_id, "Updated")
            user_states[user_id] = None

    return "ok"

# ---------------- WEB VERIFY ----------------
@app.route("/verify")
def verify():
    uid = request.args.get("uid")
    return f"""
    <html>
    <body style='background:black;color:white;text-align:center'>
    <h1>Verify</h1>
    <button onclick="go()">Verify Now</button>
    <script>
    function getDevice(){{
        return navigator.userAgent+screen.width+screen.height+navigator.platform;
    }}
    function go(){{
        let d = btoa(getDevice());
        fetch('/done?uid={uid}&device='+d)
        .then(()=>window.location='https://t.me/ZenithWave_Refer_Bot')
    }}
    </script>
    </body>
    </html>
    """

@app.route("/done")
def done():
    uid = request.args.get("uid")
    device = request.args.get("device")

    exist = sb("users", params=f"?device_id=eq.{device}")
    if exist:
        return "Device already used"

    sb("users", "patch", {
        "verified": True,
        "device_id": device
    }, f"?user_id=eq.{uid}")

    user = sb("users", params=f"?user_id=eq.{uid}")[0]

    if user.get("referrer_id"):
        ref = user["referrer_id"]
        r = sb("users", params=f"?user_id=eq.{ref}")[0]

        sb("users", "patch", {"points": r["points"] + 1}, f"?user_id=eq.{ref}")
        send(ref, "New referral +1 point")

    return "ok"

@app.route("/")
def home():
    return "Running"

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
