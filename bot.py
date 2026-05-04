import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta, time as dtime
from collections import Counter
import random

# ---------- INTENTS ----------
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------- CONFIG ----------
DATA_FILE = "/app/data/data.json"
ANNOUNCE_CHANNEL_ID = 1500210291890327742  # 🔧 Replace with your channel ID

SHOP = {
    # 💬 Communication
    "Compliment for 3 minutes":         8,
    "Romantic word":                     1,
    "Voice message":                     3,
    "Ask me anything":                   8,
    "Personal playlist made for you":   20,

    # 📸 Media & Content
    "Send a photo now":                  3,
    "Good selfie":                       5,
    "Movie/media recommendation":        1,
    "Draw something":                   20,

    # 🎮 Activities Together
    "Game to play together":             5,
    "Workout together":                 16,
    "Study together session":            8,
    "Learn something together (30 min)":10,

    # 📅 Control & Decisions
    "Request call at a specific time":   5,
    "Pick what I eat":                   5,
    "Outfit choice":                    15,
    "You decide my schedule tomorrow":  15,
    "Force someone to do a task":       10,
    "Block other person's action (YT Shorts, scrolling, X, etc.)": 30,

    # 🎁 Special
    "Language teacher for 1 hour":      15,
    "Very close attention for 15 minutes": 10,
    "Dance":                            15,
    "Send a letter":                    50,
    "Belohnung":                        25,
}


# ---------- TASKS ----------
TASKS = {
    "A": {"name": "A - Study", "description": "Study for 1 hour uninterrupted", "reward": 1},
    "B": {"name": "B - Reading", "description": "Read a book for 30 minutes", "reward": 1},
    "C": {"name": "C - Running", "description": "Go out and run", "reward": 1},
    "D": {"name": "D - Sports", "description": "Do a non superfluous sports/training session", "reward": 1},
    "E": {"name": "E - Research", "description": "Research a topic of interest", "reward": 1},
    "F": {"name": "F - Language studying", "description": "Study a language (english, german, japanese)", "reward": 1},
    "G": {"name": "G - Waking up", "description": "No phone when waking up", "reward": 1},
    "H": {"name": "H - Screentime", "description": "Have a daily screentime smaller than 3 hours", "reward": 2},
    "I": {"name": "I - Cleaning", "description": "Cleaning room well", "reward": 1},
    "J": {"name": "J - Sleep", "description": "No phone before going to sleep", "reward": 1},
}

