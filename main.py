#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔═══════════════════════════════════════════════════════════════════════╗
║           DevLaunch India — Production PaaS Platform v2.0            ║
║   Telegram Bot + Web Dashboard + Docker + AI Fix + UPI Payments      ║
║   Owner: @Zolvit | Channel: t.me/narzoxbot                           ║
╚═══════════════════════════════════════════════════════════════════════╝

Single-file production deployment platform for Indian developers.
Features: Docker isolation, WebSocket terminal, AI error fix, abuse detection,
UPI payments, subscriptions, GitHub deploy, script hosting, admin panel.
"""

# ═══════════════════════════════════════════════════════════════════════
# SECTION 1: AUTO-INSTALL & IMPORTS
# ═══════════════════════════════════════════════════════════════════════

import os, sys, subprocess

def _pip(*pkgs):
    subprocess.check_call([sys.executable, "-m", "pip", "install", *pkgs, "-q",
                           "--break-system-packages"], stderr=subprocess.DEVNULL)

REQUIRED = {
    "flask": "flask", "flask_socketio": "flask-socketio",
    "telebot": "pyTelegramBotAPI", "dotenv": "python-dotenv",
    "jwt": "PyJWT", "qrcode": "qrcode[pil]", "PIL": "Pillow",
    "requests": "requests", "git": "gitpython",
    "eventlet": "eventlet", "psutil": "psutil",
}
for mod, pkg in REQUIRED.items():
    try: __import__(mod)
    except ImportError:
        print(f"[SETUP] Installing {pkg}...")
        _pip(pkg)

# Try docker — optional (platform works without it in script-only mode)
DOCKER_AVAILABLE = False
try:
    import docker as docker_sdk
    docker_client = docker_sdk.from_env()
    docker_client.ping()
    DOCKER_AVAILABLE = True
    print("[OK] Docker connected")
except Exception as _e:
    print(f"[WARN] Docker not available ({_e}) — container features disabled")
    docker_client = None

import json, sqlite3, hashlib, time, uuid, zipfile, shutil, re
import logging, secrets, traceback, threading, signal, io, base64, hmac
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
from io import BytesIO
from collections import defaultdict

from flask import (Flask, request, jsonify, session, redirect, render_template_string,
                   send_file, abort, Response)
from flask_socketio import SocketIO, emit, join_room, leave_room, disconnect
import telebot
from telebot import types
from dotenv import load_dotenv
import jwt as pyjwt
import qrcode
import requests as http_requests
import psutil

# Load .env
load_dotenv()

# ═══════════════════════════════════════════════════════════════════════
# SECTION 2: CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════

BOT_TOKEN     = os.getenv("BOT_TOKEN", "8451737127:AAGRbO0CygbnYuqMCBolTP8_EG7NLrh5d04")
OWNER_ID      = int(os.getenv("OWNER_ID", "7524032836"))
ADMIN_IDS     = [OWNER_ID] + [int(x) for x in os.getenv("ADMIN_IDS", "8285724366").split(",") if x.strip()]
ADMIN_EMAIL   = os.getenv("ADMIN_EMAIL", "Kvinit6421@gmail.com")
ADMIN_PASS    = os.getenv("ADMIN_PASS",  "28@HumblerRaj")
SECRET_KEY    = os.getenv("SECRET_KEY",  secrets.token_hex(32))
JWT_SECRET    = os.getenv("JWT_SECRET",  secrets.token_hex(32))
PORT          = int(os.getenv("PORT", "5000"))
BASE_URL      = os.getenv("BASE_URL", f"http://localhost:{PORT}")
UPI_ID        = os.getenv("UPI_ID", "your-upi@bank")
DOMAIN        = os.getenv("DOMAIN", "devlaunch.in")
CHANNEL       = os.getenv("CHANNEL", "t.me/narzoxbot")
BOT_USERNAME  = os.getenv("BOT_USERNAME", "@Zolvit")
REDIS_URL     = os.getenv("REDIS_URL", "")          # optional
GITHUB_TOKEN  = os.getenv("GITHUB_TOKEN", "")       # optional

# ── Limits & Costs ──────────────────────────────────────────────
FREE_CREDITS   = 3.0
COSTS = {"file_upload": 0.5, "github_deploy": 1.0, "backup": 0.5,
         "script_host": 0.0, "ai_fix": 0.2, "template": 0.5}

RATE_LIMITS = {
    "deploy":  {"count": 5,  "window": 3600},
    "restart": {"count": 5,  "window": 3600},
    "ai_fix":  {"count": 10, "window": 3600},
}

# ── Subscription Plans ───────────────────────────────────────────
PLANS = {
    "free":    {"days": 0,   "price": 0,   "apps": 1, "ram": "256m", "cpu": 0.5, "sleep": True,  "label": "Free"},
    "starter": {"days": 30,  "price": 99,  "apps": 2, "ram": "512m", "cpu": 1.0, "sleep": False, "label": "Starter (30d)"},
    "pro":     {"days": 90,  "price": 249, "apps": 5, "ram": "1g",   "cpu": 2.0, "sleep": False, "label": "Pro (90d)"},
    "elite":   {"days": 180, "price": 449, "apps": 15,"ram": "2g",   "cpu": 4.0, "sleep": False, "label": "Elite (180d)"},
}

CREDIT_PACKS = {
    "starter": {"credits": 10,  "price": 50,  "label": "10 Credits — ₹50"},
    "popular": {"credits": 99,  "price": 399, "label": "99 Credits — ₹399"},
    "elite":   {"credits": 199, "price": 699, "label": "199 Credits — ₹699"},
}

# ── Bot Templates ────────────────────────────────────────────────
BOT_TEMPLATES = {
    "echo": {
        "name": "Echo Bot",
        "desc": "Replies to every message — perfect starter template",
        "icon": "🔁",
        "code": '''import telebot, os
bot = telebot.TeleBot(os.getenv("BOT_TOKEN", "YOUR_TOKEN"))
@bot.message_handler(func=lambda m: True)
def echo(m): bot.reply_to(m, m.text)
bot.infinity_polling()
''',
        "requires": ["pyTelegramBotAPI"],
    },
    "broadcast": {
        "name": "Broadcast Bot",
        "desc": "Admin-only broadcast to all registered users",
        "icon": "📢",
        "code": '''import telebot, os, json
bot = telebot.TeleBot(os.getenv("BOT_TOKEN", "YOUR_TOKEN"))
ADMIN = int(os.getenv("ADMIN_ID", "0"))
users = set()
@bot.message_handler(commands=["start"])
def start(m):
    users.add(m.from_user.id)
    bot.reply_to(m, "Subscribed!")
@bot.message_handler(commands=["broadcast"])
def bc(m):
    if m.from_user.id != ADMIN: return
    text = m.text.replace("/broadcast","").strip()
    [bot.send_message(u, text) for u in users]
bot.infinity_polling()
''',
        "requires": ["pyTelegramBotAPI"],
    },
    "filter": {
        "name": "Auto Filter Bot",
        "desc": "Keyword-based message filter for groups",
        "icon": "🔍",
        "code": '''import telebot, os, re
bot = telebot.TeleBot(os.getenv("BOT_TOKEN", "YOUR_TOKEN"))
FILTERS = os.getenv("FILTER_WORDS", "spam,flood").split(",")
@bot.message_handler(func=lambda m: True, content_types=["text"])
def filt(m):
    if any(w in m.text.lower() for w in FILTERS):
        bot.delete_message(m.chat.id, m.message_id)
        bot.send_message(m.chat.id, f"⚠️ Message removed: contains filtered word")
bot.infinity_polling()
''',
        "requires": ["pyTelegramBotAPI"],
    },
    "payment": {
        "name": "UPI Payment Bot",
        "desc": "Collect UPI payments with QR generation",
        "icon": "💳",
        "code": '''import telebot, os, qrcode
from io import BytesIO
bot = telebot.TeleBot(os.getenv("BOT_TOKEN", "YOUR_TOKEN"))
UPI = os.getenv("UPI_ID", "your@upi")
@bot.message_handler(commands=["pay"])
def pay(m):
    try: amt = int(m.text.split()[1])
    except: return bot.reply_to(m, "Usage: /pay AMOUNT")
    url = f"upi://pay?pa={UPI}&am={amt}&cu=INR"
    qr = qrcode.make(url)
    buf = BytesIO(); qr.save(buf); buf.seek(0)
    bot.send_photo(m.chat.id, buf, caption=f"Pay ₹{amt} via UPI: {UPI}")
bot.infinity_polling()
''',
        "requires": ["pyTelegramBotAPI", "qrcode[pil]", "Pillow"],
    },
    "scraper": {
        "name": "Web Scraper Bot",
        "desc": "Scrape any URL and return text content",
        "icon": "🕷️",
        "code": '''import telebot, os, requests
from bs4 import BeautifulSoup
bot = telebot.TeleBot(os.getenv("BOT_TOKEN", "YOUR_TOKEN"))
@bot.message_handler(commands=["scrape"])
def scrape(m):
    try:
        url = m.text.split()[1]
        r = requests.get(url, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text()[:2000]
        bot.reply_to(m, f"📄 Content:\\n{text}")
    except Exception as e:
        bot.reply_to(m, f"Error: {e}")
bot.infinity_polling()
''',
        "requires": ["pyTelegramBotAPI", "requests", "beautifulsoup4"],
    },
}

# ── Abuse Patterns ───────────────────────────────────────────────
ABUSE_PATTERNS = {
    "crypto_miner": [
        r"xmrig", r"minerd", r"cpuminer", r"stratum\+tcp",
        r"nicehash", r"coinhive", r"cryptonight", r"monero",
        r"ethminer", r"bfgminer", r"cgminer",
    ],
    "spam": [
        r"sendMessage.*\d{5,}", r"flood.*telegram",
        r"mass.*message", r"spam.*bot",
    ],
    "phishing": [
        r"\.tk/", r"\.ml/", r"\.ga/", r"bit\.ly.*login",
        r"paypal.*verify", r"bank.*urgent",
    ],
    "shell_escape": [
        r"rm\s+-rf", r"/etc/passwd", r"/etc/shadow",
        r"wget.*\|.*sh", r"curl.*\|.*bash",
        r"chmod.*777", r"nc\s+-e", r"python.*-c.*exec",
    ],
}

# ── Python Package Map ───────────────────────────────────────────
PACKAGE_MAP = {
    "telebot": "pyTelegramBotAPI", "telegram": "pyTelegramBotAPI",
    "flask": "flask", "requests": "requests", "bs4": "beautifulsoup4",
    "PIL": "Pillow", "cv2": "opencv-python", "numpy": "numpy",
    "pandas": "pandas", "sklearn": "scikit-learn", "scipy": "scipy",
    "matplotlib": "matplotlib", "aiohttp": "aiohttp", "fastapi": "fastapi",
    "uvicorn": "uvicorn", "pydantic": "pydantic", "sqlalchemy": "SQLAlchemy",
    "pymongo": "pymongo", "redis": "redis", "celery": "celery",
    "dotenv": "python-dotenv", "yaml": "pyyaml", "toml": "toml",
    "jwt": "PyJWT", "bcrypt": "bcrypt", "qrcode": "qrcode[pil]",
    "pytube": "pytube", "yt_dlp": "yt-dlp", "paramiko": "paramiko",
    "cryptography": "cryptography", "httpx": "httpx", "trio": "trio",
}

# ═══════════════════════════════════════════════════════════════════════
# SECTION 3: LOGGING & DIRECTORIES
# ═══════════════════════════════════════════════════════════════════════

BASE_DIR = Path("devlaunch_data")
for d in ["uploads","deployments","scripts","backups","logs",
          "payments","static","templates","metrics","containers"]:
    (BASE_DIR / d).mkdir(parents=True, exist_ok=True)

DB_PATH = BASE_DIR / "devlaunch.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "logs" / "app.log"),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("DevLaunch")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 4: DATABASE
# ═══════════════════════════════════════════════════════════════════════

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA cache_size=10000")
    return conn

DB_LOCK = threading.Lock()

def db_exec(sql, params=(), fetch="none"):
    with DB_LOCK:
        with get_db() as conn:
            cur = conn.execute(sql, params)
            if fetch == "one":  return cur.fetchone()
            if fetch == "all":  return cur.fetchall()
            if fetch == "id":   return cur.lastrowid
            return cur.rowcount

def init_db():
    with DB_LOCK:
        with get_db() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                email TEXT UNIQUE,
                password_hash TEXT,
                credits REAL DEFAULT 3.0,
                plan TEXT DEFAULT 'free',
                is_admin INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                is_suspended INTEGER DEFAULT 0,
                ban_reason TEXT,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                join_date TEXT DEFAULT (datetime('now')),
                last_seen TEXT DEFAULT (datetime('now')),
                fingerprint TEXT,
                jwt_token TEXT,
                bot_state TEXT DEFAULT 'idle',
                abuse_score INTEGER DEFAULT 0,
                total_deploys INTEGER DEFAULT 0,
                total_restarts INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                plan TEXT NOT NULL,
                start_date TEXT DEFAULT (datetime('now')),
                end_date TEXT,
                is_active INTEGER DEFAULT 1,
                payment_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                container_id TEXT UNIQUE,
                name TEXT,
                image TEXT DEFAULT 'python:3.11-slim',
                status TEXT DEFAULT 'stopped',
                ram_limit TEXT DEFAULT '256m',
                cpu_limit REAL DEFAULT 0.5,
                port INTEGER,
                subdomain TEXT,
                env_vars TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now')),
                last_started TEXT,
                restart_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS deployments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                container_id INTEGER REFERENCES containers(id),
                name TEXT,
                type TEXT,
                source TEXT,
                branch TEXT DEFAULT 'main',
                build_cmd TEXT DEFAULT '',
                start_cmd TEXT DEFAULT 'python main.py',
                env_vars TEXT DEFAULT '{}',
                commit_hash TEXT,
                status TEXT DEFAULT 'pending',
                build_logs TEXT DEFAULT '',
                error_logs TEXT DEFAULT '',
                port INTEGER,
                url TEXT,
                is_rollback INTEGER DEFAULT 0,
                version INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS hosted_scripts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                name TEXT,
                filename TEXT,
                file_type TEXT,
                file_path TEXT,
                status TEXT DEFAULT 'stopped',
                pid INTEGER,
                logs TEXT DEFAULT '',
                auto_restart INTEGER DEFAULT 0,
                restart_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                last_started TEXT
            );

            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                container_id TEXT,
                cpu_pct REAL,
                ram_mb REAL,
                ram_pct REAL,
                net_rx REAL DEFAULT 0,
                net_tx REAL DEFAULT 0,
                recorded_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                type TEXT,
                plan_or_pack TEXT,
                amount REAL,
                upi_txn_id TEXT,
                screenshot_path TEXT,
                status TEXT DEFAULT 'pending',
                admin_notes TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS abuse_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                container_id TEXT,
                abuse_type TEXT,
                details TEXT,
                action_taken TEXT,
                detected_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS activity_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                details TEXT,
                ip TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS rate_limit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER REFERENCES users(id),
                referred_id INTEGER REFERENCES users(id) UNIQUE,
                rewarded INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS broadcast_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER,
                message TEXT,
                target TEXT,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS ai_fix_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                error_text TEXT,
                suggestion TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_users_tg ON users(telegram_id);
            CREATE INDEX IF NOT EXISTS idx_scripts_user ON hosted_scripts(user_id);
            CREATE INDEX IF NOT EXISTS idx_deploys_user ON deployments(user_id);
            CREATE INDEX IF NOT EXISTS idx_metrics_time ON metrics(recorded_at);
            CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
            """)
    log.info("✅ Database initialized")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 5: DB HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def get_user_by_tg(tg_id):
    return db_exec("SELECT * FROM users WHERE telegram_id=?", (tg_id,), "one")

def get_user_by_id(uid):
    return db_exec("SELECT * FROM users WHERE id=?", (uid,), "one")

def create_tg_user(tg_id, username=None):
    ref = secrets.token_urlsafe(8)
    db_exec("INSERT OR IGNORE INTO users (telegram_id,username,credits,referral_code) VALUES (?,?,?,?)",
            (tg_id, username or f"user_{tg_id}", FREE_CREDITS, ref))
    return get_user_by_tg(tg_id)

def add_credits(user_id, amount, reason=""):
    db_exec("UPDATE users SET credits=credits+? WHERE id=?", (amount, user_id))
    log_activity(user_id, "credits_add", f"+{amount}: {reason}")

def deduct_credits(user_id, amount):
    u = get_user_by_id(user_id)
    if not u or u["credits"] < amount:
        return False
    db_exec("UPDATE users SET credits=credits-? WHERE id=?", (amount, user_id))
    return True

def log_activity(user_id, action, details="", ip=""):
    db_exec("INSERT INTO activity_log (user_id,action,details,ip) VALUES (?,?,?,?)",
            (user_id, action, details, ip))

def get_user_plan(user):
    if user["telegram_id"] in ADMIN_IDS:
        return PLANS["elite"]
    sub = db_exec(
        "SELECT * FROM subscriptions WHERE user_id=? AND is_active=1 AND end_date>datetime('now')",
        (user["id"],), "one"
    )
    if sub:
        return PLANS.get(sub["plan"], PLANS["free"])
    return PLANS["free"]

def is_subscribed(user_id):
    return bool(db_exec(
        "SELECT id FROM subscriptions WHERE user_id=? AND is_active=1 AND end_date>datetime('now')",
        (user_id,), "one"
    ))

