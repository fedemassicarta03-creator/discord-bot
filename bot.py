import discord
from discord.ext import commands, tasks as ext_tasks
import json
import os
import re
import copy
import shutil
import calendar
import random
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone, time as dtime

# ======================================================================
#  CONFIG
# ======================================================================
# Railway (volume mounted at /app/data) or your own PC (file next to bot.py)
DATA_FILE = "/app/data/data.json" if os.path.isdir("/app/data") else "data.json"
ANNOUNCE_CHANNEL_ID = 1500210291890327742   # 🔧 channel for weekly / monthly posts
TIMEZONE = "Europe/Rome"   # 🔧 default timezone + clock of the 08:00 daily job. Everyone can set their own with !timezone

SCREEN_GOAL = 3          # phone hours: under this => task H is awarded automatically
MAX_TASK_HOURS = 16      # sanity cap per task per day
MAX_SCREEN_HOURS = 24
BACKFILL_DAYS = 2        # how many days back you may log / correct
STREAK_MILESTONES = {7: 3, 14: 5, 30: 10}   # streak day -> bonus points (paid once per streak)
MYSTERY_BOX_COST = 10

# Phase 1: quests, weekly goals, team challenges
QUEST_REWARDS = {"easy": 2, "medium": 4, "hard": 6}          # bonus pts per tier
QUEST_POOL = {                                               # (task letter, minutes)
    "easy":   [("B", 15), ("F", 15), ("A", 20), ("C", 15), ("D", 15), ("E", 15), ("I", 15)],
    "medium": [("F", 30), ("B", 45), ("A", 30), ("C", 30), ("D", 30), ("E", 30), ("I", 30)],
    "hard":   [("A", 60), ("D", 60), ("C", 60), ("B", 90), ("F", 60), ("E", 60)],
}
GOAL_TARGET_REWARD = 5   # weekly goal reached
GOAL_STRETCH_REWARD = 2  # extra for the stretch goal
TEAM_REWARD = 3          # each, when a team challenge succeeds
TEAM_DAYS = 7

try:
    from zoneinfo import ZoneInfo
    TZ = ZoneInfo(TIMEZONE)
except Exception:
    print(f"⚠️ Timezone '{TIMEZONE}' not available, using UTC (add 'tzdata' to requirements.txt).")
    TZ = timezone.utc

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ======================================================================
#  TASKS  (type: hours = pts per hour | flag = fixed pts per day | auto = from phone time)
# ======================================================================
TASKS = {
    "A": {"name": "A - Study",            "description": "Hours of focused study",          "type": "hours", "rate": 1},
    "B": {"name": "B - Reading",          "description": "Hours reading a book",            "type": "hours", "rate": 2},
    "C": {"name": "C - Running",          "description": "Hours running",                   "type": "hours", "rate": 1},
    "D": {"name": "D - Sports",           "description": "Hours of sports / training",      "type": "hours", "rate": 1},
    "E": {"name": "E - Research",         "description": "Hours researching a topic",       "type": "hours", "rate": 1},
    "F": {"name": "F - Language studying","description": "Hours studying a language",       "type": "hours", "rate": 2},
    "G": {"name": "G - Waking up",        "description": "No phone when waking up",         "type": "flag",  "reward": 1},
    "H": {"name": "H - Screentime",       "description": "Automatic: phone time under goal","type": "auto",  "reward": 2},
    "I": {"name": "I - Cleaning",         "description": "Hours cleaning",                  "type": "hours", "rate": 1},
    "J": {"name": "J - Sleep",            "description": "No phone before going to sleep",  "type": "flag",  "reward": 1},
}

HOURS_TASKS = [k for k, t in TASKS.items() if t["type"] == "hours"]

# ======================================================================
#  SHOP  (single source of truth: edit prices / items only here)
# ======================================================================
SHOP_CATEGORIES = {
    "💬 Communication": {
        "Romantic word": 1,
        "Voice message": 3,
        "Request call at a specific time": 5,
        "Movie/media recommendation": 1,
        "Compliment for 3 minutes": 8,
        "Ask me anything": 8,
        "Very close attention for 15 minutes": 10,
    },
    "📸 Media & Content": {
        "Send a photo now": 3,
        "Good selfie": 5,
        "Draw something": 20,
    },
    "🎮 Activities Together": {
        "Game to play together": 5,
        "Study together session": 8,
        "Learn something together (30 min)": 10,
        "Language teacher for 1 hour": 15,
        "Workout together": 16,
    },
    "📅 Control & Decisions": {
        "Pick what I eat": 5,
        "Outfit choice": 15,
        "You decide my schedule tomorrow": 15,
        "Force someone to do a task": 10,
        "30 min of YouTube": 15,
        "Block other person's action (YT Shorts, scrolling, X, etc.)": 30,
    },
    "🎁 Special": {
        "Dance": 15,
        "Personal playlist made for you": 20,
        "Belohnung": 25,
        "Send a letter": 50,
    },
}
SHOP = {item: price for items in SHOP_CATEGORIES.values() for item, price in items.items()}


def find_shop_item(name):
    for item in SHOP:
        if item.lower() == name.strip().lower():
            return item
    return None


# ======================================================================
#  TIME + PARSING HELPERS
# ======================================================================
DATE_FMT = "%Y-%m-%d"
MEDALS = ["🥇", "🥈", "🥉"]


def now_local():
    return datetime.now(TZ)


def today_date():
    return now_local().date()


def today_str():
    return today_date().strftime(DATE_FMT)


# ---- per-person timezones: every person's "today" follows their own midnight ----
_tz_cache = {}


def get_tz(name):
    if not name:
        return None
    if name not in _tz_cache:
        try:
            _tz_cache[name] = ZoneInfo(name)
        except Exception:
            _tz_cache[name] = None
    return _tz_cache[name]


def user_tz(u):
    return get_tz(u.get("tz")) or TZ


def user_now(u):
    return datetime.now(user_tz(u))


def user_today(u):
    return user_now(u).date()


def user_today_str(u):
    return user_today(u).strftime(DATE_FMT)


def find_timezone(text):
    """'Europe/Rome', 'europe/rome' or just 'Tokyo' -> 'Asia/Tokyo' (None if unknown)."""
    text = text.strip().replace(" ", "_")
    if get_tz(text):
        return text
    try:
        from zoneinfo import available_timezones
        names = available_timezones()
    except Exception:
        return None
    low = text.lower()
    exact = [n for n in names if n.lower() == low]
    if exact:
        return exact[0]
    matches = [n for n in names if n.lower().endswith("/" + low)]
    return matches[0] if len(matches) == 1 else None


def is_date_token(t):
    t = t.lower()
    return t in ("today", "yesterday") or re.fullmatch(r"\d{4}-\d{2}-\d{2}", t) is not None


def resolve_date(token, u, limit=True):
    t = token.lower()
    today = user_today(u)
    if t == "today":
        d = today
    elif t == "yesterday":
        d = today - timedelta(days=1)
    else:
        try:
            d = datetime.strptime(t, DATE_FMT).date()
        except ValueError:
            return None, "❌ Date must be `today`, `yesterday` or `YYYY-MM-DD`."
    if d > today:
        return None, "❌ You can't log the future."
    if limit and (today - d).days > BACKFILL_DAYS:
        return None, f"❌ You can only log / correct the last {BACKFILL_DAYS} days."
    return d.strftime(DATE_FMT), None


def parse_hours(s):
    m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(m|min|h)?", s.strip().lower())
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    if m.group(2) in ("m", "min"):
        v /= 60
    return round(v, 2)


SCREEN_WORDS = {"screen", "s", "phone", "screentime"}


def parse_record_args(tokens, mode, u):
    """Returns (items, date_str, error). items = [(key, value)], key is a task letter or 'screen'."""
    items, date_str, i = [], user_today_str(u), 0
    while i < len(tokens):
        raw = tokens[i]
        t = raw.lower()
        if is_date_token(t):
            date_str, err = resolve_date(t, u)
            if err:
                return None, None, err
            i += 1
            continue
        if t in SCREEN_WORDS:
            if mode == "remove":
                items.append(("screen", None))
                i += 1
                continue
            if i + 1 >= len(tokens):
                return None, None, "❌ `screen` needs hours, e.g. `screen 2.5`."
            v = parse_hours(tokens[i + 1])
            if v is None:
                return None, None, f"❌ `{tokens[i + 1]}` is not a valid number of hours."
            items.append(("screen", v))
            i += 2
            continue
        key = raw.upper()
        if key not in TASKS:
            return None, None, f"❌ I don't know `{raw}`. Use task letters A-J, `screen <hours>`, `yesterday` or a date."
        task = TASKS[key]
        if task["type"] == "auto":
            return None, None, "❌ **H** is automatic. Log your phone time with `screen <hours>`."
        if mode == "remove":
            items.append((key, None))
            i += 1
            continue
        if task["type"] == "flag":
            items.append((key, True))
            i += 1
            continue
        if i + 1 >= len(tokens):
            return None, None, f"❌ `{key}` needs hours, e.g. `{key} 1.5` or `{key} 30m`."
        v = parse_hours(tokens[i + 1])
        if v is None:
            return None, None, f"❌ `{tokens[i + 1]}` is not a valid number of hours."
        items.append((key, v))
        i += 2
    if not items:
        return None, None, "❌ Nothing to log. Example: `!record A 4 B 1 G screen 2.5`"
    return items, date_str, None


# ======================================================================
#  DATA MODEL
# ======================================================================
def new_user():
    return {
        "points": 0, "earned": 0, "records": {}, "inventory": [],
        "streak": 0, "milestones_paid": [], "achievements": [],
        "challenges_won": 0, "challenges_issued": 0, "used_count": 0,
        "total_spent": 0, "total_gambles": 0, "biggest_single_bet": 0,
        "biggest_bet": 0, "slot_jackpot": False, "won_legendary": False,
        "natural_blackjack": False, "minesweeper_pro": False,
        "bought_letter": False, "items_bought": [], "tz": None,
        "quests": {}, "goals": {}, "team": None,
    }


def day_points(rec):
    total = 0
    for key, val in rec["tasks"].items():
        t = TASKS.get(key)
        if not t:
            continue
        if t["type"] == "hours":
            total += int(val * t["rate"] + 0.5)
        elif t["type"] == "flag":
            total += t["reward"]
    if rec.get("screen") is not None and rec["screen"] < SCREEN_GOAL:
        total += TASKS["H"]["reward"]
    return total


def get_streak(u):
    recs = u.get("records", {})
    d = user_today(u)
    if d.strftime(DATE_FMT) not in recs:
        d -= timedelta(days=1)
    s = 0
    while d.strftime(DATE_FMT) in recs:
        s += 1
        d -= timedelta(days=1)
    return s


def migrate_user(u):
    """One-time conversion of old !claim history + screentime into daily records."""
    days = {}
    for e in u.get("history", []):
        d = str(e.get("time", ""))[:10]
        if len(d) != 10:
            continue
        day = days.setdefault(d, {"tasks": {}, "pts": 0})
        day["pts"] += e.get("points", 0)
        t = TASKS.get(e.get("task"))
        if not t:
            continue
        if t["type"] == "hours":
            day["tasks"][e["task"]] = round(day["tasks"].get(e["task"], 0) + 1 / t["rate"], 2)
        elif t["type"] == "flag":
            day["tasks"][e["task"]] = 1
    recs = u["records"]
    for d, day in days.items():
        if d not in recs:
            recs[d] = {"tasks": day["tasks"], "screen": None, "pts": day["pts"], "bonus": 0}
    for d, h in u.get("screentime", {}).items():
        rec = recs.setdefault(d, {"tasks": {}, "screen": None, "pts": 0, "bonus": 0})
        rec["screen"] = h
    # 'bonus' keeps the day total identical to what was really paid out before
    for rec in recs.values():
        rec["bonus"] = rec["pts"] - day_points(rec)
    u["migrated_v2"] = True
    u["streak"] = get_streak(u)


