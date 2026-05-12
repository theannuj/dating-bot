# -*- coding: utf-8 -*-
import html 
import json
import os
import random
import threading
import time
import traceback
from pathlib import Path
 
from flask import Flask, request
import psycopg2
from psycopg2 import pool
import telebot

DB_POOL = None
from telebot import apihelper
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove

apihelper.CONNECT_TIMEOUT = 5
apihelper.READ_TIMEOUT = 7

TOKEN = os.getenv("BOT_TOKEN")
MAIN_ADMIN_ID = 526264365
PAYMENT_ADMINS = [MAIN_ADMIN_ID]
CHAT_ADMINS = [MAIN_ADMIN_ID]
PAYMENT_LINK = "https://tinyurl.com/SecretSwipe"
VIP_PLAN_DAYS = {
    "1m": ("1 Month", 30),
    "3m": ("3 Months", 90),
    "6m": ("6 Months", 180),
    "1y": ("1 Year", 365),
}

# --- AI SETUP START ---
import requests
import os
from datetime import datetime, timedelta, timezone

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
AI_MODEL = "microsoft/wizardlm-2-8x22b"

def get_ist_time():
    ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
    return ist_now.strftime("%I:%M %p")

# 🔥 THE CLEAN SYSTEM WRAPPER (No hardcoded persona)
def build_ai_prompt(name, age, location, character_prompt, user_real_name=None, user_city=None):
    current_time = get_ist_time()
    
    # 🧠 SMART MEMORY: User ke database facts
    user_context = ""
    if user_real_name and user_real_name.strip() and user_real_name.lower() != "user":
        user_context += f"- User's Name: {user_real_name}\n"
    if user_city and user_city.strip():
        user_context += f"- User's City: {user_city}\n"
        
    if user_context:
        user_context = f"\n[CRITICAL: KNOWN FACTS ABOUT THE USER]\n{user_context}*Use this naturally. Always prefer their Real Name over Telegram name.*\n"
        
    return f"""You are {name}, a {age}-year-old girl from {location}.

[YOUR CHARACTER & PERSONA]
{character_prompt}

Current Time in India: {current_time}
{user_context}

[TECHNICAL RULES]
1. Output ONLY the text message to be sent. No tags, no internal thoughts, no reasoning.
2. Keep replies natural and conversational, as if chatting on WhatsApp/Telegram.
3. Be consistent with the character described above. 

NEVER break character. NEVER sound like an AI assistant."""

def get_ai_reply(system_prompt, message_history):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://t.me",
        "X-Title": "Bot Testing"
    }
    
    messages = [{"role": "system", "content": system_prompt}] + message_history
    
    data = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.85, 
        "max_tokens": 100, 
        "frequency_penalty": 0.8, 
        "presence_penalty": 0.6   
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        result = response.json()
        if "error" in result:
            print(f"🚨 OPENROUTER ERROR: {result['error']}", flush=True)
            return "mera net thoda slow chal raha hai yaar"
        return result['choices'][0]['message']['content']
    except Exception as e:
        print(f"❌ AI API Error: {e}", flush=True)
        return "mera net thoda slow chal raha hai yaar"
# --- AI SETUP END ---



BASE_DIR = Path(__file__).resolve().parent
PROFILES_FILE = BASE_DIR / "profiles.json"
STATE_FILE = BASE_DIR / "bot_state.json"
WEBHOOK_BASE_URL = (
    os.getenv("WEBHOOK_BASE_URL")
    or os.getenv("RAILWAY_STATIC_URL")
    or os.getenv("RAILWAY_PUBLIC_DOMAIN")
)


DISCLAIMER_TEXT = """📄 <b>Terms & Disclaimer</b>

<b>1. Nature of Service</b>
• This platform provides chat-based interactions for entertainment and social connection.  
• We do not guarantee real-life meetings, relationships, or outcomes.

<b>2. Matching & Users</b>
• Matches are based on system logic, availability, and user activity.  
• We do not guarantee connection with any specific person.

<b>3. Interaction System</b>
• Some initial interactions may be automated to maintain engagement.  
• These are designed to ensure a smooth user experience.

<b>4. Payments & Features</b>
• Payments unlock additional features such as extended chat access or priority matching.  
• Payments do not guarantee any specific match or response.  
• All payments are non-refundable once activated.

<b>5. User Responsibility</b>
• You agree to behave respectfully with others.  
• Abuse, harassment, or misuse may result in restriction or permanent ban.

<b>6. Privacy & Safety</b>
• Do not share personal or sensitive information (phone, address, etc.).  
• We are not responsible for information voluntarily shared with others.

<b>7. Service Availability</b>
• We do not guarantee uninterrupted or error-free service.  
• Features may change at any time without notice.

<b>8. Age Requirement</b>
• You must be 18+ to use this service.  
• Accounts found to be underage may be removed.

<b>9. Data & Account Control</b>
• You may reset your profile anytime using /reset.  
• Some data may be retained for safety and system purposes.

By continuing to use this service, you agree to these terms."""


def init_db_pool():
    global DB_POOL
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        return
    try:
        # Ye pehle se 1 se 20 connection ready rakhega
        DB_POOL = psycopg2.pool.ThreadedConnectionPool(1, 20, database_url, connect_timeout=5, client_encoding="UTF8")
        print("✅ Database Connection Pool Started", flush=True)
    except Exception as e:
        print(f"❌ Pool error: {e}", flush=True)

def get_db_connection():
    global DB_POOL
    if not DB_POOL:
        init_db_pool()
    if DB_POOL:
        try:
            return DB_POOL.getconn()
        except Exception as e:
            print(f"DB getconn error: {e}", flush=True)
    return None

def release_db_connection(conn):
    global DB_POOL
    if DB_POOL and conn:
        try:
            DB_POOL.putconn(conn)
        except:
            pass


# Legacy text checking removed to save CPU (Database uses clean UTF-8 now)

def normalize_storage_value(value):
    return value


def parse_matches_payload(value):
    if isinstance(value, list):
        return normalize_storage_value(value)
    if not value:
        return []
    try:
        return normalize_storage_value(json.loads(value))
    except Exception:
        return []


def user_record_score(record):
    if not isinstance(record, dict):
        return 0

    score = 0
    for key in ("name", "city", "photo", "gender", "step", "payment_status"):
        if record.get(key):
            score += 1

    if record.get("agreed"):
        score += 1
    if record.get("paid"):
        score += 2

    for key in ("matches", "shown", "liked", "skipped", "incoming_likes", "used_openers", "pending_events"):
        value = record.get(key)
        if isinstance(value, list):
            score += len(value)

    chat_threads = record.get("chat_threads", {})
    if isinstance(chat_threads, dict):
        score += len(chat_threads) * 5
        for thread in chat_threads.values():
            if isinstance(thread, dict):
                score += len(thread.get("messages", []))

    profile_cache = record.get("profile_cache", {})
    if isinstance(profile_cache, dict):
        score += len(profile_cache)

    return score


def init_vip_table():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS vip_users (
        user_id BIGINT PRIMARY KEY,
        paid BOOLEAN,
        payment_status TEXT,
        matches TEXT,
        vip_start_date BIGINT,
        vip_end_date BIGINT
        )
        """)
        cur.execute("ALTER TABLE vip_users ADD COLUMN IF NOT EXISTS paid BOOLEAN")
        cur.execute("ALTER TABLE vip_users ADD COLUMN IF NOT EXISTS payment_status TEXT")
        cur.execute("ALTER TABLE vip_users ADD COLUMN IF NOT EXISTS matches TEXT")
        cur.execute("ALTER TABLE vip_users ADD COLUMN IF NOT EXISTS vip_start_date BIGINT")
        cur.execute("ALTER TABLE vip_users ADD COLUMN IF NOT EXISTS vip_end_date BIGINT")
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"VIP table init error: {e}", flush=True)
    finally:
        release_db_connection(conn)


def save_vip_to_db(user_id, user):
    conn = get_db_connection()
    if not conn:
        return
    try:
        normalized_user = normalize_storage_value(user)
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO vip_users (user_id, paid, payment_status, matches, vip_start_date, vip_end_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET paid = EXCLUDED.paid,
        payment_status = EXCLUDED.payment_status,
        matches = EXCLUDED.matches,
        vip_start_date = EXCLUDED.vip_start_date,
        vip_end_date = EXCLUDED.vip_end_date
        """, (
            user_id,
            normalized_user.get("paid"),
            normalized_user.get("payment_status"),
            json.dumps(normalized_user.get("matches", []), ensure_ascii=False),
            normalized_user.get("vip_start_date"),
            normalized_user.get("vip_end_date"),
        ))
        conn.commit()
        cur.execute("SELECT COUNT(*) FROM vip_users")
        count = cur.fetchone()[0]
        # print("VIP rows after insert:", count)
        cur.close()
    except Exception as e:
        conn.rollback()
        print("DB error:", e, flush=True)
    finally:
        release_db_connection(conn)


def load_vip_from_db():
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, paid, payment_status, matches, vip_start_date, vip_end_date FROM vip_users")
        rows = cur.fetchall()
        result = {
            row[0]: {
                "paid": row[1],
                "payment_status": normalize_storage_value(row[2]),
                "matches": parse_matches_payload(row[3]),
                "vip_start_date": row[4],
                "vip_end_date": row[5],
            }
            for row in rows
        }
        print("Rows fetched from DB:", len(rows))
        cur.close()
        return result
    except Exception as e:
        print(f"VIP load error: {e}", flush=True)
        return {}
    finally:
        release_db_connection(conn)


def init_users_table():
    conn = get_db_connection()
    if not conn:
        return
    try:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        data TEXT
        )
        """)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS data TEXT")
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"Users table init error: {e}", flush=True)
    finally:
        release_db_connection(conn)


def run_schema_migrations():
    init_users_table()
    init_vip_table()


def serialize_user_record(user):
    return json.dumps(normalize_storage_value(user), ensure_ascii=False)


def save_user_to_db(user_id, user):
    conn = get_db_connection()
    if not conn:
        return
    try:
        serialized_user = serialize_user_record(user)
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO users (user_id, data)
        VALUES (%s, %s)
        ON CONFLICT (user_id)
        DO UPDATE SET data = EXCLUDED.data
        """, (user_id, serialized_user))
        conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"DB save error: {e}", flush=True)
    finally:
        release_db_connection(conn)


def load_users_from_db():
    conn = get_db_connection()
    if not conn:
        return {}
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id, data FROM users")
        rows = cur.fetchall()
        cur.close()
        result = {}
        for row in rows:
            try:
                result[int(row[0])] = normalize_storage_value(json.loads(row[1]))
            except Exception as row_error:
                print(f"Skipping bad user row {row[0]}: {row_error}", flush=True)
        return result
    except Exception as e:
        print(f"Users load error: {e}", flush=True)
        return {}
    finally:
        release_db_connection(conn)

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
BTN_BUY = "🔓 Unlock Chat"
BTN_VIEW_PROFILE = "View profile"
BTN_LIKE = "💚"
BTN_SKIP = "❌"
BTN_MAIN_MENU = "🏠 Main Menu"
BTN_SEND_GIFT = "🎁 Send gift"
BTN_SEE_LIKES = "See who likes you"
BTN_GET_VIP = "💎 Get VIP"
BTN_MY_PROFILE = "👤 My profile"
BTN_HOW_IT_WORKS = "❓ How it works"
BTN_VIP = "🔓 Unlock Chat"
BTN_CHAT = "💬 Chat"
BTN_SEND_PAYMENT = "Send payment screenshot"
BTN_NEXT_MATCH = "➡️ Next Match"
BTN_PREV_MATCH = "⬅️ Prev"
BTN_MATCH_NEXT = "➡️ Next"
BTN_END_CHAT = "❌ End Chat"
BTN_ADMIN_CHATS = "💬 Admin Chats"
BTN_ADMIN_REFRESH = "🔄 Refresh"
BTN_ADMIN_UNREAD = "📩 Unread Only"
BTN_ADMIN_PANEL = "📊 Admin Panel"
BTN_ADMIN_STATS = "📊 Stats"
BTN_ADMIN_PENDING = "⏳ Pending"
BTN_ADMIN_BACK = "🔙 Back"
BTN_CONFIRM_END_CHAT = "✅ Yes, End Chat"
BTN_CANCEL_END_CHAT = "❌ Cancel"
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
    # --- Short & natural ---
    "hey…",
    "hmm hi",
    "hey you",
    "hi :)",
    "hmm…",
    "hello… maybe 😄",
    
    # --- Curious ---
    "you seem interesting 👀",
    "hmm… not sure why I texted",
    "idk… just felt like texting",
    "you don't look boring 😄",
    "something about you…",
    "okay… I'm curious now",
    
    # --- Soft human feel ---
    "wasn't going to text… but okay",
    "I usually don't text first 😅",
    "this feels random 😄",
    "hmm this is a bit weird",
    "not sure if I should say hi…",
    
    # --- Playful doubt (trust builder) ---
    "you're real right? 😅",
    "tum real ho na?",
    "btw you're not a bot… right?",
    "don't tell me you're a bot 😄",
    "idk thoda suspicious lag raha 😄",
    
    # --- Light tease ---
    "you look like trouble 😄",
    "I think you reply late…",
    "don't be boring please 😄",
    "let's see how this goes",
    "try not to be dry 😏",
    
    # --- Light question (limited use) ---
    "btw where are you from? 😄",
    "tum kaha se ho?",
    "random… where are you from?",
    "I feel you're not from here 😄",
    "waise tum kaha ke ho?",
]

FOMO_MESSAGES = [
    "She might go offline soon...",
    "Don't miss your chance to reply...",
    "She's waiting for your message...",
    "This conversation is getting interesting...",
]

bot = telebot.TeleBot(TOKEN, threaded=False)
app = Flask(__name__)
chat_map = {}
admin_active_chat = {}
admin_notifications = {}
LAST_ACTION_TIME = {}
LAST_TEXT_TIME = {}
LAST_ACTIVITY_TIME = {}
LAST_ENGAGEMENT_PING = {}
COOLDOWN_SECONDS = 2.5
INACTIVITY_MIN_SECONDS = 10 * 60
INACTIVITY_MAX_SECONDS = 15 * 60
INACTIVITY_CHECK_SECONDS = 60