def get_app_limit(user):
    return get_user_plan(user)["apps"]

def get_user_scripts(user_id):
    return db_exec("SELECT * FROM hosted_scripts WHERE user_id=? ORDER BY created_at DESC",
                   (user_id,), "all")

def get_user_deployments(user_id):
    return db_exec("SELECT * FROM deployments WHERE user_id=? ORDER BY created_at DESC",
                   (user_id,), "all")

def get_stats():
    return {
        "users": db_exec("SELECT COUNT(*) FROM users", fetch="one")[0],
        "scripts": db_exec("SELECT COUNT(*) FROM hosted_scripts", fetch="one")[0],
        "running": db_exec("SELECT COUNT(*) FROM hosted_scripts WHERE status='running'", fetch="one")[0],
        "deployments": db_exec("SELECT COUNT(*) FROM deployments", fetch="one")[0],
        "containers": db_exec("SELECT COUNT(*) FROM containers", fetch="one")[0],
        "pending_pay": db_exec("SELECT COUNT(*) FROM payments WHERE status='pending'", fetch="one")[0],
        "abuse_count": db_exec("SELECT COUNT(*) FROM abuse_log WHERE detected_at>datetime('now','-24 hours')", fetch="one")[0],
        "revenue": db_exec("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'", fetch="one")[0],
    }

# ═══════════════════════════════════════════════════════════════════════
# SECTION 6: RATE LIMITER
# ═══════════════════════════════════════════════════════════════════════

def check_rate_limit(user_id, action):
    cfg = RATE_LIMITS.get(action, {"count": 10, "window": 3600})
    cutoff = (datetime.now() - timedelta(seconds=cfg["window"])).strftime("%Y-%m-%d %H:%M:%S")
    count = db_exec(
        "SELECT COUNT(*) FROM rate_limit_log WHERE user_id=? AND action=? AND created_at>?",
        (user_id, action, cutoff), "one"
    )[0]
    if count >= cfg["count"]:
        return False, count, cfg["count"]
    db_exec("INSERT INTO rate_limit_log (user_id,action) VALUES (?,?)", (user_id, action))
    return True, count + 1, cfg["count"]

# ═══════════════════════════════════════════════════════════════════════
# SECTION 7: JWT AUTH
# ═══════════════════════════════════════════════════════════════════════

def create_jwt(user_id, tg_id, is_admin=False):
    payload = {
        "uid": user_id,
        "tg": tg_id,
        "admin": is_admin,
        "exp": datetime.utcnow() + timedelta(days=7),
        "iat": datetime.utcnow(),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt(token):
    try:
        return pyjwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except pyjwt.ExpiredSignatureError:
        return None
    except Exception:
        return None

def api_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            token = request.args.get("token", "")
        payload = verify_jwt(token)
        if not payload:
            return jsonify({"error": "Unauthorized"}), 401
        request.jwt = payload
        return f(*args, **kwargs)
    return wrapper

def admin_api_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        payload = verify_jwt(token)
        if not payload or not payload.get("admin"):
            return jsonify({"error": "Admin access required"}), 403
        request.jwt = payload
        return f(*args, **kwargs)
    return wrapper

def web_admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper

# ═══════════════════════════════════════════════════════════════════════
# SECTION 8: DOCKER MANAGER
# ═══════════════════════════════════════════════════════════════════════

class DockerManager:
    def __init__(self):
        self.client = docker_client
        self.available = DOCKER_AVAILABLE
        self.network_name = "devlaunch_net"
        if self.available:
            self._ensure_network()

    def _ensure_network(self):
        try:
            self.client.networks.get(self.network_name)
        except Exception:
            try:
                self.client.networks.create(
                    self.network_name,
                    driver="bridge",
                    options={"com.docker.network.bridge.enable_icc": "false"}
                )
            except Exception as e:
                log.warning(f"Could not create Docker network: {e}")

    def create_container(self, user_id, deploy_name, image, env_vars, ram_limit, cpu_limit, start_cmd):
        if not self.available:
            return None, "Docker not available"
        try:
            cname = f"devlaunch_{user_id}_{deploy_name}_{int(time.time())}"
            env_list = [f"{k}={v}" for k, v in env_vars.items()]
            container = self.client.containers.run(
                image=image,
                name=cname,
                command=start_cmd,
                environment=env_list,
                mem_limit=ram_limit,
                cpu_period=100000,
                cpu_quota=int(cpu_limit * 100000),
                nano_cpus=int(cpu_limit * 1e9),
                pids_limit=50,
                network=self.network_name,
                security_opt=["no-new-privileges:true"],
                read_only=False,
                user="nobody",
                detach=True,
                restart_policy={"Name": "on-failure", "MaximumRetryCount": 3},
            )
            return container.id, None
        except Exception as e:
            return None, str(e)

    def stop_container(self, container_id):
        if not self.available: return False
        try:
            c = self.client.containers.get(container_id)
            c.stop(timeout=10)
            return True
        except Exception as e:
            log.error(f"Stop container {container_id}: {e}")
            return False

    def restart_container(self, container_id):
        if not self.available: return False
        try:
            c = self.client.containers.get(container_id)
            c.restart(timeout=10)
            return True
        except Exception as e:
            log.error(f"Restart container {container_id}: {e}")
            return False

    def kill_container(self, container_id):
        if not self.available: return False
        try:
            c = self.client.containers.get(container_id)
            c.kill()
            c.remove(force=True)
            return True
        except Exception:
            return False

    def get_logs(self, container_id, tail=100):
        if not self.available: return "Docker not available"
        try:
            c = self.client.containers.get(container_id)
            return c.logs(tail=tail, timestamps=True).decode("utf-8", errors="replace")
        except Exception as e:
            return f"Error fetching logs: {e}"

    def get_stats(self, container_id):
        if not self.available:
            return {"cpu": 0, "ram_mb": 0, "ram_pct": 0}
        try:
            c = self.client.containers.get(container_id)
            raw = c.stats(stream=False)
            cpu_d = raw["cpu_stats"]["cpu_usage"]["total_usage"] - raw["precpu_stats"]["cpu_usage"]["total_usage"]
            sys_d = raw["cpu_stats"]["system_cpu_usage"] - raw["precpu_stats"]["system_cpu_usage"]
            num_cpu = raw["cpu_stats"].get("online_cpus", 1)
            cpu_pct = (cpu_d / sys_d) * num_cpu * 100 if sys_d > 0 else 0
            mem_usage = raw["memory_stats"]["usage"]
            mem_limit = raw["memory_stats"]["limit"]
            ram_mb = mem_usage / (1024 * 1024)
            ram_pct = (mem_usage / mem_limit) * 100 if mem_limit > 0 else 0
            return {"cpu": round(cpu_pct, 2), "ram_mb": round(ram_mb, 2), "ram_pct": round(ram_pct, 2)}
        except Exception:
            return {"cpu": 0, "ram_mb": 0, "ram_pct": 0}

    def get_status(self, container_id):
        if not self.available: return "unknown"
        try:
            c = self.client.containers.get(container_id)
            return c.status
        except Exception:
            return "dead"

    def exec_in_container(self, container_id, cmd):
        if not self.available: return False, "Docker not available"
        BLACKLIST = ["rm -rf /", "curl | sh", "wget | bash", "/etc/shadow", "dd if="]
        for bl in BLACKLIST:
            if bl in cmd:
                return False, f"Blocked command: {bl}"
        try:
            c = self.client.containers.get(container_id)
            result = c.exec_run(cmd, user="nobody", privileged=False, tty=False)
            return True, result.output.decode("utf-8", errors="replace")
        except Exception as e:
            return False, str(e)

docker_mgr = DockerManager()

# ═══════════════════════════════════════════════════════════════════════
# SECTION 9: ABUSE DETECTION
# ═══════════════════════════════════════════════════════════════════════

class AbuseDetector:
    CPU_LIMIT     = 90.0   # % sustained for > 60s
    RAM_LIMIT     = 95.0   # %
    ABUSE_TIMEOUT = 60     # seconds sustained before kill

    def __init__(self):
        self.spike_tracker = defaultdict(list)  # container_id -> [timestamps]

    def scan_logs(self, logs_text):
        """Scan logs for abuse patterns. Returns list of (type, detail) tuples."""
        findings = []
        for atype, patterns in ABUSE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, logs_text, re.IGNORECASE):
                    findings.append((atype, pattern))
        return findings

    def scan_code(self, code_text):
        """Pre-flight scan of uploaded code."""
        return self.scan_logs(code_text)

    def check_resource_abuse(self, container_id, stats):
        cpu = stats.get("cpu", 0)
        ram_pct = stats.get("ram_pct", 0)
        now = time.time()
        if cpu > self.CPU_LIMIT or ram_pct > self.RAM_LIMIT:
            self.spike_tracker[container_id].append(now)
            # Keep only last 2 minutes
            self.spike_tracker[container_id] = [
                t for t in self.spike_tracker[container_id] if now - t < 120
            ]
            # If sustained spike > ABUSE_TIMEOUT seconds worth of data points
            if len(self.spike_tracker[container_id]) > 12:  # ~12 × 5s = 60s
                return True, f"Sustained CPU {cpu:.1f}% / RAM {ram_pct:.1f}%"
        else:
            self.spike_tracker.pop(container_id, None)
        return False, None

    def handle_abuse(self, user_id, container_id, abuse_type, details):
        log.warning(f"ABUSE DETECTED user={user_id} type={abuse_type}: {details}")
        # Kill container
        docker_mgr.kill_container(container_id)
        # Suspend account
        db_exec("UPDATE users SET is_suspended=1,abuse_score=abuse_score+10 WHERE id=?", (user_id,))
        db_exec("UPDATE containers SET status='killed' WHERE container_id=?", (container_id,))
        db_exec("INSERT INTO abuse_log (user_id,container_id,abuse_type,details,action_taken) VALUES (?,?,?,?,?)",
                (user_id, container_id, abuse_type, details, "container_killed,account_suspended"))
        log_activity(user_id, "abuse_action", f"{abuse_type}: {details}")
        # Notify admins
        for aid in ADMIN_IDS:
            try:
                bot.send_message(aid,
                    f"🚨 <b>ABUSE DETECTED</b>\n\n"
                    f"👤 User ID: {user_id}\n"
                    f"📦 Container: {container_id[:12]}...\n"
                    f"🔍 Type: {abuse_type}\n"
                    f"📋 Details: {details}\n"
                    f"⚡ Action: Container killed, account suspended")
            except Exception:
                pass

abuse_detector = AbuseDetector()

# ═══════════════════════════════════════════════════════════════════════
# SECTION 10: AI ERROR FIX SUGGESTIONS
# ═══════════════════════════════════════════════════════════════════════

AI_FIX_RULES = [
    {
        "pattern": r"ModuleNotFoundError: No module named '(\w+)'",
        "fix": lambda m: (
            f"📦 Missing package: <code>{m.group(1)}</code>\n\n"
            f"Fix: Add to requirements.txt:\n<code>{PACKAGE_MAP.get(m.group(1), m.group(1))}</code>\n\n"
            f"Or in code: <code>pip install {PACKAGE_MAP.get(m.group(1), m.group(1))}</code>"
        )
    },
    {
        "pattern": r"SyntaxError: (.+) \((.+), line (\d+)\)",
        "fix": lambda m: (
            f"🔴 Syntax Error in {m.group(2)} at line {m.group(3)}\n\n"
            f"Error: {m.group(1)}\n\n"
            f"💡 Check: missing colon, unclosed parenthesis/bracket, incorrect indentation"
        )
    },
    {
        "pattern": r"OSError: \[Errno 98\] Address already in use",
        "fix": lambda _: (
            "🔌 Port already in use!\n\n"
            "Fix options:\n"
            "• Change PORT in your .env\n"
            "• Kill existing process: <code>fuser -k 8080/tcp</code>\n"
            "• Use <code>os.getenv('PORT', '8080')</code> in your app"
        )
    },
    {
        "pattern": r"PermissionError: \[Errno 13\]",
        "fix": lambda _: (
            "🔐 Permission denied!\n\n"
            "Fix: Use paths inside /app/ directory.\n"
            "Container runs as non-root — avoid writing to /etc, /usr, /var"
        )
    },
    {
        "pattern": r"ConnectionRefusedError|Connection refused",
        "fix": lambda _: (
            "🔗 Connection refused!\n\n"
            "Possible causes:\n"
            "• Database not running\n"
            "• Wrong HOST/PORT in env vars\n"
            "• Service not started yet (add retry logic)\n"
            "• Firewall blocking port"
        )
    },
    {
        "pattern": r"jwt\.exceptions|InvalidSignatureError|DecodeError",
        "fix": lambda _: (
            "🔑 JWT Token Error!\n\n"
            "Fix: Check SECRET_KEY in .env — must match between encode and decode.\n"
            "Regenerate: <code>python -c \"import secrets; print(secrets.token_hex(32))\"</code>"
        )
    },
    {
        "pattern": r"RecursionError: maximum recursion depth",
        "fix": lambda _: (
            "♾️ Infinite recursion detected!\n\n"
            "Fix: Check your function — it's calling itself without a base case.\n"
            "Add: <code>import sys; sys.setrecursionlimit(1000)</code> as a temporary workaround."
        )
    },
    {
        "pattern": r"MemoryError|Killed|OOM",
        "fix": lambda _: (
            "💾 Out of Memory!\n\n"
            "Fix options:\n"
            "• Upgrade your plan for more RAM\n"
            "• Use generators instead of lists\n"
            "• Process data in chunks\n"
            "• Avoid loading large files into memory at once"
        )
    },
    {
        "pattern": r"FileNotFoundError: \[Errno 2\] No such file or directory: '(.+)'",
        "fix": lambda m: (
            f"📂 File not found: <code>{m.group(1)}</code>\n\n"
            f"Fix: Ensure the file exists at that path in your deployment.\n"
            f"Use <code>os.path.exists()</code> to check before opening."
        )
    },
    {
        "pattern": r"telegram\.error\.Unauthorized|401 Unauthorized",
        "fix": lambda _: (
            "🤖 Invalid Bot Token!\n\n"
            "Fix: Set correct BOT_TOKEN in your .env\n"
            "Get token from @BotFather on Telegram."
        )
    },
]

def ai_suggest_fix(logs_text):
    """Analyze logs and suggest AI fixes."""
    suggestions = []
    for rule in AI_FIX_RULES:
        match = re.search(rule["pattern"], logs_text, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                fix = rule["fix"](match)
                suggestions.append(fix)
            except Exception:
                pass
    if not suggestions:
        return (
            "🤖 <b>AI Analysis</b>\n\n"
            "No specific fix found for this error.\n\n"
            "💡 General debugging tips:\n"
            "• Check all env vars are set correctly\n"
            "• Ensure requirements.txt is complete\n"
            "• Add <code>import logging; logging.basicConfig(level=logging.DEBUG)</code>\n"
            "• Check Python version compatibility"
        )
    return "🤖 <b>AI Fix Suggestions</b>\n\n" + "\n\n━━━━\n\n".join(suggestions)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 11: SCRIPT RUNNER (Process-based, no Docker)
# ═══════════════════════════════════════════════════════════════════════

running_procs = {}  # script_id -> subprocess.Popen

def detect_imports(code):
    imports = set()
    for m in re.finditer(r'^(?:import|from)\s+(\w+)', code, re.MULTILINE):
        imports.add(m.group(1))
    return imports

def auto_install_deps(imports):
    installed = []
    for imp in imports:
        try:
            __import__(imp)
        except ImportError:
            pkg = PACKAGE_MAP.get(imp, imp)
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", pkg, "-q", "--break-system-packages"],
                    timeout=90, stderr=subprocess.DEVNULL
                )
                installed.append(pkg)
            except Exception as e:
                log.warning(f"Failed to install {pkg}: {e}")
    return installed

def auto_install_node(folder):
    pkg_json = Path(folder) / "package.json"
    if pkg_json.exists():
        try:
            subprocess.check_call(["npm", "install", "--prefix", str(folder)],
                                  timeout=120, stderr=subprocess.DEVNULL)
            return True
        except Exception:
            return False
    return False

def run_script_process(script_id, file_path, script_dir, file_type, user_id):
    try:
        if file_type == "py":
            code = Path(file_path).read_text(errors="ignore")
            # Abuse scan before running
            findings = abuse_detector.scan_code(code)
            if findings:
                atype, detail = findings[0]
                db_exec("UPDATE hosted_scripts SET status='blocked' WHERE id=?", (script_id,))
                db_exec("INSERT INTO abuse_log (user_id,abuse_type,details,action_taken) VALUES (?,?,?,?)",
                        (user_id, atype, detail, "script_blocked"))
                return False, f"🚫 Script blocked: abuse pattern detected ({atype})"
            imports = detect_imports(code)
            auto_install_deps(imports)
            cmd = [sys.executable, file_path]
        elif file_type == "js":
            auto_install_node(script_dir)
            cmd = ["node", file_path]
        else:
            return False, "Unsupported file type"

        proc = subprocess.Popen(
            cmd, cwd=script_dir,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1
        )
        running_procs[script_id] = proc
        db_exec("UPDATE hosted_scripts SET status='running',pid=?,last_started=datetime('now') WHERE id=?",
                (proc.pid, script_id))

        def collect_output():
            buf = []
            for line in proc.stdout:
                buf.append(line)
                if len(buf) > 500: buf.pop(0)
                # Real-time abuse scan every 50 lines
                if len(buf) % 50 == 0:
                    findings = abuse_detector.scan_logs("".join(buf[-50:]))
                    if findings:
                        atype, detail = findings[0]
                        abuse_detector.handle_abuse(user_id, f"script_{script_id}", atype, detail)
                        proc.kill()
                        break
            db_exec("UPDATE hosted_scripts SET logs=?,status='stopped',pid=NULL WHERE id=?",
                    ("".join(buf[-200:]), script_id))
            running_procs.pop(script_id, None)
            # Auto restart if enabled
            script = db_exec("SELECT auto_restart FROM hosted_scripts WHERE id=?", (script_id,), "one")
            if script and script["auto_restart"] and proc.returncode != 0:
                db_exec("UPDATE hosted_scripts SET restart_count=restart_count+1 WHERE id=?", (script_id,))
                time.sleep(5)
                run_script_process(script_id, file_path, script_dir, file_type, user_id)

        threading.Thread(target=collect_output, daemon=True).start()
        return True, proc.pid

    except Exception as e:
        db_exec("UPDATE hosted_scripts SET status='error' WHERE id=?", (script_id,))
        return False, str(e)