def ensure_user(user_id):
    if user_id not in data:
        data[user_id] = {}
    u = data[user_id]
    for k, v in new_user().items():
        if k not in u:
            u[k] = v
    if not u.get("migrated_v2"):
        migrate_user(u)
    return u


def save_data(_unused=None):
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, DATA_FILE)


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


data = load_data()
_needs_migration = any(not u.get("migrated_v2") for u in data.values())
if _needs_migration and os.path.exists(DATA_FILE):
    shutil.copy(DATA_FILE, DATA_FILE + ".bak-before-records")
for _uid in list(data):
    ensure_user(_uid)
if _needs_migration:
    save_data()


# ======================================================================
#  RECORD LOGIC
# ======================================================================
def apply_record(user_id, date_str, items, mode="add"):
    """mode: add | set | remove. Returns (error, info)."""
    u = data[user_id]
    old_rec = u["records"].get(date_str)
    rec = copy.deepcopy(old_rec) if old_rec else {"tasks": {}, "screen": None, "pts": 0, "bonus": 0}
    old_pts = old_rec.get("pts", 0) if old_rec else 0

    for key, val in items:
        if key == "screen":
            if mode == "remove":
                rec["screen"] = None
            else:
                if val > MAX_SCREEN_HOURS:
                    return f"❌ Screen time can't be more than {MAX_SCREEN_HOURS} h.", None
                rec["screen"] = round(val, 2)
            continue
        task = TASKS[key]
        if mode == "remove":
            rec["tasks"].pop(key, None)
        elif task["type"] == "flag":
            rec["tasks"][key] = 1
        else:
            new = round(rec["tasks"].get(key, 0) + val, 2) if mode == "add" else round(val, 2)
            if new > MAX_TASK_HOURS:
                return (f"❌ That would be {new:g} h of {task['name']} in one day (max {MAX_TASK_HOURS} h). "
                        f"Use `!record set` to correct a value."), None
            if new <= 0:
                rec["tasks"].pop(key, None)
            else:
                rec["tasks"][key] = new

    if not rec["tasks"] and rec["screen"] is None:
        u["records"].pop(date_str, None)
        new_pts, stored = 0, None
    else:
        new_pts = day_points(rec) + rec.get("bonus", 0)
        rec["pts"] = new_pts
        u["records"][date_str] = rec
        stored = rec
    delta = new_pts - old_pts
    u["points"] += delta
    u["earned"] += delta
    return None, {"rec": stored, "delta": delta, "pts": new_pts, "date": date_str}


def pay_milestones(u):
    s = get_streak(u)
    u["streak"] = s
    if s == 0:
        return []
    end = user_today(u)
    if end.strftime(DATE_FMT) not in u["records"]:
        end -= timedelta(days=1)
    start = end - timedelta(days=s - 1)
    msgs = []
    for m, pts in sorted(STREAK_MILESTONES.items()):
        key = f"{start.strftime(DATE_FMT)}:{m}"
        if s >= m and key not in u["milestones_paid"]:
            u["milestones_paid"].append(key)
            u["points"] += pts
            u["earned"] += pts
            msgs.append(f"🔥 {m}-day streak! +{pts} pts")
    return msgs


def record_lines(rec):
    lines = []
    for key in sorted(rec["tasks"]):
        t, v = TASKS[key], rec["tasks"][key]
        if t["type"] == "hours":
            lines.append(f"{t['name']}: **{v:g} h** → {int(v * t['rate'] + 0.5)} pts")
        else:
            lines.append(f"{t['name']}: ✔ → {t['reward']} pts")
    if rec.get("screen") is not None:
        s = rec["screen"]
        if s < SCREEN_GOAL:
            lines.append(f"📱 Phone: **{s:g} h** → H +{TASKS['H']['reward']} pts ✅")
        else:
            lines.append(f"📱 Phone: **{s:g} h** (goal: under {SCREEN_GOAL:g} h)")
    return lines


def rec_summary(rec):
    parts = []
    for key in sorted(rec["tasks"]):
        t, v = TASKS[key], rec["tasks"][key]
        parts.append(f"{key} {v:g}h" if t["type"] == "hours" else key)
    if rec.get("screen") is not None:
        parts.append(f"📱{rec['screen']:g}h")
    return " · ".join(parts) + f"  —  {rec.get('pts', 0)} pts"


def build_record_embed(user_id, info, title, extra=None):
    u = data[user_id]
    rec = info["rec"]
    e = discord.Embed(title=f"{title} — {info['date']}", color=discord.Color.green())
    e.description = "\n".join(record_lines(rec)) if rec else "This day's record is now empty."
    sign = "+" if info["delta"] >= 0 else ""
    e.add_field(name="📅 Day total", value=f"{info['pts']} pts", inline=True)
    e.add_field(name="➕ This change", value=f"{sign}{info['delta']} pts", inline=True)
    e.add_field(name="💰 Balance", value=f"{u['points']} pts", inline=True)
    if extra:
        e.add_field(name="🎉 Bonus", value="\n".join(extra), inline=False)
    e.set_footer(text=f"🔥 Streak: {get_streak(u)} day(s)")
    return e


def build_day_embed(user_id, date_str):
    rec = data[user_id]["records"].get(date_str)
    e = discord.Embed(title=f"📅 Record — {date_str}", color=discord.Color.blurple())
    if not rec:
        e.description = "Nothing logged for this day."
        return e
    e.description = "\n".join(record_lines(rec))
    e.add_field(name="📅 Day total", value=f"{rec['pts']} pts", inline=True)
    return e


def do_record(user_id, date_str, items, mode):
    """Shared by the command and the panel. Returns (error, embed)."""
    err, info = apply_record(user_id, date_str, items, mode)
    if err:
        return err, None
    msgs = pay_milestones(data[user_id])
    msgs += check_quest(data[user_id])
    msgs += check_goals(data[user_id])
    msgs += update_team(user_id)
    save_data()
    title = {"add": "✅ Record updated", "set": "✏️ Record corrected", "remove": "🧹 Removed"}[mode]
    return None, build_record_embed(user_id, info, title, msgs)


# ======================================================================
#  ACHIEVEMENTS
# ======================================================================
def _hours(u, k):
    return sum(r["tasks"].get(k, 0) for r in u["records"].values())


def _units(u, k):
    t = TASKS[k]
    if t["type"] == "hours":
        return _hours(u, k) * t["rate"]
    if t["type"] == "flag":
        return sum(1 for r in u["records"].values() if k in r["tasks"])
    return sum(1 for r in u["records"].values() if r.get("screen") is not None and r["screen"] < SCREEN_GOAL)


def _day_keys(r):
    keys = set(r["tasks"])
    if r.get("screen") is not None and r["screen"] < SCREEN_GOAL:
        keys.add("H")
    return keys


def _record_points(u):
    return sum(r.get("pts", 0) for r in u["records"].values())


def _completionist(u):
    seen = set()
    for r in u["records"].values():
        seen |= _day_keys(r)
    return len(seen) >= len(TASKS)


def _best_variety(u):
    return max((len(_day_keys(r)) for r in u["records"].values()), default=0)


def _bought_all_items(u):
    return all(item in u.get("items_bought", []) for item in SHOP)


ACHIEVEMENTS = {
    # First steps
    "first_blood":     {"name": "🎯 First Blood",        "desc": "Earn your first point",                       "check": lambda u: u["earned"] >= 1},
    "first_purchase":  {"name": "🛒 First Purchase",     "desc": "Buy your first item from the shop",           "check": lambda u: u.get("total_spent", 0) >= 1},
    "first_challenge": {"name": "⚔️ First Challenge",    "desc": "Issue your first challenge",                  "check": lambda u: u.get("challenges_issued", 0) >= 1},
    "gambler":         {"name": "🎰 Gambler",            "desc": "Place your first gamble",                     "check": lambda u: u.get("total_gambles", 0) >= 1},
    # Streaks
    "week_warrior":    {"name": "🔥 Week Warrior",       "desc": "Reach a 7-day streak",                        "check": lambda u: get_streak(u) >= 7},
    "month_legend":    {"name": "⚡ Month Legend",       "desc": "Reach a 30-day streak",                       "check": lambda u: get_streak(u) >= 30},
    "unstoppable":     {"name": "🌪️ Unstoppable",        "desc": "Reach a 60-day streak",                       "check": lambda u: get_streak(u) >= 60},
    "immortal":        {"name": "♾️ Immortal",           "desc": "Reach a 100-day streak",                      "check": lambda u: get_streak(u) >= 100},
    # Records
    "completionist":   {"name": "✅ Completionist",      "desc": "Log every task type (A-J) at least once",     "check": _completionist},
    "all_in_one_day":  {"name": "💥 All In One Day",     "desc": "Complete all 10 tasks in a single day",       "check": lambda u: _best_variety(u) >= len(TASKS)},
    "jack_of_trades":  {"name": "🃏 Jack of All Trades", "desc": "Complete 5 different tasks in one day",       "check": lambda u: _best_variety(u) >= 5},
    "grinder":         {"name": "⚙️ Grinder",            "desc": "Earn 50 points from daily records",           "check": lambda u: _record_points(u) >= 50},
    "dedicated":       {"name": "🏆 Dedicated",          "desc": "Earn 100 points from daily records",          "check": lambda u: _record_points(u) >= 100},
    # Task specific
    "bookworm":        {"name": "📚 Bookworm",           "desc": "Read 5 hours in total",                       "check": lambda u: _hours(u, "B") >= 5},
    "avid_reader":     {"name": "📖 Avid Reader",        "desc": "Read 20 hours in total",                      "check": lambda u: _hours(u, "B") >= 20},
    "researcher":      {"name": "🔬 Researcher",         "desc": "Study 50 hours in total",                     "check": lambda u: _hours(u, "A") >= 50},
    "marathon_runner": {"name": "🏃 Marathon Runner",    "desc": "Run 20 hours in total",                       "check": lambda u: _hours(u, "C") >= 20},
    "superhuman":      {"name": "💪 Superhuman",         "desc": "Do 40 hours of sports",                       "check": lambda u: _hours(u, "D") >= 40},
    "polyglot":        {"name": "🌍 Citizen of the World","desc": "Study languages for 20 hours",               "check": lambda u: _hours(u, "F") >= 20},
    "freedom":         {"name": "📵 Freedom",            "desc": "Phone under the goal on 35 days",             "check": lambda u: _units(u, "H") >= 35},
    "clean_freak":     {"name": "🧹 Clean Freak",        "desc": "Clean for 15 hours in total",                 "check": lambda u: _hours(u, "I") >= 15},
    "night_owl":       {"name": "🌙 Disciplined",        "desc": "No phone before sleep (J) on 20 days",        "check": lambda u: _units(u, "J") >= 20},
    # Points
    "rich":            {"name": "💎 Rich",               "desc": "Earn 100 points total",                       "check": lambda u: u["earned"] >= 100},
    "millionaire":     {"name": "👑 Millionaire",        "desc": "Earn 500 points total",                       "check": lambda u: u["earned"] >= 500},
    "saving_up":       {"name": "🐷 Saving Up",          "desc": "Have 50 pts at once",                         "check": lambda u: u["points"] >= 50},
    "rich_kid":        {"name": "💰 Rich Kid",           "desc": "Have 100 pts at once",                        "check": lambda u: u["points"] >= 100},
    "vault":           {"name": "🏦 Vault",              "desc": "Have 200 pts at once",                        "check": lambda u: u["points"] >= 200},
    # Shop
    "big_spender":     {"name": "💸 Big Spender",        "desc": "Spend 50 pts total in the shop",              "check": lambda u: u.get("total_spent", 0) >= 50},
    "collector":       {"name": "🗃️ Collector",          "desc": "Own 5 different items at once",               "check": lambda u: len(set(u.get("inventory", []))) >= 5},
    "generous":        {"name": "🤲 Generous",           "desc": "Use 10 items total",                          "check": lambda u: u.get("used_count", 0) >= 10},
    "letter_sender":   {"name": "✉️ Letter Sender",      "desc": "Buy the 'Send a letter' item",                "check": lambda u: u.get("bought_letter", False)},
    "billionaire":     {"name": "🤑 Billionaire",        "desc": "Buy every single shop item at least once",    "check": _bought_all_items},
    # Challenges
    "undefeated":      {"name": "🏅 Undefeated",         "desc": "Win 5 challenges",                            "check": lambda u: u.get("challenges_won", 0) >= 5},
    "bold":            {"name": "😤 Bold",               "desc": "Issue a challenge with a 10+ pt bet",         "check": lambda u: u.get("biggest_bet", 0) >= 10},
    "challenger":      {"name": "⚔️ Challenger",         "desc": "Issue 3 challenges",                          "check": lambda u: u.get("challenges_issued", 0) >= 3},
    # Gambling
    "gambling_addiction": {"name": "🎲 Gambling Addiction", "desc": "Bet 50+ pts in a single gamble",           "check": lambda u: u.get("biggest_single_bet", 0) >= 50},
    "slot_god":        {"name": "🎰 Slot God",           "desc": "Hit a triple 7 jackpot on slots",             "check": lambda u: u.get("slot_jackpot", False)},
    "lucky_box":       {"name": "🎁 Lucky Box",          "desc": "Win a legendary item from the mystery box",   "check": lambda u: u.get("won_legendary", False)},
    "blackjack_ach":   {"name": "🃏 Blackjack!",         "desc": "Get a natural blackjack",                     "check": lambda u: u.get("natural_blackjack", False)},
    "bosnian":         {"name": "💣 Bosnian",            "desc": "Cash out minesweeper with 3+ safe tiles",     "check": lambda u: u.get("minesweeper_pro", False)},
}


