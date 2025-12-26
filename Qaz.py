#==================== Import ======================#
from colorama import Fore
from pyrogram import Client, filters, idle, errors
from pyrogram.types import *
from functools import wraps, lru_cache
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dbutils.pooled_db import PooledDB  # تغییر این خط
import asyncio
import subprocess
import html
import zipfile
import pymysql
import shutil
import signal
import json
import re
import os
import time
import logging
import tempfile
import io
from PIL import Image
from datetime import datetime, timedelta

#==================== Config =====================#
Admin = 8324661572
Token = "8407995036:AAGsNEnLcL49NLmyry_t1JSR5k7RiEL7fJA"
API_ID = 32723346
API_HASH = "00b5473e6d13906442e223145510676e"
Channel_ID = "SHAH_SELF"
Channel_Help = "SHAH_SELF"
Helper_ID = "SHAH_SELF"
api_channel = "SHAH_SELF"
DBName = "SELFSAZ"
DBUser = "SELFSAZ"
DBPass = "Zxcvbnm1111"
HelperDBName = "HELPER"
HelperDBUser = "HELPER"
HelperDBPass = "Zxcvbnm1111"
CardNumber = "6037701213986919"
CardName = "امیرعلی میرزایی"

#==================== Logging Optimization =====================#
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.basicConfig(level=logging.WARNING)

#==================== Database Connection Pool =====================#
db_pool = None
helper_db_pool = None

def init_db_pools():
    global db_pool, helper_db_pool
    
    db_pool = PooledDB(
        creator=pymysql,
        mincached=2,
        maxcached=10,
        maxconnections=20,
        host="localhost",
        user=DBUser,
        password=DBPass,
        database=DBName,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )
    
    helper_db_pool = PooledDB(
        creator=pymysql,
        mincached=2,
        maxcached=5,
        maxconnections=10,
        host="localhost",
        user=HelperDBUser,
        password=HelperDBPass,
        database=HelperDBName,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

init_db_pools()

#==================== Caching System =====================#
class CacheManager:
    def __init__(self, ttl=300):  # 5 minutes default
        self.cache = {}
        self.ttl = ttl
    
    def get(self, key):
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            else:
                del self.cache[key]
        return None
    
    def set(self, key, value):
        self.cache[key] = (value, time.time())
    
    def delete(self, key):
        if key in self.cache:
            del self.cache[key]
    
    def clear(self):
        self.cache.clear()

cache_manager = CacheManager(ttl=60)  # 1 minute TTL for user data

#==================== Database Functions (Optimized) =====================#
def execute_query(query, params=None, fetchone=False, fetchall=False, commit=False, helper=False):
    """Execute database query with connection pooling"""
    pool = helper_db_pool if helper else db_pool
    
    try:
        with pool.connection() as conn:
            with conn.cursor() as cursor:
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                if commit:
                    conn.commit()
                
                if fetchone:
                    return cursor.fetchone()
                elif fetchall:
                    return cursor.fetchall()
                else:
                    return cursor.rowcount
    except Exception as e:
        print(f"Database error: {e}")
        return None

# Optimized database functions
def get_data(query, params=None):
    return execute_query(query, params, fetchone=True)

def get_datas(query, params=None):
    return execute_query(query, params, fetchall=True)

def update_data(query, params=None):
    return execute_query(query, params, commit=True)

def helper_getdata(query, params=None):
    return execute_query(query, params, fetchone=True, helper=True)

def helper_updata(query, params=None):
    return execute_query(query, params, commit=True, helper=True)

def get_user_data_cached(user_id):
    """Get user data with caching"""
    cache_key = f"user_{user_id}"
    cached = cache_manager.get(cache_key)
    
    if cached:
        return cached
    
    user_data = get_data("SELECT * FROM user WHERE id = %s LIMIT 1", (user_id,))
    if user_data:
        cache_manager.set(cache_key, user_data)
    
    return user_data

def update_user_data(user_id, **kwargs):
    """Update user data and invalidate cache"""
    if not kwargs:
        return
    
    set_clause = ", ".join([f"{k} = %s" for k in kwargs.keys()])
    values = list(kwargs.values())
    values.append(user_id)
    
    query = f"UPDATE user SET {set_clause} WHERE id = %s"
    result = update_data(query, values)
    
    # Invalidate cache
    cache_manager.delete(f"user_{user_id}")
    return result

@lru_cache(maxsize=128)
def get_setting_cached(key):
    """Get setting with LRU cache"""
    result = get_data("SELECT setting_value FROM settings WHERE setting_key = %s", (key,))
    return result["setting_value"] if result else None

def update_setting(key, value):
    """Update setting and clear cache"""
    update_data("UPDATE settings SET setting_value = %s WHERE setting_key = %s", (value, key))
    get_setting_cached.cache_clear()

#==================== Create Directories =====================#
def ensure_directories():
    dirs = ["sessions", "selfs", "cards", "temp"]
    for dir_name in dirs:
        if not os.path.isdir(dir_name):
            os.mkdir(dir_name)

ensure_directories()

#==================== App Configuration =====================#
app = Client(
    "Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=Token,
    workers=4,  # Reduced workers
    sleep_threshold=30,
    no_updates=False,
    max_concurrent_transmissions=2
)

temp_Client = {}
lock = asyncio.Lock()

#==================== Database Initialization =====================#
def init_database():
    """Initialize database tables if not exist"""
    
    # Main database tables
    tables = [
        """
        CREATE TABLE IF NOT EXISTS bot(
            status varchar(10) DEFAULT 'ON'
        ) default charset=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS user(
            id bigint PRIMARY KEY,
            step varchar(150) DEFAULT 'none',
            phone varchar(150) DEFAULT NULL,
            api_id varchar(50) DEFAULT NULL,
            api_hash varchar(100) DEFAULT NULL,
            expir bigint DEFAULT '0',
            account varchar(50) DEFAULT 'unverified',
            self varchar(50) DEFAULT 'inactive',
            pid bigint DEFAULT NULL,
            last_language_change bigint DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_step (step(50)),
            INDEX idx_expir (expir)
        ) default charset=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS codes(
            id INT AUTO_INCREMENT PRIMARY KEY,
            code VARCHAR(20) UNIQUE NOT NULL,
            days INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used_by BIGINT DEFAULT NULL,
            used_at TIMESTAMP NULL,
            is_active BOOLEAN DEFAULT TRUE,
            INDEX idx_code (code),
            INDEX idx_active (is_active)
        ) default charset=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS cards(
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id bigint NOT NULL,
            card_number varchar(20) NOT NULL,
            bank_name varchar(50) DEFAULT NULL,
            verified varchar(10) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_id (user_id),
            INDEX idx_verified (verified),
            INDEX idx_card_number (card_number(10)),
            FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE
        ) default charset=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS settings(
            id INT AUTO_INCREMENT PRIMARY KEY,
            setting_key VARCHAR(100) NOT NULL UNIQUE,
            setting_value TEXT NOT NULL,
            description VARCHAR(255) DEFAULT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_key (setting_key)
        ) default charset=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS block(
            id bigint PRIMARY KEY
        ) default charset=utf8mb4;
        """
    ]
    
    for table_sql in tables:
        update_data(table_sql)
    
    # Helper database tables
    helper_tables = [
        """
        CREATE TABLE IF NOT EXISTS ownerlist(
            id bigint PRIMARY KEY
        ) default charset=utf8mb4;
        """,
        """
        CREATE TABLE IF NOT EXISTS adminlist(
            id bigint PRIMARY KEY
        ) default charset=utf8mb4;
        """
    ]
    
    for table_sql in helper_tables:
        helper_updata(table_sql)
    
    # Insert default data if not exists
    if not get_data("SELECT * FROM bot LIMIT 1"):
        update_data("INSERT INTO bot() VALUES()")
    
    if not helper_getdata("SELECT * FROM ownerlist WHERE id = %s LIMIT 1", (Admin,)):
        helper_updata("INSERT INTO ownerlist(id) VALUES(%s)", (Admin,))
    
    if not helper_getdata("SELECT * FROM adminlist WHERE id = %s LIMIT 1", (Admin,)):
        helper_updata("INSERT INTO adminlist(id) VALUES(%s)", (Admin,))
    
    # Default settings
    default_settings = [
        ("start_message", "**\nسلام [ {user_link} ],  به ربات خرید دستیار تلگرام خوش آمدید.\n\nتوی این ربات میتونید از خرید، نصب دستیار بهره ببرید.\n\nلطفا اگر سوالی دارید از بخش پشتیبانی ، با پشتیبان ها در ارتباط باشید یا در گروه پشتیبانی ما عضو شوید.\n\n\n **", "پیام استارت ربات"),
        ("price_message", "**\nنرخ ربات دستیار عبارت است از :\n\n» 1 ماهه : ( `{price_1month}` تومان )\n\n» 2 ماهه : ( `{price_2month}` تومان )\n\n» 3 ماهه : ( `{price_3month}` تومان )\n\n» 4 ماهه : ( `{price_4month}` تومان )\n\n» 5 ماهه : ( `{price_5month}` تومان )\n\n» 6 ماهه : ( `{price_6month}` تومان )\n\n\n(⚠️) توجه داشته باشید که ربات دستیار روی شماره های ایران توصیه میشود و در صورت نصب روی شماره های خارج از کشور، ما مسئولیتی در مورد مسدود شدن اکانت نداریم.\n\n\nدر صورتی که میخواهید به صورت ارزی پرداخت کنید از پشتیبانی درخواست ولت کنید.\n‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌\n‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌‌\n**", "پیام نرخ‌ها"),
        ("whatself_message", "**\nسلف به رباتی گفته میشه که روی اکانت شما نصب میشه و امکانات خاصی رو در اختیارتون میزاره ، لازم به ذکر هست که نصب شدن بر روی اکانت شما به معنی وارد شدن ربات به اکانت شما هست ( به دلیل دستور گرفتن و انجام فعالیت ها )\nاز جمله امکاناتی که در اختیار شما قرار میدهد شامل موارد زیر است:\n\n❈ گذاشتن ساعت با فونت های مختلف بر روی بیو ، اسم\n❈ قابلیت تنظیم حالت خوانده شدن خودکار پیام ها\n❈ تنظیم حالت پاسخ خودکار\n❈ پیام انیمیشنی\n❈ منشی هوشمند\n❈ دریافت پنل و تنظیمات اکانت هوشمند\n❈ دو زبانه بودن دستورات و جواب ها\n❈ تغییر نام و کاور فایل ها\n❈ اعلان پیام ادیت و حذف شده در پیوی\n❈ ذخیره پروفایل های جدید و اعلان حذف پروفایل مخاطبین\n\nو امکاناتی دیگر که میتوانید با مراجعه به بخش راهنما آن ها را ببینید و مطالعه کنید!\n\n❈ لازم به ذکر است که امکاناتی که در بالا گفته شده تنها ذره ای از امکانات سلف میباشد .\n**", "پیام توضیح سلف"),
        ("price_1month", "75000", "قیمت 1 ماهه"),
        ("price_2month", "150000", "قیمت 2 ماهه"),
        ("price_3month", "220000", "قیمت 3 ماهه"),
        ("price_4month", "275000", "قیمت 4 ماهه"),
        ("price_5month", "340000", "قیمت 5 ماهه"),
        ("price_6month", "390000", "قیمت 6 ماهه"),
        ("card_number", CardNumber, "شماره کارت"),
        ("card_name", CardName, "نام صاحب کارت"),
        ("phone_restriction", "enabled", "محدودیت شماره (فقط ایران)"),
    ]
    
    for key, value, description in default_settings:
        if not get_data("SELECT * FROM settings WHERE setting_key = %s", (key,)):
            update_data("INSERT INTO settings(setting_key, setting_value, description) VALUES(%s, %s, %s)", 
                       (key, value, description))

init_database()

#==================== Performance Monitor =====================#
def performance_monitor(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            end_time = time.time()
            duration = end_time - start_time
            if duration > 0.5:  # Log slow operations (>500ms)
                func_name = func.__name__
                print(f"⏱️ Performance: {func_name} took {duration:.3f}s")
    return wrapper

#==================== Optimized Functions =====================#
@lru_cache(maxsize=128)
def get_prices_cached():
    """Get prices with caching"""
    return {
        "1month": get_setting_cached("price_1month") or "75000",
        "2month": get_setting_cached("price_2month") or "150000",
        "3month": get_setting_cached("price_3month") or "220000",
        "4month": get_setting_cached("price_4month") or "275000",
        "5month": get_setting_cached("price_5month") or "340000",
        "6month": get_setting_cached("price_6month") or "390000",
    }

def add_card(user_id, card_number, bank_name=None):
    params = [user_id, card_number]
    if bank_name:
        update_data("INSERT INTO cards(user_id, card_number, bank_name, verified) VALUES(%s, %s, %s, 'pending')", 
                   (user_id, card_number, bank_name))
    else:
        update_data("INSERT INTO cards(user_id, card_number, verified) VALUES(%s, %s, 'pending')", 
                   (user_id, card_number))

def get_user_cards(user_id):
    return get_datas("SELECT * FROM cards WHERE user_id = %s AND verified = 'verified' ORDER BY id DESC", (user_id,))

def get_user_all_cards(user_id):
    return get_datas("SELECT * FROM cards WHERE user_id = %s ORDER BY id DESC", (user_id,))

def get_pending_cards():
    return get_datas("SELECT * FROM cards WHERE verified = 'pending'")

def update_card_status(card_id, status, bank_name=None):
    if bank_name:
        update_data("UPDATE cards SET verified = %s, bank_name = %s WHERE id = %s", (status, bank_name, card_id))
    else:
        update_data("UPDATE cards SET verified = %s WHERE id = %s", (status, card_id))

def delete_card(card_id):
    update_data("DELETE FROM cards WHERE id = %s", (card_id,))

def get_card_by_number(user_id, card_number):
    return get_data("SELECT * FROM cards WHERE user_id = %s AND card_number = %s LIMIT 1", (user_id, card_number))

def get_card_by_id(card_id):
    return get_data("SELECT * FROM cards WHERE id = %s LIMIT 1", (card_id,))

def generate_random_code(length=16):
    import random
    import string
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

def create_code(days):
    code = generate_random_code()
    update_data("INSERT INTO codes(code, days) VALUES(%s, %s)", (code, days))
    return code

def get_code_by_value(code_value):
    return get_data("SELECT * FROM codes WHERE code = %s AND is_active = TRUE LIMIT 1", (code_value,))

def use_code(code_value, user_id):
    update_data("UPDATE codes SET used_by = %s, used_at = NOW(), is_active = FALSE WHERE code = %s", 
               (user_id, code_value))

def get_active_codes():
    return get_datas("SELECT * FROM codes WHERE is_active = TRUE ORDER BY created_at DESC")

def get_all_codes():
    return get_datas("SELECT * FROM codes ORDER BY created_at DESC")

def delete_code(code_id):
    update_data("DELETE FROM codes WHERE id = %s", (code_id,))

def cleanup_inactive_codes():
    update_data("DELETE FROM codes WHERE is_active = FALSE")

def add_admin(user_id):
    if not helper_getdata("SELECT * FROM adminlist WHERE id = %s LIMIT 1", (user_id,)):
        helper_updata("INSERT INTO adminlist(id) VALUES(%s)", (user_id,))

def delete_admin(user_id):
    helper_updata("DELETE FROM adminlist WHERE id = %s LIMIT 1", (user_id,))

#==================== Decorators =====================#
def checker(func):
    @wraps(func)
    @performance_monitor
    async def wrapper(c, m, *args, **kwargs):
        chat_id = m.chat.id if hasattr(m, "chat") else m.from_user.id
        
        # Check block status
        block = get_data("SELECT * FROM block WHERE id = %s LIMIT 1", (chat_id,))
        if block is not None and chat_id != Admin:
            return
        
        # Check bot status
        bot_status = get_data("SELECT status FROM bot LIMIT 1")
        if bot_status["status"] == "OFF" and chat_id != Admin:
            await app.send_message(chat_id, "**درحال حاظر ربات خاموش میباشد، بعدا مجدد اقدام نمایید.**")
            return
        
        # Check channel membership (cached)
        try:
            chat = await app.get_chat(Channel_ID)
            await app.get_chat_member(Channel_ID, chat_id)
        except errors.UserNotParticipant:
            channel_name = chat.title if chat else "کانال"
            await app.send_message(chat_id, 
                "**• برای استفاده از خدمات ما ابتدا باید در کانال ما عضو باشید، بعد از این که عضو شدید روی دکمه عضو شدم کلیک کنید.**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text=f"( {channel_name} )", url=f"https://t.me/{Channel_ID}")],
                    [InlineKeyboardButton(text="عضو شدم ( ✔️ )", callback_data="check_membership")]
                ])
            )
            return
        except errors.ChatAdminRequired:
            if chat_id == Admin:
                await app.send_message(Admin, "**• ابتدا ربات را در کانال ادمین کرده سپس ربات را [ /start ] کنید.**")
            return
        
        return await func(c, m, *args, **kwargs)
    return wrapper