def stop_script(script_id):
    proc = running_procs.get(script_id)
    if proc:
        proc.terminate()
        try: proc.wait(timeout=5)
        except: proc.kill()
        running_procs.pop(script_id, None)
    db_exec("UPDATE hosted_scripts SET status='stopped',pid=NULL WHERE id=?", (script_id,))

# ═══════════════════════════════════════════════════════════════════════
# SECTION 12: DEPLOYMENT SYSTEM
# ═══════════════════════════════════════════════════════════════════════

def deploy_from_github(user_id, repo_url, deploy_name, build_cmd="", start_cmd="python main.py",
                       env_vars=None, branch="main"):
    dest = BASE_DIR / "deployments" / str(user_id) / deploy_name
    dest.mkdir(parents=True, exist_ok=True)
    logs = []
    try:
        import git
        logs.append(f"[{datetime.now():%H:%M:%S}] Cloning {repo_url}...")
        if dest.exists():
            shutil.rmtree(dest)
        clone_kwargs = {"branch": branch} if branch else {}
        if GITHUB_TOKEN and "github.com" in repo_url:
            auth_url = repo_url.replace("https://", f"https://{GITHUB_TOKEN}@")
            git.Repo.clone_from(auth_url, dest, **clone_kwargs)
        else:
            git.Repo.clone_from(repo_url, dest, **clone_kwargs)

        repo = git.Repo(dest)
        commit_hash = repo.head.commit.hexsha[:8]
        logs.append(f"[{datetime.now():%H:%M:%S}] Cloned. Commit: {commit_hash}")

        # Install deps
        req_file = dest / "requirements.txt"
        if req_file.exists():
            logs.append(f"[{datetime.now():%H:%M:%S}] Installing Python deps...")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file), "-q",
                 "--break-system-packages"],
                capture_output=True, text=True, timeout=120
            )
            logs.append(result.stdout[-500:] if result.stdout else "")

        pkg_json = dest / "package.json"
        if pkg_json.exists():
            logs.append(f"[{datetime.now():%H:%M:%S}] Installing Node deps...")
            subprocess.run(["npm", "install", "--prefix", str(dest)],
                           capture_output=True, timeout=120)

        # Custom build cmd
        if build_cmd:
            logs.append(f"[{datetime.now():%H:%M:%S}] Running build: {build_cmd}")
            result = subprocess.run(build_cmd, shell=True, cwd=dest,
                                    capture_output=True, text=True, timeout=120)
            logs.append(result.stdout[-500:] if result.stdout else "")

        deploy_id = db_exec(
            "INSERT INTO deployments (user_id,name,type,source,branch,build_cmd,start_cmd,env_vars,commit_hash,status,build_logs) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, deploy_name, "github", repo_url, branch, build_cmd, start_cmd,
             json.dumps(env_vars or {}), commit_hash, "ready", "\n".join(logs)),
            "id"
        )
        db_exec("UPDATE users SET total_deploys=total_deploys+1 WHERE id=?", (user_id,))
        return True, "\n".join(logs), deploy_id

    except Exception as e:
        logs.append(f"[ERROR] {e}")
        db_exec(
            "INSERT INTO deployments (user_id,name,type,source,status,build_logs,error_logs) VALUES (?,?,?,?,?,?,?)",
            (user_id, deploy_name, "github", repo_url, "failed", "\n".join(logs), str(e)), "id"
        )
        return False, "\n".join(logs), None

def deploy_from_file(user_id, file_path, deploy_name, start_cmd="python main.py", env_vars=None):
    dest = BASE_DIR / "deployments" / str(user_id) / deploy_name
    dest.mkdir(parents=True, exist_ok=True)
    logs = []
    try:
        fname = str(file_path)
        if fname.endswith(".zip"):
            logs.append(f"[{datetime.now():%H:%M:%S}] Extracting ZIP...")
            with zipfile.ZipFile(file_path, 'r') as z:
                z.extractall(dest)
        else:
            shutil.copy(file_path, dest)

        logs.append(f"[{datetime.now():%H:%M:%S}] Files deployed to {dest}")

        req_file = dest / "requirements.txt"
        if req_file.exists():
            logs.append(f"[{datetime.now():%H:%M:%S}] Installing deps...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-r", str(req_file),
                 "-q", "--break-system-packages"],
                capture_output=True, timeout=120
            )

        deploy_id = db_exec(
            "INSERT INTO deployments (user_id,name,type,source,start_cmd,env_vars,status,build_logs) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, deploy_name, "file", str(file_path), start_cmd,
             json.dumps(env_vars or {}), "ready", "\n".join(logs)),
            "id"
        )
        db_exec("UPDATE users SET total_deploys=total_deploys+1 WHERE id=?", (user_id,))
        return True, "\n".join(logs), deploy_id

    except Exception as e:
        logs.append(f"[ERROR] {e}")
        return False, "\n".join(logs), None

def rollback_deployment(deploy_id, user_id):
    """Rollback to a previous deployment."""
    deploy = db_exec("SELECT * FROM deployments WHERE id=? AND user_id=?",
                     (deploy_id, user_id), "one")
    if not deploy:
        return False, "Deployment not found"
    if deploy["type"] == "github":
        return deploy_from_github(
            user_id, deploy["source"], f"{deploy['name']}_rollback",
            deploy["build_cmd"], deploy["start_cmd"],
            json.loads(deploy["env_vars"] or "{}"), deploy["branch"]
        )
    return False, "Rollback only supported for GitHub deployments"

# ═══════════════════════════════════════════════════════════════════════
# SECTION 13: TEMPLATE DEPLOYER
# ═══════════════════════════════════════════════════════════════════════

def deploy_template(user_id, template_key, bot_token="", extra_env=None):
    tpl = BOT_TEMPLATES.get(template_key)
    if not tpl:
        return False, "Template not found", None
    tdir = BASE_DIR / "scripts" / str(user_id) / f"tpl_{template_key}_{int(time.time())}"
    tdir.mkdir(parents=True, exist_ok=True)
    code = tpl["code"]
    if bot_token:
        code = code.replace("YOUR_TOKEN", bot_token)
    main_file = tdir / "main.py"
    main_file.write_text(code)
    req_file = tdir / "requirements.txt"
    req_file.write_text("\n".join(tpl.get("requires", [])))
    # Install deps
    if tpl.get("requires"):
        subprocess.run(
            [sys.executable, "-m", "pip", "install"] + tpl["requires"] +
            ["-q", "--break-system-packages"],
            capture_output=True, timeout=90
        )
    # Register as hosted script
    sid = db_exec(
        "INSERT INTO hosted_scripts (user_id,name,filename,file_type,file_path) VALUES (?,?,?,?,?)",
        (user_id, f"{tpl['name']} (template)", "main.py", "py", str(main_file)), "id"
    )
    log_activity(user_id, "template_deploy", template_key)
    return True, f"Template '{tpl['name']}' deployed!", sid

# ═══════════════════════════════════════════════════════════════════════
# SECTION 14: PAYMENT SYSTEM
# ═══════════════════════════════════════════════════════════════════════

def generate_upi_qr(amount, ref):
    upi_url = f"upi://pay?pa={UPI_ID}&pn=DevLaunch&am={amount}&cu=INR&tn={ref}"
    qr = qrcode.QRCode(version=1, box_size=8, border=4,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf

def create_payment(user_id, ptype, plan_or_pack, amount):
    return db_exec(
        "INSERT INTO payments (user_id,type,plan_or_pack,amount) VALUES (?,?,?,?)",
        (user_id, ptype, plan_or_pack, amount), "id"
    )

def approve_payment(pay_id, admin_id):
    pay = db_exec("SELECT * FROM payments WHERE id=?", (pay_id,), "one")
    if not pay or pay["status"] != "pending":
        return False, "Not found or already processed"
    if pay["type"] == "credits":
        pack = CREDIT_PACKS.get(pay["plan_or_pack"])
        if pack:
            add_credits(pay["user_id"], pack["credits"], f"Pack: {pack['label']}")
    elif pay["type"] == "subscription":
        plan = PLANS.get(pay["plan_or_pack"])
        if plan:
            end = datetime.now() + timedelta(days=plan["days"])
            db_exec("UPDATE subscriptions SET is_active=0 WHERE user_id=?", (pay["user_id"],))
            db_exec(
                "INSERT INTO subscriptions (user_id,plan,end_date,payment_id) VALUES (?,?,?,?)",
                (pay["user_id"], pay["plan_or_pack"],
                 end.strftime("%Y-%m-%d %H:%M:%S"), pay_id)
            )
            db_exec("UPDATE users SET plan=? WHERE id=?", (pay["plan_or_pack"], pay["user_id"]))
    db_exec(
        "UPDATE payments SET status='approved',admin_notes=?,updated_at=datetime('now') WHERE id=?",
        (f"Approved by {admin_id}", pay_id)
    )
    return True, "Approved"

def reject_payment(pay_id, admin_id, reason=""):
    db_exec(
        "UPDATE payments SET status='rejected',admin_notes=?,updated_at=datetime('now') WHERE id=?",
        (f"Rejected by {admin_id}: {reason}", pay_id)
    )
    return True, "Rejected"

# ═══════════════════════════════════════════════════════════════════════
# SECTION 15: METRICS COLLECTOR
# ═══════════════════════════════════════════════════════════════════════

def collect_metrics():
    """Background thread: collect Docker stats and check for abuse."""
    while True:
        try:
            containers = db_exec(
                "SELECT c.*,u.id as uid FROM containers c JOIN users u ON c.user_id=u.id WHERE c.status='running'",
                fetch="all"
            )
            for cont in (containers or []):
                cid = cont["container_id"]
                stats = docker_mgr.get_stats(cid)
                db_exec(
                    "INSERT INTO metrics (user_id,container_id,cpu_pct,ram_mb,ram_pct) VALUES (?,?,?,?,?)",
                    (cont["uid"], cid, stats["cpu"], stats["ram_mb"], stats["ram_pct"])
                )
                # Delete old metrics (keep 24h)
                db_exec("DELETE FROM metrics WHERE recorded_at < datetime('now','-24 hours')")
                # Abuse check
                is_abuse, reason = abuse_detector.check_resource_abuse(cid, stats)
                if is_abuse:
                    abuse_detector.handle_abuse(cont["uid"], cid, "resource_abuse", reason)
        except Exception as e:
            log.error(f"Metrics collector error: {e}")
        time.sleep(5)

def get_metrics_history(container_id, hours=1):
    rows = db_exec(
        "SELECT cpu_pct,ram_mb,ram_pct,recorded_at FROM metrics "
        "WHERE container_id=? AND recorded_at>datetime('now',?) ORDER BY recorded_at",
        (container_id, f"-{hours} hours"), "all"
    )
    return [dict(r) for r in rows] if rows else []

def get_system_metrics():
    """Host system metrics."""
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    return {
        "cpu_pct": cpu,
        "ram_used_gb": round(mem.used / 1e9, 2),
        "ram_total_gb": round(mem.total / 1e9, 2),
        "ram_pct": mem.percent,
        "disk_used_gb": round(disk.used / 1e9, 2),
        "disk_total_gb": round(disk.total / 1e9, 2),
        "disk_pct": disk.percent,
        "proc_count": len(running_procs),
    }

# ═══════════════════════════════════════════════════════════════════════
# SECTION 16: NGINX CONFIG GENERATOR
# ═══════════════════════════════════════════════════════════════════════

def generate_nginx_config(subdomain, port, domain=DOMAIN):
    return f"""
# DevLaunch auto-generated config for {subdomain}.{domain}
server {{
    listen 80;
    server_name {subdomain}.{domain};
    return 301 https://$host$request_uri;
}}
server {{
    listen 443 ssl http2;
    server_name {subdomain}.{domain};
    ssl_certificate /etc/letsencrypt/live/{domain}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{domain}/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES128-GCM-SHA256:ECDHE-RSA-AES256-GCM-SHA384;
    add_header X-Frame-Options SAMEORIGIN;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }}
}}
"""

# ═══════════════════════════════════════════════════════════════════════
# SECTION 17: BOT STATE MACHINE
# ═══════════════════════════════════════════════════════════════════════

user_states = {}

def set_state(tg_id, state, data=None):
    user_states[tg_id] = {"state": state, "data": data or {}, "ts": time.time()}

def get_state(tg_id):
    st = user_states.get(tg_id, {"state": "idle", "data": {}, "ts": 0})
    # Auto-expire after 10 minutes
    if time.time() - st.get("ts", 0) > 600:
        user_states.pop(tg_id, None)
        return {"state": "idle", "data": {}}
    return st

def clear_state(tg_id):
    user_states.pop(tg_id, None)

# ═══════════════════════════════════════════════════════════════════════
# SECTION 18: TELEGRAM BOT — KEYBOARDS
# ═══════════════════════════════════════════════════════════════════════

def main_menu_kb(tg_id):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        types.KeyboardButton("🚀 My Scripts"),
        types.KeyboardButton("📦 Deploy App"),
        types.KeyboardButton("🐋 Containers"),
        types.KeyboardButton("🤖 Templates"),
        types.KeyboardButton("💰 Credits"),
        types.KeyboardButton("👑 Subscribe"),
        types.KeyboardButton("👤 Profile"),
        types.KeyboardButton("🔗 Referral"),
        types.KeyboardButton("🤖 AI Fix"),
        types.KeyboardButton("❓ Help"),
    )
    if tg_id in ADMIN_IDS:
        kb.add(types.KeyboardButton("⚙️ Admin Panel"))
    return kb

def back_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(types.KeyboardButton("🏠 Main Menu"))
    return kb

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 19: TELEGRAM BOT — COMMANDS
# ═══════════════════════════════════════════════════════════════════════

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id)
    args = msg.text.split()
    ref_code = args[1] if len(args) > 1 else None
    if not user:
        user = create_tg_user(tg_id, msg.from_user.username)
        if ref_code:
            referrer = db_exec("SELECT * FROM users WHERE referral_code=?", (ref_code,), "one")
            if referrer and referrer["telegram_id"] != tg_id:
                db_exec("INSERT OR IGNORE INTO referrals (referrer_id,referred_id) VALUES (?,?)",
                        (referrer["id"], user["id"]))
                add_credits(referrer["id"], 1.0, f"Referral: {msg.from_user.username}")
                try:
                    bot.send_message(referrer["telegram_id"],
                        f"🎉 <b>Referral Bonus!</b>\n+1 credit for inviting {msg.from_user.first_name}!")
                except: pass
    plan = get_user_plan(user)
    scripts = get_user_scripts(user["id"])
    jwt_token = create_jwt(user["id"], tg_id, tg_id in ADMIN_IDS)
    db_exec("UPDATE users SET jwt_token=?,last_seen=datetime('now') WHERE id=?", (jwt_token, user["id"]))
    text = (
        f"⚡ <b>DevLaunch India</b>\n"
        f"<i>Production PaaS for Indian Developers</i>\n\n"
        f"👋 Welcome, {msg.from_user.first_name}!\n\n"
        f"📊 <b>Your Stats</b>\n"
        f"├ 💰 Credits: <b>{user['credits']:.1f}</b>\n"
        f"├ 👑 Plan: <b>{plan['label']}</b>\n"
        f"├ 📜 Scripts: <b>{len(scripts)}/{plan['apps']}</b>\n"
        f"└ 🔑 Token: <code>{jwt_token[:20]}...</code>\n\n"
        f"🌐 Dashboard: {BASE_URL}\n"
        f"📢 Channel: {CHANNEL}"
    )
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🌐 Open Dashboard", url=f"{BASE_URL}?token={jwt_token}"))
    bot.send_message(msg.chat.id, text, reply_markup=main_menu_kb(tg_id))
    bot.send_message(msg.chat.id, "👇 Choose an option:", reply_markup=kb)

@bot.message_handler(func=lambda m: m.text == "🏠 Main Menu")
def cmd_home(msg):
    clear_state(msg.from_user.id)
    cmd_start(msg)