def handle_rate_limit(e):
    import re
    error_msg = str(e).lower()
    if "too many requests" in error_msg or "429" in error_msg:
        match = re.search(r'retry after (\d+)', error_msg)
        return int(match.group(1)) + 1 if match else 2
    # 🔥 NEW: Agar Telegram ka server slow ho ya Timeout aaye, toh 1 sec wait karke retry karo
    if "timed out" in error_msg or "connection" in error_msg or "timeout" in error_msg:
        return 1 
    return 0

def safe_send_message(bot, *args, **kwargs):
    for attempt in range(3):
        try:
            return bot.send_message(*args, **kwargs)
        except Exception as e:
            retry_after = handle_rate_limit(e)
            if retry_after > 0:
                time.sleep(retry_after)
                continue
            print(f"❌ send_message error: {e}", flush=True)
            return None
    return None

def safe_send_photo(bot, chat_id, photo, **kwargs):
    for attempt in range(3):
        try:
            return bot.send_photo(chat_id, photo, **kwargs)
        except Exception as e:
            retry_after = handle_rate_limit(e)
            if retry_after > 0:
                time.sleep(retry_after)
                continue
            print(f"❌ Bad photo skipped (chat_id={chat_id}): {e}", flush=True)
            return safe_send_message(bot, chat_id, "Profile loaded")
    return None

def safe_send_chat_action(bot, *args, **kwargs):
    target = args[0] if args else kwargs.get("chat_id")
    for attempt in range(2):
        try:
            return bot.send_chat_action(*args, **kwargs)
        except Exception as e:
            retry_after = handle_rate_limit(e)
            if retry_after > 0:
                time.sleep(retry_after)
                continue
            return None
    return None

def safe_edit_message_text(bot, text, chat_id, message_id, **kwargs):
    for attempt in range(3):
        try:
            return bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if "message is not modified" in error_msg:
                return None
            retry_after = handle_rate_limit(e)
            if retry_after > 0:
                time.sleep(retry_after)
                continue
            print(f"❌ edit_message error: {e}", flush=True)
            return None
    return None

def safe_answer_callback_query(bot, *args, **kwargs):
    for attempt in range(2):
        try:
            # 🔥 FIX: Yahan 'bot.answer_callback_query' aayega, khud ka naam nahi!
            return bot.answer_callback_query(*args, **kwargs)
        except Exception as e:
            retry_after = handle_rate_limit(e)
            if retry_after > 0:
                time.sleep(retry_after)
                continue
            return None
    return None


def is_on_cooldown(user_id):
    now = time.time()
    last = LAST_ACTION_TIME.get(user_id, 0)
    if now - last < COOLDOWN_SECONDS:
        LAST_ACTION_TIME[user_id] = now
        return True
    LAST_ACTION_TIME[user_id] = now
    return False


def touch_user_activity(user_id):
    LAST_ACTIVITY_TIME[user_id] = time.time()


def send_typing_then_message(user_id, text, reply_markup=None, parse_mode=None, delay=None):
    safe_send_chat_action(bot, user_id, "typing")
    time.sleep(delay if delay is not None else typing_delay_for_text(text))
    if parse_mode is None:
        text = f"<b>{text}</b>"
        parse_mode = "HTML"
    safe_send_message(bot, user_id, text, reply_markup=reply_markup, parse_mode=parse_mode)


def load_profiles():
    if not PROFILES_FILE.exists():
        try:
            PROFILES_FILE.write_text("[]", encoding="utf-8")
        except OSError:
            return []

    try:
        with PROFILES_FILE.open("r", encoding="utf-8") as file:
            data = normalize_storage_value(json.load(file))
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
        "age": None,
        "gender": "",
        "city": "",
        "name": "",
        "photo": "",
        "agreed": False,
        "paid": False,
        "awaiting_payment": False,
        "payment_status": "none",
        "payment_proof_photo_id": None,
        "payment_username": "N/A",
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
        "used_openers": [],
        "total_chats_used": 0,
        "chat_limit": 1,
        "chat_started_notified": {},
        "vip_start_date": None,
        "vip_end_date": None,
    }


def get_current_timestamp():
    return int(time.time())


def get_vip_start_timestamp(user):
    try:
        return int(user.get("vip_start_date") or 0)
    except (TypeError, ValueError):
        return 0


def get_vip_end_timestamp(user):
    try:
        return int(user.get("vip_end_date") or 0)
    except (TypeError, ValueError):
        return 0


def is_vip_active(user, now_ts=None):
    if now_ts is None:
        now_ts = get_current_timestamp()
    return get_vip_end_timestamp(user) > now_ts


def sync_user_vip_state(user, now_ts=None):
    if now_ts is None:
        now_ts = get_current_timestamp()
    user.setdefault("vip_start_date", None)
    user.setdefault("vip_end_date", None)
    active = is_vip_active(user, now_ts=now_ts)
    user["paid"] = active
    user["chat_limit"] = 5 if active else 1
    if active:
        user["payment_status"] = "approved"
    elif user.get("payment_status") == "approved" and user.get("vip_end_date"):
        user["payment_status"] = "expired"
    return active


def get_vip_remaining_days(user, now_ts=None):
    if now_ts is None:
        now_ts = get_current_timestamp()
    remaining_seconds = get_vip_end_timestamp(user) - now_ts
    if remaining_seconds <= 0:
        return 0
    return (remaining_seconds + 86399) // 86400


def get_vip_plan_label(user):
    duration_seconds = get_vip_end_timestamp(user) - get_vip_start_timestamp(user)
    duration_days = int(round(duration_seconds / 86400)) if duration_seconds > 0 else 0
    for label, days in VIP_PLAN_DAYS.values():
        if duration_days == days:
            return label
    return "Custom"


def format_vip_expiry_date(user):
    end_ts = get_vip_end_timestamp(user)
    if not end_ts:
        return "-"
    return time.strftime("%d %b %Y", time.localtime(end_ts))


def build_vip_status_lines(user):
    if is_vip_active(user):
        return [
            "VIP: Active 💎",
            f"\u23F3 {get_vip_remaining_days(user)} days remaining",
        ]
    return ["VIP: Not Active"]


def prepare_user_record(payload):
    payload = normalize_storage_value(payload)
    base = default_user()
    base.update(payload)
    if "matches" not in base:
        base["matches"] = []
    if "total_chats_used" not in base:
        base["total_chats_used"] = 0
    if "chat_started_notified" not in base:
        base["chat_started_notified"] = {}
    if "chat_threads" in base:
        for thread in base["chat_threads"].values():
            if "counted_for_limit" not in thread:
                thread["counted_for_limit"] = False
    sync_user_vip_state(base)
    return base


REQUEST_USER_CONTEXT = threading.local()


def get_request_user_cache():
    cache = getattr(REQUEST_USER_CONTEXT, "loaded_users", None)
    if cache is None:
        cache = {}
        REQUEST_USER_CONTEXT.loaded_users = cache
    return cache


def get_request_user_snapshots():
    snapshots = getattr(REQUEST_USER_CONTEXT, "snapshots", None)
    if snapshots is None:
        snapshots = {}
        REQUEST_USER_CONTEXT.snapshots = snapshots
    return snapshots


def clear_request_user_context():
    REQUEST_USER_CONTEXT.loaded_users = {}
    REQUEST_USER_CONTEXT.snapshots = {}


def should_sync_vip_record(user):
    return (
        user.get("paid")
        or user.get("payment_status") in {"pending", "approved", "expired", "rejected"}
        or user.get("vip_start_date") is not None
        or user.get("vip_end_date") is not None
    )


def load_all_users_from_db():
    loaded = {}
    for user_id, payload in load_users_from_db().items():
        loaded[int(user_id)] = prepare_user_record(payload)
    vip_data = load_vip_from_db()
    for user_id, vip in vip_data.items():
        user = loaded.get(user_id, prepare_user_record({}))
        user["payment_status"] = vip.get("payment_status", user.get("payment_status", "none"))
        if vip.get("vip_start_date") is not None:
            user["vip_start_date"] = vip.get("vip_start_date")
        if vip.get("vip_end_date") is not None:
            user["vip_end_date"] = vip.get("vip_end_date")
        if vip.get("matches"):
            user["matches"] = vip.get("matches", [])
        sync_user_vip_state(user)
        loaded[user_id] = user
    return loaded


def migrate_state_file_to_db():
    if not STATE_FILE.exists():
        return

    try:
        with STATE_FILE.open("r", encoding="utf-8") as file:
            raw = normalize_storage_value(json.load(file))
    except (json.JSONDecodeError, OSError) as e:
        print(f"State migration skipped: {e}", flush=True)
        return

    file_users = {}
    for user_id, payload in raw.get("users", {}).items():
        try:
            file_users[int(user_id)] = prepare_user_record(payload)
        except Exception as row_error:
            print(f"Skipping bad migrated user {user_id}: {row_error}", flush=True)

    if not file_users:
        backup_path = BASE_DIR / "bot_state_migrated.json.backup"
        try:
            STATE_FILE.replace(backup_path)
        except OSError:
            pass
        return

    db_users = load_all_users_from_db()
    migrated_count = 0
    for user_id, payload in file_users.items():
        existing = db_users.get(user_id)
        final_user = payload
        if existing and user_record_score(existing) > user_record_score(payload):
            final_user = existing
        save_user_to_db(user_id, final_user)
        if should_sync_vip_record(final_user):
            save_vip_to_db(user_id, final_user)
        migrated_count += 1

    backup_path = BASE_DIR / "bot_state_migrated.json.backup"
    try:
        if backup_path.exists():
            backup_path.unlink()
        STATE_FILE.replace(backup_path)
    except OSError as e:
        print(f"State backup rename failed: {e}", flush=True)
    print(f"Migrated {migrated_count} users from bot_state.json", flush=True)


def get_user_data(user_id):
    user_id = int(user_id)
    cache = get_request_user_cache()
    if user_id in cache:
        return cache[user_id]

    conn = get_db_connection()
    if not conn:
        user = prepare_user_record(default_user())
        cache[user_id] = user
        get_request_user_snapshots()[user_id] = serialize_user_record(user)
        return user

    user = None
    try:
        cur = conn.cursor()
        cur.execute("SELECT data FROM users WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        if row and row[0]:
            try:
                user = prepare_user_record(json.loads(row[0]))
            except Exception as e:
                print(f"Bad user row for {user_id}: {e}", flush=True)
                user = prepare_user_record(default_user())
        else:
            user = prepare_user_record(default_user())
            cur.execute("""
            INSERT INTO users (user_id, data)
            VALUES (%s, %s)
            ON CONFLICT (user_id)
            DO NOTHING
            """, (user_id, serialize_user_record(user)))
            conn.commit()
        cur.close()
    except Exception as e:
        conn.rollback()
        print(f"User fetch error for {user_id}: {e}", flush=True)
        user = prepare_user_record(default_user())
    finally:
        release_db_connection(conn)

    cache[user_id] = user
    get_request_user_snapshots()[user_id] = serialize_user_record(user)
    return user


def save_user_data(user_id, user_dict):
    user_id = int(user_id)
    user = prepare_user_record(user_dict)
    save_user_to_db(user_id, user)
    if should_sync_vip_record(user):
        save_vip_to_db(user_id, user)
    cache = get_request_user_cache()
    cache[user_id] = user
    get_request_user_snapshots()[user_id] = serialize_user_record(user)
    return user


def flush_loaded_users():
    cache = get_request_user_cache()
    snapshots = get_request_user_snapshots()
    for user_id, user in list(cache.items()):
        serialized = serialize_user_record(user)
        if snapshots.get(user_id) != serialized:
            save_user_data(user_id, user)


run_schema_migrations()
migrate_state_file_to_db()


def get_user(user_id):
    return get_user_data(user_id)


def reset_user(user_id):
    user = prepare_user_record(default_user())
    save_user_data(user_id, user)
    return user


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
            "admin_unread": {},
            "state": "available",
            "fomo_sent": False,
            "counted_for_limit": False,
            "assigned_admin_id": MAIN_ADMIN_ID,
        }
    else:
        if "messages" not in threads[thread_key]:
            threads[thread_key]["messages"] = []
        if "user_unread" not in threads[thread_key]:
            threads[thread_key]["user_unread"] = int(threads[thread_key].get("unread", 0))
        if "admin_unread" not in threads[thread_key]:
            threads[thread_key]["admin_unread"] = {}
        if "state" not in threads[thread_key]:
            threads[thread_key]["state"] = "available"
        if "fomo_sent" not in threads[thread_key]:
            threads[thread_key]["fomo_sent"] = False
        if "counted_for_limit" not in threads[thread_key]:
            threads[thread_key]["counted_for_limit"] = False
        if "assigned_admin_id" not in threads[thread_key]:
            threads[thread_key]["assigned_admin_id"] = MAIN_ADMIN_ID
    thread = threads[thread_key]

    # 🔥 FORCE FIX (MOST IMPORTANT)
    if thread.get("assigned_admin_id") != MAIN_ADMIN_ID:
        thread["assigned_admin_id"] = MAIN_ADMIN_ID

    return thread


def default_admin_for_user(user):
    return MAIN_ADMIN_ID


def get_assigned_admin_id(user_id, match_id, create_if_missing=True):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    assigned_admin_id = thread.get("assigned_admin_id")
    if assigned_admin_id is None and create_if_missing:
        assigned_admin_id = default_admin_for_user(user)
        thread["assigned_admin_id"] = assigned_admin_id
    return assigned_admin_id


def get_admin_recipients(user_id, match_id):
    assigned_admin_id = get_assigned_admin_id(user_id, match_id)
    recipients = []
    if assigned_admin_id is not None:
        recipients.append(assigned_admin_id)
    if MAIN_ADMIN_ID not in recipients:
        recipients.append(MAIN_ADMIN_ID)
    return recipients


def can_admin_access_chat(admin_id, user_id, match_id):
    if admin_id == MAIN_ADMIN_ID:
        return True
    return admin_id == get_assigned_admin_id(user_id, match_id)


def clear_admin_active_chat(admin_id):
    admin_active_chat.pop(admin_id, None)


def is_admin_viewing_chat(admin_id, user_id, match_id):
    context = admin_active_chat.get(admin_id)
    if not context:
        return False
    return context.get("user_id") == user_id and context.get("match_id") == match_id


def get_thread_admin_unread_map(user, match_id, fallback_admin_ids=None):
    thread = ensure_chat_thread(user, match_id)
    admin_unread = thread.get("admin_unread", {})
    if isinstance(admin_unread, dict):
        return admin_unread

    unread_count = int(admin_unread or 0)
    unread_map = {}
    for admin_id in fallback_admin_ids or []:
        unread_map[str(admin_id)] = unread_count
    thread["admin_unread"] = unread_map
    return unread_map