#==================== Scheduler Functions =====================#
async def expirdec(user_id):
    """Decrease expiration date"""
    user = get_user_data_cached(user_id)
    if not user:
        return
    
    user_expir = user.get("expir", 0)
    if user_expir > 0:
        update_user_data(user_id, expir=user_expir - 1)
    else:
        job = scheduler.get_job(str(user_id))
        if job:
            scheduler.remove_job(str(user_id))
        
        if user_id != Admin:
            delete_admin(user_id)
        
        # Cleanup user files
        await cleanup_user_files(user_id)
        
        await app.send_message(user_id, 
            "**انقضای سلف شما به پایان رسید، شما میتوانید از بخش **خرید اشتراک**، **سلف خود را تمدید کنید.**")
        
        update_user_data(user_id, self='inactive', pid=None)

async def cleanup_user_files(user_id):
    """Cleanup user files asynchronously"""
    try:
        # Stop process if running
        user_data = get_user_data_cached(user_id)
        if user_data and user_data.get("pid"):
            try:
                os.kill(user_data["pid"], signal.SIGKILL)
            except:
                pass
        
        # Remove directories
        user_folder = f"selfs/self-{user_id}"
        if os.path.isdir(user_folder):
            await asyncio.to_thread(shutil.rmtree, user_folder, ignore_errors=True)
        
        # Remove session files
        session_files = [
            f"sessions/{user_id}.session",
            f"sessions/{user_id}.session-journal",
            f"sessions/{user_id}.session-wal",
            f"sessions/{user_id}.session-shm"
        ]
        
        for file_path in session_files:
            if os.path.exists(file_path):
                await asyncio.to_thread(os.remove, file_path)
    
    except Exception as e:
        print(f"Cleanup error for user {user_id}: {e}")



async def expirdec_task():
    """Task to decrease expiration dates"""
    while True:
        await asyncio.sleep(24 * 3600)  # هر 24 ساعت
        
        users = get_datas("SELECT id, expir FROM user WHERE expir > 0")
        for user in users:
            user_id = user["id"]
            user_expir = user["expir"]
            
            if user_expir > 0:
                update_data("UPDATE user SET expir = expir - 1 WHERE id = %s", (user_id,))
            else:
                # Cleanup user
                await cleanup_user_files(user_id)
                
                if user_id != Admin:
                    delete_admin(user_id)
                
                await app.send_message(
                    user_id, 
                    "**انقضای سلف شما به پایان رسید، شما میتوانید از بخش **خرید اشتراک**، **سلف خود را تمدید کنید.**"
                )

#==================== Self Status Check =====================#
async def check_self_status(user_id):
    """Check self bot status with caching"""
    cache_key = f"self_status_{user_id}"
    cached = cache_manager.get(cache_key)
    if cached:
        return cached
    
    try:
        user_folder = f"selfs/self-{user_id}"
        if not os.path.isdir(user_folder):
            result = {
                "status": "not_installed",
                "message": "سلف شما نصب نشده است.",
                "language": None
            }
            cache_manager.set(cache_key, result)
            return result
        
        data_file = os.path.join(user_folder, "data.json")
        if not os.path.isfile(data_file):
            result = {
                "status": "error",
                "message": "تنطیمات سلف نصب نشده است.",
                "language": None
            }
            cache_manager.set(cache_key, result)
            return result
        
        # Read JSON file
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        language = data.get("language", "fa")
        language_text = "فارسی" if language == "fa" else "انگلیسی"
        
        user_data = get_user_data_cached(user_id)
        if not user_data:
            result = {
                "status": "error",
                "message": "اطلاعات ربات پیدا نشد.",
                "language": language_text
            }
            cache_manager.set(cache_key, result)
            return result
        
        pid = user_data.get("pid")
        self_status = user_data.get("self", "inactive")
        
        if pid:
            try:
                os.kill(pid, 0)
                process_status = "running"
            except OSError:
                process_status = "stopped"
        else:
            process_status = "no_pid"
        
        if self_status == "active" and process_status == "running":
            result = {
                "status": "healthy",
                "message": "`دستیار شما موردی نداره و روشن هست.`",
                "language": language_text
            }
        elif self_status == "active" and process_status == "stopped":
            result = {
                "status": "problem",
                "message": "`دستیار شما با مشکل مواجه شده و نیاز به ورود مجدد است.`",
                "language": language_text
            }
        elif self_status == "inactive":
            result = {
                "status": "inactive",
                "message": "`دستیار شما خاموش است.`",
                "language": language_text
            }
        else:
            result = {
                "status": "unknown",
                "message": "`وضعیت دستیار شما نامشخص است`",
                "language": language_text
            }
        
        cache_manager.set(cache_key, result)
        return result
            
    except Exception as e:
        result = {
            "status": "error",
            "message": "**سلف شما نصب نشده است، ابتدا دستیار خود را نصب کنید.**",
            "language": None
        }
        cache_manager.set(cache_key, result)
        return result

async def change_self_language(user_id, target_language):
    """Change self bot language"""
    try:
        user_folder = f"selfs/self-{user_id}"
        data_file = os.path.join(user_folder, "data.json")
        
        if not os.path.isfile(data_file):
            return False, "**تنظیمات ربات دستیار نصب نشده است.**"
        
        # Read and update JSON
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        old_language = data.get("language", "fa")
        data["language"] = target_language
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        # Update cache
        cache_manager.delete(f"self_status_{user_id}")
        
        # Update database
        current_time = int(time.time())
        update_user_data(user_id, last_language_change=current_time)
        
        return True, old_language
        
    except Exception as e:
        return False, str(e)