@bot.message_handler(commands=["help"])
@bot.message_handler(func=lambda m: m.text == "❓ Help")
def cmd_help(msg):
    bot.send_message(msg.chat.id,
        "📖 <b>DevLaunch India — Help</b>\n\n"
        "📁 <b>Script Hosting</b>\n"
        "  Send .py/.js/.zip → auto-hosted\n"
        "  Auto-installs all dependencies\n\n"
        "📦 <b>Deploy from GitHub</b>\n"
        "  Clone → install → run\n"
        "  Full build command support\n\n"
        "🐋 <b>Docker Containers</b>\n"
        f"  Isolated per user {'✅' if DOCKER_AVAILABLE else '❌ (unavailable)'}\n"
        "  CPU + RAM limits enforced\n\n"
        "🤖 <b>AI Error Fix</b>\n"
        "  Paste logs → get fix suggestions\n"
        "  Supports 10+ error types\n\n"
        "🤖 <b>Bot Templates</b>\n"
        "  5 prebuilt bots, 1-click deploy\n\n"
        "💰 <b>Credits & Plans</b>\n"
        f"  Free: {PLANS['free']['apps']} app | Starter: {PLANS['starter']['apps']} | Pro: {PLANS['pro']['apps']} | Elite: {PLANS['elite']['apps']}\n\n"
        "💳 <b>UPI Payment — No credit card!</b>\n"
        f"  UPI: {UPI_ID}\n\n"
        "🔗 <b>Referral</b>\n"
        "  +1 credit per friend invited\n\n"
        f"📢 {CHANNEL}",
        reply_markup=main_menu_kb(msg.from_user.id)
    )

@bot.message_handler(func=lambda m: m.text == "👤 Profile")
def cmd_profile(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    plan = get_user_plan(user)
    scripts = get_user_scripts(user["id"])
    deploys = get_user_deployments(user["id"])
    running = sum(1 for s in scripts if s["status"] == "running")
    sub_status = "✅ Active" if is_subscribed(user["id"]) else "❌ None"
    ref_count = db_exec("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user["id"],), "one")[0]
    suspended = "🔴 Suspended" if user["is_suspended"] else ""
    bot.send_message(msg.chat.id,
        f"👤 <b>Your Profile</b> {suspended}\n\n"
        f"🆔 Telegram ID: <code>{tg_id}</code>\n"
        f"👤 Username: @{user['username'] or 'N/A'}\n"
        f"💰 Credits: <b>{user['credits']:.1f}</b>\n"
        f"👑 Plan: <b>{plan['label']}</b>\n"
        f"📜 Subscription: {sub_status}\n"
        f"📦 Apps: <b>{len(scripts)}/{plan['apps']}</b> ({running} running)\n"
        f"🚀 Total Deploys: {user['total_deploys']}\n"
        f"🔄 Total Restarts: {user['total_restarts']}\n"
        f"👥 Referrals: {ref_count} (+{ref_count:.1f} credits)\n"
        f"📅 Joined: {str(user['join_date'])[:10]}\n"
        f"🔑 Ref Code: <code>{user['referral_code']}</code>\n\n"
        f"🌐 Dashboard: {BASE_URL}",
        reply_markup=main_menu_kb(tg_id)
    )

@bot.message_handler(func=lambda m: m.text == "🔗 Referral")
def cmd_referral(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    link = f"https://t.me/{BOT_USERNAME.lstrip('@')}?start={user['referral_code']}"
    count = db_exec("SELECT COUNT(*) FROM referrals WHERE referrer_id=?", (user["id"],), "one")[0]
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📤 Share Referral Link",
           url=f"https://t.me/share/url?url={link}&text=🚀+Deploy+on+DevLaunch+India!"))
    bot.send_message(msg.chat.id,
        f"🔗 <b>Referral Program</b>\n\n"
        f"Earn <b>+1 credit</b> for every friend you invite!\n\n"
        f"📤 Your referral link:\n<code>{link}</code>\n\n"
        f"📊 Stats:\n"
        f"├ 👥 Referrals: <b>{count}</b>\n"
        f"└ 💰 Earned: <b>{count:.1f} credits</b>",
        reply_markup=kb
    )

# ── My Scripts ───────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🚀 My Scripts")
def cmd_scripts(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    scripts = get_user_scripts(user["id"])
    plan = get_user_plan(user)
    limit = plan["apps"]
    if not scripts:
        bot.send_message(msg.chat.id,
            f"📦 <b>My Scripts</b>\n\n"
            f"No scripts yet! Send a <b>.py</b>, <b>.js</b>, or <b>.zip</b> file.\n"
            f"Scripts: 0/{limit}", reply_markup=main_menu_kb(tg_id))
        return
    text = f"📦 <b>My Scripts</b> ({len(scripts)}/{limit})\n\n"
    kb = types.InlineKeyboardMarkup(row_width=2)
    for s in scripts[:10]:
        icon = {"running": "🟢", "stopped": "🔴", "error": "🟠", "blocked": "⛔"}.get(s["status"], "⚪")
        text += f"{icon} <b>{s['name']}</b> [{s['file_type'].upper()}] — restarts: {s['restart_count']}\n"
        kb.row(
            types.InlineKeyboardButton(
                "▶️" if s["status"] != "running" else "⏹",
                callback_data=f"sc_{'start' if s['status'] != 'running' else 'stop'}_{s['id']}"
            ),
            types.InlineKeyboardButton("📋 Logs", callback_data=f"sc_logs_{s['id']}"),
            types.InlineKeyboardButton("🔧 AI Fix", callback_data=f"sc_aifix_{s['id']}"),
            types.InlineKeyboardButton("🗑", callback_data=f"sc_del_{s['id']}"),
        )
    bot.send_message(msg.chat.id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("sc_"))
def cb_script(call):
    parts = call.data.split("_")
    action = parts[1]
    sid = int(parts[2])
    tg_id = call.from_user.id
    user = get_user_by_tg(tg_id)
    script = db_exec("SELECT * FROM hosted_scripts WHERE id=? AND user_id=?", (sid, user["id"]), "one")
    if not script:
        bot.answer_callback_query(call.id, "Script not found!")
        return
    if action == "start":
        ok, res = run_script_process(
            sid, script["file_path"],
            str(Path(script["file_path"]).parent),
            script["file_type"], user["id"]
        )
        bot.answer_callback_query(call.id, f"{'✅ Started' if ok else '❌ ' + str(res)[:40]}")
    elif action == "stop":
        stop_script(sid)
        bot.answer_callback_query(call.id, "⏹ Stopped")
    elif action == "logs":
        logs = (script["logs"] or "No logs yet.")[-3000:]
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            f"📋 <b>Logs — {script['name']}</b>\n\n<pre>{logs}</pre>")
    elif action == "aifix":
        bot.answer_callback_query(call.id)
        if not script["logs"]:
            bot.send_message(call.message.chat.id, "No logs found. Run the script first!")
            return
        suggestion = ai_suggest_fix(script["logs"])
        db_exec("INSERT INTO ai_fix_log (user_id,error_text,suggestion) VALUES (?,?,?)",
                (user["id"], script["logs"][-500:], suggestion))
        bot.send_message(call.message.chat.id, suggestion)
    elif action == "del":
        stop_script(sid)
        try: Path(script["file_path"]).unlink(missing_ok=True)
        except: pass
        db_exec("DELETE FROM hosted_scripts WHERE id=?", (sid,))
        bot.answer_callback_query(call.id, "🗑 Deleted")

# ── File Upload Handler ───────────────────────────────────────────────
@bot.message_handler(content_types=["document"])
def handle_file(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    if user["is_banned"] or user["is_suspended"]:
        bot.reply_to(msg, "❌ Account suspended. Contact support.")
        return
    scripts = get_user_scripts(user["id"])
    limit = get_user_plan(user)["apps"]
    if len(scripts) >= limit:
        bot.reply_to(msg, f"❌ App limit reached ({limit}). Upgrade your plan!")
        return
    doc = msg.document
    fname = doc.file_name or "script"
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    if ext not in ["py", "js", "zip"]:
        bot.reply_to(msg, "❌ Only .py, .js, and .zip files supported.")
        return
    wait = bot.reply_to(msg, "⏳ Downloading & scanning file...")
    try:
        finfo = bot.get_file(doc.file_id)
        fbytes = bot.download_file(finfo.file_path)
    except Exception as e:
        bot.edit_message_text(f"❌ Download failed: {e}", msg.chat.id, wait.message_id)
        return
    user_dir = BASE_DIR / "scripts" / str(tg_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^\w\-.]", "_", fname)
    fpath = user_dir / safe_name
    fpath.write_bytes(fbytes)

    run_ext = ext
    run_path = str(fpath)
    dep_info = ""

    if ext == "zip":
        extract_dir = user_dir / safe_name.replace(".zip", "")
        extract_dir.mkdir(exist_ok=True)
        with zipfile.ZipFile(fpath, 'r') as z:
            z.extractall(extract_dir)
        for candidate in ["main.py","app.py","bot.py","index.js","main.js","run.py"]:
            cf = extract_dir / candidate
            if cf.exists():
                run_ext = cf.suffix.lstrip(".")
                run_path = str(cf)
                break
        else:
            py_files = list(extract_dir.glob("*.py"))
            js_files = list(extract_dir.glob("*.js"))
            mf = py_files[0] if py_files else (js_files[0] if js_files else None)
            if not mf:
                bot.edit_message_text("❌ No runnable file found in ZIP.", msg.chat.id, wait.message_id)
                return
            run_ext = mf.suffix.lstrip(".")
            run_path = str(mf)

    # Pre-flight abuse scan
    code_text = Path(run_path).read_text(errors="ignore") if run_ext == "py" else ""
    findings = abuse_detector.scan_code(code_text)
    if findings:
        atype, detail = findings[0]
        bot.edit_message_text(
            f"🚫 <b>File blocked!</b>\n\nAbuse pattern detected: <code>{atype}</code>\n"
            f"Pattern: <code>{detail}</code>\n\nIf this is a false positive, contact support.",
            msg.chat.id, wait.message_id
        )
        db_exec("INSERT INTO abuse_log (user_id,abuse_type,details,action_taken) VALUES (?,?,?,?)",
                (user["id"], atype, detail, "upload_blocked"))
        return

    # Auto deps
    if run_ext == "py":
        imports = detect_imports(code_text)
        installed = auto_install_deps(imports)
        if installed:
            dep_info = f"\n📦 Auto-installed: <code>{', '.join(installed)}</code>"

    sid = db_exec(
        "INSERT INTO hosted_scripts (user_id,name,filename,file_type,file_path) VALUES (?,?,?,?,?)",
        (user["id"], fname, safe_name, run_ext, run_path), "id"
    )
    log_activity(user["id"], "script_upload", fname)
    kb = types.InlineKeyboardMarkup()
    kb.row(
        types.InlineKeyboardButton("▶️ Start Now", callback_data=f"sc_start_{sid}"),
        types.InlineKeyboardButton("⏸ Keep Stopped", callback_data=f"sc_noop_{sid}"),
    )
    kb.add(types.InlineKeyboardButton("✅ Enable Auto-Restart", callback_data=f"sc_autorestart_{sid}"))
    bot.edit_message_text(
        f"✅ <b>Script Hosted!</b>\n\n"
        f"📄 Name: <b>{fname}</b>\n"
        f"🔧 Type: <b>{run_ext.upper()}</b>\n"
        f"📁 Slots: {len(scripts)+1}/{limit}"
        f"{dep_info}\n\n"
        f"🛡️ Security scan: <b>PASSED</b>\n\n"
        f"Start the script?",
        msg.chat.id, wait.message_id, reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("sc_noop_"))
def cb_noop(call): bot.answer_callback_query(call.id, "Saved but not started.")

@bot.callback_query_handler(func=lambda c: c.data.startswith("sc_autorestart_"))
def cb_autorestart(call):
    sid = int(call.data.split("_")[2])
    db_exec("UPDATE hosted_scripts SET auto_restart=1 WHERE id=?", (sid,))
    bot.answer_callback_query(call.id, "✅ Auto-restart enabled!")

# ── Deploy App ─────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "📦 Deploy App")
def cmd_deploy(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    plan = get_user_plan(user)
    deploys = get_user_deployments(user["id"])
    if len(deploys) >= plan["apps"] and tg_id not in ADMIN_IDS:
        bot.send_message(msg.chat.id,
            f"❌ Deployment limit reached ({plan['apps']}).\nUpgrade your plan for more!",
            reply_markup=main_menu_kb(tg_id))
        return
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🐙 From GitHub", callback_data="dep_github"),
        types.InlineKeyboardButton("📁 From ZIP/File", callback_data="dep_file"),
    )
    bot.send_message(msg.chat.id,
        f"📦 <b>Deploy App</b>\n\n"
        f"Credits available: <b>{user['credits']:.1f}</b>\n"
        f"GitHub deploy costs: <b>{COSTS['github_deploy']}cr</b>\n"
        f"File deploy costs: <b>{COSTS['file_upload']}cr</b>\n\n"
        f"Choose deployment method:",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data == "dep_github")
def cb_dep_github(call):
    tg_id = call.from_user.id
    user = get_user_by_tg(tg_id)
    ok, cnt, mx = check_rate_limit(user["id"], "deploy")
    if not ok:
        bot.answer_callback_query(call.id, f"Rate limit: {mx} deploys/hour. Try again later.")
        return
    if user["credits"] < COSTS["github_deploy"]:
        bot.answer_callback_query(call.id, f"Need {COSTS['github_deploy']} credits!")
        return
    set_state(tg_id, "dep_github_url")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
        "🐙 <b>GitHub Deploy</b>\n\n"
        "Send the <b>GitHub repo URL</b>:\n"
        "Example: <code>https://github.com/user/my-bot</code>",
        reply_markup=back_kb()
    )

@bot.callback_query_handler(func=lambda c: c.data == "dep_file")
def cb_dep_file(call):
    tg_id = call.from_user.id
    user = get_user_by_tg(tg_id)
    if user["credits"] < COSTS["file_upload"]:
        bot.answer_callback_query(call.id, f"Need {COSTS['file_upload']} credits!")
        return
    set_state(tg_id, "dep_file_wait")
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
        "📁 <b>File Deploy</b>\n\n"
        "Send a <b>ZIP file</b> or Python/JS file to deploy.\n"
        "Include a <code>requirements.txt</code> in your ZIP.",
        reply_markup=back_kb()
    )

# Deploy step: collect GitHub URL
@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "dep_github_url")
def step_github_url(msg):
    tg_id = msg.from_user.id
    url = msg.text.strip()
    if not re.match(r"https://(github|gitlab)\.com/\S+", url):
        bot.reply_to(msg, "❌ Invalid URL. Must be a GitHub/GitLab repo link.")
        return
    set_state(tg_id, "dep_github_branch", {"url": url})
    bot.reply_to(msg, "🌿 Enter the <b>branch name</b> (or send <code>main</code>):")

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "dep_github_branch")
def step_github_branch(msg):
    tg_id = msg.from_user.id
    st = get_state(tg_id)
    branch = msg.text.strip() or "main"
    st["data"]["branch"] = branch
    set_state(tg_id, "dep_github_startcmd", st["data"])
    bot.reply_to(msg, "⚙️ Enter the <b>start command</b>:\n"
                      "Example: <code>python main.py</code> or <code>node index.js</code>")

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "dep_github_startcmd")
def step_github_startcmd(msg):
    tg_id = msg.from_user.id
    st = get_state(tg_id)
    st["data"]["start_cmd"] = msg.text.strip()
    set_state(tg_id, "dep_github_env", st["data"])
    bot.reply_to(msg,
        "🔐 Enter <b>environment variables</b> (or send <code>skip</code>):\n\n"
        "Format: <code>KEY=value,KEY2=value2</code>\n"
        "Example: <code>BOT_TOKEN=123456:abc,PORT=8080</code>"
    )

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "dep_github_env")
def step_github_env(msg):
    tg_id = msg.from_user.id
    st = get_state(tg_id)
    user = get_user_by_tg(tg_id)
    env_vars = {}
    if msg.text.strip().lower() != "skip":
        for pair in msg.text.strip().split(","):
            if "=" in pair:
                k, v = pair.split("=", 1)
                env_vars[k.strip()] = v.strip()
    clear_state(tg_id)
    wait = bot.reply_to(msg, "⏳ Deploying from GitHub... This may take a minute.")
    data = st["data"]

    def do_deploy():
        if not deduct_credits(user["id"], COSTS["github_deploy"]):
            bot.edit_message_text("❌ Insufficient credits!", msg.chat.id, wait.message_id)
            return
        ok, logs, did = deploy_from_github(
            user["id"], data["url"],
            data["url"].rstrip("/").split("/")[-1],
            start_cmd=data.get("start_cmd", "python main.py"),
            env_vars=env_vars,
            branch=data.get("branch", "main")
        )
        log_activity(user["id"], "github_deploy", data["url"])
        icon = "✅" if ok else "❌"
        status_text = f"{icon} <b>Deploy {'Success' if ok else 'Failed'}!</b>\n\n"
        if did:
            status_text += f"🆔 Deploy ID: <code>{did}</code>\n"
        status_text += f"\n<pre>{logs[-1500:]}</pre>"
        if not ok:
            suggestion = ai_suggest_fix(logs)
            status_text += f"\n\n{suggestion}"
        bot.edit_message_text(status_text, msg.chat.id, wait.message_id,
                              reply_markup=main_menu_kb(tg_id))

    threading.Thread(target=do_deploy, daemon=True).start()

# Deploy from file (during file_wait state)
@bot.message_handler(content_types=["document"],
    func=lambda m: get_state(m.from_user.id)["state"] == "dep_file_wait")
