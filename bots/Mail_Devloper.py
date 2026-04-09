import os
import requests
import telebot
from telebot import types
import datetime
import random
import string
import threading
import re
import time
import json

OWNER_ID = '5716550739'
BOT_TOKEN = '8242402286:AAEniXofasEUGSe4VtJQD7SpUibZKfcu-tI'

bot = telebot.TeleBot(BOT_TOKEN)
API_BASE = "https://api.mail.tm"

user_sessions = {}  # Store user_id: {email, password, token}

# File to store statistics and user data
DATA_FILE = "bot_data.json"

# Initialize data structure
def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"users": {}, "stats": {"total_emails": 0, "total_otps": 0}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Load data at startup
bot_data = load_data()

def get_random_password(length=12):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def login_mailtm(email, password):
    try:
        resp = requests.post(API_BASE + "/token", json={"address": email, "password": password})
        if resp.status_code == 200:
            return resp.json()['token']
        else:
            return None
    except:
        return None

def check_new_messages(user_id):
    if user_id not in user_sessions:
        return
    session = user_sessions[user_id]
    headers = {"Authorization": f"Bearer {session['token']}"}
    try:
        resp = requests.get(API_BASE + "/messages", headers=headers)
        resp.raise_for_status()
        messages = resp.json()['hydra:member']
        for msg in messages:
            msg_id = msg['id']

            # Get full message
            detail = requests.get(f"{API_BASE}/messages/{msg_id}", headers=headers).json()
            subject = detail.get("subject", "")
            text = detail.get("text", "")

            # Try to find OTP: look for 4-8 digit code in subject or text
            otp_match = re.search(r'\b(\d{4,8})\b', subject + "\n" + text)
            if otp_match:
                otp = otp_match.group(1)
                sender = detail.get("from", {}).get("address", "Unknown Sender")

                # Update OTP count in statistics
                bot_data["stats"]["total_otps"] += 1
                save_data(bot_data)

                full_message = (
                    f"📨 <b>New Message Received</b>\n"
                    f"<b>From:</b> {sender}\n"
                    f"<b>Subject:</b> {subject}\n"
                    f"<b>OTP:</b> <code>{otp}</code>\n\n"
                    f"<b>Message:</b>\n{text}"
                )
                bot.send_message(user_id, full_message, parse_mode="html")

                # Delete this message after reading
                requests.delete(f"{API_BASE}/messages/{msg_id}", headers=headers)
            else:
                # If you want to notify message without OTP, skip or send message here
                pass
    except Exception as e:
        print(f"[ERROR] Checking messages for {user_id}: {e}")

def start_checking(user_id):
    # Run infinite checking every 10 seconds in separate thread for this user
    def run():
        while user_id in user_sessions:
            token = user_sessions[user_id]['token']
            if not token:
                # Try login again if no token
                email = user_sessions[user_id]['email']
                password = user_sessions[user_id]['password']
                new_token = login_mailtm(email, password)
                if new_token:
                    user_sessions[user_id]['token'] = new_token
            check_new_messages(user_id)
            time.sleep(10)
    thread = threading.Thread(target=run, daemon=True)
    thread.start()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = str(message.from_user.id)
    name = message.from_user.first_name

    # Add user to database if not exists
    if user_id not in bot_data["users"]:
        bot_data["users"][user_id] = {
            "name": name,
            "username": message.from_user.username,
            "join_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        save_data(bot_data)

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(text='❤𝐂𝐑𝐄𝐀𝐓𝐎𝐑❤', url='https://t.me/BugsAllRounder01'),
        types.InlineKeyboardButton(text='❤ 𝐂𝐇𝐀𝐍𝐍𝐄𝐋❤', url='https://t.me/Devloper_Network'),
        types.InlineKeyboardButton(text="💣Delete My Account", callback_data='delete'),
        types.InlineKeyboardButton(text="💌Create a New Email", callback_data='create')
    )
    welcome_text = f"🕶 WELCOME, AGENT {name}⚡\nUse /info to check your data.\nBot By: @devloper_admin_bot"
    bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.message.chat.id
    if call.data == "create":
        create_mailtm_email(call.message)
    elif call.data == "delete":
        delete_account(call.message)