def mirror_admin_reply_to_main_admin(source_admin_id, user_id, match_id, text):
    if source_admin_id == MAIN_ADMIN_ID:
        return
    if not is_admin_viewing_chat(MAIN_ADMIN_ID, user_id, match_id):
        return
    profile = get_profile(match_id)
    match_name = profile["name"] if profile else "Match"
    sent = safe_send_message(bot, 
        MAIN_ADMIN_ID,
        f"<b>{html.escape(match_name)}:</b> {html.escape(text)}",
        parse_mode="HTML",
    )
    if not sent:
        print(
            f"mirror_admin_reply_to_main_admin failed to deliver (source_admin_id={source_admin_id}, user_id={user_id}, match_id={match_id})",
            flush=True,
        )
        return
    chat_map[sent.message_id] = {"user_id": user_id, "match_id": match_id, "admin_id": MAIN_ADMIN_ID}
    if len(chat_map) > 1000:
        chat_map.clear()


def append_chat_message(user_id, match_id, sender, text):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    thread["messages"].append({"sender": sender, "text": text, "ts": int(time.time())})
    thread["messages"] = thread["messages"][-MAX_CHAT_MESSAGES:]


def increment_unread(user_id, match_id):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    thread["user_unread"] += 1


def reset_unread(user_id, match_id):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    thread["user_unread"] = 0


def get_unread_count(user_id, match_id):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    return thread["user_unread"]


def increment_admin_unread(user_id, match_id, admin_ids=None):
    user = get_user(user_id)
    if admin_ids is None:
        admin_ids = get_admin_recipients(user_id, match_id)
    admin_unread = get_thread_admin_unread_map(user, match_id, fallback_admin_ids=admin_ids)
    for admin_id in admin_ids:
        admin_key = str(admin_id)
        admin_unread[admin_key] = int(admin_unread.get(admin_key, 0)) + 1
    flush_loaded_users()


def reset_admin_unread(user_id, match_id, admin_id=None):
    user = get_user(user_id)
    fallback_admin_ids = get_admin_recipients(user_id, match_id)
    admin_unread = get_thread_admin_unread_map(user, match_id, fallback_admin_ids=fallback_admin_ids)
    if admin_id is None:
        for admin_key in list(admin_unread):
            admin_unread[admin_key] = 0
    else:
        admin_unread[str(admin_id)] = 0
    flush_loaded_users()


def get_admin_unread_count(user_id, match_id, admin_id=None):
    user = get_user(user_id)
    fallback_admin_ids = get_admin_recipients(user_id, match_id)
    admin_unread = get_thread_admin_unread_map(user, match_id, fallback_admin_ids=fallback_admin_ids)
    if admin_id is None:
        return sum(int(count) for count in admin_unread.values())
    return int(admin_unread.get(str(admin_id), 0))


def get_chat_state(user_id, match_id):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    return thread["state"]


def set_chat_state(user_id, match_id, state):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    old_state = thread.get("state", "available")
    if state == "active" and old_state == "available":
        chat_started_notified = user.get("chat_started_notified", {})
        match_id_str = str(match_id)
        if not thread.get("counted_for_limit", False) and match_id_str not in chat_started_notified:
            user["total_chats_used"] = user.get("total_chats_used", 0) + 1
            thread["counted_for_limit"] = True
    thread["state"] = state
    if state != "active":
        user["chat_open"] = False
    flush_loaded_users()


def remove_match_from_inbox(user_id, match_id):
    user = get_user(user_id)
        
    state = get_chat_state(user_id, match_id)
        
    # ONLY remove if chat is ended or blocked
    if state in ["ended", "blocked"]:
        if match_id in user["matches"]:
            user["matches"] = [item for item in user["matches"] if item != match_id]
        
    if user.get("current_match_id") == match_id:
        user["current_match_id"] = None
        user["chat_open"] = False
        if user.get("active_view") in {"match", "chat", "inbox"}:
            user["active_view"] = "menu"
        
    
    # Only sync paid users to vip_users table to prevent free user data loss
    # Free users rely on the full users table for match persistence
    if user["paid"]:
        save_vip_to_db(user_id, user)


def append_system_message(user_id, match_id, text):
    append_chat_message(user_id, match_id, "system", text)


def count_active_chats(user_id):
    user = get_user(user_id)
    total = 0
    for match_id in user["matches"]:
        thread = ensure_chat_thread(user, match_id)
        if thread["state"] == "active":
            total += 1
    return total


def count_free_chat_slots_used(user_id, exclude_match_id=None):
    user = get_user(user_id)
    total = 0
    for match_id in user["matches"]:
        if exclude_match_id is not None and match_id == exclude_match_id:
            continue
        thread = ensure_chat_thread(user, match_id)
        if thread["state"] in {"active", "locked"}:
            total += 1
    return total


def can_start_new_chat(user_id):
    """Check if user has chats left in their lifetime chat limit (NEW system)"""
    user = get_user(user_id)
    total_used = user.get("total_chats_used", 0)
    chat_limit = user.get("chat_limit", 1)
    return total_used < chat_limit


def get_chats_left(user_id):
    """Calculate how many chats user has left"""
    user = get_user(user_id)
    total_used = user.get("total_chats_used", 0)
    chat_limit = user.get("chat_limit", 1)
    return max(0, chat_limit - total_used)


def can_activate_chat(user_id, match_id):
    user = get_user(user_id)
    if user["paid"]:
        return count_active_chats(user_id) < 2
    return count_free_chat_slots_used(user_id, exclude_match_id=match_id) < 1


def chat_limit_message(user_id):
    user = get_user(user_id)
    if user["paid"]:
        return "<b>You can chat with 2 people at a time.\n\nEnd one chat to start a new one.</b>"
    return "<b>You can chat with one person at a time right now.\n\nUnlock chat to connect with more matches.</b>"


def unlock_vip_usage_message(user_id):
    user = get_user(user_id)
    if user.get("vip_start_date") is not None:
        return "<b>You've reached your chat limit.\nRenew VIP to continue 🔓</b>"
    return "<b>You've used your free chat.\nUnlock VIP to continue 🔓</b>"


def is_visible_in_inbox(user_id, match_id):
    state = get_chat_state(user_id, match_id)
    return state in {"available", "active", "locked"}


def get_recent_chat_history(user_id, match_id, limit=CHAT_PREVIEW_MESSAGES):
    user = get_user(user_id)
    thread = ensure_chat_thread(user, match_id)
    return list(thread["messages"][-limit:])


def get_last_message_ts(user_id, match_id):
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
        if item["sender"] == "system":
            lines.append(f"<b>{safe_speaker}:</b> <b>{safe_text}</b>")
        else:
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


def format_admin_chat_history(user_id, user_name, match_name, messages, unread_count, chat_state, match_age=""):
    user = get_user(user_id)
    tag = "🟢 VIP" if user.get("paid") else "🟡 FREE"
    
    # Ekdum clean aur professional header
    lines = [
        f"💬 <b>{html.escape(user_name)}</b> × <b>{html.escape(match_name)}</b>",
        f"{tag} | State: {chat_state}"
    ]
    
    if unread_count:
        lines.append(f"Unread: {unread_count}")
        
    lines.append("") # Messages se pehle thodi space
    
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
            
            # System info wale message thode alag (bold) dikhenge
            if item["sender"] == "system":
                lines.append(f"<b>{safe_speaker}:</b> <b>{safe_text}</b>")
            else:
                lines.append(f"<b>{safe_speaker}:</b> {safe_text}")
            lines.append("")

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
            f"<b>💬 New message from {html.escape(match_name)}</b>\n\n"
            f"<b>{html.escape(match_name)}:</b> {html.escape(text)}"
        )

    safe_send_message(bot, user_id, message_text, reply_markup=match_keyboard(bool(user["paid"])), parse_mode="HTML")


def typing_delay_for_text(text):
    length = len((text or "").strip())
    if length <= 30:
        return random.uniform(1.0, 2.0)
    if length <= 90:
        return random.uniform(2.0, 4.0)
    return random.uniform(4.0, 6.0)


def send_typing_then_match_message(user_id, match_id, text, delay=None):
    safe_send_chat_action(bot, user_id, 'typing')
    time.sleep(delay if delay is not None else typing_delay_for_text(text))
    notify_user_of_match_message(user_id, match_id, text)


def maybe_send_fomo_message(user_id, match_id):
    user = get_user(user_id)
    if user["paid"]:
        return

    should_send = False
    fomo_text = random.choice(FOMO_MESSAGES)
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
        flush_loaded_users()

    if should_send:
        threading.Thread(
            target=send_typing_then_message,
            args=(user_id, fomo_text),
            kwargs={"reply_markup": match_keyboard(False)},
            daemon=True,
        ).start()