# ---------- ACHIEVEMENTS ----------
ACHIEVEMENTS = {
    # 🎯 First Steps
    "first_blood":      {"name": "🎯 First Blood",       "desc": "Complete your first task",                          "check": lambda u: u["earned"] >= 1},
    "first_purchase":   {"name": "🛒 First Purchase",    "desc": "Buy your first item from the shop",                 "check": lambda u: u.get("total_spent", 0) >= 1},
    "first_challenge":  {"name": "⚔️ First Challenge",   "desc": "Issue your first challenge",                        "check": lambda u: u.get("challenges_issued", 0) >= 1},
    "gambler":          {"name": "🎰 Gambler",           "desc": "Place your first gamble",                           "check": lambda u: u.get("total_gambles", 0) >= 1},

    # 🔥 Streaks
    "week_warrior":     {"name": "🔥 Week Warrior",      "desc": "Reach a 7-day streak",                              "check": lambda u: u.get("streak", 0) >= 7},
    "month_legend":     {"name": "⚡ Month Legend",      "desc": "Reach a 30-day streak",                             "check": lambda u: u.get("streak", 0) >= 30},
    "unstoppable":      {"name": "🌪️ Unstoppable",       "desc": "Reach a 60-day streak",                             "check": lambda u: u.get("streak", 0) >= 60},
    "immortal":         {"name": "♾️ Immortal",           "desc": "Reach a 100-day streak",                            "check": lambda u: u.get("streak", 0) >= 100},

    # 📋 Tasks
    "completionist":    {"name": "✅ Completionist",     "desc": "Complete every task type at least once",            "check": lambda u: len(set(e["task"] for e in u["history"])) >= len(TASKS)},
    "all_in_one_day":   {"name": "💥 All In One Day",   "desc": "Complete all 10 tasks in a single day",             "check": lambda u: _all_in_one_day(u)},
    "jack_of_trades":   {"name": "🃏 Jack of All Trades","desc": "Complete 5 different tasks in one day",             "check": lambda u: _jack_of_trades(u)},
    "speed_claimer":    {"name": "⚡ Speed Claimer",     "desc": "Claim 5 tasks within 1 minute",                     "check": lambda u: _speed_claimer(u)},
    "grinder":          {"name": "⚙️ Grinder",           "desc": "Complete 50 tasks total",                           "check": lambda u: len(u["history"]) >= 50},
    "dedicated":        {"name": "🏆 Dedicated",         "desc": "Complete 100 tasks total",                          "check": lambda u: len(u["history"]) >= 100},

    # 📚 Task Specific
    "bookworm":         {"name": "📚 Bookworm",          "desc": "Complete task B (Reading) 10 times",                "check": lambda u: sum(1 for e in u["history"] if e["task"] == "B") >= 10},
    "researcher":       {"name": "🔬 Researcher",        "desc": "Complete task A (Study) 50 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "A") >= 50},
    "avid_reader":      {"name": "📖 Avid Reader",       "desc": "Complete task B (Reading) 40 times",                "check": lambda u: sum(1 for e in u["history"] if e["task"] == "B") >= 40},
    "marathon_runner":  {"name": "🏃 Marathon Runner",   "desc": "Complete task C (Running) 20 times",                "check": lambda u: sum(1 for e in u["history"] if e["task"] == "C") >= 20},
    "superhuman":       {"name": "💪 Superhuman",        "desc": "Complete task D (Sports) 40 times",                 "check": lambda u: sum(1 for e in u["history"] if e["task"] == "D") >= 40},
    "polyglot":         {"name": "🌍 Citizen of the World","desc": "Complete task F (Language) 40 times",             "check": lambda u: sum(1 for e in u["history"] if e["task"] == "F") >= 40},
    "freedom":          {"name": "📵 Freedom",           "desc": "Complete task H (Screentime) 35 times",             "check": lambda u: sum(1 for e in u["history"] if e["task"] == "H") >= 35},
    "clean_freak":      {"name": "🧹 Clean Freak",       "desc": "Complete task I (Cleaning) 15 times",               "check": lambda u: sum(1 for e in u["history"] if e["task"] == "I") >= 15},
    "night_owl":        {"name": "🌙 Disciplined",       "desc": "Complete task J (Sleep) 20 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "J") >= 20},

    # 💰 Points
    "rich":             {"name": "💎 Rich",              "desc": "Earn 100 points total",                             "check": lambda u: u["earned"] >= 100},
    "millionaire":      {"name": "👑 Millionaire",       "desc": "Earn 500 points total",                             "check": lambda u: u["earned"] >= 500},
    "saving_up":        {"name": "🐷 Saving Up",         "desc": "Have 50 pts at once without spending",              "check": lambda u: u["points"] >= 50},
    "rich_kid":         {"name": "💰 Rich Kid",          "desc": "Have 100 pts at once",                              "check": lambda u: u["points"] >= 100},
    "vault":            {"name": "🏦 Vault",             "desc": "Have 200 pts at once",                              "check": lambda u: u["points"] >= 200},

    # 🛒 Shop
    "big_spender":      {"name": "💸 Big Spender",       "desc": "Spend 50 pts total in the shop",                    "check": lambda u: u.get("total_spent", 0) >= 50},
    "collector":        {"name": "🗃️ Collector",          "desc": "Own 5 different items at once in inventory",        "check": lambda u: len(set(u.get("inventory", []))) >= 5},
    "generous":         {"name": "🤲 Generous",          "desc": "Use 10 items total",                                "check": lambda u: u.get("used_count", 0) >= 10},
    "letter_sender":    {"name": "✉️ Letter Sender",      "desc": "Buy the 'Send a letter' item",                      "check": lambda u: u.get("bought_letter", False)},
    "billionaire":      {"name": "🤑 Billionaire",       "desc": "Buy every single shop item at least once",          "check": lambda u: _bought_all_items(u)},

    # ⚔️ Challenges
    "undefeated":       {"name": "🏅 Undefeated",        "desc": "Win 5 challenges",                                  "check": lambda u: u.get("challenges_won", 0) >= 5},
    "bold":             {"name": "😤 Bold",              "desc": "Issue a challenge with a 10+ pt bet",               "check": lambda u: u.get("biggest_bet", 0) >= 10},
    "challenger":       {"name": "⚔️ Challenger",        "desc": "Issue 3 challenges",                                "check": lambda u: u.get("challenges_issued", 0) >= 3},

    # 🎰 Gambling
    "gambling_addiction":{"name": "🎲 Gambling Addiction","desc": "Bet 50+ pts in a single gamble",                   "check": lambda u: u.get("biggest_single_bet", 0) >= 50},
    "slot_god":         {"name": "🎰 Slot God",          "desc": "Hit a triple 7 jackpot on slots",                   "check": lambda u: u.get("slot_jackpot", False)},
    "lucky_box":        {"name": "🎁 Lucky Box",         "desc": "Win a legendary item from mystery box",             "check": lambda u: u.get("won_legendary", False)},
    "blackjack_ach":    {"name": "🃏 Blackjack!",        "desc": "Get a natural blackjack",                           "check": lambda u: u.get("natural_blackjack", False)},
    "bosnian":          {"name": "💣 Bosnian",           "desc": "Cash out minesweeper with 3+ safe tiles revealed",  "check": lambda u: u.get("minesweeper_pro", False)},
}
def _all_in_one_day(u):
    from collections import defaultdict
    days = defaultdict(set)
    for e in u["history"]:
        day = e["time"][:10]
        days[day].add(e["task"])
    return any(len(tasks) >= len(TASKS) for tasks in days.values())

def _jack_of_trades(u):
    from collections import defaultdict
    days = defaultdict(set)
    for e in u["history"]:
        day = e["time"][:10]
        days[day].add(e["task"])
    return any(len(tasks) >= 5 for tasks in days.values())

def _speed_claimer(u):
    if len(u["history"]) < 5:
        return False
    times = [datetime.strptime(e["time"], "%Y-%m-%d %H:%M:%S") for e in u["history"]]
    for i in range(len(times) - 4):
        window = times[i:i+5]
        if (max(window) - min(window)).seconds <= 60:
            return True
    return False

def _bought_all_items(u):
    return all(item in u.get("items_bought", []) for item in SHOP.keys())

# ---------- LOAD / SAVE ----------
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# ---------- CHALLENGES STORAGE ----------
challenges = {}  # {challenge_id: {challenger, challenged, task, bet, status, created_at}}

def ensure_user(user_id):
    if user_id not in data:
        data[user_id] = {
            "points": 0,
            "earned": 0,
            "history": [],
            "inventory": [],
            "last_claim_date": None,
            "streak": 0,
            "achievements": [],
            "challenges_won": 0,
            "challenges_issued": 0,
            "used_count": 0,
            "total_spent": 0,
            "total_gambles": 0,
            "biggest_single_bet": 0,
            "biggest_bet": 0,
            "slot_jackpot": False,
            "won_legendary": False,
            "natural_blackjack": False,
            "minesweeper_pro": False,
            "bought_letter": False,
            "items_bought": [],
        }
    for field, default in [
        ("last_claim_date", None),
        ("streak", 0),
        ("achievements", []),
        ("challenges_won", 0),
        ("challenges_issued", 0),
        ("used_count", 0),
        ("total_spent", 0),
        ("total_gambles", 0),
        ("biggest_single_bet", 0),
        ("biggest_bet", 0),
        ("slot_jackpot", False),
        ("won_legendary", False),
        ("natural_blackjack", False),
        ("minesweeper_pro", False),
        ("bought_letter", False),
        ("items_bought", []),
    ]:
        if field not in data[user_id]:
            data[user_id][field] = default

# ---------- ACHIEVEMENT CHECKER ----------
async def check_achievements(ctx, user_id):
    user = data[user_id]
    newly_earned = []

    for key, ach in ACHIEVEMENTS.items():
        if key not in user["achievements"]:
            try:
                if ach["check"](user):
                    user["achievements"].append(key)
                    newly_earned.append(ach)
            except Exception:
                pass

    if newly_earned:
        for ach in newly_earned:
            # Give 1 point per achievement
            data[user_id]["points"] += 1
            data[user_id]["earned"] += 1

            save_data(data)
            embed = discord.Embed(
                title="🏅 Achievement Unlocked!",
                description=f"**{ach['name']}**\n{ach['desc']}\n\n+1 bonus point rewarded!",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)

# ---------- STREAK HELPERS ----------
def update_streak(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    last = data[user_id].get("last_claim_date")

    if last == today:
        return
    elif last == yesterday:
        data[user_id]["streak"] += 1
    else:
        data[user_id]["streak"] = 1

    data[user_id]["last_claim_date"] = today

def get_streak_bonus(streak):
    if streak >= 30:
        return 3
    elif streak >= 14:
        return 2
    elif streak >= 7:
        return 1
    return 0

# ---------- BOT READY ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    weekly_announcement.start()
    expire_challenges.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    await bot.process_commands(message)

# ---------- WEEKLY ANNOUNCEMENT ----------

@tasks.loop(time=dtime(hour=8, minute=0))
async def weekly_announcement():
    await bot.wait_until_ready()
    now = datetime.now()
    if now.weekday() != 0:
        return

    channel = bot.get_channel(ANNOUNCE_CHANNEL_ID)
    if not channel:
        return

    week_ago = now - timedelta(days=7)
    results = {}

    for user_id, info in data.items():
        total = sum(
            e["points"] for e in info.get("history", [])
            if datetime.strptime(e["time"], "%Y-%m-%d %H:%M:%S") >= week_ago
        )
        if total > 0:
            results[user_id] = total

    if not results:
        await channel.send("📅 No activity this past week!")
        return

    sorted_users = sorted(results.items(), key=lambda x: x[1], reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    embed = discord.Embed(title="📅 Weekly Leaderboard — Automatic Summary", color=discord.Color.blue())

    for i, (user_id, pts) in enumerate(sorted_users[:10], start=1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.mention
        except discord.NotFound:
            name = "Unknown"
        medal = medals[i - 1] if i <= 3 else f"{i}."
        embed.add_field(name=f"{medal} {name}", value=f"{pts} pts", inline=False)

    await channel.send(embed=embed)

# ---------- EXPIRE CHALLENGES (every hour) ----------
@tasks.loop(hours=1)
async def expire_challenges():
    now = datetime.now()
    expired = [cid for cid, c in challenges.items()
               if c["status"] == "pending" and now - c["created_at"] > timedelta(hours=24)]
    for cid in expired:
        challenges[cid]["status"] = "expired"

# ---------- CLAIM ----------
@bot.command()
async def claim(ctx, *tasks_input):
    user_id = str(ctx.author.id)

    if not tasks_input:
        await ctx.send("❌ Please provide at least one task. Example: `!claim A B C`")
        return

    ensure_user(user_id)
    update_streak(user_id)
    streak = data[user_id]["streak"]
    bonus = get_streak_bonus(streak)

    results = []
    total_reward = 0

    for task in tasks_input:
        task = task.upper()

        if task not in TASKS:
            results.append(f"❌ `{task}` — invalid task")
            continue

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        reward = TASKS[task]["reward"] + bonus
        data[user_id]["points"] += reward
        data[user_id]["earned"] += reward
        data[user_id]["history"].append({"points": reward, "task": task, "time": now})
        total_reward += reward
        results.append(f"✅ **{TASKS[task]['name']}** +{reward} pts")

    save_data(data)

    bonus_text = f" *(+{bonus} streak bonus per task!)*" if bonus > 0 else ""
    streak_text = f"🔥 Streak: **{streak} day{'s' if streak != 1 else ''}**"

    embed = discord.Embed(title="📋 Tasks Claimed", color=discord.Color.green())
    embed.description = "\n".join(results)
    embed.add_field(name="💰 Total Earned", value=f"+{total_reward} pts{bonus_text}", inline=True)
    embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
    embed.set_footer(text=streak_text)

    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)
# ---------- CHALLENGE ----------
@bot.command()
async def challenge(ctx, member: discord.Member, task: str, bet: int = 0):
    """Challenge someone to complete a task first. !challenge @user A 5"""
    if member.id == ctx.author.id:
        await ctx.send("❌ You can't challenge yourself.")
        return

    task = task.upper()
    if task not in TASKS:
        await ctx.send("❌ Invalid task. Use `!tasks` to see valid tasks.")
        return

    challenger_id = str(ctx.author.id)
    challenged_id = str(member.id)

    ensure_user(challenger_id)
    ensure_user(challenged_id)

    if bet < 0:
        await ctx.send("❌ Bet cannot be negative.")
        return

    if bet > 0 and data[challenger_id]["points"] < bet:
        await ctx.send(f"❌ You don't have enough points to bet {bet}.")
        return

    cid = f"{challenger_id}_{challenged_id}_{task}_{int(datetime.now().timestamp())}"
    challenges[cid] = {
        "challenger": challenger_id,
        "challenged": challenged_id,
        "task": task,
        "bet": bet,
        "status": "pending",
        "created_at": datetime.now(),
        "started_at": None,
    }

    data[challenger_id]["challenges_issued"] = data[challenger_id].get("challenges_issued", 0) + 1
    if bet >= 10:
        data[challenger_id]["biggest_bet"] = max(data[challenger_id].get("biggest_bet", 0), bet)
    save_data(data)


    bet_text = f" for **{bet} pts**" if bet > 0 else ""
    embed = discord.Embed(
        title="⚔️ Challenge Issued!",
        description=f"{ctx.author.mention} challenged {member.mention} to complete **{TASKS[task]['name']}** first{bet_text}!",
        color=discord.Color.red()
    )
    embed.add_field(name="Task", value=TASKS[task]["name"], inline=True)
    embed.add_field(name="Bet", value=f"{bet} pts" if bet > 0 else "No bet", inline=True)
    embed.set_footer(text=f"Challenge ID: {cid[:20]}... | {member.name}, use !accept or !decline")
    await ctx.send(embed=embed)
    await check_achievements(ctx, challenger_id)

# ---------- ACCEPT CHALLENGE ----------
@bot.command()
async def accept(ctx):
    """Accept the most recent pending challenge against you."""
    user_id = str(ctx.author.id)
    pending = [
        (cid, c) for cid, c in challenges.items()
        if c["challenged"] == user_id and c["status"] == "pending"
    ]

    if not pending:
        await ctx.send("❌ You have no pending challenges.")
        return

    cid, c = sorted(pending, key=lambda x: x[1]["created_at"], reverse=True)[0]

    ensure_user(user_id)
    if c["bet"] > 0 and data[user_id]["points"] < c["bet"]:
        await ctx.send(f"❌ You don't have enough points to accept this {c['bet']} pt bet.")
        return

    data[user_id]["total_gambles"] = data[user_id].get("total_gambles", 0) + 1
    data[user_id]["biggest_single_bet"] = max(data[user_id].get("biggest_single_bet", 0), amount)

    challenges[cid]["status"] = "accepted"
    challenges[cid]["started_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    embed = discord.Embed(
        title="✅ Challenge Accepted!",
        description=f"The race is on! Both players must complete **{TASKS[c['task']]['name']}**. First to `!claim {c['task']}` wins!",
        color=discord.Color.green()
    )
    if c["bet"] > 0:
        embed.add_field(name="💰 Prize", value=f"{c['bet']} pts to the winner")
    await ctx.send(embed=embed)

# ---------- DECLINE CHALLENGE ----------
@bot.command()
async def decline(ctx):
    """Decline the most recent pending challenge against you."""
    user_id = str(ctx.author.id)
    pending = [
        (cid, c) for cid, c in challenges.items()
        if c["challenged"] == user_id and c["status"] == "pending"
    ]

    if not pending:
        await ctx.send("❌ You have no pending challenges.")
        return

    cid, c = sorted(pending, key=lambda x: x[1]["created_at"], reverse=True)[0]
    challenges[cid]["status"] = "declined"

    await ctx.send(f"❌ Challenge declined.")

# ---------- CHALLENGES LIST ----------
@bot.command()
async def mychallenges(ctx):
    """See your active challenges."""
    user_id = str(ctx.author.id)
    active = [
        (cid, c) for cid, c in challenges.items()
        if user_id in [c["challenger"], c["challenged"]] and c["status"] in ["pending", "accepted"]
    ]

    if not active:
        await ctx.send("You have no active challenges.")
        return

    embed = discord.Embed(title="⚔️ Your Challenges", color=discord.Color.red())
    for cid, c in active:
        try:
            other_id = c["challenged"] if c["challenger"] == user_id else c["challenger"]
            other = await bot.fetch_user(int(other_id))
            other_name = other.name
        except discord.NotFound:
            other_name = "Unknown"

        role = "Challenger" if c["challenger"] == user_id else "Challenged"
        embed.add_field(
            name=f"{TASKS[c['task']]['name']} vs {other_name}",
            value=f"Status: **{c['status']}** | Bet: {c['bet']} pts | Role: {role}",
            inline=False
        )

    await ctx.send(embed=embed)

# ---------- ACHIEVEMENTS ----------
@bot.command()
async def achievements(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    ensure_user(user_id)

    earned = data[user_id]["achievements"]

    earned_list = []
    locked_list = []

    for key, ach in ACHIEVEMENTS.items():
        if key in earned:
            earned_list.append(f"{ach['name']} — {ach['desc']}")
        else:
            locked_list.append(f"🔒 {ach['desc']}")

    # Split into chunks of 10 to avoid field length limit
    def chunks(lst, n):
        for i in range(0, len(lst), n):
            yield lst[i:i + n]

    embed1 = discord.Embed(
        title=f"🏅 {member.name}'s Achievements ({len(earned)}/{len(ACHIEVEMENTS)})",
        color=discord.Color.gold()
    )

    earned_text = "\n".join(earned_list) if earned_list else "None yet — start claiming tasks!"
    embed1.add_field(
        name=f"✅ Earned ({len(earned)})",
        value=earned_text[:1024],
        inline=False
    )

    await ctx.send(embed=embed1)

    # Send locked in chunks
    locked_chunks = list(chunks(locked_list, 10))
    for i, chunk in enumerate(locked_chunks):
        embed = discord.Embed(
            title=f"🔒 Locked Achievements ({i+1}/{len(locked_chunks)})",
            color=discord.Color.dark_gray()
        )
        embed.add_field(
            name=f"Locked ({len(locked_list)} remaining)",
            value="\n".join(chunk),
            inline=False
        )
        await ctx.send(embed=embed)
# ---------- PROFILE ----------
@bot.command()
async def profile(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    ensure_user(user_id)
    info = data[user_id]

    today = datetime.now().strftime("%Y-%m-%d")
    claimed_today = [e["task"] for e in info["history"] if e["time"].startswith(today)]
    not_claimed = [k for k in TASKS if k not in claimed_today]
    earned_achievements = info.get("achievements", [])

    embed = discord.Embed(title=f"👤 {member.name}'s Profile", color=discord.Color.blurple())
    embed.add_field(name="💰 Current Points", value=f"{info['points']} pts", inline=True)
    embed.add_field(name="🏆 Total Earned", value=f"{info['earned']} pts", inline=True)
    embed.add_field(name="🔥 Streak", value=f"{info.get('streak', 0)} days", inline=True)
    embed.add_field(name="🎒 Inventory", value=f"{len(info['inventory'])} items", inline=True)
    embed.add_field(name="🏅 Achievements", value=f"{len(earned_achievements)}/{len(ACHIEVEMENTS)}", inline=True)
    embed.add_field(name="⚔️ Challenges Won", value=f"{info.get('challenges_won', 0)}", inline=True)
    embed.add_field(name="✅ Claimed Today", value=", ".join(claimed_today) if claimed_today else "None", inline=False)
    embed.add_field(name="⏳ Remaining Today", value=", ".join(not_claimed) if not_claimed else "All done! 🎉", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)

    await ctx.send(embed=embed)

# ---------- COMPARE ----------
@bot.command()
async def compare(ctx, member: discord.Member):
    """Side by side stats with another user."""
    uid1 = str(ctx.author.id)
    uid2 = str(member.id)
    ensure_user(uid1)
    ensure_user(uid2)

    u1 = data[uid1]
    u2 = data[uid2]

    week_ago = datetime.now() - timedelta(days=7)

    def weekly_pts(u):
        return sum(
            e["points"] for e in u.get("history", [])
            if datetime.strptime(e["time"], "%Y-%m-%d %H:%M:%S") >= week_ago
        )

    def top_task(u):
        counts = Counter(e["task"] for e in u.get("history", []))
        if not counts:
            return "None"
        top = counts.most_common(1)[0]
        return f"{top[0]} ({top[1]}x)"

    embed = discord.Embed(
        title=f"📊 {ctx.author.name} vs {member.name}",
        color=discord.Color.blurple()
    )

    def fmt(val1, val2, higher_is_better=True):
        if val1 == val2:
            return f"{val1} 🟰", f"{val2} 🟰"
        if (val1 > val2) == higher_is_better:
            return f"**{val1} ✅**", f"{val2}"
        return f"{val1}", f"**{val2} ✅**"

    rows = [
        ("💰 Current Points", u1["points"], u2["points"]),
        ("🏆 Total Earned", u1["earned"], u2["earned"]),
        ("🔥 Streak", u1.get("streak", 0), u2.get("streak", 0)),
        ("📅 This Week", weekly_pts(u1), weekly_pts(u2)),
        ("📋 Total Tasks", len(u1["history"]), len(u2["history"])),
        ("🏅 Achievements", len(u1.get("achievements", [])), len(u2.get("achievements", []))),
        ("⚔️ Challenges Won", u1.get("challenges_won", 0), u2.get("challenges_won", 0)),
    ]

    for label, v1, v2 in rows:
        f1, f2 = fmt(v1, v2)
        embed.add_field(name=label, value=f"{ctx.author.name}: {f1}\n{member.name}: {f2}", inline=False)

    embed.add_field(name="⭐ Top Task", value=f"{ctx.author.name}: {top_task(u1)}\n{member.name}: {top_task(u2)}", inline=False)

    await ctx.send(embed=embed)

# ---------- TASK SUMMARY ----------
@bot.command()
async def tasksummary(ctx, member: discord.Member = None):
    """Breakdown of how often you do each task."""
    member = member or ctx.author
    user_id = str(member.id)
    ensure_user(user_id)

    history = data[user_id]["history"]
    if not history:
        await ctx.send("No history yet.")
        return

    counts = Counter(e["task"] for e in history)
    total = len(history)

    embed = discord.Embed(title=f"📊 {member.name}'s Task Breakdown", color=discord.Color.teal())
    for key, task in TASKS.items():
        count = counts.get(key, 0)
        pct = int((count / total) * 10) if total > 0 else 0
        bar = "█" * pct + "░" * (10 - pct)
        embed.add_field(
            name=f"`{key}` {task['name']}",
            value=f"{bar} {count}x ({round(count/total*100) if total else 0}%)",
            inline=False
        )
    embed.set_footer(text=f"Total tasks completed: {total}")
    await ctx.send(embed=embed)

# ---------- BEST WEEK ----------
@bot.command()
async def best(ctx, member: discord.Member = None):
    """Show your single best week ever."""
    member = member or ctx.author
    user_id = str(member.id)
    ensure_user(user_id)

    history = data[user_id]["history"]
    if not history:
        await ctx.send("No history yet.")
        return

    week_totals = {}
    for entry in history:
        dt = datetime.strptime(entry["time"], "%Y-%m-%d %H:%M:%S")
        week_key = dt.strftime("%Y-W%W")
        week_totals[week_key] = week_totals.get(week_key, 0) + entry["points"]

    best_week = max(week_totals, key=week_totals.get)
    best_pts = week_totals[best_week]

    embed = discord.Embed(title=f"🌟 {member.name}'s Best Week", color=discord.Color.gold())
    embed.add_field(name="📅 Week", value=best_week, inline=True)
    embed.add_field(name="💰 Points", value=f"{best_pts} pts", inline=True)
    await ctx.send(embed=embed)

# ---------- HISTORY ----------
@bot.command()
async def history(ctx, amount: int = 10):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    entries = data[user_id]["history"][-amount:][::-1]
    if not entries:
        await ctx.send("No history yet.")
        return

    embed = discord.Embed(title=f"📜 Last {len(entries)} claims", color=discord.Color.green())
    for entry in entries:
        task_name = TASKS.get(entry["task"], {}).get("name", entry["task"])
        embed.add_field(name=task_name, value=f"+{entry['points']} pts — {entry['time']}", inline=False)
    await ctx.send(embed=embed)

# ---------- STREAK ----------
@bot.command()
async def streak(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    ensure_user(user_id)

    s = data[user_id].get("streak", 0)
    if s == 0:
        msg = f"😴 **{member.name}** has no active streak. Claim a task to start one!"
    elif s < 7:
        msg = f"🔥 **{member.name}** is on a **{s}-day streak!** Keep going!"
    elif s < 14:
        msg = f"🔥🔥 **{member.name}** is on a **{s}-day streak!** +1 bonus pt per claim!"
    elif s < 30:
        msg = f"🔥🔥🔥 **{member.name}** is on a **{s}-day streak!** +2 bonus pts per claim!"
    else:
        msg = f"⚡ **{member.name}** is on a legendary **{s}-day streak!** +3 bonus pts per claim!"
    await ctx.send(msg)

# ---------- PROGRESS ----------
@bot.command()
async def progress(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)
    pts = data[user_id]["points"]

    embed = discord.Embed(title="🛒 Shop Progress", color=discord.Color.gold())
    for item, price in sorted(SHOP.items(), key=lambda x: x[1]):
        if pts >= price:
            bar = "✅ Can afford!"
        else:
            filled = int((pts / price) * 10)
            bar = "█" * filled + "░" * (10 - filled) + f" {pts}/{price} pts"
        embed.add_field(name=item, value=bar, inline=False)
    await ctx.send(embed=embed)

# ---------- TASKS LIST ----------
@bot.command()
async def tasks(ctx):
    embed = discord.Embed(title="📋 Available Tasks", color=discord.Color.teal())
    for key, task in TASKS.items():
        embed.add_field(
            name=f"`{key}` — {task['name']} ({task['reward']} pt{'s' if task['reward'] > 1 else ''})",
            value=task["description"],
            inline=False
        )
    await ctx.send(embed=embed)

# ---------- ALL-TIME LEADERBOARD ----------
@bot.command()
async def alltime(ctx):
    if not data:
        await ctx.send("No data yet.")
        return

    sorted_users = sorted(data.items(), key=lambda x: x[1]["earned"], reverse=True)
    msg = await ctx.send("⏳ Fetching leaderboard...")
    medals = ["🥇", "🥈", "🥉"]

    embed = discord.Embed(title="🏆 All-Time Leaderboard", color=discord.Color.gold())
    for i, (user_id, info) in enumerate(sorted_users[:10], start=1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except discord.NotFound:
            name = "Unknown"
        medal = medals[i - 1] if i <= 3 else f"{i}."
        embed.add_field(
            name=f"{medal} {name}",
            value=f"{info['earned']} pts | 🔥 {info.get('streak', 0)}d | 🏅 {len(info.get('achievements', []))} achievements",
            inline=False
        )
    await msg.delete()
    await ctx.send(embed=embed)

# ---------- WEEKLY LEADERBOARD ----------
@bot.command()
async def weekly(ctx):
    week_ago = datetime.now() - timedelta(days=7)
    results = {}

    for user_id, info in data.items():
        total = sum(
            e["points"] for e in info.get("history", [])
            if datetime.strptime(e["time"], "%Y-%m-%d %H:%M:%S") >= week_ago
        )
        if total > 0:
            results[user_id] = total

    if not results:
        await ctx.send("No activity in the past 7 days.")
        return

    sorted_users = sorted(results.items(), key=lambda x: x[1], reverse=True)
    msg = await ctx.send("⏳ Fetching leaderboard...")
    medals = ["🥇", "🥈", "🥉"]

    embed = discord.Embed(title="📅 Weekly Leaderboard", color=discord.Color.blue())
    for i, (user_id, pts) in enumerate(sorted_users[:10], start=1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except discord.NotFound:
            name = "Unknown"
        medal = medals[i - 1] if i <= 3 else f"{i}."
        embed.add_field(name=f"{medal} {name}", value=f"{pts} pts", inline=False)

    await msg.delete()
    await ctx.send(embed=embed)

# ---------- CATEGORY LEADERBOARD ----------
@bot.command()
async def category(ctx, task: str):
    task = task.upper()
    if task not in TASKS:
        await ctx.send("❌ Invalid task. Use `!tasks` to see valid tasks.")
        return

    results = {}
    for user_id, info in data.items():
        total = sum(e["points"] for e in info.get("history", []) if e["task"] == task)
        if total > 0:
            results[user_id] = total

    if not results:
        await ctx.send(f"No data for **{TASKS[task]['name']}** yet.")
        return

    sorted_users = sorted(results.items(), key=lambda x: x[1], reverse=True)
    msg = await ctx.send("⏳ Fetching leaderboard...")
    medals = ["🥇", "🥈", "🥉"]

    embed = discord.Embed(title=f"🧩 {TASKS[task]['name']} Leaderboard", color=discord.Color.purple())
    for i, (user_id, pts) in enumerate(sorted_users[:10], start=1):
        try:
            user = await bot.fetch_user(int(user_id))
            name = user.name
        except discord.NotFound:
            name = "Unknown"
        medal = medals[i - 1] if i <= 3 else f"{i}."
        embed.add_field(name=f"{medal} {name}", value=f"{pts} pts", inline=False)

    await msg.delete()
    await ctx.send(embed=embed)

# ---------- SHOP ----------
@bot.command()
async def shop(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)
    pts = data[user_id]["points"]

    categories = {
        "💬 Communication": [
            "Compliment for 3 minutes",
            "Romantic word",
            "Voice message",
            "Ask me anything",
            "Personal playlist made for you",
        ],
        "📸 Media & Content": [
            "Send a photo now",
            "Good selfie",
            "Movie/media recommendation",
            "Draw something",
        ],
        "🎮 Activities Together": [
            "Game to play together",
            "Workout together",
            "Study together session",
            "Learn something together (30 min)",
        ],
        "📅 Control & Decisions": [
            "Request call at a specific time",
            "Pick what I eat",
            "Outfit choice",
            "You decide my schedule tomorrow",
            "Force someone to do a task",
            "Block other person's action (YT Shorts, scrolling, X, etc.)",
        ],
        "🎁 Special": [
            "Language teacher for 1 hour",
            "Very close attention for 15 minutes",
            "Dance",
            "Send a letter",
            "Belohnung",
        ],
    }

    embed = discord.Embed(
        title="🛒 Shop",
        description=f"💰 Your balance: **{pts} pts**\n✅ = affordable  ❌ = need more points",
        color=discord.Color.gold()
    )

    for category, items in categories.items():
        lines = []
        for item in items:
            price = SHOP[item]
            icon = "✅" if pts >= price else "❌"
            lines.append(f"{icon} {item} — **{price} pts**")
        embed.add_field(name=category, value="\n".join(lines), inline=False)

    embed.set_footer(text="Use !buy <item name> to purchase | !progress to see how close you are")
    await ctx.send(embed=embed)

# ---------- BUY ----------
@bot.command()
async def buy(ctx, *, item: str):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if item not in SHOP:
        await ctx.send("❌ Item not found. Use `!shop` to see available items.")
        return

    price = SHOP[item]
    if data[user_id]["points"] < price:
        shortage = price - data[user_id]["points"]
        await ctx.send(f"❌ Not enough points. You need **{shortage}** more pts.")
        return

    data[user_id]["points"] -= price
    data[user_id]["inventory"].append(item)

    data[user_id]["total_spent"] = data[user_id].get("total_spent", 0) + price
    if item not in data[user_id].get("items_bought", []):
        data[user_id].setdefault("items_bought", []).append(item)
    if item == "Send a letter":
        data[user_id]["bought_letter"] = True

    save_data(data)

    embed = discord.Embed(title="✅ Purchase Successful!", description=f"You bought **{item}**!", color=discord.Color.green())
    embed.add_field(name="💰 Remaining Points", value=f"{data[user_id]['points']} pts")
    embed.set_footer(text="Check your inventory with !inventory")
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)
    await check_achievements(ctx, user_id)

# ---------- USE ----------
@bot.command()
async def use(ctx, *, item: str):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if item not in data[user_id]["inventory"]:
        await ctx.send(f"❌ You don't have **{item}** in your inventory.")
        return

    data[user_id]["inventory"].remove(item)
    data[user_id]["used_count"] = data[user_id].get("used_count", 0) + 1
    save_data(data)

    embed = discord.Embed(title="🎉 Item Used!", description=f"**{item}** has been activated!", color=discord.Color.green())
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)

# ---------- INVENTORY ----------
@bot.command()
async def inventory(ctx, member: discord.Member = None):
    member = member or ctx.author
    user_id = str(member.id)
    ensure_user(user_id)

    if not data[user_id]["inventory"]:
        await ctx.send(f"🎒 **{member.name}'s** inventory is empty.")
        return

    counts = Counter(data[user_id]["inventory"])
    embed = discord.Embed(title=f"🎒 {member.name}'s Inventory", color=discord.Color.blurple())
    for item, count in counts.items():
        embed.add_field(name=item, value=f"x{count}", inline=True)
    await ctx.send(embed=embed)

# ---------- PING ----------
@bot.command()
async def ping(ctx):
    await ctx.send(f"🏓 Pong! Latency: {round(bot.latency * 1000)}ms")

# ---------- GAMBLING ----------

MYSTERY_BOX_COST = 10

@bot.command()
async def gamble(ctx):
    embed = discord.Embed(
        title="🎰 Gambling Den",
        description="Welcome! Choose a game to play:",
        color=discord.Color.dark_gold()
    )
    embed.add_field(name="🎁 `!mysterybox`", value=f"Pay {MYSTERY_BOX_COST} pts — win a random shop item. Rarer items = lower chance.", inline=False)
    embed.add_field(name="🎲 `!doubleornothing <amount>`", value="50/50 chance to double your bet or lose it all.", inline=False)
    embed.add_field(name="🪙 `!coinflip @user <amount>`", value="Challenge someone to a 50/50 coin flip.", inline=False)
    embed.add_field(name="🎰 `!slots <amount>`", value="Spin 3 reels. Match symbols to win big.", inline=False)
    embed.add_field(name="💣 `!minesweeper <amount>`", value="Reveal tiles safely. Hit a mine and lose everything.", inline=False)
    embed.add_field(name="🃏 `!blackjack <amount>`", value="Beat the dealer without going over 21.", inline=False)
    embed.set_footer(text="Gamble responsibly — points are hard earned!")
    await ctx.send(embed=embed)

# ---------- MYSTERY BOX ----------
@bot.command()
async def mysterybox(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if data[user_id]["points"] < MYSTERY_BOX_COST:
        await ctx.send(f"❌ You need **{MYSTERY_BOX_COST} pts** to open a mystery box.")
        return

    data[user_id]["points"] -= MYSTERY_BOX_COST

    data[user_id]["total_gambles"] = data[user_id].get("total_gambles", 0) + 1
    data[user_id]["biggest_single_bet"] = max(data[user_id].get("biggest_single_bet", 0), MYSTERY_BOX_COST)


    # Weight items by inverse price — cheaper = more common
    items = list(SHOP.keys())
    prices = [SHOP[i] for i in items]
    max_price = max(prices)
    weights = [max_price - p + 1 for p in prices]

    won_item = random.choices(items, weights=weights, k=1)[0]
    data[user_id]["inventory"].append(won_item)

    if SHOP[won_item] >= 20:
        data[user_id]["won_legendary"] = True

    save_data(data)

    rarity = "⭐ Common" if SHOP[won_item] <= 5 else "🌟 Rare" if SHOP[won_item] <= 15 else "💎 Legendary"

    embed = discord.Embed(title="🎁 Mystery Box", color=discord.Color.purple())
    embed.add_field(name="You opened the box and found...", value=f"**{won_item}**", inline=False)
    embed.add_field(name="Rarity", value=rarity, inline=True)
    embed.add_field(name="Worth", value=f"{SHOP[won_item]} pts", inline=True)
    embed.add_field(name="💰 Remaining", value=f"{data[user_id]['points']} pts", inline=True)
    embed.set_footer(text="Item added to your inventory! Use !use <item> to activate it.")
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)

# ---------- DOUBLE OR NOTHING ----------
@bot.command()
async def doubleornothing(ctx, amount: int):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if data[user_id]["points"] < amount:
        await ctx.send(f"❌ You don't have enough points. You have **{data[user_id]['points']} pts**.")
        return

    won = random.random() < 0.5

    if won:
        data[user_id]["points"] += amount
        data[user_id]["earned"] += amount
        color = discord.Color.green()
        title = "🎉 You Won!"
        result = f"+{amount} pts"
    else:
        data[user_id]["points"] -= amount
        color = discord.Color.red()
        title = "💀 You Lost!"
        result = f"-{amount} pts"

    save_data(data)

    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Bet", value=f"{amount} pts", inline=True)
    embed.add_field(name="Result", value=result, inline=True)
    embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)

# ---------- COINFLIP ----------
pending_coinflips = {}

@bot.command()
async def coinflip(ctx, member: discord.Member, amount: int):
    user_id = str(ctx.author.id)
    other_id = str(member.id)
    ensure_user(user_id)
    ensure_user(other_id)

    if member.id == ctx.author.id:
        await ctx.send("❌ You can't flip against yourself.")
        return
    if amount <= 0:
        await ctx.send("❌ Amount must be greater than 0.")
        return
    if data[user_id]["points"] < amount:
        await ctx.send(f"❌ You don't have enough points.")
        return

    pending_coinflips[other_id] = {
        "challenger": user_id,
        "amount": amount,
        "channel": ctx.channel.id
    }

    embed = discord.Embed(
        title="🪙 Coin Flip Challenge!",
        description=f"{ctx.author.mention} challenged {member.mention} to a coin flip for **{amount} pts**!",
        color=discord.Color.blurple()
    )
    embed.set_footer(text=f"{member.name} — use !flipaccept to accept or !flipdecline to decline")
    await ctx.send(embed=embed)

@bot.command()
async def flipaccept(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if user_id not in pending_coinflips:
        await ctx.send("❌ You have no pending coin flip.")
        return

    flip = pending_coinflips.pop(user_id)
    challenger_id = flip["challenger"]
    amount = flip["amount"]
    ensure_user(challenger_id)

    if data[user_id]["points"] < amount:
        await ctx.send(f"❌ You don't have enough points to accept.")
        return
    if data[challenger_id]["points"] < amount:
        await ctx.send(f"❌ The challenger no longer has enough points.")
        return

    winner_id = random.choice([user_id, challenger_id])
    loser_id = challenger_id if winner_id == user_id else user_id

    data[winner_id]["points"] += amount
    data[winner_id]["earned"] += amount
    data[loser_id]["points"] -= amount
    save_data(data)

    winner = await bot.fetch_user(int(winner_id))
    loser = await bot.fetch_user(int(loser_id))

    embed = discord.Embed(title="🪙 Coin Flip Result!", color=discord.Color.gold())
    embed.add_field(name="🎉 Winner", value=f"{winner.mention} +{amount} pts", inline=True)
    embed.add_field(name="💀 Loser", value=f"{loser.mention} -{amount} pts", inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def flipdecline(ctx):
    user_id = str(ctx.author.id)
    if user_id in pending_coinflips:
        pending_coinflips.pop(user_id)
        await ctx.send("❌ Coin flip declined.")
    else:
        await ctx.send("❌ You have no pending coin flip.")

# ---------- SLOT MACHINE ----------
SLOT_SYMBOLS = ["🍒", "🍋", "🔔", "⭐", "💎", "7️⃣"]
SLOT_MULTIPLIERS = {
    "🍒": 2,
    "🍋": 2,
    "🔔": 3,
    "⭐": 4,
    "💎": 8,
    "7️⃣": 15,
}
SLOT_WEIGHTS = [30, 25, 20, 15, 7, 3]

@bot.command()
async def slots(ctx, amount: int):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if data[user_id]["points"] < amount:
        await ctx.send(f"❌ Not enough points. You have **{data[user_id]['points']} pts**.")
        return

    reels = random.choices(SLOT_SYMBOLS, weights=SLOT_WEIGHTS, k=3)
    data[user_id]["points"] -= amount

    data[user_id]["total_gambles"] = data[user_id].get("total_gambles", 0) + 1
    data[user_id]["biggest_single_bet"] = max(data[user_id].get("biggest_single_bet", 0), amount)

    if reels[0] == reels[1] == reels[2]:
        multiplier = SLOT_MULTIPLIERS[reels[0]]
        winnings = amount * multiplier
        data[user_id]["points"] += winnings
        data[user_id]["earned"] += winnings
        if reels[0] == "7️⃣":
            data[user_id]["slot_jackpot"] = True
        result_text = f"🎉 JACKPOT! x{multiplier} — +{winnings} pts"
        color = discord.Color.gold()
    elif reels[0] == reels[1] or reels[1] == reels[2] or reels[0] == reels[2]:
        winnings = int(amount * 1.5)
        data[user_id]["points"] += winnings
        data[user_id]["earned"] += winnings
        result_text = f"✅ Two of a kind! x1.5 — +{winnings} pts"
        color = discord.Color.green()
    else:
        result_text = f"💀 No match — -{amount} pts"
        color = discord.Color.red()

    save_data(data)

    embed = discord.Embed(title="🎰 Slot Machine", color=color)
    embed.add_field(name="Reels", value=f"[ {reels[0]} | {reels[1]} | {reels[2]} ]", inline=False)
    embed.add_field(name="Result", value=result_text, inline=False)
    embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)

# ---------- MINESWEEPER ----------
active_minesweeper = {}

@bot.command()
async def minesweeper(ctx, amount: int):
    user_id = str(ctx.author.id)
    ensure_user(user_id)

    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if data[user_id]["points"] < amount:
        await ctx.send(f"❌ Not enough points. You have **{data[user_id]['points']} pts**.")
        return
    if user_id in active_minesweeper:
        await ctx.send("❌ You already have an active minesweeper game. Use `!reveal <1-9>` to continue or `!cashout` to stop.")
        return

    data[user_id]["points"] -= amount
    save_data(data)

    # 9 tiles, 3 mines
    tiles = ["💣"] * 3 + ["✅"] * 6
    random.shuffle(tiles)

    active_minesweeper[user_id] = {
        "tiles": tiles,
        "revealed": [],
        "bet": amount,
        "multiplier": 1.0,
        "alive": True
    }

    embed = discord.Embed(
        title="💣 Minesweeper",
        description="A 3x3 grid with **3 mines** hidden. Reveal tiles to multiply your bet!\nUse `!reveal <1-9>` to reveal a tile. Use `!cashout` to take your winnings.",
        color=discord.Color.orange()
    )
    embed.add_field(name="Bet", value=f"{amount} pts", inline=True)
    embed.add_field(name="Current Multiplier", value="1.0x", inline=True)
    embed.add_field(name="Grid", value="1️⃣ 2️⃣ 3️⃣\n4️⃣ 5️⃣ 6️⃣\n7️⃣ 8️⃣ 9️⃣", inline=False)
    embed.set_footer(text="Each safe tile increases your multiplier. Hit a mine = lose your bet!")
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
    tile_value = game["tiles"][tile - 1]

    if tile_value == "💣":
        del active_minesweeper[user_id]
        save_data(data)

        embed = discord.Embed(title="💥 BOOM! You hit a mine!", color=discord.Color.red())
        embed.add_field(name="Lost", value=f"-{game['bet']} pts", inline=True)
        embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)

        # Show full grid
        grid = ""
        for i, t in enumerate(game["tiles"]):
            grid += t + " "
            if (i + 1) % 3 == 0:
                grid += "\n"
        embed.add_field(name="Full Grid", value=grid, inline=False)
        await ctx.send(embed=embed)
    else:
        game["multiplier"] = round(game["multiplier"] + 0.5, 1)
        safe_left = 6 - len([r for r in game["revealed"] if game["tiles"][r] == "✅"])

        # Build grid display
        grid = ""
        for i in range(9):
            if i in game["revealed"]:
                grid += game["tiles"][i] + " "
            else:
                grid += "⬜ "
            if (i + 1) % 3 == 0:
                grid += "\n"

        potential = int(game["bet"] * game["multiplier"])
        embed = discord.Embed(title="💣 Minesweeper — Safe!", color=discord.Color.green())
        embed.add_field(name="Multiplier", value=f"{game['multiplier']}x", inline=True)
        embed.add_field(name="Potential Win", value=f"{potential} pts", inline=True)
        embed.add_field(name="Safe tiles left", value=f"{safe_left}", inline=True)
        embed.add_field(name="Grid", value=grid, inline=False)
        embed.set_footer(text="Use !reveal <1-9> to continue or !cashout to take your winnings")
        await ctx.send(embed=embed)

        if safe_left == 0:
            # All safe tiles revealed
            winnings = int(game["bet"] * game["multiplier"])
            data[user_id]["points"] += winnings
            data[user_id]["earned"] += winnings
            save_data(data)
            del active_minesweeper[user_id]
            embed2 = discord.Embed(title="🎉 You cleared the board!", color=discord.Color.gold())
            embed2.add_field(name="Winnings", value=f"+{winnings} pts", inline=True)
            embed2.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
            await ctx.send(embed=embed2)

@bot.command()
async def cashout(ctx):
    user_id = str(ctx.author.id)

    if user_id not in active_minesweeper:
        await ctx.send("❌ No active minesweeper game.")
        return

    game = active_minesweeper.pop(user_id)

    safe_revealed = len([r for r in game["revealed"] if game["tiles"][r] == "✅"])
    if safe_revealed >= 3:
        data[user_id]["minesweeper_pro"] = True


    if game["multiplier"] <= 1.0:
        winnings = game["bet"]
    else:
        winnings = int(game["bet"] * game["multiplier"])

    data[user_id]["points"] += winnings
    data[user_id]["earned"] += winnings
    save_data(data)

    embed = discord.Embed(title="💰 Cashed Out!", color=discord.Color.green())
    embed.add_field(name="Multiplier", value=f"{game['multiplier']}x", inline=True)
    embed.add_field(name="Winnings", value=f"+{winnings} pts", inline=True)
    embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
    await ctx.send(embed=embed)
    await check_achievements(ctx, user_id)

# ---------- BLACKJACK ----------
active_blackjack = {}

def bj_card():
    cards = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
    return random.choice(cards)

def bj_value(hand):
    total = 0
    aces = 0
    for card in hand:
        if card in ["J", "Q", "K"]:
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
    ensure_user(user_id)

    if amount <= 0:
        await ctx.send("❌ Bet must be greater than 0.")
        return
    if data[user_id]["points"] < amount:
        await ctx.send(f"❌ Not enough points. You have **{data[user_id]['points']} pts**.")
        return
    if user_id in active_blackjack:
        await ctx.send("❌ You already have an active blackjack game. Use `!hit` or `!stand`.")
        return

    data[user_id]["total_gambles"] = data[user_id].get("total_gambles", 0) + 1
    data[user_id]["biggest_single_bet"] = max(data[user_id].get("biggest_single_bet", 0), amount)

    data[user_id]["points"] -= amount
    save_data(data)

    player_hand = [bj_card(), bj_card()]
    dealer_hand = [bj_card(), bj_card()]

    active_blackjack[user_id] = {
        "player": player_hand,
        "dealer": dealer_hand,
        "bet": amount
    }

    player_total = bj_value(player_hand)

    embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.dark_green())
    embed.add_field(name="Your Hand", value=f"{bj_hand_str(player_hand)} — **{player_total}**", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{dealer_hand[0]} | ❓", inline=False)
    embed.add_field(name="Bet", value=f"{amount} pts", inline=True)

    if player_total == 21:
        winnings = int(amount * 2.5)
        data[user_id]["points"] += winnings
        data[user_id]["earned"] += winnings
        data[user_id]["natural_blackjack"] = True
        save_data(data)
        del active_blackjack[user_id]
        embed.add_field(name="🎉 BLACKJACK!", value=f"+{winnings} pts (2.5x)", inline=False)
        embed.color = discord.Color.gold()
        await check_achievements(ctx, user_id) 
    else:
        embed.set_footer(text="Use !hit to draw a card or !stand to hold")

    await ctx.send(embed=embed)

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
        save_data(data)

        embed = discord.Embed(title="💥 Bust! You went over 21.", color=discord.Color.red())
        embed.add_field(name="Your Hand", value=f"{bj_hand_str(game['player'])} — **{total}**", inline=False)
        embed.add_field(name="Lost", value=f"-{game['bet']} pts", inline=True)
        embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="🃏 Blackjack — Hit!", color=discord.Color.dark_green())
        embed.add_field(name="Your Hand", value=f"{bj_hand_str(game['player'])} — **{total}**", inline=False)
        embed.add_field(name="Dealer's Hand", value=f"{game['dealer'][0]} | ❓", inline=False)
        embed.set_footer(text="Use !hit to draw again or !stand to hold")
        await ctx.send(embed=embed)

@bot.command()
async def stand(ctx):
    user_id = str(ctx.author.id)

    if user_id not in active_blackjack:
        await ctx.send("❌ No active blackjack game. Start one with `!blackjack <amount>`.")
        return

    game = active_blackjack.pop(user_id)
    player_total = bj_value(game["player"])

    # Dealer draws until 17+
    while bj_value(game["dealer"]) < 17:
        game["dealer"].append(bj_card())

    dealer_total = bj_value(game["dealer"])
    bet = game["bet"]

    embed = discord.Embed(title="🃏 Blackjack — Result", color=discord.Color.dark_green())
    embed.add_field(name="Your Hand", value=f"{bj_hand_str(game['player'])} — **{player_total}**", inline=False)
    embed.add_field(name="Dealer's Hand", value=f"{bj_hand_str(game['dealer'])} — **{dealer_total}**", inline=False)

    if dealer_total > 21 or player_total > dealer_total:
        winnings = bet * 2
        data[user_id]["points"] += winnings
        data[user_id]["earned"] += winnings
        embed.add_field(name="🎉 You Win!", value=f"+{winnings} pts", inline=True)
        embed.color = discord.Color.green()
    elif player_total == dealer_total:
        data[user_id]["points"] += bet
        embed.add_field(name="🤝 Push — Tie!", value=f"Bet returned: {bet} pts", inline=True)
        embed.color = discord.Color.blurple()
    else:
        embed.add_field(name="💀 Dealer Wins!", value=f"-{bet} pts", inline=True)
        embed.color = discord.Color.red()

    embed.add_field(name="💰 Balance", value=f"{data[user_id]['points']} pts", inline=True)
    save_data(data)
    await ctx.send(embed=embed)

# ---------- HELP ----------
@bot.command(name="help")
async def help_command(ctx):
    embed1 = discord.Embed(
        title="📖 Bot Commands (1/2)",
        description="Here's everything you can do:",
        color=discord.Color.blurple()
    )

    embed1.add_field(name="━━━ 📋 Tasks ━━━", value="\u200b", inline=False)
    embed1.add_field(name="`!tasks`", value="List all available tasks", inline=True)
    embed1.add_field(name="`!claim <A-J> ...`", value="Claim one or more tasks", inline=True)

    embed1.add_field(name="━━━ 👤 Profile & Stats ━━━", value="\u200b", inline=False)
    embed1.add_field(name="`!profile [@user]`", value="View your or someone's profile", inline=True)
    embed1.add_field(name="`!streak [@user]`", value="Check streak and bonus info", inline=True)
    embed1.add_field(name="`!history [amount]`", value="See your last N claims", inline=True)
    embed1.add_field(name="`!tasksummary [@user]`", value="Breakdown of tasks you do most", inline=True)
    embed1.add_field(name="`!best [@user]`", value="Your highest scoring week ever", inline=True)
    embed1.add_field(name="`!compare @user`", value="Side by side stats with another user", inline=True)

    embed1.add_field(name="━━━ 🏆 Leaderboards ━━━", value="\u200b", inline=False)
    embed1.add_field(name="`!alltime`", value="All-time points leaderboard", inline=True)
    embed1.add_field(name="`!weekly`", value="Points earned in the last 7 days", inline=True)
    embed1.add_field(name="`!category <A-J>`", value="Leaderboard for a specific task", inline=True)

    embed2 = discord.Embed(
        title="📖 Bot Commands (2/2)",
        color=discord.Color.blurple()
    )

    embed2.add_field(name="━━━ 🏅 Achievements ━━━", value="\u200b", inline=False)
    embed2.add_field(name="`!achievements [@user]`", value="See earned and locked achievements", inline=True)

    embed2.add_field(name="━━━ ⚔️ Challenges ━━━", value="\u200b", inline=False)
    embed2.add_field(name="`!challenge @user <A-J> [bet]`", value="Challenge someone to complete a task first", inline=True)
    embed2.add_field(name="`!accept`", value="Accept the latest pending challenge", inline=True)
    embed2.add_field(name="`!decline`", value="Decline the latest pending challenge", inline=True)
    embed2.add_field(name="`!mychallenges`", value="See your active and pending challenges", inline=True)

    embed2.add_field(name="━━━ 🛒 Shop ━━━", value="\u200b", inline=False)
    embed2.add_field(name="`!shop`", value="Browse the shop (shows what you can afford)", inline=True)
    embed2.add_field(name="`!buy <item name>`", value="Buy an item from the shop", inline=True)
    embed2.add_field(name="`!use <item name>`", value="Use an item from your inventory", inline=True)
    embed2.add_field(name="`!inventory [@user]`", value="See your or someone's inventory", inline=True)
    embed2.add_field(name="`!progress`", value="Progress bars toward each shop item", inline=True)

    embed2.add_field(name="━━━ 🎰 Gambling ━━━", value="\u200b", inline=False)
    embed2.add_field(name="`!gamble`", value="See all gambling games", inline=True)
    embed2.add_field(name="`!mysterybox`", value=f"Pay {MYSTERY_BOX_COST} pts for a random shop item", inline=True)
    embed2.add_field(name="`!doubleornothing <amount>`", value="50/50 to double or lose your bet", inline=True)
    embed2.add_field(name="`!coinflip @user <amount>`", value="Challenge someone to a coin flip", inline=True)
    embed2.add_field(name="`!slots <amount>`", value="Spin the slot machine", inline=True)
    embed2.add_field(name="`!minesweeper <amount>`", value="Reveal tiles, avoid mines", inline=True)
    embed2.add_field(name="`!blackjack <amount>`", value="Beat the dealer to 21", inline=True)

    embed2.add_field(name="━━━ 🔧 Other ━━━", value="\u200b", inline=False)
    embed2.add_field(name="`!ping`", value="Check bot latency", inline=True)

    embed2.set_footer(text="data.json | Arguments in <> are required, [] are optional")

    await ctx.send(embed=embed1)
    await ctx.send(embed=embed2)

# ---------- RUN ----------
bot.run(os.environ.get("TOKEN"))