def handle_deploy_file(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id)
    clear_state(tg_id)
    doc = msg.document
    fname = doc.file_name or "deploy.zip"
    wait = bot.reply_to(msg, "⏳ Downloading and deploying...")
    try:
        finfo = bot.get_file(doc.file_id)
        fbytes = bot.download_file(finfo.file_path)
    except Exception as e:
        bot.edit_message_text(f"❌ Download failed: {e}", msg.chat.id, wait.message_id)
        return
    fpath = BASE_DIR / "uploads" / f"{tg_id}_{int(time.time())}_{fname}"
    fpath.write_bytes(fbytes)

    def do_deploy():
        if not deduct_credits(user["id"], COSTS["file_upload"]):
            bot.edit_message_text("❌ Insufficient credits!", msg.chat.id, wait.message_id)
            return
        ok, logs, did = deploy_from_file(user["id"], fpath, fname.replace(".zip","").replace(".py",""))
        icon = "✅" if ok else "❌"
        bot.edit_message_text(
            f"{icon} <b>Deploy {'Success' if ok else 'Failed'}!</b>\n\n<pre>{logs[-1000:]}</pre>",
            msg.chat.id, wait.message_id, reply_markup=main_menu_kb(tg_id)
        )

    threading.Thread(target=do_deploy, daemon=True).start()

# ── Deploy History & Rollback ──────────────────────────────────────────
@bot.message_handler(commands=["history"])
def cmd_history(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    deploys = get_user_deployments(user["id"])[:10]
    if not deploys:
        bot.reply_to(msg, "No deployments yet.")
        return
    kb = types.InlineKeyboardMarkup(row_width=1)
    text = "📋 <b>Deploy History</b>\n\n"
    for d in deploys:
        icon = {"ready": "✅", "failed": "❌", "pending": "⏳"}.get(d["status"], "⚪")
        text += f"{icon} <b>#{d['id']}</b> {d['name']} [{d['type']}] {d['status']}\n"
        text += f"   📅 {str(d['created_at'])[:16]} | commit: {d['commit_hash'] or 'N/A'}\n"
        if d["type"] == "github":
            kb.add(types.InlineKeyboardButton(
                f"🔄 Rollback #{d['id']}", callback_data=f"rollback_{d['id']}"
            ))
    bot.reply_to(msg, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("rollback_"))
def cb_rollback(call):
    did = int(call.data.split("_")[1])
    tg_id = call.from_user.id
    user = get_user_by_tg(tg_id)
    bot.answer_callback_query(call.id, "⏳ Rolling back...")
    wait = bot.send_message(call.message.chat.id, "⏳ Initiating rollback...")

    def do_rollback():
        ok, logs, new_did = rollback_deployment(did, user["id"])
        bot.edit_message_text(
            f"{'✅' if ok else '❌'} <b>Rollback {'complete' if ok else 'failed'}</b>\n\n<pre>{str(logs)[-1000:]}</pre>",
            call.message.chat.id, wait.message_id
        )

    threading.Thread(target=do_rollback, daemon=True).start()

# ── Containers ─────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🐋 Containers")
def cmd_containers(msg):
    if not DOCKER_AVAILABLE:
        bot.send_message(msg.chat.id,
            "🐋 <b>Docker Containers</b>\n\n"
            "⚠️ Docker is not available on this server.\n"
            "Contact admin to enable containerized deployments.",
            reply_markup=main_menu_kb(msg.from_user.id))
        return
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    conts = db_exec("SELECT * FROM containers WHERE user_id=? ORDER BY created_at DESC",
                    (user["id"],), "all") or []
    if not conts:
        bot.send_message(msg.chat.id,
            "🐋 <b>My Containers</b>\n\nNo containers yet.\n"
            "Deploy from GitHub to create a container!",
            reply_markup=main_menu_kb(tg_id))
        return
    kb = types.InlineKeyboardMarkup(row_width=3)
    text = f"🐋 <b>My Containers</b> ({len(conts)})\n\n"
    for c in conts:
        live_status = docker_mgr.get_status(c["container_id"]) if c["container_id"] else "unknown"
        icon = {"running": "🟢", "stopped": "🔴", "exited": "🟡"}.get(live_status, "⚪")
        text += f"{icon} <b>{c['name']}</b> | {c['ram_limit']} RAM | restarts: {c['restart_count']}\n"
        kb.row(
            types.InlineKeyboardButton("🔄 Restart", callback_data=f"ct_restart_{c['id']}"),
            types.InlineKeyboardButton("⏹ Stop", callback_data=f"ct_stop_{c['id']}"),
            types.InlineKeyboardButton("📊 Stats", callback_data=f"ct_stats_{c['id']}"),
        )
    bot.send_message(msg.chat.id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("ct_"))
def cb_container(call):
    parts = call.data.split("_")
    action = parts[1]
    cid = int(parts[2])
    tg_id = call.from_user.id
    user = get_user_by_tg(tg_id)
    cont = db_exec("SELECT * FROM containers WHERE id=? AND user_id=?", (cid, user["id"]), "one")
    if not cont:
        bot.answer_callback_query(call.id, "Container not found!")
        return
    if action == "restart":
        ok, cnt, mx = check_rate_limit(user["id"], "restart")
        if not ok:
            bot.answer_callback_query(call.id, f"Rate limit: {mx} restarts/hour!")
            return
        docker_mgr.restart_container(cont["container_id"])
        db_exec("UPDATE containers SET restart_count=restart_count+1 WHERE id=?", (cid,))
        db_exec("UPDATE users SET total_restarts=total_restarts+1 WHERE id=?", (user["id"],))
        bot.answer_callback_query(call.id, "🔄 Container restarted!")
    elif action == "stop":
        docker_mgr.stop_container(cont["container_id"])
        db_exec("UPDATE containers SET status='stopped' WHERE id=?", (cid,))
        bot.answer_callback_query(call.id, "⏹ Container stopped")
    elif action == "stats":
        stats = docker_mgr.get_stats(cont["container_id"])
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            f"📊 <b>Container Stats — {cont['name']}</b>\n\n"
            f"⚡ CPU: <b>{stats['cpu']:.1f}%</b>\n"
            f"💾 RAM: <b>{stats['ram_mb']:.1f} MB</b> ({stats['ram_pct']:.1f}%)\n"
            f"🔄 Restarts: <b>{cont['restart_count']}</b>\n"
            f"📅 Created: {str(cont['created_at'])[:16]}"
        )

# ── Templates ──────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🤖 Templates")
def cmd_templates(msg):
    tg_id = msg.from_user.id
    kb = types.InlineKeyboardMarkup(row_width=1)
    text = "🤖 <b>Bot Templates</b>\n\nDeploy prebuilt bots instantly!\n\n"
    for key, tpl in BOT_TEMPLATES.items():
        text += f"{tpl['icon']} <b>{tpl['name']}</b>\n{tpl['desc']}\n\n"
        kb.add(types.InlineKeyboardButton(
            f"{tpl['icon']} Deploy {tpl['name']}",
            callback_data=f"tpl_select_{key}"
        ))
    bot.send_message(msg.chat.id, text, reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("tpl_select_"))
def cb_tpl_select(call):
    key = call.data.split("_", 2)[2]
    tg_id = call.from_user.id
    tpl = BOT_TEMPLATES.get(key)
    if not tpl:
        bot.answer_callback_query(call.id, "Template not found")
        return
    user = get_user_by_tg(tg_id)
    if user["credits"] < COSTS["template"] and tg_id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, f"Need {COSTS['template']} credits!")
        return
    set_state(tg_id, "tpl_await_token", {"key": key})
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id,
        f"{tpl['icon']} <b>{tpl['name']}</b>\n\n"
        f"Enter your <b>Telegram Bot Token</b>\n"
        f"(Get from @BotFather)\n\n"
        f"Or send <code>skip</code> to use placeholder:",
        reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "tpl_await_token")
def handle_tpl_token(msg):
    tg_id = msg.from_user.id
    st = get_state(tg_id)
    clear_state(tg_id)
    user = get_user_by_tg(tg_id)
    token = "" if msg.text.strip().lower() == "skip" else msg.text.strip()
    key = st["data"]["key"]
    if tg_id not in ADMIN_IDS:
        deduct_credits(user["id"], COSTS["template"])
    ok, result_msg, sid = deploy_template(user["id"], key, token)
    if ok and sid:
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("▶️ Start Now", callback_data=f"sc_start_{sid}"),
            types.InlineKeyboardButton("📋 View Script", callback_data=f"sc_logs_{sid}"),
        )
        bot.reply_to(msg, f"✅ {result_msg}\n\n"
                         f"Bot template deployed and ready!", reply_markup=kb)
    else:
        bot.reply_to(msg, f"❌ {result_msg}")