def earned_count(u):
    return sum(1 for k in u.get("achievements", []) if k in ACHIEVEMENTS)


async def check_achievements(dest, user_id):
    """dest: anything with .send() (ctx, channel, interaction.followup)."""
    u = data[user_id]
    newly = []
    for key, ach in ACHIEVEMENTS.items():
        if key in u["achievements"]:
            continue
        try:
            if ach["check"](u):
                u["achievements"].append(key)
                newly.append(ach)
        except Exception:
            pass
    if newly:
        u["points"] += len(newly)
        u["earned"] += len(newly)
        save_data()
        for ach in newly:
            await dest.send(embed=discord.Embed(
                title="🏅 Achievement Unlocked!",
                description=f"**{ach['name']}**\n{ach['desc']}\n\n+1 bonus point!",
                color=discord.Color.gold()))


# ======================================================================
#  STATS HELPERS
# ======================================================================
async def get_name(user_id):
    uid = int(user_id)
    user = bot.get_user(uid)
    if user is None:
        try:
            user = await bot.fetch_user(uid)
        except (discord.NotFound, discord.HTTPException):
            return f"User {user_id}"
    return user.display_name


async def leaderboard_embed(title, color, rows, fmt):
    """rows: sorted [(user_id, value)]. Names go in the field name (mentions don't render there)."""
    embed = discord.Embed(title=title, color=color)
    for i, (uid, val) in enumerate(rows[:10], start=1):
        name = await get_name(uid)
        medal = MEDALS[i - 1] if i <= 3 else f"{i}."
        embed.add_field(name=f"{medal} {name}", value=fmt(uid, val), inline=False)
    return embed


def weekly_points(u, start, end):
    s, e = start.strftime(DATE_FMT), end.strftime(DATE_FMT)
    return sum(r.get("pts", 0) for d, r in u["records"].items() if s <= d <= e)


async def weekly_embed(start, end, title):
    rows = [(uid, weekly_points(u, start, end)) for uid, u in data.items()]
    rows = [r for r in rows if r[1] > 0]
    if not rows:
        return None
    rows.sort(key=lambda x: x[1], reverse=True)
    return await leaderboard_embed(title, discord.Color.blue(), rows, lambda uid, v: f"{v} pts")


def month_totals(u, year, month):
    prefix = f"{year:04d}-{month:02d}-"
    recs = {d: r for d, r in u["records"].items() if d.startswith(prefix)}
    hours = {k: 0.0 for k, t in TASKS.items() if t["type"] == "hours"}
    days = {k: 0 for k, t in TASKS.items() if t["type"] == "flag"}
    screens, h_days, pts = {}, 0, 0
    for d, r in recs.items():
        pts += r.get("pts", 0)
        for k, v in r["tasks"].items():
            if k in hours:
                hours[k] += v
            elif k in days:
                days[k] += 1
        if r.get("screen") is not None:
            screens[d] = r["screen"]
            if r["screen"] < SCREEN_GOAL:
                h_days += 1
    total_screen = sum(screens.values())
    return {
        "days_logged": len(recs), "hours": {k: round(v, 2) for k, v in hours.items()},
        "days": days, "screens": screens, "screen_total": total_screen,
        "screen_avg": (total_screen / len(screens)) if screens else None,
        "h_days": h_days, "pts": pts,
    }


def build_month_embed(name, u, year, month):
    s = month_totals(u, year, month)
    dim = calendar.monthrange(year, month)[1]
    e = discord.Embed(title=f"📊 {name} — {calendar.month_name[month]} {year}", color=discord.Color.teal())
    if s["days_logged"] == 0:
        e.description = "No records this month."
        return e
    e.add_field(name="🗓️ Days logged", value=f"{s['days_logged']}/{dim}", inline=True)
    e.add_field(name="💰 Points from records", value=f"{s['pts']}", inline=True)
    e.add_field(name="🔥 Current streak", value=f"{get_streak(u)} days", inline=True)

    if s["screens"]:
        best = min(s["screens"], key=s["screens"].get)
        worst = max(s["screens"], key=s["screens"].get)
        e.add_field(name="📱 Phone", value=(
            f"Total **{s['screen_total']:.1f} h** · avg **{s['screen_avg']:.1f} h/day**\n"
            f"Under {SCREEN_GOAL:g} h: **{s['h_days']}** days\n"
            f"Best: {best[-2:]}. ({s['screens'][best]:g} h) · Worst: {worst[-2:]}. ({s['screens'][worst]:g} h)"),
            inline=False)
    else:
        e.add_field(name="📱 Phone", value="No screen time logged.", inline=False)

    total_h = sum(s["hours"].values())
    lines = [f"{TASKS[k]['name']}: **{h:g} h**" for k, h in s["hours"].items() if h > 0]
    e.add_field(name=f"⏱️ Hours tracked ({total_h:g} h)", value="\n".join(lines) or "—", inline=False)
    e.add_field(name="✅ Habits", value=" · ".join(
        [f"{TASKS[k]['name']}: {n} days" for k, n in s["days"].items()]), inline=False)

    py, pm = (year - 1, 12) if month == 1 else (year, month - 1)
    prev = month_totals(u, py, pm)
    if prev["days_logged"]:
        cmp_lines = [f"Hours tracked: {total_h - sum(prev['hours'].values()):+.1f} h"]
        if s["screen_avg"] is not None and prev["screen_avg"] is not None:
            cmp_lines.append(f"Phone avg: {s['screen_avg'] - prev['screen_avg']:+.1f} h/day")
        e.add_field(name=f"📈 vs {calendar.month_name[pm]}", value="\n".join(cmp_lines), inline=False)
    return e


def build_month_ranking(users, year, month):
    e = discord.Embed(title=f"🏆 {calendar.month_name[month]} {year} — who won what", color=discord.Color.gold())
    stats = [(name, month_totals(u, year, month)) for name, u in users]
    for key, t in TASKS.items():
        if t["type"] != "hours":
            continue
        best = max(stats, key=lambda x: x[1]["hours"][key])
        if best[1]["hours"][key] > 0:
            e.add_field(name=t["name"], value=f"{best[0]} — {best[1]['hours'][key]:g} h", inline=True)
    phone = [(n, s["screen_avg"]) for n, s in stats if s["screen_avg"] is not None]
    if phone:
        n, a = min(phone, key=lambda x: x[1])
        e.add_field(name="📱 Lowest phone time", value=f"{n} — {a:.1f} h/day", inline=True)
    return e


# ======================================================================
#  EVENTS + DAILY JOB
# ======================================================================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    if not daily_job.is_running():
        daily_job.start()


@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)


challenges = {}  # in memory (lost on restart)


def expire_challenges():
    for c in challenges.values():
        if c["status"] == "pending" and now_local() - c["created_at"] > timedelta(hours=24):
            c["status"] = "expired"


def challenge_day(c, uid):
    """The challenge day of a person = their own local date at the moment the challenge was accepted."""
    return c["accepted_at"].astimezone(user_tz(data[uid])).strftime(DATE_FMT)


async def resolve_challenges(channel):
    for cid, c in list(challenges.items()):
        if c["status"] != "accepted":
            continue
        a, b = c["challenger"], c["challenged"]
        da, db = challenge_day(c, a), challenge_day(c, b)
        # wait until BOTH people's challenge day is over in their own timezone
        if da >= user_today_str(data[a]) or db >= user_today_str(data[b]):
            continue
        ha = data[a]["records"].get(da, {"tasks": {}})["tasks"].get(c["task"], 0)
        hb = data[b]["records"].get(db, {"tasks": {}})["tasks"].get(c["task"], 0)
        c["status"] = "completed"
        tname = TASKS[c["task"]]["name"]
        if ha == hb:
            text = f"🤝 Challenge **{tname}** ({c['date']}): tie at {ha:g} h. No points moved."
            winner = None
        else:
            winner, loser = (a, b) if ha > hb else (b, a)
            bet = min(c["bet"], max(0, data[loser]["points"]))
            if bet:
                data[winner]["points"] += bet
                data[loser]["points"] -= bet
            data[winner]["challenges_won"] += 1
            text = (f"⚔️ Challenge **{tname}** ({c['date']}): <@{a}> {ha:g} h vs <@{b}> {hb:g} h\n"
                    f"🏆 Winner: <@{winner}>" + (f" (+{bet} pts)" if bet else ""))
        save_data()
        if channel:
            await channel.send(text)
            if winner:
                await check_achievements(channel, winner)


@ext_tasks.loop(time=dtime(hour=8, minute=0, tzinfo=TZ))
async def daily_job():
    try:
        now = now_local()
        channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
        await resolve_challenges(channel)
        for uid in list(data):
            team_msgs = update_team(uid)
            if team_msgs and channel:
                await channel.send("\n".join(team_msgs))
        save_data()
        if not channel:
            return
        if now.weekday() == 0:  # Monday: last Mon-Sun
            end = now.date() - timedelta(days=1)
            emb = await weekly_embed(end - timedelta(days=6), end, "📅 Weekly Leaderboard — last week")
            await channel.send(embed=emb) if emb else await channel.send("📅 No activity last week!")
        if now.day == 1:  # 1st: overview of last month
            last = now.replace(day=1) - timedelta(days=1)
            users = []
            for uid, u in data.items():
                if month_totals(u, last.year, last.month)["days_logged"]:
                    name = await get_name(uid)
                    await channel.send(embed=build_month_embed(name, u, last.year, last.month))
                    users.append((name, u))
            if len(users) > 1:
                await channel.send(embed=build_month_ranking(users, last.year, last.month))
    except Exception:
        traceback.print_exc()


# ======================================================================
#  DAILY RECORD: panel (buttons) + command
# ======================================================================
TASK_OPTIONS = [
    discord.SelectOption(label=t["name"], value=k, description=t["description"][:100])
    for k, t in TASKS.items() if t["type"] != "auto"
]


class HoursModal(discord.ui.Modal):
    def __init__(self, user_id, key, date_str):
        super().__init__(title=f"Log: {TASKS[key]['name']}"[:45])
        self.user_id, self.key, self.date_str = user_id, key, date_str
        self.hours_input = discord.ui.TextInput(label="Hours (e.g. 1.5 or 30m)", placeholder="1.5", max_length=8)
        self.add_item(self.hours_input)

    async def on_submit(self, interaction):
        v = parse_hours(self.hours_input.value)
        if v is None:
            await interaction.response.send_message("❌ Enter a number like `1.5` or `30m`.", ephemeral=True)
            return
        err, embed = do_record(self.user_id, self.date_str, [(self.key, v)], "add")
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await interaction.response.send_message(embed=embed)
        await check_achievements(interaction.followup, self.user_id)