def can_change_language(user_id):
    """Check if user can change language"""
    user_data = get_user_data_cached(user_id)
    
    if not user_data or user_data.get("last_language_change") is None:
        return True, 0
    
    last_change = int(user_data.get("last_language_change", 0))
    current_time = int(time.time())
    time_passed = current_time - last_change
    
    if time_passed >= 1800:  # 30 minutes
        return True, 0
    
    remaining_seconds = 1800 - time_passed
    remaining_minutes = (remaining_seconds + 59) // 60
    
    return False, remaining_minutes

def get_current_language(user_id):
    """Get current language of self bot"""
    try:
        user_folder = f"selfs/self-{user_id}"
        data_file = os.path.join(user_folder, "data.json")
        
        if not os.path.isfile(data_file):
            return "fa"
        
        with open(data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return data.get("language", "fa")
    except:
        return "fa"

#==================== Self Installation =====================#
async def extract_self_files(user_id, language="fa"):
    """Extract self bot files asynchronously"""
    try:
        user_folder = f"selfs/self-{user_id}"
        
        # Remove existing directory
        if os.path.exists(user_folder):
            await asyncio.to_thread(shutil.rmtree, user_folder, ignore_errors=True)
        
        await asyncio.to_thread(os.makedirs, user_folder, exist_ok=True)
        
        # Create data.json
        data_file = os.path.join(user_folder, "data.json")
        default_data = {
            "language": language,
            "user_id": user_id,
            "bot_language": language
        }
        
        await asyncio.to_thread(
            lambda: json.dump(default_data, open(data_file, 'w', encoding='utf-8'), 
                            ensure_ascii=False, indent=2)
        )
        
        # Extract zip file
        zip_path = "source/Self.zip"
        
        if not os.path.isfile(zip_path):
            return False
        
        file_size = os.path.getsize(zip_path)
        if file_size == 0:
            return False
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                if zip_ref.testzip() is not None:
                    return False
                
                # Extract only essential files
                essential_files = ['self.py', 'requirements.txt', 'config.py']
                for file in essential_files:
                    if file in zip_ref.namelist():
                        zip_ref.extract(file, user_folder)
                
                return True
                
        except zipfile.BadZipFile:
            return False
            
    except Exception as e:
        print(f"Extract error: {e}")
        return False

def validate_phone_number(phone_number):
    """Validate phone number"""
    restriction = get_setting_cached("phone_restriction") or "enabled"
    
    if restriction == "disabled":
        return True, None
    
    if not phone_number.startswith("+"):
        phone_number = f"+{phone_number}"
    
    if phone_number.startswith("+98"):
        return True, None
    else:
        return False, "**تا اطلاع ثانوی، نصب یا خرید ربات سلف روی اکانت مجازی غیرمجاز میباشد.**"

async def safe_edit_message(chat_id, message_id, new_text):
    """Edit message safely"""
    try:
        await app.edit_message_text(chat_id, message_id, new_text)
        return True
    except errors.MessageNotModified:
        return False
    except Exception as e:
        print(f"Edit message error: {e}")
        return False

@performance_monitor
async def start_self_installation(user_id, phone, api_id, api_hash, message_id=None, language="fa"):
    """Start self bot installation"""
    try:
        # Validate phone number
        is_valid, error_message = validate_phone_number(phone)
        if not is_valid:
            if message_id:
                await safe_edit_message(user_id, message_id, error_message)
            else:
                await app.send_message(user_id, error_message)
            return False
        
        # Update message
        if message_id:
            await safe_edit_message(user_id, message_id, "**• درحال ساخت سلف، لطفا صبور باشید.**")
        else:
            await app.send_message(user_id, "**• درحال ساخت سلف، لطفا صبور باشید.**")
        
        # Extract files
        success = await extract_self_files(user_id, language)
        if not success:
            if message_id:
                await safe_edit_message(user_id, message_id, "**استخراج فایل ربات با خطا مواجه شد، با پشتیبانی در ارتباط باشید.**")
            return False
        
        # Create client
        client = Client(
            f"sessions/{user_id}",
            api_id=int(api_id),
            api_hash=api_hash
        )
        
        await client.connect()
        
        # Send code
        sent_code = await client.send_code(phone)
        
        # Store client data
        temp_Client[user_id] = {
            "client": client,
            "phone_code_hash": sent_code.phone_code_hash,
            "phone": phone,
            "api_id": api_id,
            "api_hash": api_hash,
            "language": language
        }
        
        # Send animation
        caption = "**• با توجه به ویدئو، کدی که از سمت تلگرام برای شما ارسال شده را با استفاده از دکمه زیر به اشتراک بگذارید.**"
        await app.send_animation(
            chat_id=user_id,
            animation="training.gif",
            caption=caption,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="اشتراک گذاری کد", switch_inline_query_current_chat="")]
            ])
        )
        
        # Update user step
        update_user_data(user_id, step=f'install_code-{phone}-{api_id}-{api_hash}-{language}')
        
        return True
        
    except errors.PhoneNumberInvalid:
        error_msg = "**• شماره تلفن نامعتبر است.**"
    except errors.PhoneNumberBanned:
        error_msg = "**• شماره تلفن مسدود شده است.**"
    except errors.PhoneNumberFlood:
        error_msg = "**• درحالت انتضار هستید، منتظر بمانید.**"
    except Exception as e:
        error_msg = f"**• خطا در نصب سلف:**\n```\n{str(e)[:200]}\n```"
    
    if message_id:
        await safe_edit_message(user_id, message_id, error_msg)
    
    return False

@performance_monitor
async def verify_code_and_login(user_id, phone, api_id, api_hash, code, language="fa"):
    """Verify code and login"""
    try:
        if user_id not in temp_Client:
            await app.send_message(user_id, "**• عملیات منقضی شده، مجدد مراحل نصب را انجام دهید.**")
            return False
        
        client_data = temp_Client[user_id]
        client = client_data["client"]
        phone_code_hash = client_data["phone_code_hash"]
        
        try:
            await client.sign_in(
                phone_number=phone,
                phone_code_hash=phone_code_hash,
                phone_code=code
            )
            
        except errors.SessionPasswordNeeded:
            await app.send_message(user_id,
                "**• لطفا رمز دومرحله ای اکانت را بدون هیچ کلمه یا کاراکتر اضافه ای ارسال کنید :**")
            
            update_user_data(user_id, step=f'install_2fa-{phone}-{api_id}-{api_hash}-{language}')
            return False
        
        await app.send_message(user_id, "**• ورود به اکانت با موفقیت انجام شد، درحال نصب نهایی سلف، لطفا صبور باشید.**")
        
        # Cleanup
        if client.is_connected:
            await client.disconnect()
        
        if user_id in temp_Client:
            del temp_Client[user_id]
        
        await asyncio.sleep(1)
        
        # Start self bot
        await start_self_bot(user_id, api_id, api_hash, None, language)
        return True
        
    except errors.PhoneCodeInvalid:
        await app.send_message(user_id, "**• کد وارد شده نامعتبر است، مجدد کد را وارد کنید.**")
    except errors.PhoneCodeExpired:
        await app.send_message(user_id, "**• کد موردنظر باطل شده بود، مجدد عملیات رو آغاز کنید.**")
    except Exception as e:
        await app.send_message(user_id, f"**• خطا در تایید کد:** {str(e)[:100]}")
    
    return False

async def verify_2fa_password(user_id, phone, api_id, api_hash, password, language="fa"):
    """Verify 2FA password"""
    try:
        client = Client(
            f"sessions/{user_id}",
            api_id=int(api_id),
            api_hash=api_hash
        )
        
        await client.connect()
        await client.check_password(password)
        await client.disconnect()
        
        await safe_edit_message(user_id, None, "**• ورود به اکانت با موفقیت انجام شد، درحال نصب نهایی سلف، لطفا صبور باشید.**")
        
        await start_self_bot(user_id, api_id, api_hash, None, language)
        return True
        
    except Exception as e:
        await app.send_message(user_id, "**• خطا در تایید رمز، با پشتیانی در ارتباط باشید.**")
        return False

