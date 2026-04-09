import json
import requests
import os
import asyncio
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, ContextTypes, filters

REMOVE_BG_API = 'TpM7RcbeCC4d3fESzKna1meJ'
TOKEN = '7429157341:AAFUmX5wO7NUVFZ28Vv8NKcslVBbxp2YYQQ'
ADMIN_ID = 5716550739  # Replace with your Telegram ID
USERS_FILE = 'users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    return []

def save_user(user_id):
    users = load_users()
    if user_id not in users:
        users.append(user_id)
        with open(USERS_FILE, 'w') as f:
            json.dump(users, f)

def build_progress_bar(percent, stage):
    total_blocks = 10
    filled = int(percent / 10)
    empty = total_blocks - filled
    bar = '█' * filled + '░' * empty

    emoji = {
        'uploading': '📤',
        'removing': '🎨',
        'finishing': '✅'
    }.get(stage, '🔄')

    title = {
        'uploading': "Uploading Image",
        'removing': "Removing Background",
        'finishing': "Finalizing"
    }.get(stage, "Processing")

    return f"*{emoji} {title}*\n`[{bar}] {percent}%`"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id)

    await update.message.reply_text(
        "🎉 *Welcome to* `UltraRemover™ Bot`\n\n"
        "📷 *Send me any image*, and I’ll erase its background in seconds!\n"
        "⚡ _Fast, Clean, Pro-Level Output_\n\n"
        "🪄 Just drop your image now 👇",
        parse_mode="Markdown"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id)

    msg = await update.message.reply_text(build_progress_bar(0, 'uploading'), parse_mode="Markdown")

    for p in [20, 40, 60, 80, 95]:
        await asyncio.sleep(0.5)
        await msg.edit_text(build_progress_bar(p, 'uploading'), parse_mode="Markdown")

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    image_path = "input.jpg"
    await file.download_to_drive(image_path)

    await msg.edit_text(build_progress_bar(40, 'removing'), parse_mode="Markdown")
    await asyncio.sleep(0.7)

    with open(image_path, 'rb') as image_file:
        response = requests.post(
            'https://api.remove.bg/v1.0/removebg',
            files={'image_file': image_file},
            data={'size': 'auto'},
            headers={'X-Api-Key': REMOVE_BG_API}
        )

    if response.status_code == 200:
        output_path = "no_bg.png"
        with open(output_path, 'wb') as out:
            out.write(response.content)

        await msg.edit_text(build_progress_bar(100, 'finishing'), parse_mode="Markdown")
        await asyncio.sleep(1)
        await update.message.reply_photo(photo=open(output_path, 'rb'), caption="✅ *Here’s your image without background!*", parse_mode="Markdown")
    else:
        await msg.edit_text(f"❌ *Error while processing image!*\n`{response.status_code}: {response.text}`", parse_mode="Markdown")

# /broadcast command for admin
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not allowed to use this command.")
        return

    if not context.args:
        await update.message.reply_text("❗ Usage:\n/broadcast Your message to all users")
        return

    message = ' '.join(context.args)
    users = load_users()

    sent, failed = 0, 0
    for uid in users:
        try:
            await context.bot.send_message(chat_id=uid, text=message)
            sent += 1
        except:
            failed += 1
        await asyncio.sleep(0.05)

    await update.message.reply_text(f"📢 Broadcast complete:\n✅ Sent: {sent}\n❌ Failed: {failed}")
# /showusers command (admin only)
async def show_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not allowed to use this command.")
        return

    users = load_users()
    if not users:
        await update.message.reply_text("📭 No users found.")
        return

    header = f"👥 *Total Users:* `{len(users)}`\n\n"
    user_list = "\n".join([f"`{uid}`" for uid in users])
    await update.message.reply_text(header + user_list, parse_mode="Markdown")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("showusers", show_users))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()
