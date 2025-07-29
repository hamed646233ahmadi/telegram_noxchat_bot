import os
TOKEN = os.getenv("TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from pymongo import MongoClient
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

# ====== تنظیمات مهم ======
TOKEN = "mongodb+srv://hamed008a:NwJ9GLgstIOY1n1v@cluster0.bbdhpii.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
MONGO_URI = "mongodb+srv://hamed008a:NwJ9GLgstIOY1n1v@cluster0.bbdhpii.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

# ====== اتصال به دیتابیس ======
client = MongoClient(MONGO_URI)
db = client["dating"]
users = db["users"]
settings_col = db["settings"]
active_chats = {}

# ====== تنظیمات پیش‌فرض ======
default_settings = {
    "daily_free_chats": 3,
    "coin_per_chat": 1,
    "coin_per_invite": 5
}

def get_settings():
    st = settings_col.find_one({})
    if not st:
        settings_col.insert_one(default_settings)
        return default_settings
    return st

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c

def reset_daily_free_chats_if_needed(user):
    today = datetime.now().strftime("%Y-%m-%d")
    if user.get("last_reset") != today:
        settings = get_settings()
        users.update_one({"_id": user["_id"]}, {"$set": {
            "daily_free_chats": settings["daily_free_chats"],
            "last_reset": today
        }})

def start(update: Update, context: CallbackContext):
    update.message.reply_text("سلام! برای ثبت‌نام /register رو بزن.")

def register(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    args = context.args
    invited_by = int(args[0]) if args else None

    user = users.find_one({"_id": user_id})
    if user:
        update.message.reply_text("شما قبلاً ثبت‌نام کردید.")
        return

    users.insert_one({
        "_id": user_id,
        "step": "name",
        "invited_by": invited_by,
        "coins": 0,
        "daily_free_chats": get_settings()["daily_free_chats"],
        "last_reset": datetime.now().strftime("%Y-%m-%d"),
        "available": True
    })
    update.message.reply_text("نام خودت رو وارد کن:")

def handle_text(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    text = update.message.text
    user = users.find_one({"_id": user_id})

    if not user:
        update.message.reply_text("اول باید ثبت‌نام کنی. /register")
        return

    if user_id in active_chats:
        partner_id = active_chats[user_id]
        context.bot.send_message(partner_id, f"پیام ناشناس: {text}")
        return

    step = user.get("step")
    if step == "name":
        users.update_one({"_id": user_id}, {"$set": {"name": text, "step": "age"}})
        update.message.reply_text("چند سالته؟")
    elif step == "age":
        if not text.isdigit():
            update.message.reply_text("سن باید عدد باشه.")
            return
        users.update_one({"_id": user_id}, {"$set": {"age": int(text), "step": "gender"}})
        update.message.reply_text("جنسیتت چیه؟ (مثلاً: پسر / دختر)")
    elif step == "gender":
        users.update_one({"_id": user_id}, {"$set": {"gender": text, "step": "target"}})
        update.message.reply_text("به دنبال آشنایی با چه جنسیتی هستی؟")
    elif step == "target":
        users.update_one({"_id": user_id}, {"$set": {"target": text, "step": "city"}})
        update.message.reply_text("نام شهرت چیه؟")
    elif step == "city":
        users.update_one({"_id": user_id}, {"$set": {"city": text, "step": "bio"}})
        update.message.reply_text("بیو کوتاه بنویس:")
    elif step == "bio":
        users.update_one({"_id": user_id}, {"$set": {"bio": text, "step": "location"}})
        ask_location(update)
    else:
        update.message.reply_text("برای شروع چت /find و برای خروج /end رو بزن.")

def ask_location(update: Update):
    kb = [[KeyboardButton("📍 ارسال موقعیت مکانی", request_location=True)]]
    update.message.reply_text("موقعیت مکانی‌تو بفرست:", reply_markup=ReplyKeyboardMarkup(kb, resize_keyboard=True))

def handle_location(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    loc = update.message.location
    users.update_one({"_id": user_id}, {"$set": {
        "location": [loc.latitude, loc.longitude],
        "step": "done",
        "available": True
    }})
    update.message.reply_text("✅ پروفایل شما ثبت شد. برای شروع چت /find رو بزن.")

    user = users.find_one({"_id": user_id})
    invited_by = user.get("invited_by")
    if invited_by:
        settings = get_settings()
        users.update_one({"_id": invited_by}, {"$inc": {"coins": settings["coin_per_invite"]}})
        context.bot.send_message(invited_by, f"🎉 یک نفر با کد دعوت شما عضو شد و {settings['coin_per_invite']} سکه گرفتید.")

def find_friend(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    me = users.find_one({"_id": user_id})

    if not me or me.get("step") != "done":
        update.message.reply_text("ابتدا ثبت‌نام کن با /register")
        return

    reset_daily_free_chats_if_needed(me)

    if me.get("available") == False:
        update.message.reply_text("شما در حال چت هستید. برای پایان /end بزن.")
        return

    settings = get_settings()

    if me.get("daily_free_chats", 0) > 0:
        users.update_one({"_id": user_id}, {"$inc": {"daily_free_chats": -1}})
    elif me.get("coins", 0) >= settings["coin_per_chat"]:
        users.update_one({"_id": user_id}, {"$inc": {"coins": -settings["coin_per_chat"]}})
    else:
        update.message.reply_text("چت رایگان تموم شده و سکه‌ای نداری. /invite برای دریافت سکه.")
        return

    my_location = me.get("location")
    my_target = me.get("target")
    candidates = users.find({
        "_id": {"$ne": user_id},
        "step": "done",
        "available": True,
        "gender": my_target
    })

    for other in candidates:
        dist = haversine(my_location[0], my_location[1], other["location"][0], other["location"][1])
        if dist < 50:
            partner_id = other["_id"]
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            users.update_one({"_id": user_id}, {"$set": {"available": False}})
            users.update_one({"_id": partner_id}, {"$set": {"available": False}})
            context.bot.send_message(partner_id, "💬 یک دوست جدید پیدا شد. شروع کن!")
            context.bot.send_message(user_id, "💬 یک دوست جدید پیدا شد. شروع کن!")
            return

    update.message.reply_text("کسی نزدیک شما پیدا نشد.")

def end_chat(update: Update, context: CallbackContext):
    user_id = update.message.chat_id
    if user_id in active_chats:
        partner_id = active_chats[user_id]
        context.bot.send_message(partner_id, "❌ چت توسط طرف مقابل پایان یافت.")
        context.bot.send_message(user_id, "✅ چت بسته شد.")
        users.update_one({"_id": user_id}, {"$set": {"available": True}})
        users.update_one({"_id": partner_id}, {"$set": {"available": True}})
        del active_chats[user_id]
        del active_chats[partner_id]
    else:
        update.message.reply_text("در حال حاضر در چتی نیستید.")

def my_coins(update: Update, context: CallbackContext):
    user = users.find_one({"_id": update.message.chat_id})
    reset_daily_free_chats_if_needed(user)
    update.message.reply_text(
        f"سکه‌ها: {user.get('coins', 0)}\n"
        f"چت رایگان باقی‌مانده امروز: {user.get('daily_free_chats', 0)}"
    )

def invite(update: Update, context: CallbackContext):
    update.message.reply_text(f"کد دعوت شما: {update.message.chat_id}\nدوستانت با این کد عضو شن تا سکه بگیری.")

def buy_coin(update: Update, context: CallbackContext):
    update.message.reply_text("برای خرید سکه با پشتیبانی تماس بگیر یا به لینک پرداخت برو.")

def main():
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("register", register, pass_args=True))
    dp.add_handler(CommandHandler("find", find_friend))
    dp.add_handler(CommandHandler("end", end_chat))
    dp.add_handler(CommandHandler("mycoins", my_coins))
    dp.add_handler(CommandHandler("invite", invite))
    dp.add_handler(CommandHandler("buycoin", buy_coin))
    dp.add_handler(MessageHandler(Filters.location, handle_location))
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_text))

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