@performance_monitor
async def start_self_bot(user_id, api_id, api_hash, message_id=None, language="fa"):
    """Start self bot process"""
    try:
        # Cleanup temp client
        async with lock:
            if user_id in temp_Client:
                try:
                    client_data = temp_Client[user_id]
                    if client_data["client"].is_connected:
                        await client_data["client"].disconnect()
                except:
                    pass
                finally:
                    if user_id in temp_Client:
                        del temp_Client[user_id]
        
        # Get user info
        user_info = get_user_data_cached(user_id)
        if not user_info:
            error_msg = "**• اطلاعات کاربر یافت نشد.**"
            if message_id:
                await safe_edit_message(user_id, message_id, error_msg)
            else:
                await app.send_message(user_id, error_msg)
            return False
        
        expir_days = user_info.get("expir", 0)
        phone_number = user_info.get("phone", "ندارد")
        
        # Get user info from Telegram
        try:
            tg_user = await app.get_users(user_id)
            first_name = html.escape(tg_user.first_name or "ندارد")
            username = f"@{tg_user.username}" if tg_user.username else "ندارد"
        except:
            first_name = "نامشخص"
            username = "ندارد"
        
        # Check user folder
        user_folder = f"selfs/self-{user_id}"
        if not os.path.isdir(user_folder):
            error_msg = "**• عملیات دچار مشکل شد!**"
            if message_id:
                await safe_edit_message(user_id, message_id, error_msg)
            else:
                await app.send_message(user_id, error_msg)
            return False
        
        # Check self.py file
        self_py_path = os.path.join(user_folder, "self.py")
        if not os.path.exists(self_py_path):
            error_msg = "**• فایل پیدا نشد، با پشتیبانی در ارتباط باشید.**"
            if message_id:
                await safe_edit_message(user_id, message_id, error_msg)
            else:
                await app.send_message(user_id, error_msg)
            return False
        
        # Cleanup locked files
        await cleanup_locked_files(user_id)
        
        # Start process
        log_file = os.path.join(user_folder, f"self_{user_id}_{int(time.time())}.log")
        
        process = await asyncio.create_subprocess_exec(
            "python3", "self.py", str(user_id), str(api_id), api_hash, Helper_ID,
            cwd=user_folder,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Wait for process to start
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except asyncio.TimeoutError:
            # Process is still running
            pass
        
        # Check if process is running
        if process.returncode is None:
            pid = process.pid
            
            # Update database
            update_user_data(user_id, self='active', pid=pid)
            add_admin(user_id)
            await setscheduler(user_id)
            
            # Send success message
            help_command = "راهنما" if language == "fa" else "HELP"
            success_message = f"""**• سلف شما نصب و روشن شد.
با دستور [ {help_command} ] میتونید راهنمای سلف رو دریافت کنید.

لطفا بعد نصب سلف حتما اگر رمز دومرحله ای فعال دارید اون رو عوض کنید و یا اکر رمز دومرحله ای روی اکانتتون فعال ندارید، فعال کنید و حواستون باشه فراموشش نکنید.

در صورتی که جوابی دریافت نمیکنید یک دقیقه صبر کنید و بعد دستور بدید، و اکر باز هم جوابی نگرفتید از منوی اصلی به بخش پشتیبانی مراجعه کنید و موضوع رو اطلاع بدید.**"""
            
            if message_id:
                await safe_edit_message(user_id, message_id, success_message)
            else:
                await app.send_message(user_id, success_message)
            
            # Send notification to admin
            await app.send_message(Admin, 
                f"**• خرید #اشتراک :\n• نام : [ {first_name} ]\n• یوزرنیم : [ {username} ]\n• آیدی عددی : [ `{user_id}` ]\n• شماره : [ `{phone_number}` ]\n• انقضا : [ `{expir_days}` ]\n• PID : [ `{pid}` ]\n• زبان : [ `{language}` ]\n ‌ ‌ ‌‌‌‌‌‌‌\n ‌ ‌ ‌**")
            
            return True
        else:
            error_msg = "**• عملیات کنسل شد، با پشتیبانی در ارتباط باشید.**"
            if message_id:
                await safe_edit_message(user_id, message_id, error_msg)
            else:
                await app.send_message(user_id, error_msg)
            return False
        
    except Exception as e:
        error_msg = f"**• عملیات کنسل شد، با پشتیبانی در ارتباط باشید.**"
        if message_id:
            await safe_edit_message(user_id, message_id, error_msg)
        else:
            await app.send_message(user_id, error_msg)
        return False

async def cleanup_locked_files(user_id):
    """Cleanup locked session files"""
    files_to_remove = [
        f"sessions/{user_id}.session-journal",
        f"sessions/{user_id}.session-wal",
        f"sessions/{user_id}.session-shm"
    ]
    
    for file_path in files_to_remove:
        if os.path.exists(file_path):
            try:
                await asyncio.to_thread(os.remove, file_path)
            except:
                pass

#==================== Bank Detection =====================#
def detect_bank(card_number):
    """Detect bank from card number"""
    bank_prefixes = {
        "627412": "اقتصاد نوین",
        "207177": "توسعه صادرات ایران",
        "627381": "انصار",
        "502229": "پاسارگاد",
        "505785": "ایران زمین",
        "502806": "شهر",
        "622106": "پارسیان",
        "502908": "توسعه تعاون",
        "639194": "پارسیان",
        "502910": "کارآفرین",
        "627884": "پارسیان",
        "502938": "دی",
        "639347": "پاسارگاد",
        "505416": "گردشگری",
        "636214": "آینده",
        "505801": "موسسه اعتباری کوثر (سپه)",
        "627353": "تجارت",
        "589210": "سپه",
        "589463": "رفاه کارگران",
        "627648": "توسعه صادرات ایران",
        "603769": "صادرات ایران",
        "603770": "کشاورزی",
        "636949": "حکمت ایرانیان (سپه)",
        "603799": "ملی ایران",
        "606373": "قرض الحسنه مهر ایران",
        "610433": "ملت",
        "621986": "سامان",
        "639607": "سرمایه",
        "639346": "سینا",
        "627488": "کارآفرین",
        "627961": "صنعت و معدن",
        "627760": "پست ایران",
        "639599": "قوامین",
        "628023": "مسکن",
        "628157": "موسسه اعتباری توسعه",
        "639217": "کشاورزی",
        "636795": "مرکزی",
        "639370": "مهر اقتصاد (سپه)",
        "991975": "ملت"
    }
    
    prefix = card_number[:6]
    return bank_prefixes.get(prefix, "نامشخص")

#==================== Keyboard Functions =====================#
def get_main_keyboard(user_id):
    """Get main menu keyboard"""
    user = get_user_data_cached(user_id)
    expir = user.get("expir", 0) if user else 0
    
    keyboard = [
        [InlineKeyboardButton(text="پشتیبانی 👨‍💻", callback_data="Support")],
        [InlineKeyboardButton(text="راهنما 🗒️", url=f"https://t.me/{Channel_Help}"),
         InlineKeyboardButton(text="دستیار چیست؟ 🧐", callback_data="WhatSelf")],
        [InlineKeyboardButton(text=f"انقضا : ( {expir} روز )", callback_data="ExpiryStatus")],
        [InlineKeyboardButton(text="خرید اشتراک 💵", callback_data="BuySub"),
         InlineKeyboardButton(text="احراز هویت ✔️", callback_data="AccVerify")]
    ]
    
    if expir > 0:
        keyboard.append(
            [InlineKeyboardButton(text="تمدید با کد 💶", callback_data="BuyCode")]
        )
    else:
        keyboard.append(
            [InlineKeyboardButton(text="خرید با کد 💶", callback_data="BuyCode")]
        )
    
    if str(user_id) == str(Admin) or helper_getdata("SELECT * FROM adminlist WHERE id = %s", (user_id,)):
        keyboard.append(
            [InlineKeyboardButton(text="مدیریت 🎈", callback_data="AdminPanel")]
        )
    
    keyboard.append(
        [InlineKeyboardButton(text="نرخ 💎", callback_data="Price")]
    )
    
    if expir > 0:
        user_folder = f"selfs/self-{user_id}"
        if os.path.isdir(user_folder):
            current_lang = get_current_language(user_id)
            lang_display = "فارسی 🇮🇷" if current_lang == "fa" else "انگلیسی 🇬🇧"
            
            keyboard.extend([
                [InlineKeyboardButton(text="ورود / نصب ⏏️", callback_data="InstallSelf"),
                 InlineKeyboardButton(text="تغییر زبان 🇬🇧", callback_data="ChangeLang")],
                [InlineKeyboardButton(text="وضعیت ⚙️", callback_data="SelfStatus")],
                [InlineKeyboardButton(text=f"زبان : ( {lang_display} )", callback_data="text")]
            ])
        else:
            keyboard.extend([
                [InlineKeyboardButton(text="ورود / نصب ⏏️", callback_data="InstallSelf"),
                 InlineKeyboardButton(text="وضعیت ⚙️", callback_data="SelfStatus")]
            ])
    
    keyboard.append(
        [InlineKeyboardButton(text="کانال ما 📢", url=f"https://t.me/{Channel_ID}")]
    )
    
    return InlineKeyboardMarkup(keyboard)

# Admin keyboards
AdminPanelKeyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton(text="آمار 📊", callback_data="AdminStats")],
    [InlineKeyboardButton(text="ارسال همگانی", callback_data="AdminBroadcast"),
     InlineKeyboardButton(text="فوروارد همگانی ✉️", callback_data="AdminForward")],
    [InlineKeyboardButton(text="بلاک کاربر 🚫", callback_data="AdminBlock"),
     InlineKeyboardButton(text="آنبلاک کاربر ✅️", callback_data="AdminUnblock")],
    [InlineKeyboardButton(text="افزودن انقضا ➕", callback_data="AdminAddExpiry"),
     InlineKeyboardButton(text="کسر انقضا ➖", callback_data="AdminDeductExpiry")],
    [InlineKeyboardButton(text="فعال کردن سلف 🔵", callback_data="AdminActivateSelf"),
     InlineKeyboardButton(text="غیرفعال کردن سلف 🔴", callback_data="AdminDeactivateSelf")],
    [InlineKeyboardButton(text="ساخت کد 🔑", callback_data="AdminCreateCode"),
     InlineKeyboardButton(text="لیست کدها 📋", callback_data="AdminListCodes")],
    [InlineKeyboardButton(text="حذف کد ❌", callback_data="AdminDeleteCode")],
    [InlineKeyboardButton(text="روشن کردن ربات 🔵", callback_data="AdminTurnOn"),
     InlineKeyboardButton(text="خاموش کردن ربات 🔴", callback_data="AdminTurnOff")],
    [InlineKeyboardButton(text="تنظیمات ⚙️", callback_data="AdminSettings")],
    [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
])

AdminSettingsKeyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton(text="تغییر متن استارت 📝", callback_data="EditStartMessage")],
    [InlineKeyboardButton(text="تغییر متن نرخ 💰", callback_data="EditPriceMessage")],
    [InlineKeyboardButton(text="تغییر متن سلف 🤖", callback_data="EditSelfMessage")],
    [InlineKeyboardButton(text="تغییر قیمت‌ها 📊", callback_data="EditPrices")],
    [InlineKeyboardButton(text="تغییر اطلاعات کارت 💳", callback_data="EditCardInfo")],
    [InlineKeyboardButton(text="محدودیت شماره 📱", callback_data="PhoneRestriction")],
    [InlineKeyboardButton(text="مشاهده تنظیمات 👁️", callback_data="ViewSettings")],
    [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")]
])

#==================== Message Handlers =====================#
@app.on_message(filters.private, group=-1)
@performance_monitor
async def update_user(c, m):
    """Update user in database"""
    user = get_user_data_cached(m.chat.id)
    if user is None:
        update_data("INSERT INTO user(id) VALUES(%s)", (m.chat.id,))
        cache_manager.delete(f"user_{m.chat.id}")

@app.on_inline_query()
@performance_monitor
async def inline_code_handler(client, inline_query):
    """Handle inline queries for code sharing"""
    query = inline_query.query.strip()
    user_id = inline_query.from_user.id
    
    if not query or not query.isdigit() or len(query) < 5:
        return
    
    user = get_user_data_cached(user_id)
    if not user or not user["step"].startswith("install_code-"):
        return
    
    code = query[:5]
    if len(code) != 5:
        return
    
    step_parts = user["step"].split("-")
    if len(step_parts) >= 4:
        phone = step_parts[1]
        api_id = step_parts[2]
        api_hash = step_parts[3]
        
        results = [
            InlineQueryResultArticle(
                title="دریافت کد",
                description=f"کد وارد شده شما : ( {code} )",
                id="1",
                input_message_content=InputTextMessageContent(
                    message_text=f"**تنظیم شد.**"
                )
            )
        ]
        
        await inline_query.answer(
            results=results,
            cache_time=0,
            is_personal=True
        )
        
        # Verify code
        await asyncio.sleep(0.5)
        await verify_code_and_login(user_id, phone, api_id, api_hash, code)

@app.on_message(filters.private & filters.command("start"))
@checker
@performance_monitor
async def start_handler(c, m):
    """Handle /start command"""
    chat_id = m.chat.id
    
    # Clear cache for this user
    cache_manager.delete(f"user_{chat_id}")
    
    # Get keyboard and message
    keyboard = get_main_keyboard(chat_id)
    user_link = f'<a href="tg://user?id={chat_id}">{html.escape(m.chat.first_name)}</a>'
    
    start_message_template = get_setting_cached("start_message") or "**سلام {user_link}، به ربات خوش آمدید.**"
    start_message = start_message_template.format(user_link=user_link)
    
    # Send message
    await app.send_message(chat_id, start_message, reply_markup=keyboard)
    
    # Update user
    update_user_data(chat_id, step='none')
    
    # Cleanup temp client
    async with lock:
        if chat_id in temp_Client:
            try:
                await temp_Client[chat_id]["client"].disconnect()
            except:
                pass
            del temp_Client[chat_id]
    
    # Cleanup session files
    journal_file = f"sessions/{chat_id}.session-journal"
    if os.path.isfile(journal_file):
        await asyncio.to_thread(os.remove, journal_file)