class ScreenModal(discord.ui.Modal):
    def __init__(self, user_id, date_str):
        super().__init__(title="Phone time today")
        self.user_id, self.date_str = user_id, date_str
        self.hours_input = discord.ui.TextInput(label="Total phone hours (replaces old value)", placeholder="2.5", max_length=8)
        self.add_item(self.hours_input)

    async def on_submit(self, interaction):
        v = parse_hours(self.hours_input.value)
        if v is None:
            await interaction.response.send_message("❌ Enter a number like `2.5`.", ephemeral=True)
            return
        err, embed = do_record(self.user_id, self.date_str, [("screen", v)], "set")
        if err:
            await interaction.response.send_message(err, ephemeral=True)
            return
        await interaction.response.send_message(embed=embed)
        await check_achievements(interaction.followup, self.user_id)


class RecordPanel(discord.ui.View):
    def __init__(self, owner_id, date_str):
        super().__init__(timeout=300)
        self.owner_id, self.date_str, self.message = owner_id, date_str, None

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("This panel belongs to someone else. Use `!record`.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    async def _reset_select(self):
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass

    @discord.ui.select(placeholder="➕ Add a task to your record…", options=TASK_OPTIONS)
    async def pick(self, interaction, select):
        key = select.values[0]
        uid = str(interaction.user.id)
        if TASKS[key]["type"] == "flag":
            err, embed = do_record(uid, self.date_str, [(key, True)], "add")
            if err:
                await interaction.response.send_message(err, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed)
                await check_achievements(interaction.followup, uid)
        else:
            await interaction.response.send_modal(HoursModal(uid, key, self.date_str))
        await self._reset_select()

    @discord.ui.button(label="📱 Screen time", style=discord.ButtonStyle.primary)
    async def screen_btn(self, interaction, button):
        await interaction.response.send_modal(ScreenModal(str(interaction.user.id), self.date_str))

    @discord.ui.button(label="👁 View day", style=discord.ButtonStyle.secondary)
    async def view_btn(self, interaction, button):
        await interaction.response.send_message(
            embed=build_day_embed(str(interaction.user.id), self.date_str), ephemeral=True)


def build_panel_embed(user_id, date_str):
    rec = data[user_id]["records"].get(date_str)
    e = discord.Embed(title=f"📅 Daily record — {date_str}", color=discord.Color.blurple())
    e.description = "\n".join(record_lines(rec)) if rec else "Nothing logged yet."
    e.add_field(name="How it works", value=(
        "Pick a task below and enter the hours (several logs per day add up).\n"
        "📱 sets your total phone time (replaces the old value).\n"
        "Fix mistakes: `!record set A 3` · `!record remove A` · `!record delete`"), inline=False)
    e.add_field(name="Quick command", value="`!record A 4 B 1 G screen 2.5`", inline=False)
    return e


@bot.command(name="record", aliases=["rec"])
async def record_cmd(ctx, *args):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)

    # no args, or just a date -> interactive panel
    if not args or (len(args) == 1 and is_date_token(args[0])):
        date_str = user_today_str(u)
        if args:
            date_str, err = resolve_date(args[0], u)
            if err:
                await ctx.send(err)
                return
        view = RecordPanel(ctx.author.id, date_str)
        view.message = await ctx.send(embed=build_panel_embed(user_id, date_str), view=view)
        return

    sub = args[0].lower()

    if sub == "view":
        date_str = user_today_str(u)
        if len(args) > 1:
            date_str, err = resolve_date(args[1], u, limit=False)
            if err:
                await ctx.send(err)
                return
        await ctx.send(embed=build_day_embed(user_id, date_str))
        return

    if sub == "delete":
        date_str = user_today_str(u)
        if len(args) > 1:
            date_str, err = resolve_date(args[1], u)
            if err:
                await ctx.send(err)
                return
        rec = u["records"].pop(date_str, None)
        if not rec:
            await ctx.send(f"❌ No record for {date_str}.")
            return
        delta = -rec.get("pts", 0)
        u["points"] += delta
        u["earned"] += delta
        save_data()
        await ctx.send(f"🗑️ Deleted the record of {date_str} ({delta} pts). Balance: {u['points']} pts")
        return

    if sub in ("set", "remove"):
        items, date_str, err = parse_record_args(list(args[1:]), sub, u)
        mode = sub
    else:
        items, date_str, err = parse_record_args(list(args), "add", u)
        mode = "add"
    if err:
        await ctx.send(err)
        return

    err, embed = do_record(user_id, date_str, items, mode)
    if err:
        await ctx.send(err)
        return
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)


@bot.command(name="claim", hidden=True)
async def claim_moved(ctx, *args):
    await ctx.send("ℹ️ `!claim` was replaced by the daily record. Try `!record` (panel) "
                   "or `!record A 2 B 1 G screen 2.5`.")


# ======================================================================
#  PROFILE + STATS
# ======================================================================
def reward_text(t):
    if t["type"] == "hours":
        r = t["rate"]
        return f"{r:g} pt per hour" if r == 1 else f"{r:g} pts per hour (1 pt per {60 / r:g} min)"
    if t["type"] == "flag":
        return f"{t['reward']} pt per day"
    return f"{t['reward']} pts automatically when phone is under {SCREEN_GOAL:g} h"


