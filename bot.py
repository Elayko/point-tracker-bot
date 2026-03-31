import discord
from discord.ext import commands
import json
import os
import re
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# =========================
# CONFIG - REPLACE THESE
# =========================

EVENT_BOT_ID = 1416101453931745351  # put the event bot's user ID here

# Put all event channel IDs here
TRACKED_CHANNEL_IDS = {
    1473814372739711058,  # example: team-guardian
    1473814491245445190,  # example: team-nightmares
    1487887767840100372,  # example: event-fight
}

SCORES_FILE = "scores.json"

# =========================
# DISCORD SETUP
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

scores = {}


# =========================
# SCORE STORAGE
# =========================

def load_scores():
    global scores
    if os.path.exists(SCORES_FILE):
        with open(SCORES_FILE, "r", encoding="utf-8") as f:
            scores = json.load(f)
    else:
        scores = {}


def save_scores():
    with open(SCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)


def get_score(user_id: int) -> int:
    return scores.get(str(user_id), 0)


def set_score(user_id: int, amount: int):
    scores[str(user_id)] = amount
    save_scores()


def add_score(user_id: int, amount: int):
    uid = str(user_id)
    scores[uid] = scores.get(uid, 0) + amount
    save_scores()


# =========================
# MEMBER MATCHING HELPERS
# =========================

def normalize_name(text: str) -> str:
    return text.replace("@", "").strip().lower()


def clean_fight_name(text: str) -> str:
    text = text.strip()
    text = text.lstrip("@")
    return text.strip()


def find_member_by_name(guild: discord.Guild, raw_name: str):
    target = normalize_name(raw_name)

    exact_matches = []
    for member in guild.members:
        candidates = {
            member.display_name.lower(),
            member.name.lower(),
            str(member).lower(),
            member.global_name.lower() if member.global_name else ""
        }
        if target in candidates:
            exact_matches.append(member)

    if len(exact_matches) == 1:
        return exact_matches[0]

    partial_matches = []
    for member in guild.members:
        display_name = member.display_name.lower()
        username = member.name.lower()
        global_name = member.global_name.lower() if member.global_name else ""

        if (
            target == display_name
            or target == username
            or target == global_name
            or target in display_name
            or target in username
            or (global_name and target in global_name)
        ):
            partial_matches.append(member)

    if len(partial_matches) == 1:
        return partial_matches[0]

    return None


# =========================
# MESSAGE / PARSING HELPERS
# =========================

def extract_text_from_message(message: discord.Message) -> str:
    """
    Reads both normal message content and embed text.
    """
    parts = []

    if message.content:
        parts.append(message.content)

    for embed in message.embeds:
        if embed.title:
            parts.append(embed.title)
        if embed.description:
            parts.append(embed.description)
        for field in embed.fields:
            if field.name:
                parts.append(field.name)
            if field.value:
                parts.append(field.value)

    return "\n".join(parts).strip()