#==================== Callback Query Handler =====================#
@app.on_callback_query()
@checker
@performance_monitor
async def callback_handler(c, call):
    """Handle callback queries"""
    chat_id = call.from_user.id
    message_id = call.message.id
    data = call.data
    
    # Get user data with caching
    user = get_user_data_cached(chat_id)
    if not user:
        await call.answer("خطا در دریافت اطلاعات کاربر", show_alert=True)
        return
    
    # Handle different callback data
    handlers = {
        "Back": handle_back,
        "BuySub": handle_buy_sub,
        "Price": handle_price,
        "AccVerify": handle_acc_verify,
        "Support": handle_support,
        "WhatSelf": handle_whatself,
        "SelfStatus": handle_self_status,
        "ChangeLang": handle_change_lang,
        "InstallSelf": handle_install_self,
        "AdminPanel": handle_admin_panel,
        "AdminStats": handle_admin_stats,
        "AdminSettings": handle_admin_settings,
        "PhoneRestriction": handle_phone_restriction,
        "BuyCode": handle_buy_code,
        "ExpiryStatus": handle_expiry_status,
        "AdminCreateCode": handle_admin_create_code,
        "AdminListCodes": handle_admin_list_codes,
        "AdminDeleteCode": handle_admin_delete_code,
    }
    
    # Check for prefix handlers
    if data.startswith("SelectCardForPayment-"):
        await handle_select_card_payment(call, data)
    elif data.startswith("Sub-"):
        await handle_subscription(call, data)
    elif data.startswith("SelectCard-"):
        await handle_select_card(call, data)
    elif data.startswith("ConfirmDelete-"):
        await handle_confirm_delete(call, data)
    elif data.startswith("ConfirmLangChange-"):
        await handle_confirm_lang_change(call, data)
    elif data.startswith("DeleteCode-"):
        await handle_delete_code(call, data)
    elif data.startswith("SelectLanguage-"):
        await handle_select_language(call, data)
    elif data.startswith("AdminVerifyCard-"):
        await handle_admin_verify_card(call, data)
    elif data.startswith("AdminRejectCard-"):
        await handle_admin_reject_card(call, data)
    elif data.startswith("AdminIncompleteCard-"):
        await handle_admin_incomplete_card(call, data)
    elif data.startswith("AdminApprovePayment-"):
        await handle_admin_approve_payment(call, data)
    elif data.startswith("AdminRejectPayment-"):
        await handle_admin_reject_payment(call, data)
    elif data.startswith("AdminBlockPayment-"):
        await handle_admin_block_payment(call, data)
    elif data.startswith("Reply-"):
        await handle_reply(call, data)
    elif data.startswith("Block-"):
        await handle_block(call, data)
    elif data == "text":
        await call.answer("• دکمه نمایشی است •", show_alert=True)
    elif data in handlers:
        await handlers[data](call)
    else:
        await call.answer("دستور نامعتبر", show_alert=True)

#==================== Callback Handlers =====================#
async def handle_back(call):
    """Handle back button"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    keyboard = get_main_keyboard(chat_id)
    await app.edit_message_text(
        chat_id, 
        message_id,
        "**به منوی اصلی بازگشتید.**",
        reply_markup=keyboard
    )
    
    update_user_data(chat_id, step='none')
    
    # Cleanup temp client
    async with lock:
        if chat_id in temp_Client:
            del temp_Client[chat_id]

async def handle_buy_sub(call):
    """Handle buy subscription"""
    chat_id = call.from_user.id
    message_id = call.message.id
    user = get_user_data_cached(chat_id)
    
    if not user or not user.get("phone"):
        await app.delete_messages(chat_id, message_id)
        await app.send_message(
            chat_id,
            "**لطفا با استفاده از دکمه زیر شماره موبایل خود را به اشتراک بگذارید.**",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton(text="اشتراک گذاری شماره", request_contact=True)]],
                resize_keyboard=True
            )
        )
        update_user_data(chat_id, step='contact')
    else:
        user_cards = get_user_cards(chat_id)
        if user_cards:
            keyboard_buttons = []
            for card in user_cards:
                card_number = card["card_number"]
                masked_card = f"{card_number[:4]} - - - - - - {card_number[-4:]}"
                keyboard_buttons.append([
                    InlineKeyboardButton(text=masked_card, callback_data=f"SelectCardForPayment-{card['id']}")
                ])
            keyboard_buttons.append([InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")])
            
            await app.edit_message_text(
                chat_id, 
                message_id,
                "**• لطفا انتخاب کنید برای پرداخت از کدام کارت احراز شده ی خود میخواهید استفاده کنید.**",
                reply_markup=InlineKeyboardMarkup(keyboard_buttons)
            )
        else:
            await app.edit_message_text(
                chat_id, 
                message_id,
                "**• برای خرید باید ابتدا احراز هویت کنید.**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="احراز هویت ✔️", callback_data="AccVerify")]
                ])
            )
    
    update_user_data(chat_id, step='none')

async def handle_select_card_payment(call, data):
    """Handle card selection for payment"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    card_id = data.split("-")[1]
    card = get_card_by_id(card_id)
    
    if card:
        update_user_data(chat_id, step=f'select_subscription-{card_id}')
        
        prices = get_prices_cached()
        
        await app.edit_message_text(
            chat_id,
            message_id,
            "**• لطفا از گزینه های زیر انتخاب کنید میخواهید دستیار را برای چند ماه خریداری کنید:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text=f"(1) ماه معادل {prices['1month']} تومان", callback_data=f"Sub-30-{prices['1month']}")],
                [InlineKeyboardButton(text=f"(2) ماه معادل {prices['2month']} تومان", callback_data=f"Sub-60-{prices['2month']}")],
                [InlineKeyboardButton(text=f"(3) ماه معادل {prices['3month']} تومان", callback_data=f"Sub-90-{prices['3month']}")],
                [InlineKeyboardButton(text=f"(4) ماه معادل {prices['4month']} تومان", callback_data=f"Sub-120-{prices['4month']}")],
                [InlineKeyboardButton(text=f"(5) ماه معادل {prices['5month']} تومان", callback_data=f"Sub-150-{prices['5month']}")],
                [InlineKeyboardButton(text=f"(6) ماه معادل {prices['6month']} تومان", callback_data=f"Sub-180-{prices['6month']}")],
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="BuySub")]
            ])
        )

async def handle_subscription(call, data):
    """Handle subscription selection"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    params = data.split("-")
    expir_count = params[1]
    cost = params[2]
    
    user = get_user_data_cached(chat_id)
    step_parts = user["step"].split("-") if user and user.get("step") else []
    
    if len(step_parts) >= 2:
        card_id = step_parts[1]
        card = get_card_by_id(card_id)
        
        if card:
            card_number = card["card_number"]
            masked_card = f"{card_number[:4]} - - - - - - {card_number[-4:]}"
            
            bot_card_number = get_setting_cached("card_number") or CardNumber
            bot_card_name = get_setting_cached("card_name") or CardName
            
            await app.edit_message_text(
                chat_id,
                message_id,
                f"**• لطفا مبلغ ( `{cost}` تومان ) رو با کارتی که احراز هویت و انتخاب کردید یعنی [ `{card_number}` ] به کارت زیر واریز کنید و فیش واریز خود را همینجا ارسال کنید.\n\n[ `{bot_card_number}` ]\nبه نام : {bot_card_name}\n\n• ربات آماده دریافت فیش واریزی شماست :**"
            )
            
            update_user_data(chat_id, step=f'payment_receipt-{expir_count}-{cost}-{card_id}')

async def handle_price(call):
    """Handle price display"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    prices = get_prices_cached()
    price_message_template = get_setting_cached("price_message") or ""
    price_message = price_message_template.format(
        price_1month=prices["1month"],
        price_2month=prices["2month"],
        price_3month=prices["3month"],
        price_4month=prices["4month"],
        price_5month=prices["5month"],
        price_6month=prices["6month"]
    )
    
    await app.edit_message_text(
        chat_id,
        message_id,
        price_message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
        ])
    )
    
    update_user_data(chat_id, step='none')

async def handle_acc_verify(call):
    """Handle account verification"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    user_cards = get_user_cards(chat_id)
    
    if user_cards:
        cards_text = "**• به منوی احراز هویت خوش آمدید:\n\nکارت های احراز شده :**\n"
        for idx, card in enumerate(user_cards, 1):
            card_number = card["card_number"]
            bank_name = card["bank_name"] if card["bank_name"] else "نامشخص"
            masked_card = f"{card_number[:4]} - - - - - - {card_number[-4:]}"
            cards_text += f"**{idx} - {bank_name} [ `{card_number}` ] \n**"
        
        keyboard_buttons = [
            [InlineKeyboardButton(text="کارت جدید ➕", callback_data="AddNewCard"),
             InlineKeyboardButton(text="حذف کارت ➖", callback_data="DeleteCard")],
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
        ]
        
        await app.edit_message_text(
            chat_id,
            message_id,
            cards_text,
            reply_markup=InlineKeyboardMarkup(keyboard_buttons)
        )
    else:
        await app.edit_message_text(
            chat_id,
            message_id,
            "**• به منوی احراز هویت خوش آمدید ، لطفا انتخاب کنید:**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="➕ کارت جدید", callback_data="AddNewCard"),
                 InlineKeyboardButton(text="حذف کارت ➖", callback_data="DeleteCard")],
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )
    
    update_user_data(chat_id, step='none')

async def handle_whatself(call):
    """Handle what is self"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    whatself_message = get_setting_cached("whatself_message") or ""
    
    await app.edit_message_text(
        chat_id,
        message_id,
        whatself_message,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
        ])
    )
    
    update_user_data(chat_id, step='none')