# ── AI Fix ──────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "🤖 AI Fix")
def cmd_aifix(msg):
    tg_id = msg.from_user.id
    set_state(tg_id, "aifix_await_logs")
    bot.send_message(msg.chat.id,
        "🤖 <b>AI Error Fix</b>\n\n"
        "Paste your <b>error logs</b> and I'll suggest fixes!\n\n"
        "Supports:\n"
        "• ModuleNotFoundError\n• SyntaxError\n• Port conflicts\n"
        "• JWT errors\n• OOM errors\n• File not found\n• Connection errors\n• And more!",
        reply_markup=back_kb()
    )

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "aifix_await_logs")
def handle_aifix(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    clear_state(tg_id)
    ok, _, _ = check_rate_limit(user["id"], "ai_fix")
    if not ok:
        bot.reply_to(msg, "⚠️ AI Fix rate limit reached (10/hour). Try again later.")
        return
    suggestion = ai_suggest_fix(msg.text)
    db_exec("INSERT INTO ai_fix_log (user_id,error_text,suggestion) VALUES (?,?,?)",
            (user["id"], msg.text[:1000], suggestion))
    bot.reply_to(msg, suggestion, reply_markup=main_menu_kb(tg_id))

# ── Credits ─────────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "💰 Credits")
def cmd_credits(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, pack in CREDIT_PACKS.items():
        kb.add(types.InlineKeyboardButton(f"💳 {pack['label']}", callback_data=f"buy_cr_{key}"))
    bot.send_message(msg.chat.id,
        f"💰 <b>Buy Credits</b>\n\n"
        f"Current balance: <b>{user['credits']:.1f} credits</b>\n\n"
        f"💡 Credit costs:\n"
        f"├ 📁 Script host: FREE\n"
        f"├ 📦 File deploy: {COSTS['file_upload']}cr\n"
        f"├ 🐙 GitHub deploy: {COSTS['github_deploy']}cr\n"
        f"├ 🤖 AI fix: {COSTS['ai_fix']}cr\n"
        f"└ 🤖 Template: {COSTS['template']}cr\n\n"
        f"Select a credit pack:",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_cr_"))
def cb_buy_credits(call):
    key = call.data.split("_", 2)[2]
    pack = CREDIT_PACKS.get(key)
    if not pack:
        bot.answer_callback_query(call.id, "Invalid pack")
        return
    tg_id = call.from_user.id
    user = get_user_by_tg(tg_id)
    pid = create_payment(user["id"], "credits", key, pack["price"])
    qr = generate_upi_qr(pack["price"], f"DL-CR-{pid}")
    bot.answer_callback_query(call.id)
    bot.send_photo(call.message.chat.id, qr,
        caption=(
            f"💳 <b>Buy {pack['credits']} Credits</b>\n\n"
            f"💰 Amount: ₹{pack['price']}\n"
            f"📱 UPI ID: <code>{UPI_ID}</code>\n"
            f"🔖 Reference: <code>DL-CR-{pid}</code>\n\n"
            f"After payment, send the <b>screenshot or UTR number</b> below 👇"
        )
    )
    set_state(tg_id, "await_payment_proof", {"pay_id": pid})

# ── Subscription ────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "👑 Subscribe")
def cmd_subscribe(msg):
    tg_id = msg.from_user.id
    user = get_user_by_tg(tg_id) or create_tg_user(tg_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, plan in PLANS.items():
        if key == "free": continue
        kb.add(types.InlineKeyboardButton(
            f"⭐ {plan['label']} — ₹{plan['price']}",
            callback_data=f"buy_sub_{key}"
        ))
    current_plan = get_user_plan(user)
    bot.send_message(msg.chat.id,
        f"👑 <b>Subscription Plans</b>\n\n"
        f"Current plan: <b>{current_plan['label']}</b>\n\n"
        f"📊 Plan comparison:\n"
        f"┌ Free: {PLANS['free']['apps']} app | 256MB RAM | Sleeps\n"
        f"├ Starter: {PLANS['starter']['apps']} apps | 512MB RAM | No sleep\n"
        f"├ Pro: {PLANS['pro']['apps']} apps | 1GB RAM | Custom domain\n"
        f"└ Elite: {PLANS['elite']['apps']} apps | 2GB RAM | Priority support\n\n"
        f"Choose a plan:",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_sub_"))
def cb_buy_sub(call):
    key = call.data.split("_", 2)[2]
    plan = PLANS.get(key)
    if not plan:
        bot.answer_callback_query(call.id, "Invalid plan")
        return
    tg_id = call.from_user.id
    user = get_user_by_tg(tg_id)
    pid = create_payment(user["id"], "subscription", key, plan["price"])
    qr = generate_upi_qr(plan["price"], f"DL-SUB-{pid}")
    bot.answer_callback_query(call.id)
    bot.send_photo(call.message.chat.id, qr,
        caption=(
            f"👑 <b>{plan['label']}</b>\n\n"
            f"💰 Amount: ₹{plan['price']}\n"
            f"📱 UPI: <code>{UPI_ID}</code>\n"
            f"🔖 Ref: <code>DL-SUB-{pid}</code>\n\n"
            f"📦 Includes:\n"
            f"├ {plan['apps']} apps\n"
            f"├ {plan['ram']} RAM each\n"
            f"└ {'No sleep' if not plan['sleep'] else 'Sleep after inactivity'}\n\n"
            f"Send <b>payment screenshot</b> after paying 👇"
        )
    )
    set_state(tg_id, "await_payment_proof", {"pay_id": pid})

# ── Payment Screenshot ──────────────────────────────────────────────────
@bot.message_handler(content_types=["photo"],
    func=lambda m: get_state(m.from_user.id)["state"] == "await_payment_proof")
def handle_payment_proof(msg):
    tg_id = msg.from_user.id
    st = get_state(tg_id)
    pid = st["data"].get("pay_id")
    clear_state(tg_id)
    photo = msg.photo[-1]
    finfo = bot.get_file(photo.file_id)
    fbytes = bot.download_file(finfo.file_path)
    ss_path = BASE_DIR / "payments" / f"{pid}_{tg_id}.jpg"
    ss_path.write_bytes(fbytes)
    db_exec("UPDATE payments SET screenshot_path=? WHERE id=?", (str(ss_path), pid))
    pay = db_exec("SELECT * FROM payments WHERE id=?", (pid,), "one")
    for aid in ADMIN_IDS:
        try:
            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok_{pid}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"pay_no_{pid}"),
            )
            bot.send_photo(aid, photo.file_id,
                caption=(
                    f"💳 <b>Payment Request #{pid}</b>\n\n"
                    f"👤 User: {tg_id} (@{msg.from_user.username})\n"
                    f"📦 {pay['type']} | {pay['plan_or_pack']}\n"
                    f"💰 ₹{pay['amount']}\n"
                    f"📅 {str(pay['created_at'])[:16]}"
                ), reply_markup=kb
            )
        except Exception: pass
    bot.reply_to(msg,
        f"✅ <b>Payment proof submitted!</b>\n\n"
        f"Our team will verify within a few minutes.\n"
        f"Reference: <code>DL-{pid}</code>"
    )

@bot.message_handler(content_types=["text"],
    func=lambda m: get_state(m.from_user.id)["state"] == "await_payment_proof")
def handle_payment_utr(msg):
    """Accept UTR/transaction ID as text too."""
    tg_id = msg.from_user.id
    st = get_state(tg_id)
    pid = st["data"].get("pay_id")
    clear_state(tg_id)
    utr = msg.text.strip()
    db_exec("UPDATE payments SET upi_txn_id=? WHERE id=?", (utr, pid))
    pay = db_exec("SELECT * FROM payments WHERE id=?", (pid,), "one")
    for aid in ADMIN_IDS:
        try:
            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok_{pid}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"pay_no_{pid}"),
            )
            bot.send_message(aid,
                f"💳 <b>Payment #{pid} (UTR)</b>\n\n"
                f"👤 {tg_id} (@{msg.from_user.username})\n"
                f"📦 {pay['type']} | {pay['plan_or_pack']}\n"
                f"💰 ₹{pay['amount']}\n"
                f"🔖 UTR: <code>{utr}</code>",
                reply_markup=kb
            )
        except Exception: pass
    bot.reply_to(msg,
        f"✅ <b>UTR submitted!</b>\n\nRef: <code>DL-{pid}</code>\n\nVerification in progress."
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("pay_"))
def cb_payment_action(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Unauthorized")
        return
    parts = call.data.split("_")
    action = parts[1]
    pid = int(parts[2])
    if action == "ok":
        ok, res = approve_payment(pid, call.from_user.id)
        pay = db_exec("SELECT * FROM payments WHERE id=?", (pid,), "one")
        user = get_user_by_id(pay["user_id"])
        try:
            bot.send_message(user["telegram_id"],
                f"✅ <b>Payment Approved!</b>\n"
                f"Your {pay['type']} ({pay['plan_or_pack']}) is now active!\n"
                f"Ref: DL-{pid}")
        except: pass
        bot.answer_callback_query(call.id, "✅ Approved!")
        bot.edit_message_caption(f"✅ APPROVED by {call.from_user.id}",
                                  call.message.chat.id, call.message.message_id)
    elif action == "no":
        reject_payment(pid, call.from_user.id)
        pay = db_exec("SELECT * FROM payments WHERE id=?", (pid,), "one")
        user = get_user_by_id(pay["user_id"])
        try:
            bot.send_message(user["telegram_id"],
                f"❌ <b>Payment Rejected</b>\n"
                f"Contact support if you believe this is wrong.\nRef: DL-{pid}")
        except: pass
        bot.answer_callback_query(call.id, "❌ Rejected")
        bot.edit_message_caption(f"❌ REJECTED by {call.from_user.id}",
                                  call.message.chat.id, call.message.message_id)

# ── Admin Panel ─────────────────────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin Panel")
def cmd_admin(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    stats = get_stats()
    sys_m = get_system_metrics()
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("👥 Users", callback_data="adm_users"),
        types.InlineKeyboardButton("💳 Payments", callback_data="adm_payments"),
        types.InlineKeyboardButton("🚨 Abuse Alerts", callback_data="adm_abuse"),
        types.InlineKeyboardButton("📢 Broadcast", callback_data="adm_broadcast"),
        types.InlineKeyboardButton("💰 Add Credits", callback_data="adm_addcredits"),
        types.InlineKeyboardButton("🔨 Ban User", callback_data="adm_ban"),
        types.InlineKeyboardButton("🔓 Unban", callback_data="adm_unban"),
        types.InlineKeyboardButton("📊 Full Stats", callback_data="adm_stats"),
    )
    bot.send_message(msg.chat.id,
        f"⚙️ <b>Admin Panel</b>\n\n"
        f"👥 Users: {stats['users']} | Running: {stats['running']}\n"
        f"💳 Pending Payments: {stats['pending_pay']}\n"
        f"🚨 Abuse (24h): {stats['abuse_count']}\n"
        f"💰 Revenue: ₹{stats['revenue']:.0f}\n\n"
        f"🖥️ <b>System</b>\n"
        f"CPU: {sys_m['cpu_pct']:.1f}% | RAM: {sys_m['ram_pct']:.1f}%\n"
        f"Disk: {sys_m['disk_pct']:.1f}%",
        reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("adm_"))
def cb_admin(call):
    if call.from_user.id not in ADMIN_IDS:
        bot.answer_callback_query(call.id, "❌ Unauthorized")
        return
    action = call.data.split("_", 1)[1]

    if action == "stats":
        stats = get_stats()
        sys_m = get_system_metrics()
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            f"📊 <b>Full Platform Stats</b>\n\n"
            f"👥 Users: {stats['users']}\n"
            f"📜 Scripts: {stats['scripts']} ({stats['running']} running)\n"
            f"📦 Deployments: {stats['deployments']}\n"
            f"🐋 Containers: {stats['containers']}\n"
            f"💳 Pending payments: {stats['pending_pay']}\n"
            f"🚨 Abuse (24h): {stats['abuse_count']}\n"
            f"💰 Total Revenue: ₹{stats['revenue']:.0f}\n\n"
            f"🖥️ Host CPU: {sys_m['cpu_pct']:.1f}%\n"
            f"💾 Host RAM: {sys_m['ram_used_gb']:.1f}/{sys_m['ram_total_gb']:.1f} GB\n"
            f"💿 Host Disk: {sys_m['disk_used_gb']:.1f}/{sys_m['disk_total_gb']:.1f} GB\n"
            f"⚙️ Active Processes: {sys_m['proc_count']}"
        )

    elif action == "abuse":
        rows = db_exec("SELECT * FROM abuse_log ORDER BY detected_at DESC LIMIT 10", fetch="all") or []
        bot.answer_callback_query(call.id)
        if not rows:
            bot.send_message(call.message.chat.id, "✅ No abuse detected in last 24h!")
            return
        text = "🚨 <b>Abuse Log (Last 10)</b>\n\n"
        for r in rows:
            text += f"👤 User {r['user_id']} | {r['abuse_type']}\n{r['details'][:80]}\n📅 {str(r['detected_at'])[:16]}\n\n"
        bot.send_message(call.message.chat.id, text)

    elif action == "broadcast":
        set_state(call.from_user.id, "adm_broadcast_msg")
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            "📢 <b>Broadcast</b>\n\nSend the message to broadcast to all users:\n"
            "(HTML formatting supported)", reply_markup=back_kb())

    elif action == "addcredits":
        set_state(call.from_user.id, "adm_addcredits_input")
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id,
            "💰 <b>Add Credits</b>\n\n"
            "Format: <code>TELEGRAM_ID AMOUNT</code>\n"
            "Example: <code>123456789 50</code>", reply_markup=back_kb())

    elif action == "ban":
        set_state(call.from_user.id, "adm_ban_input")
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🔨 Send Telegram ID to ban:", reply_markup=back_kb())

    elif action == "unban":
        set_state(call.from_user.id, "adm_unban_input")
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "🔓 Send Telegram ID to unban:", reply_markup=back_kb())

    elif action == "users":
        users = db_exec("SELECT * FROM users ORDER BY join_date DESC LIMIT 15", fetch="all") or []
        bot.answer_callback_query(call.id)
        text = "👥 <b>Recent Users</b>\n\n"
        for u in users:
            icon = "🔴" if u["is_banned"] or u["is_suspended"] else "🟢"
            text += f"{icon} <code>{u['telegram_id']}</code> @{u['username']} | {u['credits']:.1f}cr | {u['plan']}\n"
        bot.send_message(call.message.chat.id, text)

    elif action == "payments":
        pays = db_exec(
            "SELECT p.*,u.telegram_id,u.username FROM payments p JOIN users u ON p.user_id=u.id "
            "WHERE p.status='pending' ORDER BY p.created_at DESC LIMIT 10", fetch="all"
        ) or []
        bot.answer_callback_query(call.id)
        if not pays:
            bot.send_message(call.message.chat.id, "✅ No pending payments!")
            return
        for p in pays:
            kb = types.InlineKeyboardMarkup()
            kb.row(
                types.InlineKeyboardButton("✅ Approve", callback_data=f"pay_ok_{p['id']}"),
                types.InlineKeyboardButton("❌ Reject", callback_data=f"pay_no_{p['id']}")
            )
            bot.send_message(call.message.chat.id,
                f"💳 #{p['id']} | {p['telegram_id']} (@{p['username']})\n"
                f"📦 {p['type']} | {p['plan_or_pack']} | ₹{p['amount']}\n"
                f"📅 {str(p['created_at'])[:16]}",
                reply_markup=kb
            )

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "adm_broadcast_msg")
def handle_adm_broadcast(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    clear_state(msg.from_user.id)
    users = db_exec("SELECT telegram_id FROM users WHERE is_banned=0 AND is_suspended=0", fetch="all") or []
    wait = bot.reply_to(msg, f"📢 Broadcasting to {len(users)} users...")
    sent = failed = 0
    for u in users:
        try:
            bot.forward_message(u["telegram_id"], msg.chat.id, msg.message_id)
            sent += 1
        except: failed += 1
        time.sleep(0.05)
    db_exec("INSERT INTO broadcast_log (admin_id,message,target,sent_count,failed_count) VALUES (?,?,?,?,?)",
            (msg.from_user.id, msg.text or "[media]", "all", sent, failed))
    bot.edit_message_text(f"✅ Broadcast done! Sent: {sent} | Failed: {failed}",
                          msg.chat.id, wait.message_id)

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] == "adm_addcredits_input")
def handle_adm_addcredits(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    clear_state(msg.from_user.id)
    try:
        parts = msg.text.strip().split()
        tgid = int(parts[0]); amount = float(parts[1])
        u = get_user_by_tg(tgid)
        if not u:
            bot.reply_to(msg, "❌ User not found")
            return
        add_credits(u["id"], amount, f"Admin grant by {msg.from_user.id}")
        bot.reply_to(msg, f"✅ Added {amount} credits to {tgid}")
        try: bot.send_message(tgid, f"💰 <b>+{amount} credits added</b> by admin!")
        except: pass
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {e}\nFormat: TELEGRAM_ID AMOUNT")

@bot.message_handler(func=lambda m: get_state(m.from_user.id)["state"] in ("adm_ban_input","adm_unban_input"))
def handle_adm_ban(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    state = get_state(msg.from_user.id)["state"]
    clear_state(msg.from_user.id)
    try:
        tgid = int(msg.text.strip())
        if state == "adm_ban_input":
            db_exec("UPDATE users SET is_banned=1 WHERE telegram_id=?", (tgid,))
            bot.reply_to(msg, f"🔨 User {tgid} banned")
        else:
            db_exec("UPDATE users SET is_banned=0,is_suspended=0 WHERE telegram_id=?", (tgid,))
            bot.reply_to(msg, f"🔓 User {tgid} unbanned")
    except Exception as e:
        bot.reply_to(msg, f"❌ Error: {e}")

# Admin commands
@bot.message_handler(commands=["addcredits"])
def cmd_addcredits_cmd(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        _, tid, amt = msg.text.split()
        u = get_user_by_tg(int(tid))
        add_credits(u["id"], float(amt), f"Admin {msg.from_user.id}")
        bot.reply_to(msg, f"✅ +{amt} credits to {tid}")
    except: bot.reply_to(msg, "Usage: /addcredits TG_ID AMOUNT")

@bot.message_handler(commands=["ban","unban"])
def cmd_ban_cmd(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    action = msg.text.split()[0].lstrip("/")
    try:
        tid = int(msg.text.split()[1])
        val = 1 if action == "ban" else 0
        db_exec("UPDATE users SET is_banned=? WHERE telegram_id=?", (val, tid))
        bot.reply_to(msg, f"{'🔨 Banned' if val else '🔓 Unbanned'}: {tid}")
    except: bot.reply_to(msg, f"Usage: /{action} TELEGRAM_ID")

@bot.message_handler(commands=["stats"])
def cmd_stats_cmd(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    stats = get_stats()
    sys_m = get_system_metrics()
    bot.reply_to(msg,
        f"📊 Users:{stats['users']} Scripts:{stats['scripts']} Running:{stats['running']}\n"
        f"Deploys:{stats['deployments']} Revenue:₹{stats['revenue']:.0f}\n"
        f"CPU:{sys_m['cpu_pct']:.1f}% RAM:{sys_m['ram_pct']:.1f}%"
    )

@bot.message_handler(commands=["nginx"])
def cmd_nginx(msg):
    if msg.from_user.id not in ADMIN_IDS: return
    try:
        parts = msg.text.split()
        subdomain = parts[1]; port = int(parts[2])
        config = generate_nginx_config(subdomain, port)
        bot.reply_to(msg, f"<pre>{config}</pre>")
    except: bot.reply_to(msg, "Usage: /nginx SUBDOMAIN PORT")

# ═══════════════════════════════════════════════════════════════════════
# SECTION 20: FLASK WEB DASHBOARD
# ═══════════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.secret_key = SECRET_KEY
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet",
                    logger=False, engineio_logger=False)

# ── HTML Templates ───────────────────────────────────────────────────

BASE_TMPL = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DevLaunch India — {{ title or "Dashboard" }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
<style>
:root {
  --bg: #080c14;
  --surface: #0d1421;
  --card: #111827;
  --border: #1f2937;
  --border-h: #374151;
  --accent: #6366f1;
  --accent-h: #818cf8;
  --cyan: #06b6d4;
  --green: #10b981;
  --red: #ef4444;
  --yellow: #f59e0b;
  --orange: #f97316;
  --text: #f1f5f9;
  --muted: #64748b;
  --muted2: #94a3b8;
  --mono: 'JetBrains Mono', monospace;
  --sans: 'Plus Jakarta Sans', sans-serif;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  min-height: 100vh;
  line-height: 1.6;
  background-image:
    radial-gradient(ellipse at 20% 0%, rgba(99,102,241,.08) 0%, transparent 60%),
    radial-gradient(ellipse at 80% 100%, rgba(6,182,212,.06) 0%, transparent 60%);
}

/* NAVBAR */
.navbar {
  position: sticky; top: 0; z-index: 100;
  background: rgba(8,12,20,.9);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 0 2rem;
  display: flex; align-items: center; height: 64px; gap: 2rem;
}
.nav-logo {
  display: flex; align-items: center; gap: .6rem;
  font-family: var(--mono); font-weight: 800; font-size: 1.1rem;
  background: linear-gradient(135deg, var(--accent), var(--cyan));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
  white-space: nowrap;
}
.nav-logo svg { width: 28px; flex-shrink: 0; }
.nav-links { display: flex; gap: 1rem; align-items: center; margin-left: auto; }
.nav-link {
  color: var(--muted); text-decoration: none;
  font-size: .875rem; font-weight: 500; padding: .4rem .7rem;
  border-radius: 6px; transition: all .15s;
}
.nav-link:hover { color: var(--text); background: var(--card); }
.nav-link.active { color: var(--accent); }
.nav-badge {
  background: var(--red); color: #fff;
  font-size: .65rem; font-weight: 700;
  padding: .1rem .4rem; border-radius: 20px; margin-left: .3rem;
}

/* LAYOUT */
.container { max-width: 1280px; margin: 0 auto; padding: 2rem 1.5rem; }
.page-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 2rem; flex-wrap: wrap; gap: 1rem;
}
.page-title {
  font-size: 1.75rem; font-weight: 800;
  background: linear-gradient(135deg, var(--text), var(--muted2));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}

/* GRID */
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 1.25rem; margin-bottom: 2rem; }
.grid-3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1.25rem; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }

/* CARDS */
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.5rem;
  transition: border-color .2s;
}
.card:hover { border-color: var(--border-h); }
.card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 1.25rem; padding-bottom: 1rem;
  border-bottom: 1px solid var(--border);
}
.card-title {
  font-size: 1rem; font-weight: 700; color: var(--text);
  display: flex; align-items: center; gap: .5rem;
}

/* STAT CARDS */
.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 1.5rem;
  position: relative; overflow: hidden;
}
.stat-card::before {
  content: ''; position: absolute;
  top: 0; right: 0; width: 120px; height: 120px;
  border-radius: 50%; opacity: .06;
  transform: translate(30%, -30%);
}
.stat-card.indigo::before { background: var(--accent); }
.stat-card.cyan::before   { background: var(--cyan); }
.stat-card.green::before  { background: var(--green); }
.stat-card.red::before    { background: var(--red); }
.stat-val {
  font-family: var(--mono); font-size: 2.5rem; font-weight: 800; line-height: 1;
  margin-bottom: .5rem;
}
.stat-val.indigo { color: var(--accent); }
.stat-val.cyan   { color: var(--cyan); }
.stat-val.green  { color: var(--green); }
.stat-val.red    { color: var(--red); }
.stat-label { font-size: .85rem; color: var(--muted); font-weight: 500; }
.stat-sub { font-size: .75rem; color: var(--muted); margin-top: .35rem; }

/* BUTTONS */
.btn {
  display: inline-flex; align-items: center; gap: .45rem;
  padding: .55rem 1.1rem; border-radius: 8px;
  border: 1px solid transparent;
  font-size: .875rem; font-weight: 600; cursor: pointer;
  text-decoration: none; transition: all .15s; white-space: nowrap;
}
.btn-primary   { background: var(--accent); color: #fff; border-color: var(--accent); }
.btn-primary:hover { background: var(--accent-h); }
.btn-danger    { background: rgba(239,68,68,.15); color: var(--red); border-color: var(--red); }
.btn-danger:hover { background: rgba(239,68,68,.25); }
.btn-success   { background: rgba(16,185,129,.15); color: var(--green); border-color: var(--green); }
.btn-success:hover { background: rgba(16,185,129,.25); }
.btn-ghost     { background: transparent; color: var(--muted); border-color: var(--border); }
.btn-ghost:hover { color: var(--text); border-color: var(--border-h); }
.btn-cyan      { background: rgba(6,182,212,.15); color: var(--cyan); border-color: var(--cyan); }
.btn-sm { padding: .35rem .75rem; font-size: .8rem; }

/* TABLE */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th {
  text-align: left; padding: .75rem 1rem;
  font-size: .75rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--muted);
  border-bottom: 1px solid var(--border);
}
td {
  padding: .875rem 1rem;
  border-bottom: 1px solid var(--border);
  font-size: .875rem; color: var(--muted2);
}
tr:hover td { background: rgba(255,255,255,.02); }
tr:last-child td { border-bottom: none; }

/* BADGES */
.badge {
  display: inline-flex; align-items: center; gap: .3rem;
  padding: .2rem .65rem; border-radius: 20px;
  font-size: .72rem; font-weight: 700;
}
.badge::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.badge-green   { background: rgba(16,185,129,.15); color: var(--green); }
.badge-red     { background: rgba(239,68,68,.15);  color: var(--red); }
.badge-yellow  { background: rgba(245,158,11,.15); color: var(--yellow); }
.badge-blue    { background: rgba(99,102,241,.15); color: var(--accent); }
.badge-gray    { background: rgba(100,116,139,.15);color: var(--muted); }