def create_mailtm_email(message):
    user_id = message.chat.id
    try:
        # Get domains from mail.tm
        domain_resp = requests.get(API_BASE + "/domains")
        domain_resp.raise_for_status()
        domains = domain_resp.json().get('hydra:member')
        if not domains:
            bot.send_message(user_id, "❗Failed to get domains from API.")
            return
        domain = domains[0]['domain']

        login = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
        email = f"{login}@{domain}"
        password = get_random_password()

        # Register account
        data = {"address": email, "password": password}
        reg_resp = requests.post(API_BASE + "/accounts", json=data)

        if reg_resp.status_code not in [200, 201]:
            bot.send_message(user_id, f"❗Failed to create email account.\n{reg_resp.text}")
            return

        # Update email count in statistics
        bot_data["stats"]["total_emails"] += 1
        save_data(bot_data)

        # Login to get token
        token = login_mailtm(email, password)
        if not token:
            bot.send_message(user_id, "❗Failed to login to new account.")
            return

        # Save session info
        user_sessions[user_id] = {
            "email": email,
            "password": password,
            "token": token
        }

        # Start background checking for OTPs
        start_checking(user_id)

        bot.send_message(user_id, f"✅ Email Created!\n📧 {email}\nUse this email for OTPs. I will send OTP automatically here.")

    except Exception as e:
        bot.send_message(user_id, "❗Failed to create email.")
        print(f"[ERROR] Create email: {e}")

def delete_account(message):
    user_id = message.chat.id
    if user_id in user_sessions:
        del user_sessions[user_id]
        bot.send_message(user_id, "Your email account session deleted.")
    else:
        bot.send_message(user_id, "You don't have an email account.")

@bot.message_handler(commands=["info"])
def info(message):
    user_id = message.from_user.id
    if user_id in user_sessions:
        email = user_sessions[user_id]['email']
        bot.send_message(user_id, f"Your active email: {email}")
    else:
        bot.send_message(user_id, "No active email found. Use /start and create one.")

@bot.message_handler(commands=["stats"])
def stats(message):
    user_id = str(message.from_user.id)
    if user_id != OWNER_ID:
        bot.reply_to(message, "❌ This command is only for the bot owner.")
        return
        
    stats_text = (
        f"📊 Bot Statistics:\n"
        f"• Total Emails Created: {bot_data['stats']['total_emails']}\n"
        f"• Total OTPs Received: {bot_data['stats']['total_otps']}\n"
        f"• Total Users: {len(bot_data['users'])}"
    )
    bot.reply_to(message, stats_text)

@bot.message_handler(commands=["broadcast"])
def broadcast(message):
    user_id = str(message.from_user.id)
    if user_id != OWNER_ID:
        bot.reply_to(message, "❌ This command is only for the bot owner.")
        return
        
    # Extract the broadcast message text
    broadcast_text = message.text.replace('/broadcast', '').strip()
    if not broadcast_text:
        bot.reply_to(message, "❌ Please provide a message to broadcast. Format: /broadcast Your message here")
        return
        
    # Send to all users
    sent_count = 0
    failed_count = 0
    total_users = len(bot_data["users"])
    
    for uid, user_info in bot_data["users"].items():
        try:
            bot.send_message(uid, f"📢 Broadcast from admin:\n\n{broadcast_text}")
            sent_count += 1
        except Exception as e:
            print(f"Failed to send to {uid}: {e}")
            failed_count += 1
            
    # Report results to owner
    result_text = (
        f"📤 Broadcast completed:\n"
        f"• Total users: {total_users}\n"
        f"• Successfully sent: {sent_count}\n"
        f"• Failed: {failed_count}"
    )
    bot.reply_to(message, result_text)

@bot.message_handler(commands=["showallusers"])
def show_all_users(message):
    user_id = str(message.from_user.id)
    if user_id != OWNER_ID:
        bot.reply_to(message, "❌ This command is only for the bot owner.")
        return
        
    if not bot_data["users"]:
        bot.reply_to(message, "No users found in the database.")
        return
        
    users_text = "👥 All Bot Users:\n\n"
    for i, (uid, user_info) in enumerate(bot_data["users"].items(), 1):
        username = f"@{user_info.get('username', 'N/A')}" if user_info.get('username') else "N/A"
        users_text += f"{i}. {user_info.get('name', 'Unknown')} ({username}) - Joined: {user_info.get('join_date', 'Unknown')}\nID: {uid}\n\n"
    
    # Telegram has a message length limit, so we might need to split the message
    if len(users_text) > 4096:
        for x in range(0, len(users_text), 4096):
            bot.send_message(message.chat.id, users_text[x:x+4096])
    else:
        bot.send_message(message.chat.id, users_text)

# Start polling
print("⚔️𝐒𝐓𝐄𝐏𝐏𝐈𝐍𝐆 𝐈𝐍𝐓𝐎 𝐓𝐇𝐄 𝐄𝐑𝐀 𝐎𝐅 𝐒𝐏𝐈𝐃𝐄𝐘𝐘 ⚔️")

if __name__ == "__main__":
    try:
        print("[DEBUG] Removing webhook...")
        bot.remove_webhook()
        print("[DEBUG] Starting polling...")
        bot.infinity_polling()
    except Exception as e:
        print(f"[ERROR] Bot failed to start polling: {e}")