async def handle_support(call):
    """Handle support"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    await app.edit_message_text(
        chat_id,
        message_id,
        "**• شما با موفقیت به پشتیبانی متصل شدید!\nلطفا دقت کنید که توی پشتیبانی اسپم ندید و از دستورات سلف توی پشتیبانی استفاده نکنید، اکنون میتوانید پیام خود را ارسال کنید.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="لغو اتصال 💥", callback_data="Back")]
        ])
    )
    
    update_user_data(chat_id, step='support')

async def handle_phone_restriction(call):
    """Handle phone restriction settings"""
    chat_id = call.from_user.id
    
    # Check admin access
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی ندارید", show_alert=True)
        return
    
    current_status = get_setting_cached("phone_restriction") or "enabled"
    status_text = "فعال ✔️" if current_status == "enabled" else "غیرفعال ✖️"
    
    await app.edit_message_text(
        chat_id,
        call.message.id,
        f"**• محدودیت شماره مجازی\n• وضعیت فعلی : ( {status_text} )\n\nدر صورت فعال بودن این بخش، فقط کاربران ایرانی میتوانند احراز هویت و سلف نصب کنند.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("فعال (✔️)", callback_data="EnablePhoneRestriction"),
             InlineKeyboardButton("غیرفعال (✖️)", callback_data="DisablePhoneRestriction")],
            [InlineKeyboardButton("(🔙) بازگشت", callback_data="AdminSettings")]
        ])
    )

async def handle_self_status(call):
    """Handle self status check"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    user = get_user_data_cached(chat_id)
    expir = user.get("expir", 0) if user else 0
    
    if expir <= 0:
        await call.answer("• شما انقضا ندارید •", show_alert=True)
        return
    
    user_folder = f"selfs/self-{chat_id}"
    if not os.path.isdir(user_folder):
        await app.edit_message_text(
            chat_id,
            message_id,
            "**• ربات دستیار شما نصب نشده است، ابتدا ربات را نصب کرده و در صورت ایجاد مشکل به این بخش مراجعه کنید.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="نصب سلف", callback_data="InstallSelf")],
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )
        return
    
    await app.edit_message_text(
        chat_id,
        message_id,
        "**• درخواست شما به سرور ارسال شد، لطفا کمی صبر کنید.**"
    )
    
    # Check status
    status_info = await check_self_status(chat_id)
    
    if status_info["status"] == "not_installed":
        await app.edit_message_text(
            chat_id,
            message_id,
            "**• ربات دستیار شما نصب نشده است، ابتدا ربات را نصب کرده و در صورت ایجاد مشکل به این بخش مراجعه کنید.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="نصب سلف", callback_data="InstallSelf")],
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )
    elif status_info["status"] == "error":
        await app.edit_message_text(
            chat_id,
            message_id,
            f"**• خطا در بررسی وضعیت سلف.**\n\n{status_info['message']}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )
    elif status_info["status"] == "inactive":
        await app.edit_message_text(
            chat_id,
            message_id,
            "**• ربات دستیار شما نصب نشده است، ابتدا ربات را نصب کرده و در صورت ایجاد مشکل به این بخش مراجعه کنید.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="نصب سلف", callback_data="InstallSelf")],
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )
    else:
        status_message = f"**درخواست شما با موفقیت انجام شد.**\n\n**نتیجه:** {status_info['message']}\n\n"
        
        if status_info["language"]:
            status_message += f"**توجه: دستیار شما روی زبان {status_info['language']} تنظیم شده و فقط به دستورات با این زبان پاسخ خواهد داد.**"
        
        await app.edit_message_text(
            chat_id,
            message_id,
            status_message,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )

async def handle_change_lang(call):
    """Handle language change"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    user = get_user_data_cached(chat_id)
    expir = user.get("expir", 0) if user else 0
    
    if expir <= 0:
        await call.answer("• شما انقضا ندارید •", show_alert=True)
        return
    
    can_change, remaining = can_change_language(chat_id)
    
    if not can_change:
        await app.edit_message_text(
            chat_id,
            message_id,
            f"**• تغییر زبان دستیار شما تا {remaining} دقیقه دیگر امکان پذیر نیست.**"
        )
        return
    
    current_lang = get_current_language(chat_id)
    next_lang = "en" if current_lang == "fa" else "fa"
    next_lang_display = "انگلیسی 🇬🇧" if next_lang == "en" else "فارسی 🇮🇷"
    current_lang_display = "فارسی 🇮🇷" if current_lang == "fa" else "انگلیسی 🇬🇧"
    
    await app.edit_message_text(
        chat_id,
        message_id,
        f"**• آیا میخواهید زبان دستیار شما از ( {current_lang_display} ) به ( {next_lang_display} ) تنظیم شود؟**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="بله ✔️", callback_data=f"ConfirmLangChange-{next_lang}"),
             InlineKeyboardButton(text="خیر ✖️", callback_data="Back")]
        ])
    )

async def handle_confirm_lang_change(call, data):
    """Confirm language change"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    target_lang = data.split("-")[1]
    
    success, result = await change_self_language(chat_id, target_lang)
    
    if success:
        new_lang_display = "فارسی 🇮🇷" if target_lang == "fa" else "انگلیسی 🇬🇧"
        
        await app.edit_message_text(
            chat_id,
            message_id,
            f"**• زبان دستیار شما روی ( {new_lang_display} ) تنظیم شد.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )
        
        # Restart self bot
        user_data = get_user_data_cached(chat_id)
        pid = user_data.get("pid") if user_data else None
        
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                await asyncio.sleep(2)
                
                try:
                    os.kill(pid, 0)
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
                    
            except Exception:
                pass
    else:
        await app.edit_message_text(
            chat_id,
            message_id,
            f"**• عملیات کنسل شد، با پشتیبانی در ارتباط باشید.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
            ])
        )

async def handle_admin_create_code(call):
    """Admin create code"""
    chat_id = call.from_user.id
    
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی ندارید", show_alert=True)
        return
    
    await app.edit_message_text(
        chat_id,
        call.message.id,
        "**لطفا تعداد روز انقضای کد را وارد کنید:**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")]
        ])
    )
    
    update_user_data(chat_id, step='admin_create_code_days')

async def handle_admin_list_codes(call):
    """Admin list codes"""
    chat_id = call.from_user.id
    
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی ندارید", show_alert=True)
        return
    
    cleanup_inactive_codes()
    codes = get_active_codes()
    
    if codes:
        codes_text = "**• لیست کدهای فعال :\n\n"
        for idx, code in enumerate(codes, 1):
            codes_text += f"**{idx} - کد : ( `{code['code']}` )**\n"
            codes_text += f"**• روزهای انقضا : ( {code['days']} روز )**\n"
            codes_text += f"**• تاریخ ایجاد : ( {code['created_at']} )**\n\n"
        
        await app.edit_message_text(
            chat_id,
            call.message.id,
            codes_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")]
            ])
        )
    else:
        await app.edit_message_text(
            chat_id,
            call.message.id,
            "**هیچ کد فعالی وجود ندارد.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")]
            ])
        )

async def handle_admin_delete_code(call):
    """Admin delete code"""
    chat_id = call.from_user.id
    
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی ندارید", show_alert=True)
        return
    
    codes = get_active_codes()
    
    if codes:
        keyboard_buttons = []
        for code in codes:
            keyboard_buttons.append([
                InlineKeyboardButton(text=f"• {code['code']}", callback_data=f"DeleteCode-{code['id']}")
            ])
        keyboard_buttons.append([InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")])
        
        await app.edit_message_text(
            chat_id,
            call.message.id,
            "**لطفا کدی که می خواهید حذف کنید را انتخاب کنید:**",
            reply_markup=InlineKeyboardMarkup(keyboard_buttons)
        )
    else:
        await call.answer("• کد فعالی وجود ندارد •", show_alert=True)

async def handle_delete_code(call, data):
    """Delete code"""
    chat_id = call.from_user.id
    
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی ندارید", show_alert=True)
        return
    
    code_id = data.split("-")[1]
    delete_code(code_id)
    
    await app.edit_message_text(
        chat_id,
        call.message.id,
        "**کد با موفقیت حذف شد.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminListCodes")]
        ])
    )

async def handle_buy_code(call):
    """Buy with code"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    await app.edit_message_text(
        chat_id,
        message_id,
        "**• لطفا کد انقضای خریداری شده خود را ارسال کنید:**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="Back")]
        ])
    )
    
    update_user_data(chat_id, step='use_code')

async def handle_admin_settings(call):
    """Admin settings"""
    chat_id = call.from_user.id
    
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی ندارید", show_alert=True)
        return
    
    await app.edit_message_text(
        chat_id,
        call.message.id,
        "**مدیر گرامی، به بخش تنظیمات خوش آمدید.\nلطفا گزینه مورد نظر را انتخاب کنید:**",
        reply_markup=AdminSettingsKeyboard
    )
    
    update_user_data(chat_id, step='none')

async def handle_install_self(call):
    """Install self"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    user = get_user_data_cached(chat_id)
    expir = user.get("expir", 0) if user else 0
    
    if expir <= 0:
        await app.send_message(chat_id, "**شما انقضا ندارید.**")
        return
    
    user_info = get_user_data_cached(chat_id)
    
    if user_info and user_info.get("phone") and user_info.get("api_id") and user_info.get("api_hash"):
        api_hash = user_info["api_hash"]
        masked_hash = f"{api_hash[:4]}{'*' * (len(api_hash)-8)}{api_hash[-4:]}" if len(api_hash) >= 8 else "****"
        
        await app.edit_message_text(
            chat_id,
            message_id,
            f"**📞 Number : `{user_info['phone']}`\n🆔 Api ID : `{user_info['api_id']}`\n🆔 Api Hash : `{masked_hash}`\n\n• آیا اطلاعات را تایید میکنید؟**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("بله (✅)", callback_data="ConfirmInstall"),
                 InlineKeyboardButton("خیر (❎)", callback_data="ChangeInfo")],
                [InlineKeyboardButton("(🔙) بازگشت", callback_data="Back")]
            ])
        )
    else:
        await app.edit_message_text(
            chat_id,
            message_id,
            "**برای نصب سلف، لطفا شماره تلفن خود را با دکمه زیر به اشتراک بگذارید:**",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton(text="اشتراک گذاری شماره", request_contact=True)]],
                resize_keyboard=True
            )
        )
        update_user_data(chat_id, step='install_phone')

async def handle_select_card(call, data):
    """Handle card selection for deletion"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    card_id = data.split("-")[1]
    card = get_card_by_id(card_id)
    
    if card:
        card_number = card["card_number"]
        masked_card = f"{card_number[:4]} - - - - - - {card_number[-4:]}"
        
        await app.edit_message_text(
            chat_id,
            message_id,
            f"**• آیا مطمئن هستید که میخواهید کارت [ `{masked_card}` ] را حذف کنید؟**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="بله", callback_data=f"ConfirmDelete-{card_id}"),
                 InlineKeyboardButton(text="خیر", callback_data="AccVerify")]
            ])
        )

async def handle_confirm_delete(call, data):
    """Confirm card deletion"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    card_id = data.split("-")[1]
    card = get_card_by_id(card_id)
    
    if card:
        card_number = card["card_number"]
        bank_name = card["bank_name"] if card["bank_name"] else "نامشخص"
        masked_card = f"{card_number[:4]} - - - - - - {card_number[-4:]}"
        
        delete_card(card_id)
        
        await app.edit_message_text(
            chat_id,
            message_id,
            f"**• کارت ( `{bank_name}` - `{card_number}` ) با موفقیت حذف شد.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AccVerify")]
            ])
        )

async def handle_select_language(call, data):
    """Select language for installation"""
    chat_id = call.from_user.id
    message_id = call.message.id
    
    target_language = data.split("-")[1]
    user = get_user_data_cached(chat_id)
    
    if user and user.get("step", "").startswith("select_language-"):
        parts = user["step"].split("-", 1)
        if len(parts) > 1:
            remaining_parts = parts[1]
            update_user_data(chat_id, step=f'install_with_language-{remaining_parts}-{target_language}')
            
            remaining_parts_parts = remaining_parts.split("-")
            if len(remaining_parts_parts) >= 3:
                phone = remaining_parts_parts[0]
                api_id = remaining_parts_parts[1]
                api_hash = remaining_parts_parts[2]
                
                await app.edit_message_text(chat_id, message_id, "**• درحال ساخت سلف، لطفا صبور باشید.**")
                await start_self_installation(chat_id, phone, api_id, api_hash, message_id, target_language)

async def handle_expiry_status(call):
    """Show expiry status"""
    user = get_user_data_cached(call.from_user.id)
    expir = user.get("expir", 0) if user else 0
    await call.answer(f"انقضای شما : ( {expir} روز )", show_alert=True)

async def handle_admin_panel(call):
    """Admin panel"""
    chat_id = call.from_user.id
    
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی به بخش مدیریت ندارید.", show_alert=True)
        return
    
    await app.edit_message_text(
        chat_id,
        call.message.id,
        "**مدیر گرامی، به پنل ربات سلف ساز تلگرام خوش آمدید.\nاکنون ربات کاملا در اختیار شماست، در صورتی که آشنایی با پنل مدیریت یا کارکرد ربات ندارید، بخش « راهنما » را بخوانید.**",
        reply_markup=AdminPanelKeyboard
    )
    
    update_user_data(chat_id, step='none')
    
    # Cleanup temp client
    async with lock:
        if chat_id in temp_Client:
            del temp_Client[chat_id]