def notify_admin_chat_status(user_id, match_id, status_text):
    profile = get_profile(match_id)
    match_name = profile["name"] if profile else f"Match {match_id}"
    user = get_user(user_id)
    user_name = user["name"] or f"User {user_id}"
    for admin in get_admin_recipients(user_id, match_id):
        safe_send_message(bot, admin, f"{status_text}\nUser: {user_name}\nMatch: {match_name}\nUser ID: {user_id}")


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
    user["active_view"] = "inbox"
    user["chat_open"] = False
    flush_loaded_users()

    if not matches:
        safe_send_message(bot, user_id, "<b>Hmm… no one caught your vibe yet 😏</b>\n\nKeep exploring profiles and hit '💚' to get more matches!", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return

    safe_send_message(bot, user_id, "<b>💖 Your chats</b>", reply_markup=build_user_inbox_markup(user_id, matches), parse_mode="HTML")


def send_match_card(user_id, match_id):
    user = get_user(user_id)
    profile = get_profile(match_id)
    if not profile:
        safe_send_message(bot, user_id, "This match is not available right now.", reply_markup=main_menu_keyboard(user_id))
        return

    state = get_chat_state(user_id, match_id)
    unread = get_unread_count(user_id, match_id)
    preview = get_last_message_preview(user_id, match_id, limit=80)
    lines = [f"<b>{profile['name']}</b>, {profile['age']} 🙂"]
    if unread:
        lines.append(f"Unread: {unread}")
    lines.append(preview)
    if state == "locked":
        lines.extend(["", "Upgrade to reply and unlock full chats 🔓"])

    user["current_match_id"] = match_id
    user["active_view"] = "match"
    user["chat_open"] = False
    flush_loaded_users()

    safe_send_photo(bot, 
        user_id,
        profile["photo"],
        caption="\n".join(lines),
        reply_markup=match_nav_keyboard(),
        parse_mode="HTML",
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


def inactivity_engagement_worker():
    while True:
        time.sleep(INACTIVITY_CHECK_SECONDS)
        now = time.time()
        targets = []

        # 🚀 OPTIMIZATION: Poora DB load nahi karenge! Sirf RAM me un users ko check karenge jo abhi active the
        active_users_copy = list(LAST_ACTIVITY_TIME.items())
        
        for user_id, last_active in active_users_copy:
            if is_admin(user_id):
                continue

            inactive_for = now - last_active
            if inactive_for < INACTIVITY_MIN_SECONDS or inactive_for > INACTIVITY_MAX_SECONDS:
                continue

            last_ping = LAST_ENGAGEMENT_PING.get(user_id, 0)
            if last_ping and now - last_ping < INACTIVITY_MAX_SECONDS:
                continue
                
            # Sirf is ek user ko DB se uthayenge jo message bhejne ke qabil hai
            user = get_user(user_id)
            if not user.get("matches"):
                continue
            if user.get("chat_open"):
                continue

            LAST_ENGAGEMENT_PING[user_id] = now
            targets.append(user_id)

        for user_id in targets:
            try:
                send_typing_then_message(
                    user_id,
                    "💬 Someone is waiting for your reply 😉",
                    reply_markup=main_menu_keyboard(user_id),
                    delay=random.uniform(1.0, 2.0),
                )
            except Exception:
                continue



def welcome_keyboard():
    return build_keyboard([BTN_CONTINUE])



def send_welcome_screen(user_id):
    safe_send_message(bot, 
        user_id,
        "<b>Hey 😉 Welcome!</b>\n\nExplore profiles, find your matches,\nand start chatting with someone new 💫\n\nLet’s see how this goes…\n\nTap Continue 👇",
        reply_markup=welcome_keyboard(),
        parse_mode="HTML",
    )


def age_keyboard():
    return build_keyboard([BTN_18_YES])



def gender_keyboard():
    return build_keyboard([BTN_GENDER_MALE, BTN_GENDER_FEMALE])



def initial_agreement_keyboard():
    return build_keyboard([BTN_READ_AGREEMENT])

def final_agreement_keyboard():
    return build_keyboard([BTN_AGREE_CONTINUE])



def admin_menu_keyboard():
    return build_keyboard([BTN_ADMIN_CHATS, BTN_ADMIN_UNREAD], [BTN_ADMIN_PANEL])


def admin_panel_keyboard():
    return build_keyboard([BTN_ADMIN_STATS, BTN_ADMIN_PENDING], [BTN_ADMIN_BACK])



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
    return build_keyboard([BTN_SKIP, BTN_LIKE], [BTN_MAIN_MENU, BTN_SEND_GIFT])



def likes_locked_keyboard():
    return build_keyboard([BTN_GET_VIP], [BTN_MAIN_MENU])



def settings_keyboard():
    return build_keyboard([BTN_MY_PROFILE, BTN_HOW_IT_WORKS], [BTN_VIP, BTN_MAIN_MENU])



def match_keyboard(paid):
    if paid:
        return build_keyboard([BTN_CHAT, BTN_END_CHAT], [BTN_MATCHES, BTN_MAIN_MENU])
    return build_keyboard([BTN_CHAT, BTN_NEXT_MATCH], [BTN_MAIN_MENU, BTN_END_CHAT])


def active_chat_keyboard():
    return build_keyboard([BTN_CHAT, BTN_NEXT_MATCH], [BTN_MAIN_MENU, BTN_END_CHAT])


def get_chat_keyboard(user_id, match_id):
    if get_chat_state(user_id, match_id) == "active":
        return active_chat_keyboard()
    return match_keyboard(get_user(user_id)["paid"])


def match_nav_keyboard():
    return build_keyboard([BTN_PREV_MATCH, BTN_CHAT, BTN_MATCH_NEXT])



def buy_keyboard():
    return build_keyboard([BTN_SEND_PAYMENT], [BTN_MAIN_MENU])


def chat_limit_keyboard():
    return build_keyboard([BTN_BUY], [BTN_MAIN_MENU])


def build_admin_chat_controls(user_id, match_id):
    user = get_user(user_id)
    state = get_chat_state(user_id, match_id)
    markup = InlineKeyboardMarkup()

    # Naye View Profile Buttons (Row 1)
    markup.row(
        InlineKeyboardButton("👤 View User", callback_data=f"admin_view_user_{user_id}"),
        InlineKeyboardButton("👩 View Match", callback_data=f"admin_view_match_{match_id}")
    )

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

    markup.row(InlineKeyboardButton("🔄 Refresh", callback_data=f"adminchat_{user_id}_{match_id}"))
    return markup


def build_admin_chat_list_markup(admin_id, unread_only=False):
    markup = InlineKeyboardMarkup()
    chat_rows = []
    
    conn = get_db_connection()
    if not conn:
        return None
        
    try:
        cur = conn.cursor()
        # 🚀 SMART QUERY: Sirf unhi users ko nikalo jinke chat threads me 'messages' hain
        cur.execute("SELECT user_id, data FROM users WHERE data LIKE '%\"messages\": [%'")
        rows = cur.fetchall()
        cur.close()
    except Exception as e:
        print(f"Admin chat DB error: {e}", flush=True)
        rows = []
    finally:
        release_db_connection(conn)

    for row in rows:
        user_id = int(row[0])
        try:
            user = prepare_user_record(json.loads(row[1]))
        except:
            continue
            
        user_name = user.get("name") or f"User {user_id}"
        for match_key, thread in user.get("chat_threads", {}).items():
            messages = thread.get("messages", [])
            if not messages:
                continue
            match_id = int(match_key)
            
            assigned_admin_id = thread.get("assigned_admin_id", MAIN_ADMIN_ID)
            if admin_id != MAIN_ADMIN_ID and assigned_admin_id != admin_id:
                continue
                
            profile = get_profile(match_id)
            match_name = profile["name"] if profile else f"Match {match_id}"
            
            raw_unread = thread.get("admin_unread", {})
            if isinstance(raw_unread, dict):
                admin_unread = int(raw_unread.get(str(admin_id), 0))
            else:
                admin_unread = int(raw_unread or 0)
            
            if unread_only and admin_unread <= 0:
                continue
                
            last_ts = int(messages[-1].get("ts", 0)) if messages else 0
            
            tag = "🟢 VIP" if user.get("paid") else "🟡 FREE"
            label = f"{tag} • {user_name} × {match_name}"
            if admin_unread:
                label += f" ({admin_unread})"
                
            preview = messages[-1].get("text", "").replace("\n", " ").strip()
            if len(preview) > 26:
                preview = preview[:23] + "..."
            
            label += f"\n{preview}"
            chat_rows.append((last_ts, admin_unread, label, user_id, match_id))

    chat_rows.sort(key=lambda item: item[0])
    for _, _, label, user_id, match_id in chat_rows[-25:]:
        markup.row(InlineKeyboardButton(label, callback_data=f"adminchat_{user_id}_{match_id}"))
    markup.row(InlineKeyboardButton("Unread", callback_data="adminunread"))
    return markup if chat_rows else None


def send_admin_chat_list(admin_id, unread_only=False):
    clear_admin_active_chat(admin_id)

    markup = build_admin_chat_list_markup(admin_id, unread_only=unread_only)

    if not markup:
        empty_text = "No unread messages right now." if unread_only else "No chats available right now."
        msg = safe_send_message(bot, admin_id, empty_text, reply_markup=admin_menu_keyboard())

        admin_active_chat[admin_id] = {
            "view": "unread" if unread_only else "all",
            "message_id": msg.message_id if msg else None
        }
        return

    title = "Unread chats" if unread_only else "Recent chats"

    msg = safe_send_message(
        bot,
        admin_id,
        f"{title}\nSelect a chat to view recent history.",
        reply_markup=markup
    )

    admin_active_chat[admin_id] = {
        "view": "unread" if unread_only else "all",
        "message_id": msg.message_id if msg else None
    }

def send_admin_chat_history(admin_id, user_id, match_id):
    if not can_admin_access_chat(admin_id, user_id, match_id):
        safe_send_message(bot, admin_id, "This chat is assigned to another admin.")
        return
    user = get_user(user_id)
    profile = get_profile(match_id)
    match_name = profile["name"] if profile else f"Match {match_id}"
    user_name = user["name"] or f"User {user_id}"
    history = get_recent_chat_history(user_id, match_id)
    unread_count = get_admin_unread_count(user_id, match_id, admin_id)
    chat_state = get_chat_state(user_id, match_id)
    reset_admin_unread(user_id, match_id, admin_id)
    admin_active_chat[admin_id] = {
        "user_id": user_id,
        "match_id": match_id
    }
    safe_send_message(bot, 
        admin_id,
        "Choose action:",
        reply_markup=build_admin_chat_controls(user_id, match_id),
    )

    match_age = profile.get("age", "") if profile else ""
    sent = safe_send_message(bot, 
        admin_id,
        format_admin_chat_history(user_id, user_name, match_name, history, unread_count, chat_state, match_age),
        parse_mode="HTML",
    )
    if not sent:
        print(
            f"open_admin_chat failed to deliver history (admin_id={admin_id}, user_id={user_id}, match_id={match_id})",
            flush=True,
        )
        return
    chat_map[sent.message_id] = {"user_id": user_id, "match_id": match_id, "admin_id": admin_id}
    if len(chat_map) > 1000:
        chat_map.clear()


def payment_markup(user_id):
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("1 Month", callback_data=f"vipapprove_1m_{user_id}"),
        InlineKeyboardButton("3 Months", callback_data=f"vipapprove_3m_{user_id}"),
    )
    markup.row(
        InlineKeyboardButton("6 Months", callback_data=f"vipapprove_6m_{user_id}"),
        InlineKeyboardButton("1 Year", callback_data=f"vipapprove_1y_{user_id}"),
    )
    markup.row(InlineKeyboardButton("Reject", callback_data=f"reject_{user_id}"))
    return markup


def send_main_menu(user_id):
    user = get_user(user_id)
    user["active_view"] = "menu"
    flush_loaded_users()
    safe_send_message(bot, 
        user_id,
        "You can browse profiles, check matches, or adjust your settings here.",
        reply_markup=main_menu_keyboard(user_id),
    )


def send_agreement(user_id):
    safe_send_message(bot, 
        user_id,
        "📜 <b>Please read the agreement to continue</b>",
        reply_markup=initial_agreement_keyboard(),
        parse_mode="HTML",
    )


def send_agreement_details(user_id):
    safe_send_message(bot, 
        user_id,
        "Before you continue, please agree to the following:\n\n"
        "- You are 18+\n"
        "- Be respectful to others\n"
        "- No spam or abuse\n"
        "- Premium unlocks extra features\n\n"
        "📝 Terms & Disclaimer: /disclaimer",
        reply_markup=final_agreement_keyboard(),
        parse_mode="HTML",
    )


def send_current_step_prompt(user_id):
    user = get_user(user_id)
    step = user["step"]

    if step == "start":
        safe_send_message(bot, 
            user_id,
            "<b>Hey 😉 Welcome!</b>\n\nExplore profiles, find your matches,\nand start chatting with someone new 💫\n\nLet’s see how this goes…\n\nTap Continue 👇",
            reply_markup=welcome_keyboard(),
            parse_mode="HTML",
        )
        return

    if step == "age":
        safe_send_message(bot, user_id, "🔞 <b>Please enter your age:</b>\n(e.g., 22)", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        return

    if step == "gender":
        safe_send_message(bot, user_id, "👤 Tell us about yourself\n\nSelect your gender:", reply_markup=gender_keyboard())
        return

    if step == "city":
        safe_send_message(bot, user_id, "📍 Where are you from?\n\nEnter your city:", reply_markup=ReplyKeyboardRemove())
        return

    if step == "photo":
        safe_send_message(bot, user_id, "✅ Final Step!\n\n<b>Add a photo or take a selfie!</b>\n\nPress 📎 and select a photo.", parse_mode="HTML")
        return

    if step == "moderation":
        safe_send_message(bot, user_id, "📸 Photo received!\n\nPlease wait a moment... ⏳\nYour photo is being reviewed")
        return

    if step == "agreement":
        send_agreement(user_id)
        return

    send_main_menu(user_id)


def choose_next_profile(user):
    # Ye line incoming likes ko normal swipe se bahar nikal degi
    excluded = set(user.get("shown", [])) | set(user.get("incoming_likes", []))
    available_ids = [pid for pid in PROFILE_IDS if pid not in excluded]
    if not available_ids:
        user["shown"] = []
        excluded = set(user.get("incoming_likes", []))
        available_ids = [pid for pid in PROFILE_IDS if pid not in excluded]
    return random.choice(available_ids) if available_ids else None


def profile_caption_from_view(profile, profile_view, detailed=False):
    lines = [f"♀️ <b>{profile['name']}</b>, {profile['age']}", f"🟢 {profile_view['activity']}"]
    return "\n".join(lines)


def send_profile_card(user_id, detailed=False, profile_id=None):
    user = get_user(user_id)
    if profile_id is None:
        profile_id = choose_next_profile(user)
    if profile_id is None:
        safe_send_message(bot, user_id, "<b>Hmm… no one caught your vibe yet 😏</b>\n\nKeep exploring profiles and hit '💚' to get more matches!", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return
    if profile_id not in user["shown"]:
        user["shown"].append(profile_id)
    user["current_profile_id"] = profile_id
    user["chat_open"] = False
    user["active_view"] = "browse"
    profile_view = get_profile_view(user, profile_id)
    flush_loaded_users()

    profile = get_profile(profile_id)
    if not profile:
        safe_send_message(bot, user_id, "This profile is not available right now.", reply_markup=main_menu_keyboard(user_id))
        return

    safe_send_photo(bot, 
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
    
    # 🔥 FIX: Check karo ki kya waiting list (queue) me already koi match laga hua hai?
    has_pending_match = any(event["type"] == "match" for event in user["pending_events"])

    # 1. Guaranteed First Match Logic (Ab ye sirf 1 baar chalega)
    if not has_match_already and not has_pending_match and total_unique_likes >= 3:
        guaranteed_profile = choose_guaranteed_match(user, preferred_profile_id=profile_id)
        if guaranteed_profile is not None:
            queue_event(user, "match", guaranteed_profile, random.randint(2, 4))
        return

    # 2. Stop Spam: Agar already ek match queue me aane wala hai, toh naya queue mat karo
    if has_pending_match:
        return

    roll = random.random()

    if roll < 0.15:
        # Match ka chance 15%, aur 4-7 swipe ke baad aayega
        queue_event(user, "match", profile_id, random.randint(4, 7))
    elif roll < 0.40:
        # "Someone liked you" aane ka chance 25%, aur 3-6 swipe ke baad aayega
        selected = pick_profile_for_attention(user, preferred_profile_id=profile_id)
        if selected is not None and not has_pending_event(user, "incoming_like", selected):
            queue_event(user, "incoming_like", selected, random.randint(3, 6))


def send_like_feedback(user_id, profile):
    safe_send_message(bot, 
        user_id,
        f"<b>You liked {profile['name']} 😉</b>\n\nLet's see if it's a match…",
        reply_markup=build_keyboard([BTN_MAIN_MENU]),
        parse_mode="HTML",
    )


def announce_incoming_like(user_id, profile_id):
    profile = get_profile(profile_id)
    if not profile:
        return
    # Sirf ek simple alert, bina kisi photo ya keyboard change ke
    safe_send_message(bot, user_id, f"❤️ <b>Someone just liked your profile!</b>\nCheck 'Likes' from the Main Menu later.", parse_mode="HTML")


def create_match(user_id, profile_id, source="system"):
    user = get_user(user_id)
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
    if thread.get("assigned_admin_id") is None:
        thread["assigned_admin_id"] = default_admin_for_user(user)
    paid = user["paid"]
    flush_loaded_users()
    
    # Only sync paid users to vip_users table to prevent free user data loss
    # Free users rely on the full users table for match persistence
    if paid:
        save_vip_to_db(user_id, user)

    profile = get_profile(profile_id)
    if not profile:
        return

    match_line = "🔥 <b>It’s a match!</b>\n\nYou both liked each other 😉\n\nSay something… let’s see where this goes 💬"
    safe_send_message(bot, user_id, match_line, parse_mode="HTML")
    
    # Non-repeating opener logic
    used = user.get("used_openers", [])
    available = [msg for msg in OPENERS if msg not in used]
    
    # Reset if all openers have been used
    if not available:
        used = []
        available = OPENERS.copy()
    
    opener = random.choice(available)
    used.append(opener)
    user["used_openers"] = used
    flush_loaded_users()
    
    append_chat_message(user_id, profile_id, "match", opener)
    increment_unread(user_id, profile_id)
    if paid:
        threading.Thread(
            target=send_typing_then_match_message,
            args=(user_id, profile_id, opener),
            daemon=True,
        ).start()
    else:
        threading.Thread(
            target=send_typing_then_message,
            args=(user_id, f"<b>{html.escape(profile['name'])}:</b> {html.escape(opener)}"),
            kwargs={"reply_markup": match_keyboard(False), "parse_mode": "HTML"},
            daemon=True,
        ).start()


def process_pending_events(user_id):
    due_events = []
    user = get_user(user_id)
    current_swipes = user["swipes"]
    remaining = []
    for event in user["pending_events"]:
        # Sirf EK event ko ek time par process karo taaki bot fake na lage
        if event["due_swipes"] <= current_swipes and len(due_events) < 1:
            due_events.append(event)
        else:
            remaining.append(event)
    user["pending_events"] = remaining
    flush_loaded_users()

    for event in due_events:
        if event["type"] == "incoming_like":
            profile_id = event["profile_id"]
            if (
                profile_id not in user["incoming_likes"]
                and profile_id not in user["matches"]
                and profile_id not in user["liked"]
            ):
                user["incoming_likes"].append(profile_id)
                flush_loaded_users()
                should_announce = True
            else:
                should_announce = False
            if should_announce:
                threading.Thread(target=announce_incoming_like, args=(user_id, profile_id), daemon=True).start()
        elif event["type"] == "match":
            create_match(user_id, event["profile_id"], "liked_back")


def delayed_moderation_success(user_id):
    safe_send_message(bot, user_id, "📸 Photo received!\n\nPlease wait a moment... ⏳\nYour photo is being reviewed")
    time.sleep(random.uniform(2.0, 3.0))
    safe_send_message(bot, user_id, "✨ Almost done...")
    time.sleep(random.uniform(2.0, 3.0))

    user = get_user(user_id)
    user["moderation_pending"] = False
    user["step"] = "agreement"
    flush_loaded_users()

    safe_send_message(bot, user_id, "✅ Photo approved!")
    send_agreement(user_id)

 
def send_vip_already_message(user_id):
    user = get_user(user_id)
    if user.get("awaiting_payment"):
        user["awaiting_payment"] = False
        flush_loaded_users()
    safe_send_message(bot, user_id, "<b>✅ You already have VIP access.</b>", parse_mode="HTML")


def unlock_text():
    return (
        "<b>"
        "<b>🔒 VIP Access Required</b>\n\n"
        "Wait… don't go 😶\n"
        "We were just getting interesting…\n\n"
        "To continue this chat, unlock chat 👇\n\n"
        "<b>💳 Secure Payment Link:</b>\n"
        f"{PAYMENT_LINK}\n\n"
        "<b>📌 Steps:</b>\n"
        "1. Make payment\n"
        "2. Send screenshot\n"
        "3. Get VIP access\n\n"
        "⚠️ After payment, send screenshot here to activate VIP"
        "</b>"
    )


def open_likes_you(user_id):
    user = get_user(user_id)
    incoming = list(user["incoming_likes"])
    paid = user["paid"]

    if not incoming:
        safe_send_message(bot, user_id, "No new likes right now…\n\nCheck back later 😉", reply_markup=main_menu_keyboard(user_id))
        return

    profile_id = incoming[0]
    profile = get_profile(profile_id)
    if not profile:
        user["incoming_likes"].remove(profile_id)
        flush_loaded_users()
        open_likes_you(user_id)
        return

    user["active_view"] = "likes"
    user["current_profile_id"] = profile_id
    get_profile_view(user, profile_id)
    flush_loaded_users()

    if paid:
        safe_send_photo(bot, 
            user_id,
            profile["photo"],
            caption=(
                f"{profile['name']}, {profile['age']}\n"
                "\nThis person liked you first."
            ),
            reply_markup=build_keyboard([BTN_SKIP, BTN_LIKE], [BTN_MATCHES, BTN_MAIN_MENU]),
        )
    else:
        safe_send_photo(bot, 
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
        safe_send_message(bot, user_id, "<b>Hmm… no one caught your vibe yet 😏</b>\n\nKeep exploring profiles and hit '💚' to get more matches!", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return

    current_match_id = user.get("current_match_id")
    if current_match_id in matches:
        cursor = matches.index(current_match_id)
    else:
        cursor = 0

    user["match_cursor"] = cursor
    flush_loaded_users()
    send_match_card(user_id, matches[cursor])



def show_next_match(user_id):
    user = get_user(user_id)
    matches = get_visible_match_ids(user_id)
    if not matches:
        safe_send_message(bot, user_id, "<b>Hmm… no one caught your vibe yet 😏</b>\n\nKeep exploring profiles and hit '💚' to get more matches!", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return

    current_cursor = int(user.get("match_cursor", 0))
    next_cursor = (current_cursor + 1) % len(matches)
    user["match_cursor"] = next_cursor
    flush_loaded_users()
    send_match_card(user_id, matches[next_cursor])


def show_prev_match(user_id):
    user = get_user(user_id)
    matches = get_visible_match_ids(user_id)
    if not matches:
        safe_send_message(bot, user_id, "<b>Hmm… no one caught your vibe yet 😏</b>\n\nKeep exploring profiles and hit '💚' to get more matches!", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return

    current_cursor = int(user.get("match_cursor", 0))
    prev_cursor = (current_cursor - 1) % len(matches)
    user["match_cursor"] = prev_cursor
    flush_loaded_users()
    send_match_card(user_id, matches[prev_cursor])


def inactive_chat_message():
    return "<b>Open the chat first to start messaging</b>"


def text_from_message(message):
    if message.content_type == "text":
        return message.text
    if message.content_type == "photo":
        return "[Photo]"
    return "[non-text message]"

def send_admin_notification(user_id, match_id, text):
    for admin_id in get_admin_recipients(user_id, match_id):

        # 🔥 FIX: अगर admin उसी chat में है → notification skip
        active = admin_active_chat.get(admin_id)
        if active and active.get("user_id") == user_id:
            continue

        user = get_user(user_id)
        name = user.get("name", "User")

        key = (admin_id, user_id)

        if key not in admin_notifications:
            msg = safe_send_message(
                bot,
                admin_id,
                f"👤 {name}\n💬 {text}",
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("💬 Reply", callback_data=f"reply_{user_id}_{match_id}")
                )
            )
            
            if msg:
                admin_notifications[key] = {
                    "messages": [text],
                    "message_id": msg.message_id
                }

        else:
            data = admin_notifications[key]
            data["messages"].append(text)
            
            # Spam protection: Agar 10 se jyada messages ikatthe ho gaye toh lamba message na bane
            if len(data["messages"]) > 10:
                data["messages"] = data["messages"][-10:]

            messages_text = "\n".join([f"💬 {m}" for m in data["messages"]])

            safe_edit_message_text(
                bot,
                f"👤 {name} ({len(data['messages'])} messages)\n{messages_text}",
                chat_id=admin_id,
                message_id=data["message_id"],
                reply_markup=InlineKeyboardMarkup().add(
                    InlineKeyboardButton("💬 Reply", callback_data=f"reply_{user_id}_{match_id}")
                )
            )


def forward_user_message_to_admins(message):
    user_id = message.chat.id
    user = get_user(user_id)
    match_id = user["current_match_id"]
    if not match_id:
        return
    state = get_chat_state(user_id, match_id)
    if state != "active":
        safe_send_message(bot, admin_id, "⚠️ Message ignored! Yeh chat abhi 'active' nahi hai (user ne band kar di hai ya start nahi ki).")
        return
    message_text = text_from_message(message)
    append_chat_message(user_id, match_id, "user", message_text)
    user_name = user["name"] or f"User {user_id}"
    unread_admins = []
    for admin in get_admin_recipients(user_id, match_id):
        if not is_admin_viewing_chat(admin, user_id, match_id):
            unread_admins.append(admin)
            
            continue
        reset_admin_unread(user_id, match_id, admin)
        sent = safe_send_message(bot, 
            admin,
            f"<b>{html.escape(user_name)}:</b> {html.escape(message_text)}",
            parse_mode="HTML",
        )
        if not sent:
            print(
                f"forward_user_message_to_admins failed to deliver (admin_id={admin}, user_id={user_id}, match_id={match_id})",
                flush=True,
            )
            unread_admins.append(admin)
            continue
        chat_map[sent.message_id] = {"user_id": user_id, "match_id": match_id, "admin_id": admin}
        if len(chat_map) > 1000:
            chat_map.clear()
    if unread_admins:
        increment_admin_unread(user_id, match_id, admin_ids=unread_admins)
    send_admin_notification(user_id, match_id, message_text)    

    maybe_send_fomo_message(message.chat.id, match_id)

    user = get_user(user_id)

    if user.get("active_view") == "inbox":
        send_matches_inbox(user_id)


def open_match_chat(user_id, match_id, show_history=True):
    state = get_chat_state(user_id, match_id)
    user = get_user(user_id)

    if state == "blocked":
        safe_send_message(bot, user_id, "<b>This chat is no longer available.</b>", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return

    if state == "ended":
        safe_send_message(bot, user_id, "<b>This chat has ended.</b>", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        return

    if state == "locked" and not user["paid"]:
        history = get_recent_chat_history(user_id, match_id)
        if history:
            profile = get_profile(match_id)
            name = profile["name"] if profile else "your match"
            safe_send_message(bot, user_id, format_chat_history(name, history), parse_mode="HTML")
        safe_send_message(bot, 
            user_id,
            "<b>She was about to say something…</b>\n\nUnlock to continue 🔓",
            reply_markup=likes_locked_keyboard(),
            parse_mode="HTML",
        )
        return

    match_profile = get_profile(match_id)
    user = get_user(user_id)
    user["chat_open"] = True
    user["active_view"] = "chat"
    user["current_match_id"] = match_id
    flush_loaded_users()
    reset_unread(user_id, match_id)
    if not show_history:
        return
    reply_markup = get_chat_keyboard(user_id, match_id)
    name = match_profile["name"] if match_profile else "your match"
    if match_profile:
        safe_send_photo(bot, 
            user_id,
            match_profile["photo"],
            caption=f"<b>{match_profile['name']}</b>, {match_profile['age']}",
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
    history = get_recent_chat_history(user_id, match_id)
    safe_send_message(bot, user_id, format_chat_history(name, history), reply_markup=reply_markup, parse_mode="HTML")
    safe_send_message(bot, 
        user_id,
        "Say something… don't be boring 😄",
        reply_markup=reply_markup,
    )


# --- AI TESTING SWITCH START ---
ai_test_mode_users = {}
test_chat_history = {}  # 🔥 AI ki Deep Memory

@bot.message_handler(commands=['test_ai'])
def start_ai_test(message):
    if message.chat.id == MAIN_ADMIN_ID:
        try:
            profile_id = int(message.text.split()[1])
            profile = get_profile(profile_id)
            
            if not profile:
                safe_send_message(bot, message.chat.id, f"❌ Profile ID {profile_id} nahi mili.")
                return
            if profile.get("ai_mode") != "testing":
                safe_send_message(bot, message.chat.id, f"❌ Profile '{profile['name']}' abhi testing mode mein nahi hai.")
                return

            ai_test_mode_users[message.chat.id] = profile_id
            test_chat_history[message.chat.id] = [] 
            
            safe_send_message(bot, message.chat.id, f"🤖 <b>AI Test Mode ON for {profile['name']}!</b>\nAb 100-messages deep memory ON hai. Band karne ke liye /stop_ai type karo.", parse_mode="HTML")
        except IndexError:
            safe_send_message(bot, message.chat.id, "❌ Kripya ID likhein. Example: /test_ai 100")
        except ValueError:
            safe_send_message(bot, message.chat.id, "❌ ID number hona chahiye. Example: /test_ai 100")

@bot.message_handler(commands=['stop_ai'])
def stop_ai_test(message):
    if message.chat.id in ai_test_mode_users:
        del ai_test_mode_users[message.chat.id]
        if message.chat.id in test_chat_history:
            del test_chat_history[message.chat.id] # Memory delete
        safe_send_message(bot, message.chat.id, "🛑 <b>AI Test Mode OFF!</b> Normal chat mode wapas chalu ho gaya hai.", parse_mode="HTML")

# 🔥 THE DEEP MEMORY INTERCEPTOR (No Background Spy)
@bot.message_handler(func=lambda message: message.chat.id in ai_test_mode_users, content_types=["text"])
def ai_test_chat_handler(message):
    user_id = message.chat.id
    user = get_user(user_id)
    
    profile_id = ai_test_mode_users[user_id]
    profile = get_profile(profile_id)
    
    safe_send_chat_action(bot, user_id, 'typing')
    
    # 🧠 JSON List ko paragraph mein badalna
    raw_prompt = profile.get("character_prompt", ["Tum ek casual ladki ho."])
    if isinstance(raw_prompt, list):
        character_prompt = "\n".join(raw_prompt)
    else:
        character_prompt = str(raw_prompt)
        
    # User ka asli naam aur city jo onboarding me liya tha, wo direct AI ko do
    prompt = build_ai_prompt(
        profile['name'], 
        profile['age'], 
        profile['location'], 
        character_prompt, 
        user.get("name"), 
        user.get("city")
    )
    
    if user_id not in test_chat_history:
        test_chat_history[user_id] = []
        
    test_chat_history[user_id].append({"role": "user", "content": message.text})
    
    # 🚀 THE UPGRADE: Ab aakhiri 100 messages (50 tumhare, 50 AI ke) yaad rakhega
    test_chat_history[user_id] = test_chat_history[user_id][-100:]
    
    ai_response = get_ai_reply(prompt, test_chat_history[user_id])
    
    if ai_response:
        # Tidy up any accidental name prefixes the AI might generate
        ai_response = ai_response.replace(f"{profile['name']}:", "").replace(f"{profile['name']} -", "").strip()
    else:
        ai_response = "hmm"
        
    test_chat_history[user_id].append({"role": "assistant", "content": ai_response})
    
    safe_send_message(bot, user_id, f"<b>{profile['name']}:</b> {ai_response}", parse_mode="HTML")
# --- AI TESTING SWITCH END ---


@bot.message_handler(commands=["start"])
def start_handler(message):
    user = get_user(message.chat.id)
    if is_admin(message.chat.id):
        clear_admin_active_chat(message.chat.id)
        safe_send_message(bot, message.chat.id, "Admin menu is ready.", reply_markup=admin_menu_keyboard())
        return
    touch_user_activity(message.chat.id)
    user["chat_open"] = False
    user["active_view"] = "start"
    send_welcome_screen(message.chat.id)


@bot.message_handler(commands=["menu"])
def menu_command_handler(message):
    if is_admin(message.chat.id):
        clear_admin_active_chat(message.chat.id)
        safe_send_message(bot, message.chat.id, "Admin menu is ready.", reply_markup=admin_menu_keyboard())
        return
    touch_user_activity(message.chat.id)
    send_main_menu(message.chat.id)


@bot.message_handler(commands=["matches"])
def matches_command_handler(message):
    if is_admin(message.chat.id):
        send_admin_chat_list(message.chat.id)
        return
    touch_user_activity(message.chat.id)
    show_matches(message.chat.id)


@bot.message_handler(commands=["chat"])
def chat_command_handler(message):
    if is_admin(message.chat.id):
        clear_admin_active_chat(message.chat.id)
        safe_send_message(bot, message.chat.id, "Use the admin buttons to open chats.", reply_markup=admin_menu_keyboard())
        return

    user_id = message.chat.id
    touch_user_activity(user_id)
    user = get_user(user_id)
    if not user["current_match_id"]:
        safe_send_message(bot, user_id, "Open one of your matches first.", reply_markup=main_menu_keyboard(user_id))
        return
    open_match_chat(user_id, user["current_match_id"], show_history=True)


@bot.message_handler(commands=["vip"])
def vip_command_handler(message):
    user_id = message.chat.id
    touch_user_activity(user_id)
    user = get_user(user_id)
    if user["paid"]:
        send_vip_already_message(user_id)
        return
    safe_send_message(bot, user_id, unlock_text(), reply_markup=buy_keyboard(), parse_mode="HTML")


@bot.message_handler(commands=['disclaimer'])
def show_disclaimer(message):
    bot.send_message(message.chat.id, DISCLAIMER_TEXT, parse_mode="HTML")


@bot.message_handler(commands=["help"])
def help_command_handler(message):
    if not is_admin(message.chat.id):
        touch_user_activity(message.chat.id)
    markup = InlineKeyboardMarkup()
    markup.row(
        InlineKeyboardButton("💚 Getting Matches", callback_data="help_matches"),
        InlineKeyboardButton("💬 Chat Rules", callback_data="help_chat")
    )
    markup.row(
        InlineKeyboardButton("💎 VIP Benefits", callback_data="help_vip"),
        InlineKeyboardButton("🛡️ Safety & Privacy", callback_data="help_safety")
    )
    safe_send_message(bot, message.chat.id, "Need a quick guide? Choose a topic below to see how everything works 👇", reply_markup=markup)


@bot.message_handler(commands=["reset"])
def reset_command(message):
    user_id = message.chat.id
    touch_user_activity(user_id)

    safe_send_message(bot, 
        user_id,
        "⚠️ This will reset your profile and remove all data (including VIP).\n\nType CONFIRM to continue or anything else to cancel."
    )

    def confirm_reset(m):
        if m.chat.id != user_id:
            return
        if m.text == "CONFIRM":
            reset_user(user_id)
            safe_send_message(bot, user_id, "Your profile has been reset ✅")
        else:
            safe_send_message(bot, user_id, "Reset cancelled")
        bot.clear_step_handler_by_chat_id(user_id)

    bot.register_next_step_handler(message, confirm_reset)


@bot.message_handler(commands=["stats"])
def stats_handler(message):
    if message.chat.id not in CHAT_ADMINS:
        safe_send_message(bot, message.chat.id, "This command is for admins only.")
        return
    clear_admin_active_chat(message.chat.id)

    conn = get_db_connection()
    total_users = 0
    vip_users = 0
    pending_users = 0
    
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM users")
            total_users = cur.fetchone()[0]

            now_ts = get_current_timestamp()
            cur.execute("SELECT COUNT(*) FROM vip_users WHERE paid = true OR vip_end_date > %s", (now_ts,))
            vip_users = cur.fetchone()[0]

            cur.execute("SELECT COUNT(*) FROM vip_users WHERE payment_status = 'pending'")
            pending_users = cur.fetchone()[0]
            cur.close()
        except Exception as e:
            print(f"Stats DB error: {e}", flush=True)
        finally:
            release_db_connection(conn)

    stats_message = f"""📊 Stats:
Total Users: {total_users}
VIP Users: {vip_users}
Pending Payments: {pending_users}"""
    
    safe_send_message(bot, message.chat.id, stats_message)


@bot.message_handler(commands=["pending"])
def pending_handler(message):
    if message.chat.id not in CHAT_ADMINS:
        safe_send_message(bot, message.chat.id, "This command is for admins only.")
        return
    clear_admin_active_chat(message.chat.id)
    
    # 🔥 SMART FIX: Purani list ki jagah, seedha photo aur Approve/Reject ke buttons bhej do
    send_next_pending_to_admin(message.chat.id)


def get_next_pending_user_id():
    """Get the next pending user ID using Fast DB Query"""
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM vip_users WHERE payment_status = 'pending' LIMIT 1")
            row = cur.fetchone()
            cur.close()
            if row:
                return int(row[0])
        except Exception as e:
            print(f"Next Pending DB error: {e}", flush=True)
        finally:
            release_db_connection(conn)
    return None


def send_next_pending_to_admin(admin_id):
    """Send next pending user's payment proof to admin or notify if none"""
    next_uid = get_next_pending_user_id()
    if not next_uid:
        safe_send_message(bot, admin_id, "✅ No more pending payments")
        return
    
    next_user = get_user(next_uid)
    photo_id = next_user.get("payment_proof_photo_id")
    
    if not photo_id:
        name = next_user.get("name") or f"User {next_uid}"
        safe_send_message(bot, admin_id, f"🧾 Next pending: {name} (ID: {next_uid})")
        return
    
    first_name = next_user.get("name") or "User"
    username = next_user.get("payment_username", "N/A")
    
    caption = f"""🧾 Payment Proof Received

User ID: {next_uid}
Name: {first_name}
Username: @{username}

Status: 🟡 Pending"""
    
    safe_send_photo(bot, 
        admin_id,
        photo_id,
        caption=caption,
        reply_markup=payment_markup(next_uid),
    )


@bot.message_handler(func=lambda message: message.chat.id in CHAT_ADMINS and not message.reply_to_message and message.text.strip() not in {BTN_ADMIN_CHATS, BTN_ADMIN_REFRESH, BTN_ADMIN_UNREAD, BTN_ADMIN_PANEL, BTN_ADMIN_STATS, BTN_ADMIN_PENDING, BTN_ADMIN_BACK}, content_types=["text"])
def admin_direct_reply(message):
    admin_id = message.chat.id

    if admin_id not in admin_active_chat:
        safe_send_message(bot, admin_id, "⚠️ Message ignored! Kripya pehle kisi chat ka 'Reply' button dabayein ya 'Admin Chats' se open karein.")
        return

    context = admin_active_chat[admin_id]

    # 🔥 BUG FIX: Pehle check karo ki admin chat ke andar hai ya list dekh raha hai
    if "user_id" not in context or "match_id" not in context:
        safe_send_message(bot, admin_id, "⚠️ Kripya pehle kisi chat par click karke usko open karein, phir reply likhein.")
        return

    user_id = context["user_id"]
    match_id = context["match_id"]

    if not can_admin_access_chat(admin_id, user_id, match_id):
        safe_send_message(bot, admin_id, "This chat is assigned to another admin.")
        return

    state = get_chat_state(user_id, match_id)
    if state != "active":
        safe_send_message(bot, admin_id, "⚠️ Message ignored! Yeh chat abhi 'active' nahi hai (user ne band kar di hai ya start nahi ki).")
        return

    text = message.text

    append_chat_message(user_id, match_id, "match", text)
    increment_unread(user_id, match_id)
    reset_admin_unread(user_id, match_id, admin_id)
    mirror_admin_reply_to_main_admin(admin_id, user_id, match_id, text)

    # SEND ONLY TO USER (IMPORTANT)
    try:
        user = get_user(user_id)
        profile = get_profile(match_id)
        match_name = profile["name"] if profile else "Match"

        # Show typing indicator
        try:
            safe_send_chat_action(bot, user_id, "typing")
            time.sleep(2)
        except:
            pass

        safe_send_message(bot, 
            user_id,
            f"<b>{match_name}:</b> {text}",
            reply_markup=get_chat_keyboard(user_id, match_id),
            parse_mode="HTML"
        )
        key = (admin_id, user_id)
        if key in admin_notifications:
            del admin_notifications[key]
    except:
        pass


@bot.message_handler(
    func=lambda message: message.chat.id in CHAT_ADMINS and bool(message.reply_to_message),
    content_types=["text"],
)
def admin_reply_handler(message):
    chat_context = chat_map.get(message.reply_to_message.message_id)
    if chat_context:
        user_id = chat_context["user_id"]
        match_id = chat_context["match_id"]
        if not can_admin_access_chat(message.chat.id, user_id, match_id):
            safe_send_message(bot, message.chat.id, "This chat is assigned to another admin.")
            return
        state = get_chat_state(user_id, match_id)
        if state != "active":
            safe_send_message(bot, message.chat.id, "This chat is not active anymore.")
            return
        append_chat_message(user_id, match_id, "match", message.text)
        increment_unread(user_id, match_id)
        reset_admin_unread(user_id, match_id, message.chat.id)
        mirror_admin_reply_to_main_admin(message.chat.id, user_id, match_id, message.text)
        try:
            user = get_user(user_id)
            profile = get_profile(match_id)
            match_name = profile["name"] if profile else "Match"

            # Show typing indicator
            try:
                safe_send_chat_action(bot, user_id, "typing")
                time.sleep(2)
            except:
                pass

            safe_send_message(bot, 
                user_id,
                f"<b>{match_name}:</b> {message.text}",
                reply_markup=get_chat_keyboard(user_id, match_id),
                parse_mode="HTML"
            )
            key = (message.chat.id, user_id)
            if key in admin_notifications:
                del admin_notifications[key]
        except:
            pass


@bot.message_handler(func=lambda message: message.chat.id in CHAT_ADMINS and not bool(message.reply_to_message), content_types=["text"])
def admin_menu_handler(message):
    text = message.text.strip()
    if text in {BTN_ADMIN_CHATS, BTN_ADMIN_REFRESH}:
        send_admin_chat_list(message.chat.id)
        return
    if text == BTN_ADMIN_UNREAD:
        send_admin_chat_list(message.chat.id, unread_only=True)
        return
    if text == BTN_ADMIN_PANEL:
        clear_admin_active_chat(message.chat.id)
        safe_send_message(bot, message.chat.id, "Choose an admin option.", reply_markup=admin_panel_keyboard())
        return
    if text == BTN_ADMIN_STATS:
        stats_handler(message)
        return
    if text == BTN_ADMIN_PENDING:
        pending_handler(message)
        return
    if text == BTN_ADMIN_BACK:
        clear_admin_active_chat(message.chat.id)
        safe_send_message(bot, message.chat.id, "Admin menu is ready.", reply_markup=admin_menu_keyboard())
        return
    clear_admin_active_chat(message.chat.id)
    safe_send_message(bot, message.chat.id, "Use the admin buttons to open chats.", reply_markup=admin_menu_keyboard())


@bot.message_handler(content_types=["photo"])
def photo_handler(message):
    user_id = message.chat.id
    if not is_admin(user_id):
        touch_user_activity(user_id)
    if is_on_cooldown(user_id):
        safe_send_message(bot, user_id, "Please wait a moment ⏳")
        return
    user = get_user(user_id)
    file_id = message.photo[-1].file_id

    if user["step"] == "photo":
        user["photo"] = file_id
        user["step"] = "moderation"
        user["moderation_pending"] = True
        flush_loaded_users()
        threading.Thread(target=delayed_moderation_success, args=(user_id,), daemon=True).start()
        return

    if user["chat_open"] and user["current_match_id"]:
        match_id = user["current_match_id"]
        state = get_chat_state(user_id, match_id)
        if state != "active":
            safe_send_message(bot, user_id, inactive_chat_message(), parse_mode="HTML")
            return
    if user["awaiting_payment"]:
        # Block if already VIP
        if user["paid"]:
            send_vip_already_message(user_id)
            return
        
        # Initialize payment_status if not exists
        if "payment_status" not in user:
            user["payment_status"] = "none"
        
        # Check if already under review
        if user.get("payment_status") == "pending":
            safe_send_message(bot, user_id, "⏳ Your payment is already under review. Please wait.")
            return
        
        # Check if already approved
        if user["paid"]:
            send_vip_already_message(user_id)
            return
        
        # Get user info for admin notification
        first_name = message.from_user.first_name or "User"
        username = message.from_user.username or "N/A"
        
        # Enhanced caption with user info and status
        caption = f"""🧾 Payment Proof Received

User ID: {user_id}
Name: {first_name}
Username: @{username}

Status: 🟡 Pending"""
        
        for admin in PAYMENT_ADMINS:
            safe_send_photo(bot, 
                admin,
                file_id,
                caption=caption,
                reply_markup=payment_markup(user_id),
            )
        
        user["awaiting_payment"] = False
        user["payment_status"] = "pending"
        user["payment_proof_photo_id"] = file_id
        user["payment_username"] = username
        flush_loaded_users()
        
        safe_send_message(bot, user_id, "Screenshot received ✅\n\nWe’re verifying it… please wait a moment", reply_markup=main_menu_keyboard(user_id))
        return
    
    # Block if user is already VIP and sends photo without being in payment flow
    if user["paid"] and not is_admin(user_id):
        send_vip_already_message(user_id)
        return

    # SECRET ADMIN FEATURE: Agar admin random photo bheje, toh File ID de do
    if is_admin(user_id):
        safe_send_message(bot, user_id, f"Sir, Here is the File ID:\n<code>{file_id}</code>", parse_mode="HTML")
        return

    safe_send_message(bot, user_id, "Something went wrong…\n\nPlease try again")




@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):

    safe_answer_callback_query(bot,call.id)

    # --- HELP MENU LOGIC ---
    if call.data.startswith("help_"):
        if call.data == "help_matches":
            text = "<b>How to get matches? ✨</b>\n\nBrowse through profiles and hit '💚' if you like someone. If they like you back, boom... it's a match! 🔥\n\n<i>Tip: If you don't want to wait, VIP members can directly see who liked them in the '👀 Likes' section.</i>"
        elif call.data == "help_chat":
            text = "<b>How chatting works? 💬</b>\n\nGood news: <b>Your first chat with any match is completely FREE!</b> 🎉\n\nTo keep conversations focused, free members can chat with <b>one person at a time</b>.\n\nWant to talk to a new match? Just use the 'End Chat' button in your current conversation to free up your slot for the next person.\n\n<i>(Or upgrade to VIP to talk to multiple people at the exact same time! 😉)</i>"
        elif call.data == "help_vip":
            text = "<b>Why upgrade to VIP? 🚀</b>\n\nVIP is for those who don't want to wait! Here is what you get:\n\n🔓 <b>Multiple Chats:</b> Hold conversations with several matches at the same time.\n👀 <b>See Your Admirers:</b> Instantly reveal who liked your profile.\n⚡ <b>Skip The Line:</b> Get faster connections.\n\nTap 'Unlock Chat' in the Main Menu to upgrade!"
        elif call.data == "help_safety":
            text = "<b>Safety & Privacy 🛡️</b>\n\nPlease be respectful to your matches. Bad behavior may lead to a permanent ban.\n\nIf you ever want to start fresh, change your photo, or delete your data, you can easily reset your entire profile anytime by sending the <b>/reset</b> command."
        
        safe_send_message(bot, call.message.chat.id, text, parse_mode="HTML")
        return

    # --- ADMIN VIEW PROFILE BUTTONS LOGIC ---
    if call.data.startswith("admin_view_user_"):
        uid = int(call.data.replace("admin_view_user_", ""))
        u_data = get_user(uid)
        tag = "🟢 VIP" if u_data.get("paid") else "🟡 FREE"
        
        vip_info = "Not Active"
        if u_data.get("paid"):
            plan_lbl = get_vip_plan_label(u_data)
            rem_days = get_vip_remaining_days(u_data)
            exp_date = format_vip_expiry_date(u_data)
            vip_info = f"Active 💎\nPlan: {plan_lbl}\nRemaining: {rem_days} days\nExpires: {exp_date}"
        
        caption = (
            f"👤 <b>Real User Details</b>\n\n"
            f"Name: {u_data.get('name', 'N/A')}\n"
            f"Age: {u_data.get('age', 'N/A')}\n"
            f"City: {u_data.get('city', 'N/A')}\n"
            f"Status: {tag}\n\n"
            f"💎 <b>VIP Status:</b>\n{vip_info}"
        )
        if u_data.get("photo"):
            safe_send_photo(bot, call.message.chat.id, u_data["photo"], caption=caption, parse_mode="HTML")
        else:
            safe_send_message(bot, call.message.chat.id, caption + "\n\n(No photo available)", parse_mode="HTML")
        return

    if call.data.startswith("admin_view_match_"):
        mid = int(call.data.replace("admin_view_match_", ""))
        m_data = get_profile(mid)
        if m_data:
            loc = m_data.get("location", "Not Set")
            caption = (
                f"👩 <b>Match Profile (Bot)</b>\n\n"
                f"Name: {m_data['name']}\n"
                f"Age: {m_data['age']}\n"
                f"📍 Location: {loc}\n"
                f"ID: {mid}"
            )
            safe_send_photo(bot, call.message.chat.id, m_data["photo"], caption=caption, parse_mode="HTML")
        else:
            safe_send_message(bot, call.message.chat.id, "Profile not found.")
        return
    # ----------------------------------------

    # 🔥 REPLY BUTTON FIX (TOP)
    if call.data and call.data.startswith("reply_"):
        try:
            data = call.data.replace("reply_", "")
            user_id, match_id = map(int, data.split("_"))
            admin_id = call.message.chat.id

            # 🔥 TRICK: Button dabte hi us notification ko delete kar do taaki koi double click na kar sake
            try:
                bot.delete_message(admin_id, call.message.message_id)
            except:
                pass

            admin_notifications.pop((admin_id, user_id), None)

            admin_active_chat[admin_id] = {
                "user_id": user_id,
                "match_id": match_id
            }

            reset_admin_unread(user_id, match_id, admin_id)
            send_admin_chat_history(admin_id, user_id, match_id)
            safe_answer_callback_query(bot,call.id)
            return

        except Exception as e:
            print("Reply error:", e)
            safe_answer_callback_query(bot,call.id, "Error")
            return

    if not is_admin(call.message.chat.id):
        touch_user_activity(call.message.chat.id)

    if call.data == "userend_cancel":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        safe_answer_callback_query(bot,call.id, "Cancelled")
        return

    if call.data == "userend_yes":
        user_id = call.message.chat.id
        try:
            bot.delete_message(user_id, call.message.message_id)
        except:
            pass
        user = get_user(user_id)
        if not user["current_match_id"]:
            safe_answer_callback_query(bot,call.id, "Open a chat first")
            return
        match_id = user["current_match_id"]
        state = get_chat_state(user_id, match_id)
        if state != "active":
            safe_answer_callback_query(bot,call.id, "Chat already closed")
            return
        set_chat_state(user_id, match_id, "ended")
        append_system_message(user_id, match_id, "This chat has ended.\n\nYou can start a new one anytime 🙂")
        notify_admin_chat_status(user_id, match_id, "User ended chat")
        remove_match_from_inbox(user_id, match_id)
        safe_send_message(bot, 
            user_id,
            "<b>Chat closed. ✌️</b>\nHead to the Main Menu to explore new profiles and start a fresh conversation!",
            reply_markup=main_menu_keyboard(user_id),
            parse_mode="HTML",
        )
        safe_answer_callback_query(bot,call.id, "Chat ended")
        return

    if call.data.startswith("start_chat:"):
        user_id = call.message.chat.id
        match_id_str = call.data.split(":", 1)[1]
        if not match_id_str.isdigit():
            safe_answer_callback_query(bot,call.id, "Invalid match")
            return
        match_id = int(match_id_str)
        state = get_chat_state(user_id, match_id)
        if state != "active":
            if not can_start_new_chat(user_id):
                safe_send_message(bot, user_id, unlock_vip_usage_message(user_id), reply_markup=chat_limit_keyboard(), parse_mode="HTML")
                safe_answer_callback_query(bot,call.id, "No chats left")
                return
            if not can_activate_chat(user_id, match_id):
                reply_markup = chat_limit_keyboard() if not get_user(user_id)["paid"] else main_menu_keyboard(user_id)
                safe_send_message(bot, user_id, chat_limit_message(user_id), reply_markup=reply_markup, parse_mode="HTML")
                safe_answer_callback_query(bot,call.id, "Cannot start chat")
                return
            set_chat_state(user_id, match_id, "active")
        bot.edit_message_text("Opening chat...", user_id, call.message.message_id)
        open_match_chat(user_id, match_id, show_history=True)
        safe_answer_callback_query(bot,call.id, "Chat opened")
        return

    if call.data == "cancel_start_chat":
        user_id = call.message.chat.id
        bot.edit_message_text("Cancelled. Choose another action.", user_id, call.message.message_id)
        safe_answer_callback_query(bot,call.id, "Cancelled")
        return

    if call.data.startswith("chatctlyes_"):
        parts = call.data.split("_")
        if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            action = parts[1]
            user_id = int(parts[2])
            match_id = int(parts[3])
            user = get_user(user_id)
            state = get_chat_state(user_id, match_id)

            if action == "lock":
                if user["paid"]:
                    safe_answer_callback_query(bot,call.id, "VIP chat cannot be locked")
                    return
                if state != "active":
                    safe_answer_callback_query(bot,call.id, "Chat is not active")
                    return
                set_chat_state(user_id, match_id, "locked")
                append_system_message(user_id, match_id, "She was about to say something…\n\nUnlock to continue 🔓")
                safe_send_message(bot, user_id, "<b>She was about to say something…</b>\n\nUnlock to continue 🔓", reply_markup=likes_locked_keyboard(), parse_mode="HTML")
                safe_answer_callback_query(bot,call.id, "Chat locked")
                return

            if action == "end":
                if state in {"ended", "blocked"}:
                    safe_answer_callback_query(bot,call.id, "Chat already closed")
                    return
                set_chat_state(user_id, match_id, "ended")
                append_system_message(user_id, match_id, "This chat has ended.\n\nYou can start a new one anytime 🙂")
                remove_match_from_inbox(user_id, match_id)
                safe_send_message(bot, 
                    user_id,
                    "<b>Chat closed. ✌️</b>\nHead to the Main Menu to explore new profiles and start a fresh conversation!",
                    reply_markup=main_menu_keyboard(user_id),
                    parse_mode="HTML",
                )
                safe_answer_callback_query(bot,call.id, "Chat ended")
                return

            if action == "block":
                if state == "blocked":
                    safe_answer_callback_query(bot,call.id, "Chat already blocked")
                    return
                set_chat_state(user_id, match_id, "blocked")
                append_system_message(user_id, match_id, "This chat is no longer available.")
                remove_match_from_inbox(user_id, match_id)
                safe_send_message(bot, user_id, "<b>This chat is no longer available.</b>", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
                safe_answer_callback_query(bot,call.id, "Chat blocked")
                return

        safe_answer_callback_query(bot,call.id, "Invalid action")
        return

    if call.data == "chatctlcancel":
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except:
            pass
        safe_answer_callback_query(bot,call.id, "Cancelled")
        return

    if call.data.startswith("chatctl_"):
        parts = call.data.split("_")
        if len(parts) == 4 and parts[2].isdigit() and parts[3].isdigit():
            action = parts[1]
            user_id = int(parts[2])
            match_id = int(parts[3])
            markup = InlineKeyboardMarkup()
            markup.row(
                InlineKeyboardButton("Yes", callback_data=f"chatctlyes_{action}_{user_id}_{match_id}"),
                InlineKeyboardButton("Cancel", callback_data="chatctlcancel"),
            )
            safe_send_message(bot, call.message.chat.id, "Are you sure?", reply_markup=markup)
            safe_answer_callback_query(bot,call.id)
            return
        safe_answer_callback_query(bot,call.id, "Invalid action")
        return

    if call.data.startswith("userchat_"):
        match_id_text = call.data.split("_", 1)[1]
        if match_id_text.isdigit():
            user_id = call.message.chat.id
            match_id = int(match_id_text)
            user = get_user(user_id)
            if match_id not in user["matches"]:
                safe_answer_callback_query(bot,call.id, "Match not found")
                return
            user["current_match_id"] = match_id
            flush_loaded_users()
            open_match_chat(user_id, match_id, show_history=True)
            safe_answer_callback_query(bot,call.id, "Chat opened")
            return
        safe_answer_callback_query(bot,call.id, "Invalid chat")
        return

    if call.data == "adminrefresh":
        send_admin_chat_list(call.message.chat.id)
        safe_answer_callback_query(bot,call.id, "Refreshed")
        return

    if call.data == "adminunread":
        send_admin_chat_list(call.message.chat.id, unread_only=True)
        safe_answer_callback_query(bot,call.id, "Showing unread chats")
        return

    if call.data.startswith("adminchat_"):
        parts = call.data.split("_")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            user_id = int(parts[1])
            match_id = int(parts[2])
            if not can_admin_access_chat(call.message.chat.id, user_id, match_id):
                safe_answer_callback_query(bot,call.id, "This chat is assigned to another admin.")
                return
            send_admin_chat_history(call.message.chat.id, user_id, match_id)
            safe_answer_callback_query(bot,call.id, "Chat opened")
            return
        safe_answer_callback_query(bot,call.id, "Invalid chat")
        return

    # --- ADMIN VIP CONFIRMATION SYSTEM ---
    if call.data.startswith("vipapprove_"):
        if call.message.chat.id != MAIN_ADMIN_ID:
            safe_answer_callback_query(bot,call.id, "Main admin only")
            return
        parts = call.data.split("_")
        plan_key = parts[1]
        user_id = parts[2]
        plan_label, _ = VIP_PLAN_DAYS[plan_key]
        
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(f"✅ Confirm {plan_label}", callback_data=f"vipconfirm_{plan_key}_{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"vipcancel_{user_id}")
        )
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
        safe_answer_callback_query(bot,call.id, "Please confirm")
        return

    if call.data.startswith("vipcancel_"):
        user_id = call.data.split("_")[1]
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=payment_markup(user_id))
        safe_answer_callback_query(bot,call.id, "Action cancelled")
        return

    if call.data.startswith("vipconfirm_"):
        if call.message.chat.id != MAIN_ADMIN_ID:
            safe_answer_callback_query(bot,call.id, "Main admin only")
            return
        parts = call.data.split("_")
        plan_key = parts[1]
        user_id = int(parts[2])
        plan_label, duration_days = VIP_PLAN_DAYS[plan_key]
        user = get_user(user_id)
        now_ts = get_current_timestamp()
        end_ts = now_ts + (duration_days * 86400)

        user["vip_start_date"] = now_ts
        user["vip_end_date"] = end_ts
        user["paid"] = True
        user["chat_limit"] = 5
        user["awaiting_payment"] = False
        user["payment_status"] = "approved"
        try:
            save_vip_to_db(user_id, user)
        except Exception as e:
            pass
        for thread in user.get("chat_threads", {}).values():
            if thread.get("state") == "locked":
                thread["state"] = "available"
        flush_loaded_users()

        # 🔥 SAFETY FIX: Approval ke baad screenshot se buttons delete kar do
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass

        safe_send_message(bot, call.message.chat.id, f"✅ User {user_id} approved successfully\nPlan: {plan_label}\nValid till: {time.strftime('%d %b %Y', time.localtime(end_ts))}")
        safe_send_message(bot, user_id, f"<b>💎 VIP Activated!\n\nPlan: {plan_label}\n⏳ Valid till: {time.strftime('%d %b %Y', time.localtime(end_ts))}</b>", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
        safe_answer_callback_query(bot,call.id, "Approved")
        send_next_pending_to_admin(call.message.chat.id)
        return

    if call.data.startswith("reject_"):
        user_id = call.data.replace("reject_", "")
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("✅ Confirm Reject", callback_data=f"rejectconfirm_{user_id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"vipcancel_{user_id}")
        )
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=markup)
        safe_answer_callback_query(bot,call.id, "Please confirm")
        return

    if call.data.startswith("rejectconfirm_"):
        user_id = int(call.data.replace("rejectconfirm_", ""))
        user = get_user(user_id)
        user["payment_status"] = "rejected"
        user["payment_proof_photo_id"] = None
        flush_loaded_users()
        
        # 🔥 SAFETY FIX: Reject ke baad bhi buttons delete kar do
        try:
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        except:
            pass

        if user["paid"]:
            send_vip_already_message(user_id)
        else:
            safe_send_message(bot, user_id, "Payment wasn't approved. Please send a clear screenshot again.", reply_markup=buy_keyboard())
        safe_answer_callback_query(bot,call.id, "Rejected")
        send_next_pending_to_admin(call.message.chat.id)
        return

    action, _, raw_user_id = call.data.partition("_")
    if not raw_user_id.isdigit():
        safe_answer_callback_query(bot,call.id, "Invalid action")
        return

    user_id = int(raw_user_id)
    user = get_user(user_id)

    if action == "approve":
        safe_answer_callback_query(bot,call.id, "Use a duration button to approve VIP")
        return

    if action == "reject":
        user["payment_status"] = "rejected"
        # Clear stored photo_id on rejection
        user["payment_proof_photo_id"] = None
        flush_loaded_users()
        if user["paid"]:
            send_vip_already_message(user_id)
        else:
            safe_send_message(bot, user_id, "Payment wasn't approved. Please send a clear screenshot again.", reply_markup=buy_keyboard())
        safe_answer_callback_query(bot,call.id, "Rejected")
        
        # Auto-open next pending user
        send_next_pending_to_admin(call.message.chat.id)
        return

    safe_answer_callback_query(bot,call.id, "Unknown action")
  


@bot.message_handler(func=lambda message: message.chat.id not in CHAT_ADMINS, content_types=["text"])
def text_handler(message):
    user_id = message.chat.id

    # 🔥 ANTI-SPAM: Agar user 1.0 second ke andar lagataar message bhej raha hai (double click), toh ignore karo
    now = time.time()
    if now - LAST_TEXT_TIME.get(user_id, 0) < 1.0:
        return
    LAST_TEXT_TIME[user_id] = now

    touch_user_activity(user_id)
    text = message.text.strip()
    user = get_user(user_id)


    if text == BTN_CONTINUE:
        if user["step"] == "start":
            user["step"] = "age"
            flush_loaded_users()
            safe_send_message(bot, user_id, "🔞 <b>Please enter your age:</b>\n(e.g., 22)", reply_markup=ReplyKeyboardRemove(), parse_mode="HTML")
        else:
            send_current_step_prompt(user_id)
        return

    if user["step"] == "start":
        safe_send_message(bot, user_id, "Tap Continue to begin.", reply_markup=welcome_keyboard())
        return

    if user["step"] == "age":
        if not text.isdigit():
            safe_send_message(bot, user_id, "⚠️ Please enter a valid number (e.g., 22):")
            return
        age = int(text)
        if age < 18:
            safe_send_message(bot, user_id, "🚫 You must be 18+ to use this service.")
            return
        user["age"] = age
        user["step"] = "gender"
        flush_loaded_users()
        safe_send_message(bot, user_id, "👤 Tell us about yourself\n\nSelect your gender:", reply_markup=gender_keyboard())
        return

    if user["step"] == "gender":
        if text not in {BTN_GENDER_MALE, BTN_GENDER_FEMALE}:
            safe_send_message(bot, user_id, "Choose one of the gender buttons.", reply_markup=gender_keyboard())
            return
        user["gender"] = text
        user["step"] = "city"
        flush_loaded_users()
        safe_send_message(bot, user_id, "Enter your city.", reply_markup=ReplyKeyboardRemove())
        return

    if user["step"] == "city":
        user["city"] = text
        user["name"] = message.from_user.first_name or "User"
        user["step"] = "photo"
        flush_loaded_users()
        safe_send_message(bot, user_id, "✅ Final Step!\n\n<b>Add a photo or take a selfie!</b>\n\nPress 📎 and select a photo.", parse_mode="HTML")
        return

    if user["step"] == "photo":
        safe_send_message(bot, user_id, "📸 Please attach a photo to continue.\n\nPress 📎 to select a photo.")
        return

    if user["step"] == "moderation":
        safe_send_message(bot, user_id, "Your photo is still being reviewed. Please wait a moment.")
        return

    if user["step"] == "agreement":
        if text == BTN_READ_AGREEMENT:
            send_agreement_details(user_id)
            return
        if text == BTN_AGREE_CONTINUE:
            user["agreed"] = True
            user["step"] = "ready"
            flush_loaded_users()
            send_main_menu(user_id)
            return
        send_agreement(user_id)
        return

    if text.lower() in {"/profiles", BTN_START.lower()}:
        send_profile_card(user_id)
        return

    if text in {"/likes_you", BTN_LIKES, BTN_SEE_LIKES}:
        open_likes_you(user_id)
        return

    if text == BTN_MATCHES or text.startswith("💖 Matches"):
        show_matches(user_id)
        return

    if text == BTN_NEXT_MATCH or text == BTN_MATCH_NEXT:
        show_next_match(user_id)
        return

    if text == BTN_PREV_MATCH:
        show_prev_match(user_id)
        return

    if text in {"/settings", BTN_SETTINGS}:
        safe_send_message(bot, user_id, "Choose a section.", reply_markup=settings_keyboard())
        return

    if text in {"/buy", BTN_BUY, BTN_GET_VIP, BTN_VIP}:
        # Check if user is already VIP
        if user["paid"]:
            send_vip_already_message(user_id)
            return

        safe_send_message(bot, user_id, unlock_text(), reply_markup=buy_keyboard(), parse_mode="HTML")
        return

    if text == BTN_SEND_PAYMENT:
        if user["paid"]:
            send_vip_already_message(user_id)
            return
        if is_on_cooldown(user_id):
            safe_send_message(bot, user_id, "Please wait a moment ⏳")
            return
        user["awaiting_payment"] = True
        flush_loaded_users()
        safe_send_message(bot, user_id, "Send the payment screenshot now.")
        return

    if text == BTN_MY_PROFILE:
        vip_lines = build_vip_status_lines(user)
        caption = "\n".join([
            "Profile summary",
            "",
            f"Name: {user['name']}",
            f"Gender: {user['gender']}",
            f"City: {user['city']}",
            *vip_lines,
        ])
        if user["photo"]:
            safe_send_photo(bot, user_id, user["photo"], caption=caption, reply_markup=settings_keyboard())
        else:
            safe_send_message(bot, user_id, caption, reply_markup=settings_keyboard())
        return

    if text == BTN_HOW_IT_WORKS or text.lower() == "/help":
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("💚 Getting Matches", callback_data="help_matches"),
            InlineKeyboardButton("💬 Chat Rules", callback_data="help_chat")
        )
        markup.row(
            InlineKeyboardButton("💎 VIP Benefits", callback_data="help_vip"),
            InlineKeyboardButton("🛡️ Safety & Privacy", callback_data="help_safety")
        )
        safe_send_message(bot, user_id, "Need a quick guide? Choose a topic below to see how everything works 👇", reply_markup=markup)
        return

    if text == BTN_MAIN_MENU:
        send_main_menu(user_id)
        return

    if text == BTN_SEND_GIFT:
        reply_markup = main_menu_keyboard(user_id) if user["paid"] else buy_keyboard()
        safe_send_message(bot, user_id, "Gifts can be enabled later with coins or VIP.", reply_markup=reply_markup)
        return

    if text == BTN_CHAT:
        if not user["current_match_id"]:
            safe_send_message(bot, user_id, "Open one of your matches first.", reply_markup=main_menu_keyboard(user_id))
            return
        match_id = user["current_match_id"]
        current_state = get_chat_state(user_id, match_id)
        if current_state == "active":
            open_match_chat(user_id, match_id, show_history=True)
            return
        if not can_start_new_chat(user_id):
            safe_send_message(bot, user_id, unlock_vip_usage_message(user_id), reply_markup=chat_limit_keyboard(), parse_mode="HTML")
            return
        if not can_activate_chat(user_id, match_id):
            reply_markup = chat_limit_keyboard() if not user["paid"] else main_menu_keyboard(user_id)
            safe_send_message(bot, user_id, chat_limit_message(user_id), reply_markup=reply_markup, parse_mode="HTML")
            return
        chats_left = get_chats_left(user_id)
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton("Start Chat", callback_data=f"start_chat:{match_id}"),
            InlineKeyboardButton("Cancel", callback_data="cancel_start_chat")
        )
        safe_send_message(bot, 
            user_id,
            f"Start a new chat?\n\nChats left: {chats_left} / {user['chat_limit']}\nThis will use 1 chat.\n\nContinue?",
            reply_markup=markup
        )
        return

    if text == BTN_END_CHAT:
        if not user["current_match_id"]:
            safe_send_message(bot, user_id, "<b>Open a chat first.</b>", reply_markup=main_menu_keyboard(user_id), parse_mode="HTML")
            return
        match_id = user["current_match_id"]
        if get_chat_state(user_id, match_id) != "active":
            safe_send_message(bot, user_id, inactive_chat_message(), parse_mode="HTML")
            return
        chats_left = get_chats_left(user_id)
        markup = InlineKeyboardMarkup()
        markup.row(
            InlineKeyboardButton(BTN_CONFIRM_END_CHAT, callback_data="userend_yes"),
            InlineKeyboardButton(BTN_CANCEL_END_CHAT, callback_data="userend_cancel"),
        )
        safe_send_message(bot, 
            user_id,
            f"<b>Want to end this conversation? 🚪</b>\n\nThis chat will be closed permanently, and it will count towards your chat limit.\n(Chats left: {chats_left} / {user['chat_limit']})\n\nReady for a new connection?",
            reply_markup=markup,
            parse_mode="HTML"
        )
        return

    if text == BTN_LIKE:
        if is_on_cooldown(user_id):
            safe_send_message(bot, user_id, "Please wait a moment ⏳")
            return
            
        is_likes_view = (user.get("active_view") == "likes")
        profile_id = user["current_profile_id"]
        if profile_id is None:
            send_profile_card(user_id)
            return

        profile = get_profile(profile_id)
        if profile_id in user["liked"] or profile_id in user["matches"]:
            already_liked = True
            flush_loaded_users()
        else:
            already_liked = False
            user["liked"].append(profile_id)
            
        user["swipes"] += 1
        was_incoming = profile_id in user["incoming_likes"]
        if profile_id in user["incoming_likes"]:
            user["incoming_likes"].remove(profile_id)
            
        if not was_incoming and not already_liked:
            schedule_reaction_after_like(user, profile_id)
        flush_loaded_users()

        if already_liked:
            safe_send_message(bot, user_id, "You already reacted to this profile. Let's keep moving.", reply_markup=build_keyboard([BTN_MAIN_MENU]))
            process_pending_events(user_id)
            if is_likes_view:
                user["active_view"] = "menu"
                flush_loaded_users()
            else:
                time.sleep(random.uniform(0.4, 0.8))
                send_profile_card(user_id)
            return

        if is_likes_view:
            if profile:
                send_like_feedback(user_id, profile)
            if was_incoming and profile_id not in user["matches"]:
                create_match(user_id, profile_id, "liked_back")
            process_pending_events(user_id)
            
            incoming_now = list(user["incoming_likes"])
            if incoming_now:
                time.sleep(1)
                open_likes_you(user_id)
            else:
                user["active_view"] = "menu"
                flush_loaded_users()
        else:
            if profile:
                send_like_feedback(user_id, profile)
            if was_incoming and profile_id not in user["matches"]:
                create_match(user_id, profile_id, "liked_back")
            process_pending_events(user_id)
            time.sleep(random.uniform(0.6, 1.1))
            send_profile_card(user_id)
        return

    if text == BTN_SKIP:
        if is_on_cooldown(user_id):
            safe_send_message(bot, user_id, "Please wait a moment ⏳")
            return
            
        is_likes_view = (user.get("active_view") == "likes")
        profile_id = user["current_profile_id"]
        
        if profile_id and profile_id not in user["skipped"]:
            user["skipped"].append(profile_id)
        if profile_id in user["incoming_likes"]:
            user["incoming_likes"].remove(profile_id)
            
        user["swipes"] += 1
        flush_loaded_users()
        process_pending_events(user_id)
        
        if is_likes_view:
            incoming_now = list(user["incoming_likes"])
            if incoming_now:
                open_likes_you(user_id)
            else:
                user["active_view"] = "menu"
                flush_loaded_users()
                safe_send_message(bot, user_id, "No more new likes right now.", reply_markup=main_menu_keyboard(user_id))
        else:
            send_profile_card(user_id)
        return

    if user["current_match_id"]:
        match_id = user["current_match_id"]
        state = get_chat_state(user_id, match_id)
        if state == "active":
            forward_user_message_to_admins(message)
            
            # Send "Chat started" system message on first message in new chat
            user = get_user(user_id)
            state = get_chat_state(user_id, match_id)
            if state == "active":
                chat_started_notified = user.get("chat_started_notified", {})
                match_id_str = str(match_id)
                if match_id_str not in chat_started_notified:
                    chats_left = get_chats_left(user_id)
                    safe_send_message(bot, user_id, f"<b>Chat started!</b>\nChats left: {chats_left} / {user['chat_limit']}", parse_mode="HTML")
                    user = get_user(user_id)
                    user.setdefault("chat_started_notified", {})[match_id_str] = True
                    flush_loaded_users()
            return
        safe_send_message(bot, user_id, inactive_chat_message(), parse_mode="HTML")
        return

def get_webhook_base_url():
    if not WEBHOOK_BASE_URL:
        raise RuntimeError("Set WEBHOOK_BASE_URL or Railway public domain environment variable before starting the webhook server.")
    base_url = WEBHOOK_BASE_URL.strip()
    if not base_url.startswith(("http://", "https://")):
        base_url = f"https://{base_url}"
    return base_url.rstrip("/")


def configure_webhook():
    webhook_url = f"{get_webhook_base_url()}/{TOKEN}"
    for _ in range(3):
        try:
            bot.remove_webhook()
            time.sleep(1)
            bot.set_webhook(url=webhook_url)
            print(f"Webhook set: {webhook_url}")
            return
        except Exception as e:
            print(f"set_webhook error: {e}")
            time.sleep(1.5)
    raise RuntimeError("Failed to configure Telegram webhook after retries.")


# 🔥 DEDUPLICATION CACHE: Telegram ke duplicate messages ko rokne ke liye
PROCESSED_UPDATES = {}

@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    clear_request_user_context()
    try:
        json_str = request.get_data(cache=False, as_text=False).decode("utf-8")
        update = telebot.types.Update.de_json(json_str)
        
        # 🛡️ ANTI-DUPLICATE SYSTEM: Check karo agar ye message pehle hi process ho chuka hai
        update_id = update.update_id
        if update_id in PROCESSED_UPDATES:
            # Agar ID pehle se list me hai, toh chup-chaap OK bol kar wapas bhej do
            return "OK", 200
            
        # Nayi ID ko list me save karo
        PROCESSED_UPDATES[update_id] = True
        
        # Cache ko limit me rakho taaki RAM full na ho (Aakhiri 5000 messages yaad rakhega)
        if len(PROCESSED_UPDATES) > 5000:
            oldest_key = next(iter(PROCESSED_UPDATES))
            del PROCESSED_UPDATES[oldest_key]

        # Naye message ko process karne bhejo
        bot.process_new_updates([update])
        
    except Exception as e:
        print(f"❌ Webhook Error: {e}", flush=True)
        traceback.print_exc()
    finally:
        try:
            flush_loaded_users()
        except Exception as db_err:
            print(f"❌ Database Save Error in Webhook: {db_err}", flush=True)
        finally:
            clear_request_user_context()
    return "OK", 200


@app.route("/", methods=["GET"])
def healthcheck():
    return "OK", 200


threading.Thread(target=inactivity_engagement_worker, daemon=True).start()
print(f"Database configured: {bool(os.getenv('DATABASE_URL'))}")
print("DB schema ready")

if __name__ == "__main__":
    configure_webhook()

    port = int(os.environ["PORT"])

    # 🔥 PRO-LEVEL: Flask Development Server hata kar Production Server (Waitress) lagaya
    try:
        from waitress import serve
        print(f"🚀 Starting Production Server (Waitress) on port {port}...", flush=True)
        serve(app, host="0.0.0.0", port=port, threads=16)
    except ImportError:
        print("⚠️ Waitress not found! Falling back to Flask Dev Server...", flush=True)
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