@bot.command(name="tasks")
async def tasks_cmd(ctx):
    embed = discord.Embed(title="📋 Tasks", color=discord.Color.teal(),
                          description="Log them with `!record`, e.g. `!record A 2 B 1 G screen 2.5`")
    for key, t in TASKS.items():
        embed.add_field(name=f"`{key}` — {t['name']}", value=f"{t['description']}\n*{reward_text(t)}*", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def profile(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    u = ensure_user(user_id)
    today_rec = u["records"].get(user_today_str(u))
    embed = discord.Embed(title=f"👤 {member.display_name}'s Profile", color=discord.Color.blurple())
    embed.add_field(name="💰 Current Points", value=f"{u['points']} pts", inline=True)
    embed.add_field(name="🏆 Total Earned", value=f"{u['earned']} pts", inline=True)
    embed.add_field(name="🔥 Streak", value=f"{get_streak(u)} days", inline=True)
    embed.add_field(name="🎒 Inventory", value=f"{len(u['inventory'])} items", inline=True)
    embed.add_field(name="🏅 Achievements", value=f"{earned_count(u)}/{len(ACHIEVEMENTS)}", inline=True)
    embed.add_field(name="⚔️ Challenges Won", value=f"{u.get('challenges_won', 0)}", inline=True)
    embed.add_field(name="📅 Today's record",
                    value="\n".join(record_lines(today_rec)) if today_rec else "Nothing logged yet", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command()
async def streak(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = ensure_user(str(member.id))
    s = get_streak(u)
    if s == 0:
        msg = f"😴 **{member.display_name}** has no active streak. Log a record to start one!"
    else:
        msg = f"🔥 **{member.display_name}** is on a **{s}-day streak!**"
        upcoming = [(m, p) for m, p in sorted(STREAK_MILESTONES.items()) if m > s]
        if upcoming:
            m, p = upcoming[0]
            msg += f" Next bonus: day {m} (+{p} pts)."
    await ctx.send(msg)


@bot.command()
async def history(ctx, amount: int = 7):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    amount = max(1, min(amount, 15))
    days = sorted(u["records"], reverse=True)[:amount]
    if not days:
        await ctx.send("No records yet.")
        return
    embed = discord.Embed(title=f"📜 Last {len(days)} records", color=discord.Color.green())
    for d in days:
        embed.add_field(name=d, value=rec_summary(u["records"][d]), inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def tasksummary(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = ensure_user(str(member.id))
    if not u["records"]:
        await ctx.send("No records yet.")
        return
    vals = {}
    for k, t in TASKS.items():
        vals[k] = _hours(u, k) if t["type"] == "hours" else _units(u, k)
    top = max(vals.values()) or 1
    embed = discord.Embed(title=f"📊 {member.display_name}'s Task Breakdown", color=discord.Color.teal())
    for k, t in TASKS.items():
        filled = int(vals[k] / top * 10)
        unit = "h" if t["type"] == "hours" else "days"
        embed.add_field(name=f"`{k}` {t['name']}", value=f"{'█' * filled}{'░' * (10 - filled)} {vals[k]:g} {unit}", inline=False)
    embed.set_footer(text=f"Days logged: {len(u['records'])}")
    await ctx.send(embed=embed)


@bot.command()
async def best(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = ensure_user(str(member.id))
    if not u["records"]:
        await ctx.send("No records yet.")
        return
    weeks = {}
    for d, r in u["records"].items():
        y, w, _ = datetime.strptime(d, DATE_FMT).isocalendar()
        weeks[f"{y}-W{w:02d}"] = weeks.get(f"{y}-W{w:02d}", 0) + r.get("pts", 0)
    wk = max(weeks, key=weeks.get)
    embed = discord.Embed(title=f"🌟 {member.display_name}'s Best Week", color=discord.Color.gold())
    embed.add_field(name="📅 Week", value=wk, inline=True)
    embed.add_field(name="💰 Points", value=f"{weeks[wk]} pts", inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def compare(ctx, member: discord.Member):
    id1, id2 = str(ctx.author.id), str(member.id)
    u1, u2 = ensure_user(id1), ensure_user(id2)
    now = user_now(u1)
    week_start = now.date() - timedelta(days=6)
    m1, m2 = month_totals(u1, now.year, now.month), month_totals(u2, now.year, now.month)

    def fmt(a, b):
        if a == b:
            return f"{a:g} 🟰", f"{b:g} 🟰"
        return (f"**{a:g} ✅**", f"{b:g}") if a > b else (f"{a:g}", f"**{b:g} ✅**")

    rows = [
        ("💰 Current Points", u1["points"], u2["points"]),
        ("🏆 Total Earned", u1["earned"], u2["earned"]),
        ("🔥 Streak", get_streak(u1), get_streak(u2)),
        ("📅 Last 7 days (pts)", weekly_points(u1, week_start, now.date()), weekly_points(u2, week_start, now.date())),
        ("⏱️ Hours this month", sum(m1["hours"].values()), sum(m2["hours"].values())),
        ("🗓️ Days logged (all time)", len(u1["records"]), len(u2["records"])),
        ("🏅 Achievements", earned_count(u1), earned_count(u2)),
        ("⚔️ Challenges Won", u1.get("challenges_won", 0), u2.get("challenges_won", 0)),
    ]
    embed = discord.Embed(title=f"📊 {ctx.author.display_name} vs {member.display_name}", color=discord.Color.blurple())
    for label, a, b in rows:
        fa, fb = fmt(a, b)
        embed.add_field(name=label, value=f"{ctx.author.display_name}: {fa}\n{member.display_name}: {fb}", inline=False)
    if m1["screen_avg"] is not None and m2["screen_avg"] is not None:
        a, b = m1["screen_avg"], m2["screen_avg"]
        embed.add_field(name="📱 Phone avg this month (lower is better)",
                        value=f"{ctx.author.display_name}: {a:.1f} h/day{' ✅' if a < b else ''}\n"
                              f"{member.display_name}: {b:.1f} h/day{' ✅' if b < a else ''}", inline=False)
    await ctx.send(embed=embed)


@bot.command(name="month", aliases=["screenmonth"])
async def month_cmd(ctx, *args):
    """!month | !month @user | !month 2026-05 | !month @user 2026-05"""
    now = user_now(ensure_user(str(ctx.author.id)))
    year, month, member = now.year, now.month, ctx.author
    for a in args:
        if re.fullmatch(r"\d{4}-\d{2}", a) and 1 <= int(a[5:]) <= 12:
            year, month = int(a[:4]), int(a[5:])
        else:
            try:
                member = await commands.MemberConverter().convert(ctx, a)
            except commands.BadArgument:
                await ctx.send("❌ Use `!month [@user] [YYYY-MM]`")
                return
    u = ensure_user(str(member.id))
    await ctx.send(embed=build_month_embed(member.display_name, u, year, month))


# ======================================================================
#  PHASE 1: QUESTS, WEEKLY GOALS, TEAM CHALLENGES
# ======================================================================
def add_points(u, n):
    u["points"] += n
    u["earned"] += n


def fmt_minutes(m):
    return f"{m} min" if m < 60 else f"{m / 60:g} h"


def quest_text(o):
    return f"Log {fmt_minutes(o['minutes'])} of {TASKS[o['task']]['name']}"


TIER_LABEL = {"easy": "🟢 Easy", "medium": "🟡 Medium", "hard": "🔴 Hard"}


def get_quests(u):
    """Today's three offers, generated once per local day and person."""
    day = user_today_str(u)
    quests = u["quests"]
    cutoff = (user_today(u) - timedelta(days=7)).strftime(DATE_FMT)
    for old in [d for d in quests if d < cutoff]:
        del quests[old]
    if day not in quests:
        offers, used = [], set()
        for tier in ("easy", "medium", "hard"):
            options = [x for x in QUEST_POOL[tier] if x[0] not in used] or QUEST_POOL[tier]
            task, minutes = random.choice(options)
            used.add(task)
            offers.append({"tier": tier, "task": task, "minutes": minutes, "pts": QUEST_REWARDS[tier]})
        quests[day] = {"offers": offers, "chosen": None, "base": 0, "done": False}
        save_data()
    return day, quests[day]


def quest_done_minutes(u, day, q):
    o = q["offers"][q["chosen"]]
    have = u["records"].get(day, {"tasks": {}})["tasks"].get(o["task"], 0)
    return max(0.0, (have - q.get("base", 0)) * 60)


def check_quest(u):
    day = user_today_str(u)
    q = u["quests"].get(day)
    if not q or q["chosen"] is None or q["done"]:
        return []
    o = q["offers"][q["chosen"]]
    if quest_done_minutes(u, day, q) >= o["minutes"] - 0.5:
        q["done"] = True
        add_points(u, o["pts"])
        return [f"🎯 Quest complete: {quest_text(o)} → +{o['pts']} pts"]
    return []


def quest_embed(day, q):
    e = discord.Embed(title=f"🎯 Daily quests — {day}", color=discord.Color.orange())
    for i, o in enumerate(q["offers"], start=1):
        mark = ""
        if q["chosen"] == i - 1:
            mark = " ✅ done" if q["done"] else " 👈 chosen"
        e.add_field(name=f"{i}. {TIER_LABEL[o['tier']]} — +{o['pts']} pts{mark}", value=quest_text(o), inline=False)
    if q["chosen"] is None:
        e.set_footer(text="Pick one with !quest choose <1-3>. Hours logged after choosing count.")
    else:
        e.set_footer(text="Check your status with !quest progress")
    return e


@bot.command(name="quest", aliases=["quests"])
async def quest_cmd(ctx, sub: str = None, number: str = None):
    """!quest | !quest choose 1 | !quest progress"""
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    day, q = get_quests(u)
    sub = sub.lower() if sub else None

    if sub is None:
        await ctx.send(embed=quest_embed(day, q))
        return

    if sub == "choose":
        if number not in ("1", "2", "3"):
            await ctx.send("❌ Use `!quest choose 1`, `2` or `3`.")
            return
        if q["chosen"] is not None:
            await ctx.send(f"❌ You already chose quest {q['chosen'] + 1} today.")
            return
        idx = int(number) - 1
        o = q["offers"][idx]
        q["chosen"] = idx
        q["base"] = u["records"].get(day, {"tasks": {}})["tasks"].get(o["task"], 0)
        save_data()
        await ctx.send(f"🎯 Quest {number} chosen: **{quest_text(o)}** (+{o['pts']} pts). "
                       f"Log it with `!record {o['task']} {o['minutes']}m`; only time logged from now on counts.")
        return

    if sub == "progress":
        if q["chosen"] is None:
            await ctx.send("You haven't chosen a quest yet. See `!quest` and pick one with `!quest choose <1-3>`.")
            return
        o = q["offers"][q["chosen"]]
        if q["done"]:
            await ctx.send(f"✅ Quest done: **{quest_text(o)}** (+{o['pts']} pts). See you tomorrow!")
            return
        done = quest_done_minutes(u, day, q)
        filled = int(min(1, done / o["minutes"]) * 10)
        await ctx.send(f"🎯 **{quest_text(o)}** (+{o['pts']} pts)\n"
                       f"{'█' * filled}{'░' * (10 - filled)} {done:.0f}/{o['minutes']} min")
        return

    await ctx.send("❌ Use `!quest`, `!quest choose <1-3>` or `!quest progress`.")


# ---- weekly goals ------------------------------------------------------
def week_info(d):
    y, w, _ = d.isocalendar()
    monday = d - timedelta(days=d.weekday())
    return f"{y}-W{w:02d}", monday, monday + timedelta(days=6)


def week_hours(u, task, monday, sunday):
    a, b = monday.strftime(DATE_FMT), sunday.strftime(DATE_FMT)
    return round(sum(r["tasks"].get(task, 0) for d, r in u["records"].items() if a <= d <= b), 2)


def check_goals(u):
    msgs, today = [], user_today(u)
    for d in (today, today - timedelta(days=7)):   # previous week too (backfill)
        key, mon, sun = week_info(d)
        for task, g in u["goals"].get(key, {}).items():
            have = week_hours(u, task, mon, sun)
            name = TASKS[task]["name"]
            if not g["paid_target"] and have >= g["target"] - 1e-9:
                g["paid_target"] = True
                add_points(u, GOAL_TARGET_REWARD)
                msgs.append(f"📅 Weekly goal reached: {name} {g['target']:g} h → +{GOAL_TARGET_REWARD} pts")
            if g.get("stretch") and not g["paid_stretch"] and have >= g["stretch"] - 1e-9:
                g["paid_stretch"] = True
                add_points(u, GOAL_STRETCH_REWARD)
                msgs.append(f"🚀 Stretch goal reached: {name} {g['stretch']:g} h → +{GOAL_STRETCH_REWARD} pts")
    return msgs


@bot.command(name="goal", aliases=["goals"])
async def goal_cmd(ctx, *args):
    """!goal | !goal set A 8 [10] | !goal remove A"""
    u = ensure_user(str(ctx.author.id))
    today = user_today(u)
    key, mon, sun = week_info(today)
    sub = args[0].lower() if args else None

    if sub is None:
        goals = u["goals"].get(key, {})
        if not goals:
            await ctx.send("📅 No weekly goals yet. Example: `!goal set A 8 10` (8 h study, stretch 10 h).")
            return
        e = discord.Embed(title=f"📅 Weekly goals — {key} ({mon:%d.%m.}–{sun:%d.%m.})", color=discord.Color.blue())
        for task, g in goals.items():
            have = week_hours(u, task, mon, sun)
            top = g.get("stretch") or g["target"]
            filled = int(min(1, have / top) * 10)
            lines = [f"{'█' * filled}{'░' * (10 - filled)} **{have:g} h**",
                     f"Goal {g['target']:g} h: {'✅ +' + str(GOAL_TARGET_REWARD) + ' pts' if g['paid_target'] else 'open'}"]
            if g.get("stretch"):
                lines.append(f"Stretch {g['stretch']:g} h: {'✅ +' + str(GOAL_STRETCH_REWARD) + ' pts' if g['paid_stretch'] else 'open'}")
            e.add_field(name=TASKS[task]["name"], value="\n".join(lines), inline=False)
        e.set_footer(text=f"Rewards come on top of your normal points. Week ends {sun:%A}.")
        await ctx.send(embed=e)
        return

    if sub == "set":
        if len(args) < 3:
            await ctx.send("❌ Use `!goal set <task> <hours> [stretch hours]`, e.g. `!goal set A 8 10`.")
            return
        task = args[1].upper()
        if task not in HOURS_TASKS:
            await ctx.send("❌ Goals work with hour tasks: " + ", ".join(HOURS_TASKS))
            return
        target = parse_hours(args[2])
        stretch = parse_hours(args[3]) if len(args) > 3 else None
        if not target or target <= 0 or target > MAX_TASK_HOURS * 7:
            await ctx.send("❌ The goal must be a number of hours greater than 0.")
            return
        if len(args) > 3 and (stretch is None or stretch <= target):
            await ctx.send("❌ The stretch goal must be higher than the goal.")
            return
        old = u["goals"].get(key, {}).get(task)
        if old and (old["paid_target"] or old["paid_stretch"]):
            await ctx.send("❌ You already got a reward for this goal this week, so it can't be changed.")
            return
        have = week_hours(u, task, mon, sun)
        if have >= target:
            await ctx.send(f"❌ You already logged {have:g} h of {TASKS[task]['name']} this week. Set a higher goal.")
            return
        u["goals"].setdefault(key, {})[task] = {"target": target, "stretch": stretch,
                                                "paid_target": False, "paid_stretch": False}
        for k in sorted(u["goals"])[:-6]:
            del u["goals"][k]
        save_data()
        extra = f" (stretch {stretch:g} h)" if stretch else ""
        await ctx.send(f"📅 Goal set: **{target:g} h** of {TASKS[task]['name']}{extra} this week. "
                       f"Reward: +{GOAL_TARGET_REWARD} pts" + (f", +{GOAL_STRETCH_REWARD} more for the stretch." if stretch else "."))
        return

    if sub == "remove":
        task = args[1].upper() if len(args) > 1 else ""
        g = u["goals"].get(key, {}).get(task)
        if not g:
            await ctx.send("❌ No such goal this week. Use `!goal remove A`.")
            return
        if g["paid_target"] or g["paid_stretch"]:
            await ctx.send("❌ You already got a reward for this goal, so it can't be removed.")
            return
        del u["goals"][key][task]
        save_data()
        await ctx.send(f"🗑️ Goal for {TASKS[task]['name']} removed.")
        return

    await ctx.send("❌ Use `!goal`, `!goal set <task> <hours> [stretch]` or `!goal remove <task>`.")


# ---- team challenges ---------------------------------------------------
def team_progress(uid):
    """{person: (hours, first_day, last_day)} counted on each person's own local days."""
    t = data[uid]["team"]
    start = datetime.fromisoformat(t["start"])
    out = {}
    for who in (uid, t["partner"]):
        d0 = start.astimezone(user_tz(data[who])).date()
        d1 = d0 + timedelta(days=TEAM_DAYS - 1)
        a, b = d0.strftime(DATE_FMT), d1.strftime(DATE_FMT)
        hrs = sum(r["tasks"].get(t["task"], 0) for d, r in data[who]["records"].items() if a <= d <= b)
        out[who] = (round(hrs, 2), d0, d1)
    return out


def update_team(uid):
    """Completes or expires an active team challenge. Returns messages."""
    t = data[uid].get("team")
    if not t or t["status"] != "active" or t["partner"] not in data:
        return []
    pid = t["partner"]
    prog = team_progress(uid)
    total = sum(h for h, _, _ in prog.values())
    name = TASKS[t["task"]]["name"]
    if total >= t["target"] - 1e-9:
        status = "completed"
        msg = (f"🤝 Team challenge complete! {name}: {total:g}/{t['target']:g} h → "
               f"<@{uid}> and <@{pid}> get +{TEAM_REWARD} pts each")
    elif all(user_today(data[w]) > prog[w][2] for w in prog):
        status = "failed"
        msg = f"💔 Team challenge failed: {name} {total:g}/{t['target']:g} h. Try again!"
    else:
        return []
    for who in (uid, pid):
        if data[who].get("team"):
            data[who]["team"]["status"] = status
        if status == "completed":
            add_points(data[who], TEAM_REWARD)
    return [msg]


@bot.command(name="teamchallenge", aliases=["tc"])
async def teamchallenge(ctx, member: discord.Member, hours: str):
    """!teamchallenge @user 10 -> reach 10 h of a random task together within 7 days"""
    a, b = str(ctx.author.id), str(member.id)
    ua, ub = ensure_user(a), ensure_user(b)
    if member.id == ctx.author.id or member.bot:
        await ctx.send("❌ Pick the other person for a team challenge.")
        return
    target = parse_hours(hours)
    if not target or target <= 0 or target > 200:
        await ctx.send("❌ The shared hour goal must be between 0 and 200, e.g. `!teamchallenge @user 10`.")
        return
    for uid in (a, b):
        update_team(uid)
    for uid, u in ((a, ua), (b, ub)):
        if u.get("team") and u["team"]["status"] == "active":
            who = "You have" if uid == a else f"{member.display_name} has"
            await ctx.send(f"❌ {who} an active team challenge already (`!teamchallengeview`).")
            return
    task = random.choice(HOURS_TASKS)
    start = datetime.now(timezone.utc).isoformat()
    ua["team"] = {"partner": b, "task": task, "target": target, "start": start, "status": "active"}
    ub["team"] = {"partner": a, "task": task, "target": target, "start": start, "status": "active"}
    save_data()
    embed = discord.Embed(
        title="🤝 Team Challenge started!",
        description=f"{ctx.author.mention} and {member.mention} work together: log **{target:g} h** of "
                    f"**{TASKS[task]['name']}** combined within **{TEAM_DAYS} days**.",
        color=discord.Color.teal())
    embed.add_field(name="🎁 Reward", value=f"+{TEAM_REWARD} pts each when you make it", inline=True)
    embed.set_footer(text="Check the status with !teamchallengeview")
    await ctx.send(embed=embed)


@bot.command(name="teamchallengeview", aliases=["tcv"])
async def teamchallengeview(ctx):
    uid = str(ctx.author.id)
    u = ensure_user(uid)
    msgs = update_team(uid)
    save_data()
    t = u.get("team")
    if not t:
        await ctx.send("No team challenge yet. Start one with `!teamchallenge @user <hours>`.")
        return
    prog = team_progress(uid)
    total = sum(h for h, _, _ in prog.values())
    filled = int(min(1, total / t["target"]) * 10)
    status = {"active": "🟢 active", "completed": "✅ completed", "failed": "❌ failed"}[t["status"]]
    e = discord.Embed(title=f"🤝 Team challenge — {status}", color=discord.Color.teal())
    e.add_field(name="Task", value=TASKS[t["task"]]["name"], inline=True)
    e.add_field(name="Goal", value=f"{t['target']:g} h together", inline=True)
    e.add_field(name="Progress", value=f"{'█' * filled}{'░' * (10 - filled)} **{total:g}/{t['target']:g} h**", inline=False)
    for who, (hrs, d0, d1) in prog.items():
        e.add_field(name=await get_name(who), value=f"{hrs:g} h", inline=True)
    if t["status"] == "active":
        left = max(0, (prog[uid][2] - user_today(u)).days + 1)
        e.set_footer(text=f"{left} day(s) left for you")
    await ctx.send(embed=e)
    if msgs:
        await ctx.send("\n".join(msgs))


@bot.command(name="timezone", aliases=["tz"])
async def timezone_cmd(ctx, *, name: str = None):
    """!timezone | !timezone Asia/Tokyo | !timezone Rome"""
    u = ensure_user(str(ctx.author.id))
    if name is None:
        now = user_now(u)
        await ctx.send(f"🕒 Your timezone: **{u.get('tz') or TIMEZONE}**. For you it is {now:%H:%M} on {now:%Y-%m-%d}.\n"
                       f"Change it with `!timezone Asia/Tokyo` or `!timezone Europe/Rome`.")
        return
    found = find_timezone(name)
    if not found:
        await ctx.send("❌ Unknown timezone. Use e.g. `Europe/Rome` or `Asia/Tokyo` (a city alone like `Tokyo` also works). "
                       "If it keeps failing, add `tzdata` to requirements.txt.")
        return
    u["tz"] = found
    save_data()
    now = datetime.now(get_tz(found))
    await ctx.send(f"✅ Timezone set to **{found}**. For you it is now {now:%H:%M} on {now:%Y-%m-%d}. "
                   f"Your days now start and end at your own midnight.")


# ======================================================================
#  ACHIEVEMENTS COMMAND
# ======================================================================
@bot.command()
async def achievements(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = ensure_user(str(member.id))
    earned, locked = [], []
    for key, ach in ACHIEVEMENTS.items():
        if key in u["achievements"]:
            earned.append(f"{ach['name']} — {ach['desc']}")
        else:
            locked.append(f"🔒 {ach['desc']}")

    async def send_chunks(title, lines, color):
        for i in range(0, len(lines), 10):
            part = lines[i:i + 10]
            suffix = f" ({i // 10 + 1}/{(len(lines) + 9) // 10})" if len(lines) > 10 else ""
            await ctx.send(embed=discord.Embed(title=title + suffix, description="\n".join(part), color=color))

    head = f"🏅 {member.display_name}'s Achievements ({earned_count(u)}/{len(ACHIEVEMENTS)})"
    if earned:
        await send_chunks(head, earned, discord.Color.gold())
    else:
        await ctx.send(embed=discord.Embed(title=head, description="None yet. Start logging records!", color=discord.Color.gold()))
    if locked:
        await send_chunks("🔒 Locked", locked, discord.Color.dark_gray())


# ======================================================================
#  CHALLENGES  (who logs more hours of a task on the challenge day)
# ======================================================================
async def issue_challenge(ctx, member, task, bet, title="⚔️ Challenge Issued!"):
    if member.id == ctx.author.id:
        await ctx.send("❌ You can't challenge yourself.")
        return
    cid_a, cid_b = str(ctx.author.id), str(member.id)
    ensure_user(cid_a)
    ensure_user(cid_b)
    if bet < 0:
        await ctx.send("❌ Bet cannot be negative.")
        return
    if bet > 0 and data[cid_a]["points"] < bet:
        await ctx.send(f"❌ You don't have enough points to bet {bet}.")
        return

    cid = f"{cid_a}_{cid_b}_{task}_{int(now_local().timestamp())}"
    challenges[cid] = {"challenger": cid_a, "challenged": cid_b, "task": task, "bet": bet,
                       "status": "pending", "created_at": now_local(), "date": None}
    data[cid_a]["challenges_issued"] += 1
    if bet >= 10:
        data[cid_a]["biggest_bet"] = max(data[cid_a]["biggest_bet"], bet)
    save_data()

    bet_text = f" for **{bet} pts**" if bet > 0 else ""
    embed = discord.Embed(
        title=title,
        description=f"{ctx.author.mention} challenged {member.mention}: who logs more hours of "
                    f"**{TASKS[task]['name']}** on the day it's accepted{bet_text}?",
        color=discord.Color.red())
    embed.set_footer(text=f"{member.display_name}, use !accept or !decline (valid 24h)")
    await ctx.send(embed=embed)
    await check_achievements(ctx, cid_a)


@bot.command()
async def challenge(ctx, member: discord.Member, task: str, bet: int = 0):
    """!challenge @user A 5 -> who logs more hours of A on the day it is accepted"""
    task = task.upper()
    if task not in HOURS_TASKS:
        await ctx.send("❌ Challenges work with hour tasks: " + ", ".join(HOURS_TASKS))
        return
    await issue_challenge(ctx, member, task, bet)


@bot.command(name="randomchallenge", aliases=["rc"])
async def randomchallenge(ctx, member: discord.Member, bet: int = 0):
    """!randomchallenge @user 5 -> the bot picks the hour task"""
    await issue_challenge(ctx, member, random.choice(HOURS_TASKS), bet, title="🎲 Random Challenge!")


def _pending_for(user_id):
    expire_challenges()
    pending = [(cid, c) for cid, c in challenges.items() if c["challenged"] == user_id and c["status"] == "pending"]
    return sorted(pending, key=lambda x: x[1]["created_at"], reverse=True)


@bot.command()
async def accept(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)
    pending = _pending_for(user_id)
    if not pending:
        await ctx.send("❌ You have no pending challenges.")
        return
    cid, c = pending[0]
    if c["bet"] > 0 and data[user_id]["points"] < c["bet"]:
        await ctx.send(f"❌ You don't have enough points to accept this {c['bet']} pt bet.")
        return
    c["status"], c["date"] = "accepted", user_today_str(data[user_id])
    c["accepted_at"] = datetime.now(timezone.utc)
    embed = discord.Embed(
        title="✅ Challenge Accepted!",
        description=f"Both log **{TASKS[c['task']]['name']}** hours during their own current day "
                    f"(each in their own timezone). Whoever has more wins. "
                    f"The result is posted at the next 8:00 post after both days are over.",
        color=discord.Color.green())
    if c["bet"] > 0:
        embed.add_field(name="💰 Prize", value=f"{c['bet']} pts from the loser")
    await ctx.send(embed=embed)


@bot.command()
async def decline(ctx):
    pending = _pending_for(str(ctx.author.id))
    if not pending:
        await ctx.send("❌ You have no pending challenges.")
        return
    pending[0][1]["status"] = "declined"
    await ctx.send("❌ Challenge declined.")


@bot.command()
async def mychallenges(ctx):
    user_id = str(ctx.author.id)
    expire_challenges()
    active = [(cid, c) for cid, c in challenges.items()
              if user_id in (c["challenger"], c["challenged"]) and c["status"] in ("pending", "accepted")]
    if not active:
        await ctx.send("You have no active challenges.")
        return
    embed = discord.Embed(title="⚔️ Your Challenges", color=discord.Color.red())
    for cid, c in active:
        other_id = c["challenged"] if c["challenger"] == user_id else c["challenger"]
        other = await get_name(other_id)
        text = f"Status: **{c['status']}** | Bet: {c['bet']} pts"
        if c["status"] == "accepted":
            mine = data[user_id]["records"].get(challenge_day(c, user_id), {"tasks": {}})["tasks"].get(c["task"], 0)
            theirs = data[other_id]["records"].get(challenge_day(c, other_id), {"tasks": {}})["tasks"].get(c["task"], 0)
            text += f"\nYou {mine:g} h vs {other} {theirs:g} h"
        embed.add_field(name=f"{TASKS[c['task']]['name']} vs {other}", value=text, inline=False)
    await ctx.send(embed=embed)


# ======================================================================
#  LEADERBOARDS
# ======================================================================
@bot.command()
async def alltime(ctx):
    rows = sorted(((uid, u["earned"]) for uid, u in data.items()), key=lambda x: x[1], reverse=True)
    if not rows:
        await ctx.send("No data yet.")
        return
    embed = await leaderboard_embed(
        "🏆 All-Time Leaderboard", discord.Color.gold(), rows,
        lambda uid, v: f"{v} pts | 🔥 {get_streak(data[uid])}d | 🏅 {earned_count(data[uid])} achievements")
    await ctx.send(embed=embed)


@bot.command()
async def weekly(ctx):
    end = user_today(ensure_user(str(ctx.author.id)))
    embed = await weekly_embed(end - timedelta(days=6), end, "📅 Weekly Leaderboard (last 7 days)")
    await ctx.send(embed=embed) if embed else await ctx.send("No activity in the past 7 days.")


@bot.command()
async def category(ctx, task: str):
    task = task.upper()
    if task not in TASKS:
        await ctx.send("❌ Invalid task. Use `!tasks` to see valid tasks.")
        return
    t = TASKS[task]
    unit = "h" if t["type"] == "hours" else "days"
    rows = [(uid, _hours(u, task) if t["type"] == "hours" else _units(u, task)) for uid, u in data.items()]
    rows = sorted([r for r in rows if r[1] > 0], key=lambda x: x[1], reverse=True)
    if not rows:
        await ctx.send(f"No data for **{t['name']}** yet.")
        return
    embed = await leaderboard_embed(f"🧩 {t['name']} Leaderboard", discord.Color.purple(), rows,
                                    lambda uid, v: f"{v:g} {unit}")
    await ctx.send(embed=embed)


# ======================================================================
#  SHOP
# ======================================================================
@bot.command()
async def shop(ctx):
    u = ensure_user(str(ctx.author.id))
    pts = u["points"]
    embed = discord.Embed(title="🛒 Shop",
                          description=f"💰 Your balance: **{pts} pts**\n✅ = affordable  ❌ = need more points",
                          color=discord.Color.gold())
    for category_name, items in SHOP_CATEGORIES.items():
        lines = [f"{'✅' if pts >= price else '❌'} {item} — **{price} pts**" for item, price in items.items()]
        embed.add_field(name=category_name, value="\n".join(lines), inline=False)
    embed.set_footer(text="Use !buy <item name> to purchase | !progress to see how close you are")
    await ctx.send(embed=embed)


@bot.command()
async def progress(ctx):
    u = ensure_user(str(ctx.author.id))
    pts = u["points"]
    embed = discord.Embed(title="🛒 Shop Progress", color=discord.Color.gold())
    for item, price in sorted(SHOP.items(), key=lambda x: x[1])[:25]:
        if pts >= price:
            bar = "✅ Can afford!"
        else:
            filled = int(max(pts, 0) / price * 10)
            bar = "█" * filled + "░" * (10 - filled) + f" {pts}/{price} pts"
        embed.add_field(name=item, value=bar, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def buy(ctx, *, item: str):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    name = find_shop_item(item)
    if not name:
        await ctx.send("❌ Item not found. Use `!shop` to see available items.")
        return
    price = SHOP[name]
    if u["points"] < price:
        await ctx.send(f"❌ Not enough points. You need **{price - u['points']}** more pts.")
        return
    u["points"] -= price
    u["inventory"].append(name)
    u["total_spent"] += price
    if name not in u["items_bought"]:
        u["items_bought"].append(name)
    if name == "Send a letter":
        u["bought_letter"] = True
    save_data()
    embed = discord.Embed(title="✅ Purchase Successful!", description=f"You bought **{name}**!", color=discord.Color.green())
    embed.add_field(name="💰 Remaining Points", value=f"{u['points']} pts")
    embed.set_footer(text="Check your inventory with !inventory")
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)


@bot.command()
async def use(ctx, *, item: str):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    match = next((i for i in u["inventory"] if i.lower() == item.strip().lower()), None)
    if not match:
        await ctx.send(f"❌ You don't have **{item}** in your inventory.")
        return
    u["inventory"].remove(match)
    u["used_count"] += 1
    save_data()
    await ctx.send(embed=discord.Embed(title="🎉 Item Used!", description=f"**{match}** has been activated!",
                                       color=discord.Color.green()))
    await check_achievements(ctx, user_id)


@bot.command()
async def inventory(ctx, member: discord.Member = None):
    member = member or ctx.author
    u = ensure_user(str(member.id))
    if not u["inventory"]:
        await ctx.send(f"🎒 **{member.display_name}'s** inventory is empty.")
        return
    embed = discord.Embed(title=f"🎒 {member.display_name}'s Inventory", color=discord.Color.blurple())
    for item, count in Counter(u["inventory"]).items():
        embed.add_field(name=item, value=f"x{count}", inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")


# ======================================================================
#  GAMBLING
# ======================================================================
def track_gamble(u, amount):
    u["total_gambles"] += 1
    u["biggest_single_bet"] = max(u["biggest_single_bet"], amount)


@bot.command()
async def gamble(ctx):
    embed = discord.Embed(title="🎰 Gambling Den", description="Choose a game to play:", color=discord.Color.dark_gold())
    embed.add_field(name="🎁 `!mysterybox`", value=f"Pay {MYSTERY_BOX_COST} pts, win a random shop item. Pricier items are rarer.", inline=False)
    embed.add_field(name="🎲 `!doubleornothing <amount>`", value="50/50 to double your bet or lose it.", inline=False)
    embed.add_field(name="🪙 `!coinflip @user <amount>`", value="Challenge someone to a 50/50 flip.", inline=False)
    embed.add_field(name="🎰 `!slots <amount>`", value="Spin 3 reels, match symbols to win.", inline=False)
    embed.add_field(name="💣 `!minesweeper <amount>`", value="Reveal safe tiles, cash out before a mine.", inline=False)
    embed.add_field(name="🃏 `!blackjack <amount>`", value="Beat the dealer without going over 21.", inline=False)
    embed.set_footer(text="Gamble responsibly, points are hard earned!")
    await ctx.send(embed=embed)


@bot.command()
async def mysterybox(ctx):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    if u["points"] < MYSTERY_BOX_COST:
        await ctx.send(f"❌ You need **{MYSTERY_BOX_COST} pts** to open a mystery box.")
        return
    u["points"] -= MYSTERY_BOX_COST
    track_gamble(u, MYSTERY_BOX_COST)
    items = list(SHOP.keys())
    max_price = max(SHOP.values())
    weights = [max_price - SHOP[i] + 1 for i in items]
    won = random.choices(items, weights=weights, k=1)[0]
    u["inventory"].append(won)
    if SHOP[won] >= 20:
        u["won_legendary"] = True
    save_data()
    rarity = "⭐ Common" if SHOP[won] <= 5 else "🌟 Rare" if SHOP[won] <= 15 else "💎 Legendary"
    embed = discord.Embed(title="🎁 Mystery Box", color=discord.Color.purple())
    embed.add_field(name="You found...", value=f"**{won}**", inline=False)
    embed.add_field(name="Rarity", value=rarity, inline=True)
    embed.add_field(name="Worth", value=f"{SHOP[won]} pts", inline=True)
    embed.add_field(name="💰 Remaining", value=f"{u['points']} pts", inline=True)
    embed.set_footer(text="Added to your inventory! Use !use <item> to activate it.")
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)


@bot.command()
async def doubleornothing(ctx, amount: int):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if u["points"] < amount:
        await ctx.send(f"❌ You don't have enough points. You have **{u['points']} pts**.")
        return
    track_gamble(u, amount)
    if random.random() < 0.5:
        u["points"] += amount
        u["earned"] += amount
        color, title, result = discord.Color.green(), "🎉 You Won!", f"+{amount} pts"
    else:
        u["points"] -= amount
        color, title, result = discord.Color.red(), "💀 You Lost!", f"-{amount} pts"
    save_data()
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Bet", value=f"{amount} pts", inline=True)
    embed.add_field(name="Result", value=result, inline=True)
    embed.add_field(name="💰 Balance", value=f"{u['points']} pts", inline=True)
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)


pending_coinflips = {}


@bot.command()
async def coinflip(ctx, member: discord.Member, amount: int):
    user_id, other_id = str(ctx.author.id), str(member.id)
    u = ensure_user(user_id)
    ensure_user(other_id)
    if member.id == ctx.author.id:
        await ctx.send("❌ You can't flip against yourself.")
        return
    if amount <= 0:
        await ctx.send("❌ Amount must be greater than 0.")
        return
    if u["points"] < amount:
        await ctx.send("❌ You don't have enough points.")
        return
    pending_coinflips[other_id] = {"challenger": user_id, "amount": amount}
    embed = discord.Embed(
        title="🪙 Coin Flip Challenge!",
        description=f"{ctx.author.mention} challenged {member.mention} to a coin flip for **{amount} pts**!",
        color=discord.Color.blurple())
    embed.set_footer(text=f"{member.display_name}: !flipaccept or !flipdecline")
    await ctx.send(embed=embed)


@bot.command()
async def flipaccept(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)
    if user_id not in pending_coinflips:
        await ctx.send("❌ You have no pending coin flip.")
        return
    flip = pending_coinflips.pop(user_id)
    challenger_id, amount = flip["challenger"], flip["amount"]
    ensure_user(challenger_id)
    if data[user_id]["points"] < amount:
        await ctx.send("❌ You don't have enough points to accept.")
        return
    if data[challenger_id]["points"] < amount:
        await ctx.send("❌ The challenger no longer has enough points.")
        return
    winner_id = random.choice([user_id, challenger_id])
    loser_id = challenger_id if winner_id == user_id else user_id
    data[winner_id]["points"] += amount
    data[winner_id]["earned"] += amount
    data[loser_id]["points"] -= amount
    track_gamble(data[user_id], amount)
    track_gamble(data[challenger_id], amount)
    save_data()
    embed = discord.Embed(title="🪙 Coin Flip Result!", color=discord.Color.gold())
    embed.add_field(name="🎉 Winner", value=f"<@{winner_id}> +{amount} pts", inline=True)
    embed.add_field(name="💀 Loser", value=f"<@{loser_id}> -{amount} pts", inline=True)
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)
    await check_achievements(ctx, challenger_id)


@bot.command()
async def flipdecline(ctx):
    if pending_coinflips.pop(str(ctx.author.id), None):
        await ctx.send("❌ Coin flip declined.")
    else:
        await ctx.send("❌ You have no pending coin flip.")


SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
SLOT_MULTIPLIERS = {"🍒": 2, "🍋": 2, "🔔": 3, "⭐": 4, "💎": 8, "7️⃣": 15}
SLOT_WEIGHTS = [30, 25, 20, 15, 7, 3]


@bot.command()
async def slots(ctx, amount: int):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if u["points"] < amount:
        await ctx.send(f"❌ Not enough points. You have **{u['points']} pts**.")
        return
    reels = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
    u["points"] -= amount
    track_gamble(u, amount)
    if reels[0] == reels[1] == reels[2]:
        mult = SLOT_MULTIPLIERS[reels[0]]
        win = amount * mult
        u["points"] += win
        u["earned"] += win
        if reels[0] == "7️⃣":
            u["slot_jackpot"] = True
        result, color = f"🎉 JACKPOT! x{mult} — +{win} pts", discord.Color.gold()
    elif len(set(reels)) == 2:
        win = int(amount * 1.5)
        u["points"] += win
        u["earned"] += win
        result, color = f"✅ Two of a kind! x1.5 — +{win} pts", discord.Color.green()
    else:
        result, color = f"💀 No match — -{amount} pts", discord.Color.red()
    save_data()
    embed = discord.Embed(title="🎰 Slot Machine", color=color)
    embed.add_field(name="Reels", value=f"[ {reels[0]} | {reels[1]} | {reels[2]} ]", inline=False)
    embed.add_field(name="Result", value=result, inline=False)
    embed.add_field(name="💰 Balance", value=f"{u['points']} pts", inline=True)
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)


active_minesweeper = {}


@bot.command()
async def minesweeper(ctx, amount: int):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if u["points"] < amount:
        await ctx.send(f"❌ Not enough points. You have **{u['points']} pts**.")
        return
    if user_id in active_minesweeper:
        await ctx.send("❌ You already have a game. Use `!reveal <1-9>` or `!cashout`.")
        return
    u["points"] -= amount
    track_gamble(u, amount)
    save_data()
    tiles = ["💣"] * 3 + ["✅"] * 6
    random.shuffle(tiles)
    active_minesweeper[user_id] = {"tiles": tiles, "revealed": [], "bet": amount, "multiplier": 1.0}
    embed = discord.Embed(
        title="💣 Minesweeper",
        description="3x3 grid with **3 mines**. Reveal tiles to raise your multiplier.\n"
                    "`!reveal <1-9>` to reveal, `!cashout` to take your winnings.",
        color=discord.Color.orange())
    embed.add_field(name="Bet", value=f"{amount} pts", inline=True)
    embed.add_field(name="Multiplier", value="1.0x", inline=True)
    embed.add_field(name="Grid", value="1️⃣ 2️⃣ 3️⃣\n4️⃣ 5️⃣ 6️⃣\n7️⃣ 8️⃣ 9️⃣", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def reveal(ctx, tile: int):
    user_id = str(ctx.author.id)
    if user_id not in active_minesweeper:
        await ctx.send("❌ No active game. Start one with `!minesweeper <amount>`.")
        return
    game = active_minesweeper[user_id]
    if tile < 1 or tile > 9:
        await ctx.send("❌ Choose a tile between 1 and 9.")
        return
    if tile - 1 in game["revealed"]:
        await ctx.send("❌ You already revealed that tile.")
        return
    game["revealed"].append(tile - 1)
    u = data[user_id]

    if game["tiles"][tile - 1] == "💣":
        del active_minesweeper[user_id]
        grid = "".join(t + (" \n" if (i + 1) % 3 == 0 else " ") for i, t in enumerate(game["tiles"]))
        embed = discord.Embed(title="💥 BOOM! You hit a mine!", color=discord.Color.red())
        embed.add_field(name="Lost", value=f"-{game['bet']} pts", inline=True)
        embed.add_field(name="💰 Balance", value=f"{u['points']} pts", inline=True)
        embed.add_field(name="Full Grid", value=grid, inline=False)
        await ctx.send(embed=embed)
        return

    game["multiplier"] = round(game["multiplier"] + 0.5, 1)
    safe_left = 6 - len([r for r in game["revealed"] if game["tiles"][r] == "✅"])
    grid = "".join((game["tiles"][i] if i in game["revealed"] else "⬜") + (" \n" if (i + 1) % 3 == 0 else " ")
                   for i in range(9))
    potential = int(game["bet"] * game["multiplier"])
    embed = discord.Embed(title="💣 Minesweeper — Safe!", color=discord.Color.green())
    embed.add_field(name="Multiplier", value=f"{game['multiplier']}x", inline=True)
    embed.add_field(name="Potential Win", value=f"{potential} pts", inline=True)
    embed.add_field(name="Safe tiles left", value=f"{safe_left}", inline=True)
    embed.add_field(name="Grid", value=grid, inline=False)
    embed.set_footer(text="!reveal <1-9> to continue or !cashout to take your winnings")
    await ctx.send(embed=embed)

    if safe_left == 0:
        win = int(game["bet"] * game["multiplier"])
        u["points"] += win
        u["earned"] += win
        u["minesweeper_pro"] = True
        save_data()
        del active_minesweeper[user_id]
        embed2 = discord.Embed(title="🎉 You cleared the board!", color=discord.Color.gold())
        embed2.add_field(name="Winnings", value=f"+{win} pts", inline=True)
        embed2.add_field(name="💰 Balance", value=f"{u['points']} pts", inline=True)
        await ctx.send(embed=embed2)
        await check_achievements(ctx, user_id)


@bot.command()
async def cashout(ctx):
    user_id = str(ctx.author.id)
    if user_id not in active_minesweeper:
        await ctx.send("❌ No active minesweeper game.")
        return
    game = active_minesweeper.pop(user_id)
    u = data[user_id]
    if len([r for r in game["revealed"] if game["tiles"][r] == "✅"]) >= 3:
        u["minesweeper_pro"] = True
    win = game["bet"] if game["multiplier"] <= 1.0 else int(game["bet"] * game["multiplier"])
    u["points"] += win
    u["earned"] += win
    save_data()
    embed = discord.Embed(title="💰 Cashed Out!", color=discord.Color.green())
    embed.add_field(name="Multiplier", value=f"{game['multiplier']}x", inline=True)
    embed.add_field(name="Winnings", value=f"+{win} pts", inline=True)
    embed.add_field(name="💰 Balance", value=f"{u['points']} pts", inline=True)
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)


active_blackjack = {}


def bj_card():
    return random.choice(["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"])


def bj_value(hand):
    total, aces = 0, 0
    for card in hand:
        if card in ("J", "Q", "K"):
            total += 10
        elif card == "A":
            aces += 1
            total += 11
        else:
            total += int(card)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def bj_hand_str(hand):
    return " | ".join(hand)


@bot.command()
async def blackjack(ctx, amount: int):
    user_id = str(ctx.author.id)
    u = ensure_user(user_id)
    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if u["points"] < amount:
        await ctx.send(f"❌ Not enough points. You have **{u['points']} pts**.")
        return
    if user_id in active_blackjack:
        await ctx.send("❌ You already have a game. Use `!hit` or `!stand`.")
        return
    track_gamble(u, amount)
    u["points"] -= amount
    save_data()
    player, dealer = [bj_card(), bj_card()], [bj_card(), bj_card()]
    active_blackjack[user_id] = {"player": player, "dealer": dealer, "bet": amount}
    total = bj_value(player)
    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.dark_green())
    embed.add_field(name="Your Hand", value=f"{bj_hand_str(player)} — **{total}**", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{dealer[0]} | ❓", inline=False)
    embed.add_field(name="Bet", value=f"{amount} pts", inline=True)
    natural = total == 21
    if natural:
        win = int(amount * 2.5)
        u["points"] += win
        u["earned"] += win
        u["natural_blackjack"] = True
        save_data()
        del active_blackjack[user_id]
        embed.add_field(name="🎉 BLACKJACK!", value=f"+{win} pts (2.5x)", inline=False)
        embed.color = discord.Color.gold()
    else:
        embed.set_footer(text="!hit to draw a card or !stand to hold")
    await ctx.send(embed=embed)
    if natural:
        await check_achievements(ctx, user_id)


@bot.command()
async def hit(ctx):
    user_id = str(ctx.author.id)
    if user_id not in active_blackjack:
        await ctx.send("❌ No active blackjack game. Start one with `!blackjack <amount>`.")
        return
    game = active_blackjack[user_id]
    game["player"].append(bj_card())
    total = bj_value(game["player"])
    if total > 21:
        del active_blackjack[user_id]
        embed = discord.Embed(title="💥 Bust! You went over 21.", color=discord.Color.red())
        embed.add_field(name="Your Hand", value=f"{bj_hand_str(game['player'])} — **{total}**", inline=False)
        embed.add_field(name="Lost", value=f"-{game['bet']} pts", inline=True)
        embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
    else:
        embed = discord.Embed(title="🃏 Blackjack — Hit!", color=discord.Color.dark_green())
        embed.add_field(name="Your Hand", value=f"{bj_hand_str(game['player'])} — **{total}**", inline=False)
        embed.add_field(name="Dealer's Hand", value=f"{game['dealer'][0]} | ❓", inline=False)
        embed.set_footer(text="!hit to draw again or !stand to hold")
    await ctx.send(embed=embed)


@bot.command()
async def stand(ctx):
    user_id = str(ctx.author.id)
    if user_id not in active_blackjack:
        await ctx.send("❌ No active blackjack game. Start one with `!blackjack <amount>`.")
        return
    game = active_blackjack.pop(user_id)
    u = data[user_id]
    player_total = bj_value(game["player"])
    while bj_value(game["dealer"]) < 17:
        game["dealer"].append(bj_card())
    dealer_total, bet = bj_value(game["dealer"]), game["bet"]
    embed = discord.Embed(title="🃏 Blackjack — Result", color=discord.Color.dark_green())
    embed.add_field(name="Your Hand", value=f"{bj_hand_str(game['player'])} — **{player_total}**", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{bj_hand_str(game['dealer'])} — **{dealer_total}**", inline=False)
    if dealer_total > 21 or player_total > dealer_total:
        u["points"] += bet * 2
        u["earned"] += bet * 2
        embed.add_field(name="🎉 You Win!", value=f"+{bet * 2} pts", inline=True)
        embed.color = discord.Color.green()
    elif player_total == dealer_total:
        u["points"] += bet
        embed.add_field(name="🤝 Push", value=f"Bet returned: {bet} pts", inline=True)
        embed.color = discord.Color.blurple()
    else:
        embed.add_field(name="💀 Dealer Wins!", value=f"-{bet} pts", inline=True)
        embed.color = discord.Color.red()
    embed.add_field(name="💰 Balance", value=f"{u['points']} pts", inline=True)
    save_data()
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)


# ======================================================================
#  HELP (builds as many embeds as needed, max 24 fields each)
# ======================================================================
HELP_SECTIONS = [
    ("📅 Daily record", [
        ("`!record`", "Open the panel (buttons)"),
        ("`!record A 4 B 1 G screen 2.5`", "Quick log. Hours add up. Add `yesterday` or a date to backfill"),
        ("`!record set A 3`", "Correct a value (also `screen 2`)"),
        ("`!record remove A`", "Remove a task or `screen`"),
        ("`!record view [date]`", "Show a day"),
        ("`!record delete [date]`", "Delete a whole day"),
        ("`!tasks`", "Tasks and point rates"),
    ]),
    ("👤 Profile & Stats", [
        ("`!profile [@user]`", "Profile and today's record"),
        ("`!streak [@user]`", "Streak and next bonus"),
        ("`!history [n]`", "Your last records"),
        ("`!tasksummary [@user]`", "Hours per task, all time"),
        ("`!best [@user]`", "Best week ever"),
        ("`!compare @user`", "Side by side stats"),
        ("`!month [@user] [YYYY-MM]`", "Monthly overview"),
    ]),
    ("🏆 Leaderboards", [
        ("`!alltime`", "All-time points"),
        ("`!weekly`", "Points of the last 7 days"),
        ("`!category <A-J>`", "Ranking for one task"),
    ]),
    ("🏅 Achievements", [("`!achievements [@user]`", "Earned and locked")]),
    ("⚔️ Challenges", [
        ("`!challenge @user <task> [bet]`", "Who logs more hours of a task today"),
        ("`!accept`", "Accept the latest challenge"),
        ("`!decline`", "Decline it"),
        ("`!mychallenges`", "Your active challenges"),
        ("`!randomchallenge @user [bet]`", "Duel on a random hour task"),
        ("`!teamchallenge @user <hours>`", "Co-op: reach the hours together in 7 days"),
        ("`!teamchallengeview`", "Team challenge status"),
    ]),
    ("🎯 Quests & Goals", [
        ("`!quest`", "Today's 3 quests (easy / medium / hard)"),
        ("`!quest choose <1-3>`", "Pick a quest (counts hours logged after)"),
        ("`!quest progress`", "Status of your quest"),
        ("`!goal`", "Your weekly goals"),
        ("`!goal set A 8 [10]`", "Weekly goal + optional stretch"),
        ("`!goal remove A`", "Remove a goal"),
    ]),
    ("🛒 Shop", [
        ("`!shop`", "Browse the shop"),
        ("`!buy <item>`", "Buy an item"),
        ("`!use <item>`", "Use an item"),
        ("`!inventory [@user]`", "Show inventory"),
        ("`!progress`", "Progress toward items"),
    ]),
    ("🎰 Gambling", [
        ("`!gamble`", "All games"),
        ("`!mysterybox`", f"{MYSTERY_BOX_COST} pts for a random item"),
        ("`!doubleornothing <amt>`", "50/50"),
        ("`!coinflip @user <amt>`", "Flip against someone"),
        ("`!flipaccept` / `!flipdecline`", "Answer a flip"),
        ("`!slots <amt>`", "Slot machine"),
        ("`!minesweeper <amt>`", "Start minesweeper"),
        ("`!reveal <1-9>` / `!cashout`", "Play / cash out"),
        ("`!blackjack <amt>`", "Start blackjack"),
        ("`!hit` / `!stand`", "Play blackjack"),
    ]),
    ("🔧 Other", [("`!timezone [name]`", "Show / set your timezone"), ("`!ping`", "Latency")]),
]


@bot.command(name="help")
async def help_command(ctx):
    def fresh():
        return discord.Embed(color=discord.Color.blurple())

    embeds, embed, count = [], fresh(), 0
    for title, cmds in HELP_SECTIONS:
        need = 1 + len(cmds)
        if count + need > 24:
            embeds.append(embed)
            embed, count = fresh(), 0
        embed.add_field(name=f"━━━ {title} ━━━", value="\u200b", inline=False)
        for cmd, desc in cmds:
            embed.add_field(name=cmd, value=desc, inline=True)
        count += need
    embeds.append(embed)
    for i, e in enumerate(embeds, start=1):
        e.title = f"📖 Bot Commands ({i}/{len(embeds)})"
    embeds[-1].set_footer(text="Arguments in <> are required, [] are optional")
    for e in embeds:
        await ctx.send(embed=e)


# ======================================================================
if __name__ == "__main__":
    bot.run(os.environ.get("TOKEN"))