async def handle_admin_stats(call):
    """Admin stats"""
    chat_id = call.from_user.id
    
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        await call.answer("شما دسترسی ندارید", show_alert=True)
        return
    
    try:
        botinfo = await app.get_me()
        allusers = get_datas("SELECT COUNT(id) as count FROM user")[0]["count"]
        allblocks = get_datas("SELECT COUNT(id) as count FROM block")[0]["count"]
        pending_cards = len(get_pending_cards())
        
        stats_text = f"""
        • تعداد کل کاربران ربات : **[ {allusers} ]**
        • تعداد کاربران بلاک شده :  **[ {allblocks} ]**
        • تعداد کارت های در انتضار تایید : **[ {pending_cards} ]**
        
        • نام ربات : **( {botinfo.first_name} )**
        • آیدی عددی ربات : **( `{botinfo.id}` )**
        • آیدی ربات : **( @{botinfo.username} )**
        """
        
        await app.edit_message_text(
            chat_id,
            call.message.id,
            stats_text,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")]
            ])
        )
    except Exception as e:
        await call.answer(f"خطا در دریافت آمار: {e}", show_alert=True)

async def handle_admin_verify_card(call, data):
    """Admin verify card"""
    params = data.split("-")
    user_id = int(params[1])
    card_number = params[2]
    
    bank_name = detect_bank(card_number)
    card = get_card_by_number(user_id, card_number)
    
    if card:
        update_card_status(card["id"], "verified", bank_name)
    
    try:
        user_info = await app.get_users(user_id)
        username = f"@{user_info.username}" if user_info.username else "ندارد"
        
        await app.edit_message_text(
            call.message.chat.id,
            call.message.id,
            f"""**• درخواست احراز هویت از طرف ( {html.escape(user_info.first_name)} - {username} - {user_id} )
• شماره کارت : [ {card_number} ]

به دستور ( {call.from_user.id} ) تایید شد.**"""
        )
        
        await app.send_message(
            user_id,
            f"**• درخواست احراز هویت کارت ( `{card_number}` ) تایید شد.\nشما هم اکنون میتوانید از بخش خرید / تمدید اشتراک ، خرید خود را انجام دهید.**"
        )
    except Exception as e:
        print(f"Error verifying card: {e}")

async def handle_admin_reject_card(call, data):
    """Admin reject card"""
    params = data.split("-")
    user_id = int(params[1])
    card_number = params[2]
    
    card = get_card_by_number(user_id, card_number)
    if card:
        update_card_status(card["id"], "rejected")
    
    try:
        user_info = await app.get_users(user_id)
        username = f"@{user_info.username}" if user_info.username else "ندارد"
        
        await app.edit_message_text(
            call.message.chat.id,
            call.message.id,
            f"""**• درخواست احراز هویت از طرف ( {html.escape(user_info.first_name)} - {username} - {user_id} )
• شماره کارت : [ {card_number} ]

به دستور ( {call.from_user.id} ) رد شد.**"""
        )
        
        await app.send_message(
            user_id,
            f"**• درخواست احراز هویت کارت ( {card_number} ) به دلیل اشتباه بودن، رد شد.\nشما میتوانید مجددا برای احراز هویت با رعایت شرایط، درخواست دهید.**"
        )
    except Exception as e:
        print(f"Error rejecting card: {e}")

async def handle_admin_incomplete_card(call, data):
    """Admin reject incomplete card"""
    params = data.split("-")
    user_id = int(params[1])
    card_number = params[2]
    
    card = get_card_by_number(user_id, card_number)
    if card:
        update_card_status(card["id"], "rejected")
    
    try:
        user_info = await app.get_users(user_id)
        username = f"@{user_info.username}" if user_info.username else "ندارد"
        
        await app.edit_message_text(
            call.message.chat.id,
            call.message.id,
            f"""**• درخواست احراز هویت از طرف ( {html.escape(user_info.first_name)} - {username} - {user_id} )
• شماره کارت : [ {card_number} ]

به دستور ( {call.from_user.id} ) رد شد.**"""
        )
        
        await app.send_message(
            user_id,
            f"**• درخواست احراز هویت کارت ( {card_number} ) به دلیل ناقص بودن ، رد شد.\nشما میتوانید مجددا برای احراز هویت با رعایت شرایط، درخواست دهید.**"
        )
    except Exception as e:
        print(f"Error rejecting incomplete card: {e}")

# Add other admin handlers similarly...

#==================== Message Handler =====================#
@app.on_message(filters.private)
@checker
@performance_monitor
async def message_handler(c, m):
    """Handle private messages"""
    chat_id = m.chat.id
    user = get_user_data_cached(chat_id)
    
    if not user:
        return
    
    step = user.get("step", "none")
    text = m.text or ""
    
    # Handle different steps
    if step == "card_photo":
        await handle_card_photo(m, chat_id)
    elif step.startswith("card_number-"):
        await handle_card_number(m, chat_id, step, text)
    elif step.startswith("payment_receipt-"):
        await handle_payment_receipt(m, chat_id, step)
    elif step == "support":
        await handle_support_message(m, chat_id)
    elif step == "install_phone":
        await handle_install_phone(m, chat_id)
    elif step == "install_api_id":
        await handle_install_api_id(m, chat_id, text)
    elif step == "install_api_hash":
        await handle_install_api_hash(m, chat_id, text)
    elif step.startswith("install_code-"):
        await handle_install_code(m, chat_id, step, text)
    elif step.startswith("install_2fa-"):
        await handle_install_2fa(m, chat_id, step, text)
    elif step == "admin_create_code_days":
        await handle_admin_create_code_days(m, chat_id, text)
    elif step == "use_code":
        await handle_use_code(m, chat_id, text)
    elif step == "edit_start_message":
        await handle_edit_start_message(m, chat_id, text)
    elif step == "edit_price_message":
        await handle_edit_price_message(m, chat_id, text)
    elif step == "edit_self_message":
        await handle_edit_self_message(m, chat_id, text)
    elif step == "edit_all_prices":
        await handle_edit_all_prices(m, chat_id, text)
    elif step == "edit_card_number":
        await handle_edit_card_number(m, chat_id, text)
    elif step == "edit_card_name":
        await handle_edit_card_name(m, chat_id, text)
    elif step.startswith("ureply-"):
        await handle_ureply(m, chat_id, step)
    # Add other step handlers...

async def handle_card_photo(m, chat_id):
    """Handle card photo upload"""
    if m.photo:
        photo_path = await m.download(file_name=f"cards/{chat_id}_{int(time.time())}.jpg")
        update_user_data(chat_id, step=f'card_number-{photo_path}-{m.id}')
        
        await app.send_message(
            chat_id,
            "**• لطفا شماره کارت خود را به صورت اعداد انگلیسی ارسال کنید.\nدر صورتی که منصرف شدید ربات را مجدد [ /start ] کنید.**"
        )
    else:
        await app.send_message(chat_id, "**• فقط ارسال عکس مجاز است.**")

async def handle_card_number(m, chat_id, step, text):
    """Handle card number input"""
    if text and text.isdigit() and len(text) == 16:
        parts = step.split("-", 2)
        photo_path = parts[1]
        photo_message_id = parts[2] if len(parts) > 2 else None
        
        card_number = text.strip()
        add_card(chat_id, card_number)
        
        # Send to admin
        try:
            if photo_message_id:
                forwarded_photo_msg = await app.forward_messages(
                    from_chat_id=chat_id,
                    chat_id=Admin,
                    message_ids=int(photo_message_id)
                )
                
                await app.send_message(
                    Admin,
                    f"""**• درخواست احراز هویت از طرف ( {html.escape(m.chat.first_name)} - @{m.from_user.username if m.from_user.username else 'ندارد'} - {m.chat.id} )
شماره کارت : [ {card_number} ]**""",
                    reply_to_message_id=forwarded_photo_msg.id,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton(text="تایید (✅)", callback_data=f"AdminVerifyCard-{chat_id}-{card_number}")],
                        [InlineKeyboardButton(text="اشتباه (❌)", callback_data=f"AdminRejectCard-{chat_id}-{card_number}"),
                         InlineKeyboardButton(text="کامل نیست (❌)", callback_data=f"AdminIncompleteCard-{chat_id}-{card_number}")]
                    ])
                )
        except Exception as e:
            print(f"Error sending to admin: {e}")
        
        await app.send_message(
            chat_id,
            """**• درخواست احراز هویت شما برای پشتیبانی ارسال شد و در اولین فرصت تایید خواهد شد ، لطفا صبور باشید.**"""
        )
        
        update_user_data(chat_id, step='none')
    else:
        await app.send_message(
            chat_id,
            "**شماره کارت باید 16 رقم باشد.\n• در صورتی که منصرف شدید ربات رو مجددا [ /start ] کنید.**"
        )

async def handle_payment_receipt(m, chat_id, step):
    """Handle payment receipt"""
    if m.photo:
        params = step.split("-")
        expir_count = params[1]
        cost = params[2]
        card_id = params[3]
        
        card = get_card_by_id(card_id)
        card_number = card["card_number"] if card else "نامشخص"
        
        # Forward to admin
        mess = await app.forward_messages(from_chat_id=chat_id, chat_id=Admin, message_ids=m.id)
        
        transaction_id = str(int(time.time()))[-11:]
        
        await app.send_message(
            Admin,
            f"""**• درخواست خرید اشتراک از طرف ( {html.escape(m.chat.first_name)} - @{m.from_user.username if m.from_user.username else 'ندارد'} - {m.chat.id} )
اشتراک انتخاب شده : ( `{cost} تومان - {expir_count} روز` )
کارت خرید : ( `{card_number}` )**""",
            reply_to_message_id=mess.id,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="تایید (✅)", callback_data=f"AdminApprovePayment-{chat_id}-{expir_count}-{cost}-{transaction_id}")],
                [InlineKeyboardButton(text="مسدود (❌)", callback_data=f"AdminBlockPayment-{chat_id}"),
                 InlineKeyboardButton(text="رد (❌)", callback_data=f"AdminRejectPayment-{chat_id}-{transaction_id}")]
            ])
        )
        
        await app.send_message(
            chat_id,
            f"""**فیش واریزی شما ارسال شد.
• شناسه تراکنش: [ `{transaction_id}` ]
منتظر تایید فیش توسط مدیر باشید.**"""
        )
        
        update_user_data(chat_id, step='none')
    else:
        await app.send_message(chat_id, "**فقط عکس فیش واریزی را ارسال کنید.**")

async def handle_support_message(m, chat_id):
    """Handle support message"""
    mess = await app.forward_messages(from_chat_id=chat_id, chat_id=Admin, message_ids=m.id)
    
    username = f"@{m.from_user.username}" if m.from_user.username else "وجود ندارد"
    
    await app.send_message(
        Admin,
        f"""**• پیام جدید از طرف ( {html.escape(m.chat.first_name)} - `{m.chat.id}` - {username} )**""",
        reply_to_message_id=mess.id,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("پاسخ (✅)", callback_data=f"Reply-{m.chat.id}"),
             InlineKeyboardButton("مسدود (❌)", callback_data=f"Block-{m.chat.id}")]
        ])
    )
    
    await app.send_message(
        chat_id,
        "**• پیام شما به پشتیبانی ارسال شد.\nلطفا در بخش پشتیبانی اسپم نکنید و از دستورات استفاده نکنید به پیام شما در اسرع وقت پاسخ داده خواهد شد.**",
        reply_to_message_id=m.id
    )