def parse_points(text: str):
    match = re.search(r"(\d+)\s*points", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def apply_simple_gain(message: discord.Message, amount: int):
    if len(message.mentions) >= 1:
        target = message.mentions[0]
        add_score(target.id, amount)
        print(f"[GAIN] {target.display_name} +{amount}")
        return True
    return False


def apply_simple_loss(message: discord.Message, amount: int):
    if len(message.mentions) >= 1:
        target = message.mentions[-1]
        add_score(target.id, -amount)
        print(f"[LOSS] {target.display_name} -{amount}")
        return True
    return False


def handle_fight_message(message: discord.Message, content: str):
    """
    Handles:
    - @Cats has picked a fight with invi! @Cats has won 100 points!
    - @invi has picked a fight with leese! leese has won 100 points!
    - @Starfish has picked a fight with Cats! Both have lost 75 points!
    """
    guild = message.guild
    if guild is None:
        return False

    start_match = re.search(
        r"^(.+?) has picked a fight with (.+?)!",
        content,
        re.IGNORECASE
    )
    if not start_match:
        return False

    attacker_name = clean_fight_name(start_match.group(1))
    defender_name = clean_fight_name(start_match.group(2))

    attacker = find_member_by_name(guild, attacker_name)
    defender = find_member_by_name(guild, defender_name)

    amount = parse_points(content)
    if amount is None:
        return False

    if attacker is None or defender is None:
        print("[FIGHT] Could not match attacker or defender.")
        print(f" attacker text: {attacker_name}")
        print(f" defender text: {defender_name}")
        return False

    content_lower = content.lower()

    if "both have lost" in content_lower:
        add_score(attacker.id, -amount)
        add_score(defender.id, -amount)
        print(f"[FIGHT BOTH LOST] {attacker.display_name} -{amount}, {defender.display_name} -{amount}")
        return True

    winner_match = re.search(
        r"!\s*(.+?) has won \d+\s*points",
        content,
        re.IGNORECASE
    )
    if not winner_match:
        return False

    winner_name = clean_fight_name(winner_match.group(1))
    winner = find_member_by_name(guild, winner_name)

    if winner is None:
        print("[FIGHT] Winner not matched.")
        print(f" winner text: {winner_name}")
        return False

    if winner.id == attacker.id:
        loser = defender
    elif winner.id == defender.id:
        loser = attacker
    else:
        print("[FIGHT] Winner matched but was neither attacker nor defender.")
        return False

    add_score(winner.id, amount)
    add_score(loser.id, -amount)
    print(f"[FIGHT] {winner.display_name} +{amount}, {loser.display_name} -{amount}")
    return True


def process_event_message(message: discord.Message, content: str):
    content = content.strip()
    content_lower = content.lower()

    print("\n====================")
    print("EVENT BOT MESSAGE SEEN")
    print(f"Channel: {message.channel}")
    print(f"Author: {message.author} ({message.author.id})")
    print(f"Content: {repr(content)}")
    print(f"Mentions: {[m.display_name for m in message.mentions]}")
    print(f"Embeds count: {len(message.embeds)}")

    handled = False

    if "cooldown" in content_lower:
        print("[IGNORED] Cooldown message")
        return True

    # Fight messages
    if not handled and "has picked a fight with" in content_lower:
        handled = handle_fight_message(message, content)

    # Single loss
    if not handled:
        loss_match = re.search(r"(?:lost|has taken|taken)\s+(\d+)\s*points", content, re.IGNORECASE)
        if loss_match:
            amount = int(loss_match.group(1))
            handled = apply_simple_loss(message, amount)

    # Earned points
    if not handled:
        earned_match = re.search(r"earned\s+(\d+)\s*points", content, re.IGNORECASE)
        if earned_match:
            amount = int(earned_match.group(1))
            handled = apply_simple_gain(message, amount)

    # Awarded you points
    if not handled:
        awarded_match = re.search(r"awarded you\s+(\d+)\s*points", content, re.IGNORECASE)
        if awarded_match:
            amount = int(awarded_match.group(1))
            handled = apply_simple_gain(message, amount)

    # Simple tail format: "... 75 points!"
    if not handled:
        simple_tail_match = re.search(r"(\d+)\s*points!?$", content, re.IGNORECASE)
        if simple_tail_match:
            amount = int(simple_tail_match.group(1))
            handled = apply_simple_gain(message, amount)

    if not handled:
        print("[UNHANDLED MESSAGE]")
        print(repr(content))

    return handled

import asyncio

async def auto_backup():
    while True:
        await asyncio.sleep(300)  # every 5 minutes
        with open("backup_scores.json", "w") as f:
            json.dump(scores, f, indent=2)
        print("Auto backup saved")

# =========================
# BOT EVENTS
# =========================

@bot.event
async def on_ready():
    load_scores()
    bot.loop.create_task(auto_backup())
    print(f"Logged in as {bot.user}")


@bot.event
async def on_message(message: discord.Message):
    # Non-event-bot messages: only process tracker commands
    if message.author.id != EVENT_BOT_ID:
        await bot.process_commands(message)
        return

    # Ignore non-tracked channels
    if message.channel.id not in TRACKED_CHANNEL_IDS:
        return

    content = extract_text_from_message(message)
    process_event_message(message, content)

    # Let tracker commands still work
    await bot.process_commands(message)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    # In case the event bot edits a message instead of sending a new one
    if after.author.id != EVENT_BOT_ID:
        return

    if after.channel.id not in TRACKED_CHANNEL_IDS:
        return

    content = extract_text_from_message(after)
    print("\n[EDITED EVENT MESSAGE DETECTED]")
    process_event_message(after, content)


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    raise error


# =========================
# COMMANDS
# =========================

@bot.command()
@commands.has_permissions(administrator=True)
async def exportjson(ctx):
    if not scores:
        await ctx.send("No scores saved.")
        return

    data = json.dumps(scores, indent=2)

    # Discord message limit handling
    chunks = [data[i:i+1900] for i in range(0, len(data), 1900)]

    for chunk in chunks:
        await ctx.send(f"```json\n{chunk}\n```")


@bot.command()
@commands.has_permissions(administrator=True)
async def exporttext(ctx):
    if not scores:
        await ctx.send("No scores saved.")
        return

    lines = []
    for uid, total in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"User {uid}"
        lines.append(f"{name}: {total}")

    text = "\n".join(lines)

    chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]

    for chunk in chunks:
        await ctx.send(f"```{chunk}```")


@bot.command()
async def points(ctx, member: discord.Member = None):
    member = member or ctx.author
    total = get_score(member.id)
    await ctx.send(f"{member.mention} has **{total}** points.")


@bot.command()
async def leaderboard(ctx):
    if not scores:
        await ctx.send("No scores recorded yet.")
        return

    sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    lines = []
    for i, (uid, total) in enumerate(sorted_scores[:20], start=1):
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else f"User {uid}"
        lines.append(f"**{i}.** {name} — {total} points")

    await ctx.send("\n".join(lines))


@bot.command()
@commands.has_permissions(administrator=True)
async def setscore(ctx, member: discord.Member, amount: int):
    set_score(member.id, amount)
    await ctx.send(f"Set {member.mention} to **{amount}** points.")


@bot.command()
@commands.has_permissions(administrator=True)
async def addscore(ctx, member: discord.Member, amount: int):
    add_score(member.id, amount)
    await ctx.send(f"Updated {member.mention} by **{amount}** points.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetall(ctx):
    global scores
    scores = {}
    save_scores()
    await ctx.send("All scores have been reset.")


@bot.command()
@commands.has_permissions(administrator=True)
async def dump(ctx):
    if not scores:
        await ctx.send("No scores saved.")
        return

    lines = []
    for uid, total in scores.items():
        member = ctx.guild.get_member(int(uid))
        name = member.display_name if member else uid
        lines.append(f"{name}: {total}")

    text = "\n".join(lines) if lines else "No scores saved."
    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]

    for chunk in chunks:
        await ctx.send(f"```{chunk}```")


@bot.command()
@commands.has_permissions(administrator=True)
async def helptracker(ctx):
    await ctx.send(
        "**Tracker commands:**\n"
        "`!points @user` - check score\n"
        "`!leaderboard` - show top scores\n"
        "`!setscore @user amount` - set exact score\n"
        "`!addscore @user amount` - add or subtract score\n"
        "`!dump` - show all saved scores\n"
        "`!resetall` - reset all scores"
    )


bot.run(TOKEN)