/* FORM */
.form-group { margin-bottom: 1.25rem; }
.form-label {
  display: block; font-size: .85rem; font-weight: 600;
  color: var(--muted2); margin-bottom: .5rem;
}
.form-control {
  width: 100%;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: .65rem 1rem;
  color: var(--text);
  font-size: .875rem;
  font-family: var(--sans);
  transition: border-color .15s;
}
.form-control:focus { outline: none; border-color: var(--accent); }
textarea.form-control { min-height: 100px; resize: vertical; font-family: var(--mono); }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }

/* TERMINAL */
.terminal {
  background: #000;
  border: 1px solid var(--border);
  border-radius: 12px;
  font-family: var(--mono);
  font-size: .8rem;
  color: #4ade80;
  padding: 1rem;
  height: 400px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.terminal-header {
  background: var(--surface);
  border: 1px solid var(--border);
  border-bottom: none;
  border-radius: 12px 12px 0 0;
  padding: .6rem 1rem;
  display: flex; align-items: center; gap: .5rem;
}
.term-dot { width: 12px; height: 12px; border-radius: 50%; }
.term-dot.red    { background: #ff5f57; }
.term-dot.yellow { background: #febc2e; }
.term-dot.green  { background: #28c840; }
.terminal-input {
  background: #000;
  border: 1px solid var(--border);
  border-top: 1px solid var(--border-h);
  border-radius: 0 0 12px 12px;
  display: flex; align-items: center;
  padding: .5rem 1rem;
}
.terminal-prompt { color: var(--green); font-family: var(--mono); font-size: .85rem; margin-right: .5rem; }
.terminal-cmd {
  flex: 1; background: transparent; border: none;
  color: var(--text); font-family: var(--mono); font-size: .85rem;
  outline: none;
}

/* CHARTS */
.chart-bar-wrap { display: flex; flex-direction: column; gap: .75rem; }
.chart-row { display: flex; align-items: center; gap: .75rem; }
.chart-label { font-size: .8rem; color: var(--muted); width: 80px; flex-shrink: 0; }
.chart-bar-bg { flex: 1; height: 8px; background: var(--surface); border-radius: 4px; overflow: hidden; }
.chart-bar { height: 100%; border-radius: 4px; transition: width .5s ease; }
.chart-val { font-family: var(--mono); font-size: .78rem; color: var(--muted2); width: 50px; text-align: right; flex-shrink: 0; }

/* PROGRESS */
.progress { height: 6px; background: var(--surface); border-radius: 3px; overflow: hidden; margin-top: .4rem; }
.progress-bar { height: 100%; border-radius: 3px; transition: width .5s; }
.progress-bar.indigo { background: linear-gradient(90deg, var(--accent), var(--accent-h)); }
.progress-bar.cyan   { background: linear-gradient(90deg, var(--cyan), #67e8f9); }
.progress-bar.green  { background: linear-gradient(90deg, var(--green), #6ee7b7); }
.progress-bar.red    { background: linear-gradient(90deg, var(--red), #fca5a5); }

/* ALERTS */
.alert {
  padding: .875rem 1.25rem; border-radius: 8px;
  border-left: 3px solid; margin-bottom: 1rem;
  font-size: .875rem; display: flex; align-items: flex-start; gap: .75rem;
}
.alert-success { background: rgba(16,185,129,.1);  border-color: var(--green); color: #6ee7b7; }
.alert-danger  { background: rgba(239,68,68,.1);   border-color: var(--red);   color: #fca5a5; }
.alert-info    { background: rgba(99,102,241,.1);  border-color: var(--accent);color: #a5b4fc; }
.alert-warning { background: rgba(245,158,11,.1);  border-color: var(--yellow);color: #fcd34d; }

/* TABS */
.tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem; }
.tab {
  padding: .65rem 1.25rem; font-size: .875rem; font-weight: 600;
  color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent;
  transition: all .15s; text-decoration: none;
}
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab:hover:not(.active) { color: var(--text); }

/* SIDEBAR */
.layout { display: grid; grid-template-columns: 240px 1fr; gap: 2rem; align-items: start; }
.sidebar { position: sticky; top: 80px; }
.sidebar-menu { display: flex; flex-direction: column; gap: .25rem; }
.sidebar-link {
  display: flex; align-items: center; gap: .75rem;
  padding: .65rem 1rem; border-radius: 10px;
  color: var(--muted); text-decoration: none;
  font-size: .875rem; font-weight: 500;
  transition: all .15s;
}
.sidebar-link:hover { color: var(--text); background: var(--card); }
.sidebar-link.active { color: var(--accent); background: rgba(99,102,241,.1); }
.sidebar-link svg { width: 18px; flex-shrink: 0; }

/* METRIC REALTIME */
.metric-live { display: flex; flex-direction: column; gap: 1rem; }
.metric-item { display: flex; flex-direction: column; gap: .4rem; }
.metric-top { display: flex; justify-content: space-between; align-items: center; }
.metric-name { font-size: .85rem; color: var(--muted2); font-weight: 500; }
.metric-number { font-family: var(--mono); font-size: .9rem; font-weight: 700; }

/* ANIMATIONS */
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.pulse { animation: pulse 2s infinite; }
@keyframes fadeIn { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:none} }
.fade-in { animation: fadeIn .3s ease both; }
@keyframes spin { to{transform:rotate(360deg)} }
.spin { animation: spin 1s linear infinite; }

/* SCROLLBAR */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--surface); }
::-webkit-scrollbar-thumb { background: var(--border-h); border-radius: 3px; }

/* RESPONSIVE */
@media(max-width:1024px){
  .grid-4{grid-template-columns:repeat(2,1fr);}
  .layout{grid-template-columns:1fr;}
  .sidebar{position:static;}
}
@media(max-width:640px){
  .grid-4,.grid-3,.grid-2,.form-row{grid-template-columns:1fr;}
  .navbar{padding:0 1rem;}
  .container{padding:1.25rem 1rem;}
  .nav-links .nav-link:not(.show-mobile){display:none;}
}
</style>
</head>
<body>
<nav class="navbar">
  <div class="nav-logo">
    <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
      <rect width="32" height="32" rx="8" fill="url(#g1)"/>
      <path d="M8 16L14 10L20 16L14 22L8 16Z" fill="rgba(255,255,255,.9)"/>
      <path d="M16 12L22 16L16 20" stroke="white" stroke-width="2" stroke-linecap="round"/>
      <defs><linearGradient id="g1" x1="0" y1="0" x2="32" y2="32" gradientUnits="userSpaceOnUse">
        <stop stop-color="#6366f1"/><stop offset="1" stop-color="#06b6d4"/>
      </linearGradient></defs>
    </svg>
    DevLaunch India
  </div>
  {% if session.admin %}
  <div class="nav-links">
    <a href="/dashboard" class="nav-link {% if active=='dash' %}active{% endif %}">Dashboard</a>
    <a href="/admin/users" class="nav-link {% if active=='users' %}active{% endif %}">Users</a>
    <a href="/admin/payments" class="nav-link {% if active=='pay' %}active{% endif %}">
      Payments
      {% if pending_pays %}<span class="nav-badge">{{ pending_pays }}</span>{% endif %}
    </a>
    <a href="/admin/abuse" class="nav-link {% if active=='abuse' %}active{% endif %}">Abuse</a>
    <a href="/admin/broadcast" class="nav-link {% if active=='bc' %}active{% endif %}">Broadcast</a>
    <a href="/metrics" class="nav-link {% if active=='metrics' %}active{% endif %}">Metrics</a>
    <a href="/terminal" class="nav-link show-mobile {% if active=='term' %}active{% endif %}">Terminal</a>
    <a href="/logout" class="btn btn-ghost btn-sm">Logout</a>
  </div>
  {% else %}
  <div class="nav-links">
    <a href="/login" class="btn btn-primary btn-sm">Admin Login</a>
  </div>
  {% endif %}
</nav>
<div class="container fade-in">
{% with msgs = get_flashed_messages(with_categories=true) %}
{% for cat, msg in msgs %}
<div class="alert alert-{{ 'success' if cat=='success' else 'danger' }}">
  <span>{% if cat=='success' %}✅{% else %}❌{% endif %}</span>
  <span>{{ msg }}</span>
</div>
{% endfor %}
{% endwith %}
{% block content %}{% endblock %}
</div>
</body>
</html>"""

LOGIN_TMPL = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div style="max-width:420px;margin:5rem auto;">
  <div class="card" style="padding:2.5rem;">
    <div style="text-align:center;margin-bottom:2rem;">
      <div style="font-size:2.5rem;margin-bottom:.5rem;">⚡</div>
      <h1 style="font-size:1.5rem;font-weight:800;margin-bottom:.3rem;">DevLaunch India</h1>
      <p style="color:var(--muted);font-size:.875rem;">Admin Dashboard Login</p>
    </div>
    <form method="POST" action="/login">
      <div class="form-group">
        <label class="form-label">Email Address</label>
        <input class="form-control" type="email" name="email" placeholder="admin@example.com" required>
      </div>
      <div class="form-group">
        <label class="form-label">Password</label>
        <input class="form-control" type="password" name="password" placeholder="••••••••" required>
      </div>
      <button class="btn btn-primary" style="width:100%;justify-content:center;padding:.75rem" type="submit">
        Sign In →
      </button>
    </form>
    <p style="text-align:center;color:var(--muted);font-size:.8rem;margin-top:1.5rem;">
      Or use Telegram bot: <code style="color:var(--cyan)">{{ bot_username }}</code>
    </p>
  </div>
</div>
{% endblock %}""")

def render_base(template_str, **kwargs):
    stats = get_stats()
    kwargs.setdefault("pending_pays", stats["pending_pay"])
    kwargs.setdefault("bot_username", BOT_USERNAME)
    return render_template_string(template_str, **kwargs)

def flash(msg, cat="success"):
    from flask import flash as _flash
    _flash(msg, cat)

# ── Flask Routes ───────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect("/dashboard" if session.get("admin") else "/login")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        e = request.form.get("email","")
        p = request.form.get("password","")
        if e == ADMIN_EMAIL and p == ADMIN_PASS:
            session["admin"] = True
            session["email"] = e
            return redirect("/dashboard")
        from flask import flash as f_
        f_("Invalid credentials", "danger")
    return render_base(LOGIN_TMPL, title="Login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

@app.route("/dashboard")
@web_admin_required
def dashboard():
    stats = get_stats()
    sys_m = get_system_metrics()
    recent_users = db_exec("SELECT * FROM users ORDER BY join_date DESC LIMIT 8", fetch="all") or []
    recent_pays = db_exec(
        "SELECT p.*,u.telegram_id,u.username FROM payments p JOIN users u ON p.user_id=u.id "
        "ORDER BY p.created_at DESC LIMIT 5", fetch="all"
    ) or []
    tmpl = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
  <h1 class="page-title">Dashboard</h1>
  <div style="display:flex;gap:.75rem">
    <a href="/admin/broadcast" class="btn btn-ghost btn-sm">📢 Broadcast</a>
    <a href="/metrics" class="btn btn-cyan btn-sm">📊 Metrics</a>
  </div>
</div>
<div class="grid-4">
  <div class="stat-card indigo">
    <div class="stat-val indigo">{{ stats.users }}</div>
    <div class="stat-label">Total Users</div>
    <div class="stat-sub">{{ stats.pending_pay }} payments pending</div>
  </div>
  <div class="stat-card cyan">
    <div class="stat-val cyan">{{ stats.running }}</div>
    <div class="stat-label">Running Scripts</div>
    <div class="stat-sub">of {{ stats.scripts }} total</div>
  </div>
  <div class="stat-card green">
    <div class="stat-val green">₹{{ "%.0f"|format(stats.revenue) }}</div>
    <div class="stat-label">Total Revenue</div>
    <div class="stat-sub">{{ stats.deployments }} deployments</div>
  </div>
  <div class="stat-card red">
    <div class="stat-val red">{{ stats.abuse_count }}</div>
    <div class="stat-label">Abuse (24h)</div>
    <div class="stat-sub">{{ stats.containers }} containers</div>
  </div>
</div>
<div class="grid-2">
  <div class="card">
    <div class="card-header">
      <div class="card-title">🖥️ System Health</div>
      <span class="badge badge-green">Live</span>
    </div>
    <div class="metric-live">
      <div class="metric-item">
        <div class="metric-top">
          <span class="metric-name">CPU Usage</span>
          <span class="metric-number" style="color:var(--cyan)">{{ sys_m.cpu_pct }}%</span>
        </div>
        <div class="progress">
          <div class="progress-bar cyan" style="width:{{ sys_m.cpu_pct }}%"></div>
        </div>
      </div>
      <div class="metric-item">
        <div class="metric-top">
          <span class="metric-name">RAM Usage</span>
          <span class="metric-number" style="color:var(--accent)">{{ sys_m.ram_pct }}%</span>
        </div>
        <div class="progress">
          <div class="progress-bar indigo" style="width:{{ sys_m.ram_pct }}%"></div>
        </div>
        <span style="font-size:.75rem;color:var(--muted)">{{ sys_m.ram_used_gb }}GB / {{ sys_m.ram_total_gb }}GB</span>
      </div>
      <div class="metric-item">
        <div class="metric-top">
          <span class="metric-name">Disk Usage</span>
          <span class="metric-number" style="color:var(--green)">{{ sys_m.disk_pct }}%</span>
        </div>
        <div class="progress">
          <div class="progress-bar green" style="width:{{ sys_m.disk_pct }}%"></div>
        </div>
        <span style="font-size:.75rem;color:var(--muted)">{{ sys_m.disk_used_gb }}GB / {{ sys_m.disk_total_gb }}GB</span>
      </div>
      <div class="metric-item">
        <div class="metric-top">
          <span class="metric-name">Active Processes</span>
          <span class="metric-number">{{ sys_m.proc_count }}</span>
        </div>
      </div>
    </div>
  </div>
  <div class="card">
    <div class="card-header">
      <div class="card-title">💳 Recent Payments</div>
      <a href="/admin/payments" class="btn btn-ghost btn-sm">View all</a>
    </div>
    <div class="table-wrap">
      <table>
        <tr><th>User</th><th>Type</th><th>Amount</th><th>Status</th></tr>
        {% for p in recent_pays %}
        <tr>
          <td>{{ p.telegram_id }}</td>
          <td>{{ p.type }}</td>
          <td>₹{{ p.amount }}</td>
          <td>
            <span class="badge {% if p.status=='approved' %}badge-green{% elif p.status=='pending' %}badge-yellow{% else %}badge-red{% endif %}">
              {{ p.status }}
            </span>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="4" style="text-align:center;color:var(--muted)">No payments yet</td></tr>
        {% endfor %}
      </table>
    </div>
  </div>
</div>
<div class="card" style="margin-top:1.25rem">
  <div class="card-header">
    <div class="card-title">👥 Recent Users</div>
    <a href="/admin/users" class="btn btn-ghost btn-sm">View all</a>
  </div>
  <div class="table-wrap">
    <table>
      <tr><th>TG ID</th><th>Username</th><th>Credits</th><th>Plan</th><th>Status</th><th>Joined</th></tr>
      {% for u in recent_users %}
      <tr>
        <td><code>{{ u.telegram_id }}</code></td>
        <td>@{{ u.username or "N/A" }}</td>
        <td><code>{{ "%.1f"|format(u.credits) }}</code></td>
        <td><span class="badge badge-blue">{{ u.plan }}</span></td>
        <td>
          {% if u.is_banned %}<span class="badge badge-red">banned</span>
          {% elif u.is_suspended %}<span class="badge badge-yellow">suspended</span>
          {% else %}<span class="badge badge-green">active</span>{% endif %}
        </td>
        <td style="color:var(--muted)">{{ u.join_date[:10] }}</td>
      </tr>
      {% endfor %}
    </table>
  </div>
</div>
{% endblock %}""")
    return render_base(tmpl, title="Dashboard", active="dash",
                       stats=stats, sys_m=sys_m,
                       recent_users=recent_users, recent_pays=recent_pays)

@app.route("/admin/users")
@web_admin_required
def admin_users():
    users = db_exec("SELECT * FROM users ORDER BY join_date DESC", fetch="all") or []
    tmpl = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
  <h1 class="page-title">👥 All Users</h1>
  <a href="/dashboard" class="btn btn-ghost btn-sm">← Back</a>
</div>
<div class="card">
  <div class="table-wrap">
    <table>
      <tr><th>TG ID</th><th>Username</th><th>Credits</th><th>Plan</th><th>Status</th><th>Deploys</th><th>Joined</th><th>Actions</th></tr>
      {% for u in users %}
      <tr>
        <td><code>{{ u.telegram_id }}</code></td>
        <td>@{{ u.username or "N/A" }}</td>
        <td><code>{{ "%.1f"|format(u.credits) }}</code></td>
        <td><span class="badge badge-blue">{{ u.plan }}</span></td>
        <td>
          {% if u.is_banned %}<span class="badge badge-red">banned</span>
          {% elif u.is_suspended %}<span class="badge badge-yellow">suspended</span>
          {% else %}<span class="badge badge-green">active</span>{% endif %}
        </td>
        <td>{{ u.total_deploys }}</td>
        <td style="color:var(--muted)">{{ u.join_date[:10] }}</td>
        <td>
          <form method="POST" action="/admin/user/action" style="display:inline;gap:.4rem">
            <input type="hidden" name="uid" value="{{ u.id }}">
            <input type="hidden" name="tgid" value="{{ u.telegram_id }}">
            <button name="action" value="ban" class="btn btn-danger btn-sm">🔨</button>
            <button name="action" value="unban" class="btn btn-success btn-sm">🔓</button>
          </form>
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>
</div>
{% endblock %}""")
    return render_base(tmpl, title="Users", active="users", users=users)

@app.route("/admin/user/action", methods=["POST"])
@web_admin_required
def admin_user_action():
    from flask import flash as f_
    uid = int(request.form.get("uid",0))
    tgid = int(request.form.get("tgid",0))
    action = request.form.get("action")
    if action == "ban":
        db_exec("UPDATE users SET is_banned=1 WHERE id=?", (uid,))
        f_("User banned", "success")
    elif action == "unban":
        db_exec("UPDATE users SET is_banned=0,is_suspended=0 WHERE id=?", (uid,))
        f_("User unbanned", "success")
    return redirect("/admin/users")

@app.route("/admin/payments")
@web_admin_required
def admin_payments():
    pays = db_exec(
        "SELECT p.*,u.telegram_id,u.username FROM payments p JOIN users u ON p.user_id=u.id "
        "ORDER BY p.created_at DESC LIMIT 50", fetch="all"
    ) or []
    tmpl = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
  <h1 class="page-title">💳 Payments</h1>
  <a href="/dashboard" class="btn btn-ghost btn-sm">← Back</a>
</div>
<div class="card">
  <div class="table-wrap">
    <table>
      <tr><th>ID</th><th>User</th><th>Type</th><th>Package</th><th>Amount</th><th>Status</th><th>Date</th><th>Actions</th></tr>
      {% for p in pays %}
      <tr>
        <td>#{{ p.id }}</td>
        <td>{{ p.telegram_id }} (@{{ p.username }})</td>
        <td>{{ p.type }}</td>
        <td>{{ p.plan_or_pack }}</td>
        <td>₹{{ p.amount }}</td>
        <td>
          <span class="badge {% if p.status=='approved' %}badge-green{% elif p.status=='pending' %}badge-yellow{% else %}badge-red{% endif %}">
            {{ p.status }}
          </span>
        </td>
        <td style="color:var(--muted)">{{ p.created_at[:16] }}</td>
        <td>
          {% if p.status=='pending' %}
          <a href="/admin/payment/{{ p.id }}/approve" class="btn btn-success btn-sm">✅</a>
          <a href="/admin/payment/{{ p.id }}/reject" class="btn btn-danger btn-sm">❌</a>
          {% endif %}
        </td>
      </tr>
      {% endfor %}
    </table>
  </div>
</div>
{% endblock %}""")
    return render_base(tmpl, title="Payments", active="pay", pays=pays)

@app.route("/admin/payment/<int:pid>/approve")
@web_admin_required
def web_approve(pid):
    from flask import flash as f_
    ok, msg = approve_payment(pid, "web_admin")
    pay = db_exec("SELECT * FROM payments WHERE id=?", (pid,), "one")
    if pay and ok:
        u = get_user_by_id(pay["user_id"])
        try: bot.send_message(u["telegram_id"], f"✅ Payment DL-{pid} approved!")
        except: pass
    f_(msg, "success" if ok else "danger")
    return redirect("/admin/payments")

@app.route("/admin/payment/<int:pid>/reject")
@web_admin_required
def web_reject(pid):
    from flask import flash as f_
    ok, msg = reject_payment(pid, "web_admin")
    f_(msg, "success" if ok else "danger")
    return redirect("/admin/payments")

@app.route("/admin/abuse")
@web_admin_required
def admin_abuse():
    rows = db_exec("SELECT * FROM abuse_log ORDER BY detected_at DESC LIMIT 50", fetch="all") or []
    tmpl = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
  <h1 class="page-title">🚨 Abuse Log</h1>
  <a href="/dashboard" class="btn btn-ghost btn-sm">← Back</a>
</div>
<div class="card">
  <div class="table-wrap">
    <table>
      <tr><th>User ID</th><th>Container</th><th>Type</th><th>Details</th><th>Action</th><th>Detected</th></tr>
      {% for r in rows %}
      <tr>
        <td>{{ r.user_id }}</td>
        <td><code>{{ (r.container_id or "")[:12] }}</code></td>
        <td><span class="badge badge-red">{{ r.abuse_type }}</span></td>
        <td style="color:var(--muted);max-width:300px;overflow:hidden;text-overflow:ellipsis">{{ r.details }}</td>
        <td>{{ r.action_taken }}</td>
        <td style="color:var(--muted)">{{ r.detected_at[:16] }}</td>
      </tr>
      {% endfor %}
      {% if not rows %}
      <tr><td colspan="6" style="text-align:center;color:var(--muted)">✅ No abuse detected</td></tr>
      {% endif %}
    </table>
  </div>
</div>
{% endblock %}""")
    return render_base(tmpl, title="Abuse Log", active="abuse", rows=rows)

@app.route("/admin/broadcast", methods=["GET","POST"])
@web_admin_required
def admin_broadcast_web():
    from flask import flash as f_
    result = {}
    if request.method == "POST":
        msg_text = request.form.get("message","").strip()
        if msg_text:
            users = db_exec("SELECT telegram_id FROM users WHERE is_banned=0 AND is_suspended=0", fetch="all") or []
            sent = failed = 0
            for u in users:
                try:
                    bot.send_message(u["telegram_id"], f"📢 <b>Announcement</b>\n\n{msg_text}")
                    sent += 1
                except: failed += 1
                time.sleep(0.05)
            db_exec("INSERT INTO broadcast_log (admin_id,message,target,sent_count,failed_count) VALUES (?,?,?,?,?)",
                    ("web_admin", msg_text, "all", sent, failed))
            f_(f"Broadcast complete: {sent} sent, {failed} failed", "success")
    tmpl = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
  <h1 class="page-title">📢 Broadcast</h1>
</div>
<div class="card" style="max-width:700px">
  <div class="card-header"><div class="card-title">Send Announcement to All Users</div></div>
  <form method="POST">
    <div class="form-group">
      <label class="form-label">Message (HTML supported)</label>
      <textarea class="form-control" name="message" placeholder="Write your announcement..." required></textarea>
    </div>
    <button class="btn btn-primary" type="submit">📢 Broadcast to All</button>
  </form>
</div>
{% endblock %}""")
    return render_base(tmpl, title="Broadcast", active="bc")

@app.route("/metrics")
@web_admin_required
def metrics_page():
    sys_m = get_system_metrics()
    tmpl = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
  <h1 class="page-title">📊 Real-Time Metrics</h1>
  <span class="badge badge-green pulse">● Live</span>
</div>
<div class="grid-4" id="metric-cards">
  <div class="stat-card cyan">
    <div class="stat-val cyan" id="m-cpu">{{ sys_m.cpu_pct }}%</div>
    <div class="stat-label">CPU Usage</div>
    <div class="progress" style="margin-top:.75rem"><div class="progress-bar cyan" id="pb-cpu" style="width:{{ sys_m.cpu_pct }}%"></div></div>
  </div>
  <div class="stat-card indigo">
    <div class="stat-val indigo" id="m-ram">{{ sys_m.ram_pct }}%</div>
    <div class="stat-label">RAM Usage</div>
    <div class="stat-sub" id="m-ram-sub">{{ sys_m.ram_used_gb }}GB / {{ sys_m.ram_total_gb }}GB</div>
    <div class="progress" style="margin-top:.75rem"><div class="progress-bar indigo" id="pb-ram" style="width:{{ sys_m.ram_pct }}%"></div></div>
  </div>
  <div class="stat-card green">
    <div class="stat-val green" id="m-disk">{{ sys_m.disk_pct }}%</div>
    <div class="stat-label">Disk Usage</div>
    <div class="stat-sub">{{ sys_m.disk_used_gb }}GB / {{ sys_m.disk_total_gb }}GB</div>
  </div>
  <div class="stat-card">
    <div class="stat-val" id="m-proc">{{ sys_m.proc_count }}</div>
    <div class="stat-label">Active Processes</div>
  </div>
</div>
<div class="card">
  <div class="card-header"><div class="card-title">📈 CPU History (last 5 min)</div></div>
  <div id="cpu-history" style="display:flex;align-items:flex-end;gap:3px;height:80px;padding:.5rem 0"></div>
</div>
<script>
const cpuHistory = [];
async function refreshMetrics() {
  try {
    const r = await fetch('/api/system-metrics');
    const d = await r.json();
    document.getElementById('m-cpu').textContent = d.cpu_pct + '%';
    document.getElementById('pb-cpu').style.width = d.cpu_pct + '%';
    document.getElementById('m-ram').textContent = d.ram_pct + '%';
    document.getElementById('pb-ram').style.width = d.ram_pct + '%';
    document.getElementById('m-ram-sub').textContent = d.ram_used_gb + 'GB / ' + d.ram_total_gb + 'GB';
    document.getElementById('m-disk').textContent = d.disk_pct + '%';
    document.getElementById('m-proc').textContent = d.proc_count;
    cpuHistory.push(d.cpu_pct);
    if(cpuHistory.length > 60) cpuHistory.shift();
    renderBar();
  } catch(e){}
}
function renderBar(){
  const c = document.getElementById('cpu-history');
  c.innerHTML = cpuHistory.map(v=>`<div style="flex:1;background:var(--cyan);opacity:${0.3+v/100*0.7};border-radius:2px 2px 0 0;height:${Math.max(4,v)}%" title="${v}%"></div>`).join('');
}
setInterval(refreshMetrics, 5000);
</script>
{% endblock %}""")
    return render_base(tmpl, title="Metrics", active="metrics", sys_m=sys_m)

@app.route("/terminal")
@web_admin_required
def terminal_page():
    tmpl = BASE_TMPL.replace("{% block content %}{% endblock %}", """
{% block content %}
<div class="page-header">
  <h1 class="page-title">💻 Web Terminal</h1>
  <span class="badge badge-yellow">⚠️ Admin Only</span>
</div>
<div class="card">
  <div style="margin-bottom:1rem">
    <label class="form-label">Script ID (for container exec)</label>
    <input class="form-control" id="script-id" placeholder="Enter script ID or leave blank for system" style="max-width:300px">
  </div>
  <div class="terminal-header">
    <div class="term-dot red"></div>
    <div class="term-dot yellow"></div>
    <div class="term-dot green"></div>
    <span style="margin-left:.75rem;font-family:var(--mono);font-size:.8rem;color:var(--muted)">devlaunch — terminal</span>
  </div>
  <div class="terminal" id="term-out">Connected to DevLaunch Terminal\nType commands below...\n</div>
  <div class="terminal-input">
    <span class="terminal-prompt">$ </span>
    <input class="terminal-cmd" id="term-cmd" placeholder="Enter command..." autocomplete="off">
  </div>
</div>
<script>
const termOut = document.getElementById('term-out');
const termCmd = document.getElementById('term-cmd');
function appendLine(txt){ termOut.textContent += txt + '\n'; termOut.scrollTop = termOut.scrollHeight; }
termCmd.addEventListener('keydown', async (e)=>{
  if(e.key !== 'Enter') return;
  const cmd = termCmd.value.trim();
  if(!cmd) return;
  appendLine('$ ' + cmd);
  termCmd.value = '';
  try {
    const r = await fetch('/api/exec', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({cmd, script_id: document.getElementById('script-id').value})
    });
    const d = await r.json();
    appendLine(d.output || d.error || '(no output)');
  } catch(err){ appendLine('Error: ' + err); }
});
</script>
{% endblock %}""")
    return render_base(tmpl, title="Terminal", active="term")

# ── REST API ─────────────────────────────────────────────────────────

@app.route("/api/system-metrics")
@web_admin_required
def api_sys_metrics():
    return jsonify(get_system_metrics())

@app.route("/api/stats")
@api_auth
def api_stats():
    if not request.jwt.get("admin"):
        return jsonify({"error": "Admin only"}), 403
    return jsonify(get_stats())

@app.route("/api/exec", methods=["POST"])
@web_admin_required
def api_exec():
    data = request.get_json(force=True)
    cmd = data.get("cmd","").strip()
    if not cmd:
        return jsonify({"error": "No command"})
    BLACKLIST = ["rm -rf /", "curl | sh", "wget | bash", "> /dev/sda", "dd if=/dev/random"]
    for bl in BLACKLIST:
        if bl in cmd:
            return jsonify({"error": f"Blocked: {bl}"})
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30,
                                env={"PATH": "/usr/bin:/bin:/usr/local/bin"})
        output = (result.stdout + result.stderr)[:3000]
        return jsonify({"output": output})
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Command timed out (30s)"})
    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/api/scripts")
@api_auth
def api_scripts():
    uid = request.jwt.get("uid")
    scripts = get_user_scripts(uid)
    return jsonify([dict(s) for s in scripts])

@app.route("/api/scripts/<int:sid>/logs")
@api_auth
def api_script_logs(sid):
    uid = request.jwt.get("uid")
    s = db_exec("SELECT logs FROM hosted_scripts WHERE id=? AND user_id=?", (sid, uid), "one")
    if not s:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"logs": s["logs"] or ""})

@app.route("/api/scripts/<int:sid>/aifix")
@api_auth
def api_aifix(sid):
    uid = request.jwt.get("uid")
    s = db_exec("SELECT logs FROM hosted_scripts WHERE id=? AND user_id=?", (sid, uid), "one")
    if not s:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"suggestion": ai_suggest_fix(s["logs"] or "")})

@app.route("/api/deployments")
@api_auth
def api_deployments():
    uid = request.jwt.get("uid")
    deps = get_user_deployments(uid)
    return jsonify([dict(d) for d in deps])

@app.route("/api/metrics/<container_id>")
@api_auth
def api_container_metrics(container_id):
    history = get_metrics_history(container_id)
    return jsonify(history)

@app.route("/api/nginx")
@admin_api_auth
def api_nginx():
    sub = request.args.get("subdomain","app")
    port = int(request.args.get("port","8080"))
    return Response(generate_nginx_config(sub, port), content_type="text/plain")

@app.route("/api/templates")
def api_templates():
    return jsonify({k: {
        "name": v["name"], "desc": v["desc"], "icon": v["icon"]
    } for k, v in BOT_TEMPLATES.items()})

@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "docker": DOCKER_AVAILABLE,
        "ts": datetime.now().isoformat()
    })

