import discord
from discord.ext import commands, tasks
import json
import os
from datetime import datetime, timedelta
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
    "Compliment for 3 minutes": 8,
    "Request call at a specific time": 5,
    "Language teacher for 1 hour": 15,
    "Belohnung": 25,
    "Send a photo now": 3,
    "Romantic word": 1,
    "Dance": 15,
    "Very close attention for 15 minutes": 10,
    "Good selfie": 5,
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
    "first_blood":     {"name": "🎯 First Blood",      "desc": "Complete your first task",                  "check": lambda u: u["earned"] >= 1},
    "week_warrior":    {"name": "🔥 Week Warrior",     "desc": "Reach a 7-day streak",                      "check": lambda u: u.get("streak", 0) >= 7},
    "month_legend":    {"name": "⚡ Month Legend",     "desc": "Reach a 30-day streak",                     "check": lambda u: u.get("streak", 0) >= 30},
    "bookworm":        {"name": "📚 Bookworm",         "desc": "Complete task B 10 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "B") >= 10},
    "runner":          {"name": "🏃 Runner",           "desc": "Complete task C 10 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "C") >= 10},
    "athlete":         {"name": "💪 Athlete",          "desc": "Complete task D 10 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "D") >= 10},
    "scholar":         {"name": "🎓 Scholar",          "desc": "Complete task A 20 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "A") >= 20},
    "rich":            {"name": "💎 Rich",             "desc": "Earn 100 points total",                     "check": lambda u: u["earned"] >= 100},
    "millionaire":     {"name": "👑 Millionaire",      "desc": "Earn 500 points total",                     "check": lambda u: u["earned"] >= 500},
    "clean_freak":     {"name": "🧹 Clean Freak",      "desc": "Complete task I 15 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "I") >= 15},
    "night_owl":       {"name": "🌙 Disciplined",      "desc": "Complete task J 20 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "J") >= 20},
    "polyglot":        {"name": "🌍 Polyglot",         "desc": "Complete task F 15 times",                  "check": lambda u: sum(1 for e in u["history"] if e["task"] == "F") >= 15},
    "shopaholic":      {"name": "🛒 Shopaholic",       "desc": "Buy 5 items from the shop",                 "check": lambda u: len(u.get("inventory", [])) + u.get("used_count", 0) >= 5},
    "challenger":      {"name": "⚔️ Challenger",       "desc": "Complete 3 challenges",                     "check": lambda u: u.get("challenges_won", 0) >= 3},
    "grinder":         {"name": "⚙️ Grinder",          "desc": "Complete 50 tasks total",                   "check": lambda u: len(u["history"]) >= 50},
    "dedicated":       {"name": "🏆 Dedicated",        "desc": "Complete 100 tasks total",                  "check": lambda u: len(u["history"]) >= 100},
}

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
            "used_count": 0,
        }
    for field, default in [
        ("last_claim_date", None),
        ("streak", 0),
        ("achievements", []),
        ("challenges_won", 0),
        ("used_count", 0),
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
        save_data(data)
        for ach in newly_earned:
            embed = discord.Embed(
                title="🏅 Achievement Unlocked!",
                description=f"**{ach['name']}**\n{ach['desc']}",
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
@tasks.loop(hours=24)
async def weekly_announcement():
    await bot.wait_until_ready()
    now = datetime.now()
    if now.weekday() != 0 or now.hour != 8:
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
async def claim(ctx, task: str):
    user_id = str(ctx.author.id)
    task = task.upper()

    if task not in TASKS:
        await ctx.send("❌ Invalid task. Use `!tasks` to see valid tasks.")
        return

    ensure_user(user_id)


    update_streak(user_id)
    streak = data[user_id]["streak"]
    bonus = get_streak_bonus(streak)
    reward = TASKS[task]["reward"] + bonus

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data[user_id]["points"] += reward
    data[user_id]["earned"] += reward
    data[user_id]["history"].append({"points": reward, "task": task, "time": now})

    # Check if this completes any active challenge
    challenge_msg = ""
    for cid, c in challenges.items():
        if c["status"] != "accepted":
            continue
        if c["task"] != task:
            continue
        if str(ctx.author.id) not in [c["challenger"], c["challenged"]]:
            continue

        opponent_id = c["challenged"] if c["challenger"] == str(ctx.author.id) else c["challenger"]
        opponent_claimed = any(
            e["task"] == task and e["time"] >= c["started_at"]
            for e in data.get(opponent_id, {}).get("history", [])
        )

        if not opponent_claimed:
            # This user wins
            bet = c["bet"]
            data[user_id]["points"] += bet
            data[user_id]["challenges_won"] = data[user_id].get("challenges_won", 0) + 1
            if opponent_id in data and data[opponent_id]["points"] >= bet:
                data[opponent_id]["points"] -= bet
            challenges[cid]["status"] = "completed"
            challenge_msg = f"\n⚔️ You won the challenge and earned **{bet} bonus pts**!"

    save_data(data)

    bonus_text = f" *(+{bonus} streak bonus!)*" if bonus > 0 else ""
    streak_text = f"🔥 Streak: **{streak} day{'s' if streak != 1 else ''}**"
    await ctx.send(
        f"✅ **{TASKS[task]['name']}** completed! +{reward} pts{bonus_text}\n"
        f"{streak_text} | 💰 Total: {data[user_id]['points']} pts{challenge_msg}"
    )

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
    """See earned and locked achievements."""
    member = member or ctx.author
    user_id = str(member.id)
    ensure_user(user_id)

    earned = data[user_id]["achievements"]

    embed = discord.Embed(title=f"🏅 {member.name}'s Achievements", color=discord.Color.gold())

    earned_text = ""
    locked_text = ""

    for key, ach in ACHIEVEMENTS.items():
        if key in earned:
            earned_text += f"{ach['name']} — {ach['desc']}\n"
        else:
            locked_text += f"🔒 {ach['desc']}\n"

    embed.add_field(
        name=f"✅ Earned ({len(earned)}/{len(ACHIEVEMENTS)})",
        value=earned_text if earned_text else "None yet",
        inline=False
    )
    embed.add_field(
        name="🔒 Locked",
        value=locked_text if locked_text else "All unlocked!",
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

# ---------- COOLDOWNS ----------
@bot.command()
async def cooldowns(ctx):
    user_id = str(ctx.author.id)
    ensure_user(user_id)
    today = datetime.now().strftime("%Y-%m-%d")

    embed = discord.Embed(title="⏳ Today's Task Status", color=discord.Color.orange())
    for key, task in TASKS.items():
        claimed = any(e["task"] == key and e["time"].startswith(today) for e in data[user_id]["history"])
        status = "✅ Done" if claimed else "⬜ Available"
        embed.add_field(name=f"`{key}` {task['name']}", value=status, inline=True)
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

    embed = discord.Embed(title="🛒 Shop", description=f"Your balance: **{pts} pts**", color=discord.Color.gold())
    for item, price in SHOP.items():
        affordable = "✅" if pts >= price else "❌"
        embed.add_field(name=f"{affordable} {item}", value=f"{price} pts", inline=True)
    embed.set_footer(text="Use !buy <item name> to purchase")
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
    save_data(data)

    embed = discord.Embed(title="✅ Purchase Successful!", description=f"You bought **{item}**!", color=discord.Color.green())
    embed.add_field(name="💰 Remaining Points", value=f"{data[user_id]['points']} pts")
    embed.set_footer(text="Check your inventory with !inventory")
    await ctx.send(embed=embed)
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
    embed1.add_field(name="`!claim <A-J>`", value="Claim a completed task (once per day)", inline=True)
    embed1.add_field(name="`!cooldowns`", value="See which tasks you've done today", inline=True)

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

    embed2.add_field(name="━━━ 🔧 Other ━━━", value="\u200b", inline=False)
    embed2.add_field(name="`!ping`", value="Check bot latency", inline=True)

    embed2.set_footer(text="data.json | Arguments in <> are required, [] are optional")

    await ctx.send(embed=embed1)
    await ctx.send(embed=embed2)

# ---------- RUN ----------
bot.run(os.environ.get["TOKEN"])