async def handle_install_phone(m, chat_id):
    """Handle phone installation"""
    if m.contact:
        phone_number = str(m.contact.phone_number)
        if not phone_number.startswith("+"):
            phone_number = f"+{phone_number}"
        
        update_user_data(chat_id, phone=phone_number, step='install_api_id')
        
        Create = f'<a href=https://t.me/{api_channel}>کلیک کنید!</a>'
        await app.send_message(
            chat_id,
            "**• لطفا `Api ID` خود را وارد کنید. ( نمونه : 123456 )**\n• آموزش ساخت : ( {Create} )\n\n**• لغو عملیات [ /start ]**"
        )
    else:
        await app.send_message(chat_id, "**لطفا با استفاده از دکمه، شماره تلفن را به اشتراک بگذارید.**")

async def handle_install_api_id(m, chat_id, text):
    """Handle API ID installation"""
    if text and text.isdigit():
        update_user_data(chat_id, api_id=text, step='install_api_hash')
        await app.send_message(
            chat_id,
            f"**• لطفا `Api Hash` خود را وارد کنید.\n( مثال : abcdefg0123456abcdefg123456789c )\n\n• لغو عملیات [ /start ]**"
        )
    else:
        await app.send_message(chat_id, "**• لطفا یک Api ID معتبر وارد کنید.**")

async def handle_install_api_hash(m, chat_id, text):
    """Handle API Hash installation"""
    if text and len(text) == 32:
        update_user_data(chat_id, api_hash=text, step='none')
        
        user_info = get_user_data_cached(chat_id)
        api_hash = user_info["api_hash"]
        masked_hash = f"{api_hash[:4]}{'*' * (len(api_hash)-8)}{api_hash[-4:]}" if len(api_hash) >= 8 else "****"
        
        await app.send_message(
            chat_id,
            f"**📞 Number : `{user_info['phone']}`\n🆔 Api ID : `{user_info['api_id']}`\n🆔 Api Hash : `{masked_hash}`\n\n• آیا اطلاعات را تایید میکنید؟**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("بله (✅)", callback_data="ConfirmInstall"),
                 InlineKeyboardButton("خیر (❎)", callback_data="ChangeInfo")],
                [InlineKeyboardButton("(🔙) بازگشت", callback_data="Back")]
            ])
        )
    else:
        await app.send_message(chat_id, "**لطفا یک Api Hash معتبر وارد کنید.**")

async def handle_install_code(m, chat_id, step, text):
    """Handle install code"""
    parts = step.split("-")
    phone = parts[1]
    api_id = parts[2]
    api_hash = parts[3]
    language = parts[4] if len(parts) > 4 else "fa"
    
    if text:
        code = text.replace(".", "")
        
        if code.isdigit() and len(code) == 5:
            await verify_code_and_login(chat_id, phone, api_id, api_hash, code, language)
        else:
            await app.send_message(chat_id, "**• کد وارد شده نامعتبر است، مجدد کد را وارد کنید.**")
    else:
        await app.send_message(chat_id, "**لطفا کد تأیید را ارسال کنید.**")

async def handle_install_2fa(m, chat_id, step, text):
    """Handle 2FA installation"""
    parts = step.split("-")
    phone = parts[1]
    api_id = parts[2]
    api_hash = parts[3]
    language = parts[4] if len(parts) > 4 else "fa"
    
    if text:
        await verify_2fa_password(chat_id, phone, api_id, api_hash, text, language)
    else:
        await app.send_message(chat_id, "**• لطفا رمز دومرحله ای اکانت را بدون هیچ کلمه یا کاراکتر اضافه ای ارسال کنید :**")

async def handle_admin_create_code_days(m, chat_id, text):
    """Handle admin create code days"""
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        return
    
    if text.isdigit():
        days = int(text.strip())
        code = create_code(days)
        
        await app.send_message(
            chat_id,
            f"**• کد انقضا با موفقیت ایجاد شد.**\n\n"
            f"**• کد : ( `{code}` )**\n"
            f"**• تعداد روز : ( {days} روز )**\n\n"
            f"**• تاریخ ثبت : ( `{time.strftime('%Y-%m-%d %H:%M:%S')}` )**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")]
            ])
        )
        
        update_user_data(chat_id, step='none')
    else:
        await app.send_message(chat_id, "**لطفا یک عدد معتبر وارد کنید.**")

async def handle_use_code(m, chat_id, text):
    """Handle using code"""
    code_value = text.strip().upper()
    code_data = get_code_by_value(code_value)
    
    if code_data:
        user_data = get_user_data_cached(chat_id)
        old_expir = user_data.get("expir", 0) if user_data else 0
        new_expir = old_expir + code_data["days"]
        
        update_user_data(chat_id, expir=new_expir)
        use_code(code_value, chat_id)
        
        # Clear cache
        cache_manager.delete(f"user_{chat_id}")
        
        days = code_data["days"]
        month_texts = {
            30: "یک ماه",
            60: "دو ماه",
            90: "سه ماه",
            120: "چهار ماه",
            150: "پنج ماه",
            180: "شش ماه"
        }
        month_text = month_texts.get(days, f"{days} روز")
        
        message_to_user = f"""**• افزایش انقضا با موفقیت انجام شد.**

**• کد شارژ استفاده شده : ( `{code_value}` )**
**• انقضای سلف شما {month_text} اضافه گردید.**

**• انقضای قبلی شما : ( `{old_expir}` روز )**

**• انقضای جدید : ( `{new_expir}` روز )**"""
        
        await app.send_message(chat_id, message_to_user)
        
        # Notify admin
        try:
            user_info = await app.get_users(chat_id)
            username = f"@{user_info.username}" if user_info.username else "ندارد"
            
            message_to_admin = f"**کاربر ( {html.escape(user_info.first_name)} - {username} - {chat_id} ) با استفاده از کد `{code_value}` مقدار {month_text} انقضا خریداری کرد و این کد از لیست کدها حذف شد.**"
            await app.send_message(Admin, message_to_admin)
        except:
            pass
        
        update_user_data(chat_id, step='none')
    else:
        await app.send_message(chat_id, "**کد ارسالی صحیح نیست.**")

async def handle_edit_start_message(m, chat_id, text):
    """Handle edit start message"""
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        return
    
    update_setting("start_message", text)
    await app.send_message(
        chat_id,
        "**✅ متن پیام استارت با موفقیت به‌روزرسانی شد.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
        ])
    )
    
    update_user_data(chat_id, step='none')

async def handle_edit_price_message(m, chat_id, text):
    """Handle edit price message"""
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        return
    
    update_setting("price_message", text)
    await app.send_message(
        chat_id,
        "**✅ متن پیام نرخ با موفقیت به‌روزرسانی شد.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
        ])
    )
    
    update_user_data(chat_id, step='none')

async def handle_edit_self_message(m, chat_id, text):
    """Handle edit self message"""
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        return
    
    update_setting("whatself_message", text)
    await app.send_message(
        chat_id,
        "**✅ متن توضیح سلف با موفقیت به‌روزرسانی شد.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
        ])
    )
    
    update_user_data(chat_id, step='none')

async def handle_edit_all_prices(m, chat_id, text):
    """Handle edit all prices"""
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        return
    
    lines = text.strip().split('\n')
    
    if len(lines) != 6:
        await app.send_message(
            chat_id,
            "**خطا: باید دقیقا 6 قیمت (هر قیمت در یک خط) وارد کنید.**\n\n**فرمت صحیح:**\n```\nقیمت 1 ماهه\nقیمت 2 ماهه\nقیمت 3 ماهه\nقیمت 4 ماهه\nقیمت 5 ماهه\nقیمت 6 ماهه\n```",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
            ])
        )
        return
    
    price_keys = ['1month', '2month', '3month', '4month', '5month', '6month']
    price_names = {
        '1month': '1 ماهه',
        '2month': '2 ماهه', 
        '3month': '3 ماهه',
        '4month': '4 ماهه',
        '5month': '5 ماهه',
        '6month': '6 ماهه'
    }
    
    # Validate prices
    valid_prices = []
    for i, line in enumerate(lines):
        price_text = line.strip()
        if price_text.isdigit():
            valid_prices.append((price_keys[i], price_text))
        else:
            await app.send_message(
                chat_id,
                f"**خطا: قیمت {price_names[price_keys[i]]} باید عدد باشد: {price_text}**",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
                ])
            )
            update_user_data(chat_id, step='none')
            return
    
    # Update prices
    success_text = "**✅ قیمت‌ها با موفقیت به‌روزرسانی شد:**\n\n"
    for key, price in valid_prices:
        update_setting(f"price_{key}", price)
        success_text += f"**{price_names[key]}:** {price} تومان\n"
    
    success_text += "\n**تغییرات ذخیره شدند.**"
    
    await app.send_message(
        chat_id,
        success_text,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
        ])
    )
    
    # Clear cache
    get_prices_cached.cache_clear()
    update_user_data(chat_id, step='none')

async def handle_edit_card_number(m, chat_id, text):
    """Handle edit card number"""
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        return
    
    cleaned_text = text.replace(" ", "")
    if cleaned_text.isdigit() and len(cleaned_text) >= 16:
        update_setting("card_number", cleaned_text)
        await app.send_message(
            chat_id,
            f"**✅ شماره کارت با موفقیت به `{cleaned_text}` به‌روزرسانی شد.**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
            ])
        )
        update_user_data(chat_id, step='none')
    else:
        await app.send_message(chat_id, "**شماره کارت نامعتبر است. لطفا یک شماره کارت معتبر وارد کنید.**")

async def handle_edit_card_name(m, chat_id, text):
    """Handle edit card name"""
    if chat_id != Admin and not helper_getdata("SELECT * FROM adminlist WHERE id = %s", (chat_id,)):
        return
    
    update_setting("card_name", text)
    await app.send_message(
        chat_id,
        f"**✅ نام صاحب کارت با موفقیت به `{text}` به‌روزرسانی شد.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminSettings")]
        ])
    )
    update_user_data(chat_id, step='none')

async def handle_ureply(m, chat_id, step):
    """Handle admin reply to user"""
    user_id = int(step.split("-")[1])
    
    mess = await app.copy_message(from_chat_id=Admin, chat_id=user_id, message_id=m.id)
    
    await app.send_message(
        user_id,
        "**• کاربر گرامی، پاسخ شما از پشتیبانی دریافت شد.**",
        reply_to_message_id=mess.id
    )
    
    await app.send_message(
        Admin,
        "**• پیام شما برای کاربر ارسال شد.**",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(text="(🔙) بازگشت", callback_data="AdminPanel")]
        ])
    )
    
    update_user_data(Admin, step='none')

#==================== Run Bot =====================#
async def main():
    """Main function to run the bot"""
    await app.start()
    
    print(Fore.YELLOW + "Ultra Self Bot v2.0.0 Started...")
    print(Fore.GREEN + f"Bot is running as: @{(await app.get_me()).username}")
    print(Fore.CYAN + "Press Ctrl+C to stop the bot")
    
    # Start expiration task
    expiration_task = asyncio.create_task(expirdec_task())
    
    await idle()
    
    # Cleanup
    expiration_task.cancel()
    await app.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(Fore.RED + "\nBot stopped by user")
    except Exception as e:
        print(Fore.RED + f"Error: {e}")