# ── WebSocket Terminal ───────────────────────────────────────────────

@socketio.on("connect")
def ws_connect():
    token = request.args.get("token","")
    payload = verify_jwt(token)
    if not payload or not payload.get("admin"):
        disconnect()
        return
    join_room(f"user_{payload['uid']}")
    emit("output", {"data": "✅ WebSocket terminal connected\n"})

@socketio.on("command")
def ws_command(data):
    token = data.get("token","")
    payload = verify_jwt(token)
    if not payload or not payload.get("admin"):
        emit("output", {"data": "❌ Unauthorized\n"})
        return
    cmd = data.get("cmd","").strip()
    BLACKLIST = ["rm -rf /", "dd if=/dev/random", "> /dev/sd"]
    for bl in BLACKLIST:
        if bl in cmd:
            emit("output", {"data": f"⛔ Blocked: {bl}\n"})
            return
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15,
                                env={"PATH": "/usr/bin:/bin:/usr/local/bin"})
        out = (result.stdout + result.stderr)[:2000] or "(no output)\n"
        emit("output", {"data": out})
    except subprocess.TimeoutExpired:
        emit("output", {"data": "⏱️ Timeout (15s)\n"})
    except Exception as e:
        emit("output", {"data": f"Error: {e}\n"})

# ═══════════════════════════════════════════════════════════════════════
# SECTION 21: STARTUP & MAIN
# ═══════════════════════════════════════════════════════════════════════

def startup_notify():
    time.sleep(4)
    try:
        sys_m = get_system_metrics()
        bot.send_message(OWNER_ID,
            f"⚡ <b>DevLaunch India Started!</b>\n\n"
            f"🌐 Dashboard: {BASE_URL}\n"
            f"🤖 Bot: {BOT_USERNAME}\n"
            f"🐋 Docker: {'✅' if DOCKER_AVAILABLE else '❌ Unavailable'}\n"
            f"💾 RAM: {sys_m['ram_used_gb']:.1f}/{sys_m['ram_total_gb']:.1f}GB\n"
            f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
    except Exception as e:
        log.warning(f"Startup notify failed: {e}")

def run_bot_thread():
    log.info("🤖 Starting Telegram bot...")
    try:
        bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
    except Exception as e:
        log.error(f"Bot crashed: {e}")
        time.sleep(5)
        run_bot_thread()

if __name__ == "__main__":
    print("""
╔═══════════════════════════════════════════════════════════════╗
║          DevLaunch India v2.0 — Starting Up                  ║
╚═══════════════════════════════════════════════════════════════╝
""")
    init_db()

    # Start background metrics collector
    if DOCKER_AVAILABLE:
        threading.Thread(target=collect_metrics, daemon=True).start()
        log.info("📊 Metrics collector started")

    # Startup notify
    threading.Thread(target=startup_notify, daemon=True).start()

    # Bot in background thread
    bot_thread = threading.Thread(target=run_bot_thread, daemon=True, name="TelegramBot")
    bot_thread.start()
    log.info(f"🌐 Web dashboard starting on :{PORT}")
    log.info(f"🔑 Admin: {ADMIN_EMAIL}")
    log.info(f"🌍 URL: {BASE_URL}")

    # Flask + SocketIO
    socketio.run(app, host="0.0.0.0", port=PORT, debug=False, use_reloader=False)
