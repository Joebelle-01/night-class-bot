import os
import sys
import json
import time
import asyncio
import threading
from collections import defaultdict
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from google import genai
from google.genai import types

# ── CONFIG ──────────────────────────────────────────────
TOKEN          = os.environ.get("DISCORD_TOKEN")
GUILD_ID       = int(os.environ.get("GUILD_ID", "1527309915188891789"))
GEMINI_KEY     = os.environ.get("GEMINI_API_KEY")

# Role Selector Config
SELECTOR_ROLES = {
    "role_bsa": 1527371244960485578,
    "role_bsce": 1527371249494523924,
    "role_bscpe": 1527371253898416311,
    "role_bsee": 1527371258088394973,
    "role_bsece": 1527371261942960279,
    "role_bsge": 1527371265944457426,
    "role_bsme": 1527371270268653748,
    "role_bsmet": 1527371275092099112,
    "role_bscs": 1527371279953301576,
    "role_bsit": 1527371283921240136,
    "role_bsds": 1527371288375459871,
    "role_bstcm": 1527371292137885769,
    "role_bsam": 1527371296458146044,
    "role_bsap": 1527371300694265916,
    "role_bschem": 1527371304905212065,
    "role_bses": 1527371308898320414,
    "role_bsft": 1527371312958279951,
    "role_bsauto": 1527371316947324988,
    "role_bsetech": 1527371320730456184,
    "role_bsesm": 1527371324626833480,
    "role_bsemt": 1527371329215529101,
    "role_btom": 1527371333581934773,
    "role_guest": 1527313017736400978,
}

ROLE_LABELS = {
    "role_bsa": "BS Architecture",
    "role_bsce": "BS Civil Engineering",
    "role_bscpe": "BS Computer Engineering",
    "role_bsee": "BS Electrical Engineering",
    "role_bsece": "BS Electronics Engineering",
    "role_bsge": "BS Geodetic Engineering",
    "role_bsme": "BS Mechanical Engineering",
    "role_bsmet": "BS Manufacturing Eng. Technology",
    "role_bscs": "BS Computer Science",
    "role_bsit": "BS Information Technology",
    "role_bsds": "BS Data Science",
    "role_bstcm": "BS Tech. Communication Management",
    "role_bsam": "BS Applied Mathematics",
    "role_bsap": "BS Applied Physics",
    "role_bschem": "BS Chemistry",
    "role_bses": "BS Environmental Science",
    "role_bsft": "BS Food Technology",
    "role_bsauto": "BS Autotronics",
    "role_bsetech": "BS Electronics Technology",
    "role_bsesm": "BS Energy Systems and Management",
    "role_bsemt": "BS Electro-Mechanical Technology",
    "role_btom": "Bachelor of Technology, Operations, and Management",
    "role_guest": "Guest",
}

# ── GEMINI AI SETUP ──────────────────────────────────────
if GEMINI_KEY:
    ai_client = genai.Client(api_key=GEMINI_KEY)
    print("[OK] Gemini AI configured using google-genai SDK.")
else:
    ai_client = None
    print("[WARN] GEMINI_API_KEY environment variable is missing. AI commands will be disabled.")

# ── KEEP-ALIVE SERVER ────────────────────────────────────
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"Health server on port {port}")
    server.serve_forever()

threading.Thread(target=run_health_server, daemon=True).start()

# ── BOT SETUP ────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True  # Required to read text commands
bot = commands.Bot(command_prefix="!", intents=intents)

# Local anti-spam records
user_message_timestamps = defaultdict(list)
SPAM_LIMIT = 5  # Max messages
SPAM_WINDOW = 3.0  # seconds

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")

# ── BUTTON ROLE SWAPPER ──────────────────────────────────
@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    if custom_id not in SELECTOR_ROLES:
        return

    member = interaction.user
    guild  = interaction.guild

    if not member or not guild:
        await interaction.response.send_message("Error: could not find your profile.", ephemeral=True)
        return

    # Remove existing selector roles
    all_selector_ids = set(SELECTOR_ROLES.values())
    to_remove = [r for r in member.roles if r.id in all_selector_ids]
    if to_remove:
        await member.remove_roles(*to_remove)

    # Assign new role
    new_role = guild.get_role(SELECTOR_ROLES[custom_id])
    if new_role:
        await member.add_roles(new_role)
        await interaction.response.send_message(
            f"You got the **{ROLE_LABELS[custom_id]}** role and now have access to the server! 🎉",
            ephemeral=True
        )
        print(f"[Role Selector] {member.display_name} -> {ROLE_LABELS[custom_id]}")
    else:
        await interaction.response.send_message("Role not found. Contact an admin.", ephemeral=True)

# ── MESSAGE MODERATION & AI COMMANDS ─────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # 1. Anti-Spam Check (Hybrid Local Check)
    now = time.time()
    author_id = message.author.id
    timestamps = user_message_timestamps[author_id]
    timestamps.append(now)
    # Remove old timestamps
    user_message_timestamps[author_id] = [t for t in timestamps if now - t < SPAM_WINDOW]

    if len(user_message_timestamps[author_id]) > SPAM_LIMIT:
        # Spam detected! Mute user
        try:
            duration = discord.utils.utcnow() + discord.utils.datetime.timedelta(minutes=10)
            await message.author.timeout(duration, reason="Anti-Spam Triggered")
            await message.channel.send(f"⚠️ {message.author.mention} has been timed out for 10 minutes due to spamming.")
            print(f"[Anti-Spam] Timed out {message.author.display_name}")
        except Exception as e:
            print(f"[Anti-Spam] Failed to mute: {e}")
        return

    # 2. AI Assistant Command Check
    # Triggers when starting with "bot," or mentioning the bot
    content = message.content.strip()
    is_command = content.lower().startswith("bot,") or bot.user.mentioned_in(message)

    if is_command:
        # Check permissions: Only Server Owner or Administrator role can run commands
        member = message.author
        is_admin = member.guild_permissions.administrator or member.id == message.guild.owner_id
        
        if not is_admin:
            await message.channel.send("❌ Sorry, only administrators can command me.")
            return

        if not ai_client:
            await message.channel.send("❌ AI functionality is currently offline (API key missing).")
            return

        async with message.channel.typing():
            # Extract request
            if content.lower().startswith("bot,"):
                request = content[4:].strip()
            else:
                # Remove bot mention from request
                request = content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()

            # Compile context
            channels = [{"id": ch.id, "name": ch.name} for ch in message.guild.text_channels]
            mentioned_members = [{"id": m.id, "name": m.display_name} for m in message.mentions]

            context = {
                "request": request,
                "current_channel_id": message.channel.id,
                "channels": channels,
                "mentioned_members": mentioned_members
            }

            system_instruction = (
                "You are an AI assistant and moderator named Nightangle for the USTP Gamers Discord server.\n"
                "Your task is to parse the administrator's request and output a JSON array of commands to execute.\n"
                "You can select multiple commands if needed.\n\n"
                "Supported commands:\n"
                "- {\"action\": \"lock_channel\", \"channel_id\": <int>}\n"
                "- {\"action\": \"unlock_channel\", \"channel_id\": <int>}\n"
                "- {\"action\": \"mute_member\", \"member_id\": <int>, \"duration_minutes\": <int>}\n"
                "- {\"action\": \"unmute_member\", \"member_id\": <int>}\n"
                "- {\"action\": \"clear_messages\", \"channel_id\": <int>, \"count\": <int>}\n"
                "- {\"action\": \"send_message\", \"channel_id\": <int>, \"content\": <str>}\n\n"
                "If the action is successful, include a \"send_message\" command to confirm what you did.\n"
                "If the action is invalid or impossible, output a \"send_message\" command explaining the issue.\n"
                "Only return JSON."
            )

            prompt = f"System:\n{system_instruction}\n\nUser Request & Context:\n{json.dumps(context)}"

            try:
                # Generate AI response using new SDK
                response = await asyncio.to_thread(
                    ai_client.models.generate_content,
                    model='gemini-1.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                actions = json.loads(response.text)

                # Process actions
                for act in actions:
                    action_type = act.get("action")
                    
                    if action_type == "send_message":
                        target_ch = message.guild.get_channel(int(act.get("channel_id")))
                        if target_ch:
                            await target_ch.send(act.get("content"))

                    elif action_type == "lock_channel":
                        target_ch = message.guild.get_channel(int(act.get("channel_id")))
                        if target_ch:
                            # Deny Send Messages override for @everyone
                            everyone = message.guild.default_role
                            await target_ch.set_permissions(everyone, send_messages=False)

                    elif action_type == "unlock_channel":
                        target_ch = message.guild.get_channel(int(act.get("channel_id")))
                        if target_ch:
                            # Reset override
                            everyone = message.guild.default_role
                            await target_ch.set_permissions(everyone, send_messages=None)

                    elif action_type == "clear_messages":
                        target_ch = message.guild.get_channel(int(act.get("channel_id")))
                        if target_ch:
                            count = int(act.get("count", 10))
                            await target_ch.purge(limit=count + 1) # include command message if current

                    elif action_type == "mute_member":
                        target_member = message.guild.get_member(int(act.get("member_id")))
                        duration = int(act.get("duration_minutes", 10))
                        if target_member:
                            until = discord.utils.utcnow() + discord.utils.datetime.timedelta(minutes=duration)
                            await target_member.timeout(until, reason="AI Moderator Command")

                    elif action_type == "unmute_member":
                        target_member = message.guild.get_member(int(act.get("member_id")))
                        if target_member:
                            await target_member.timeout(None, reason="AI Moderator Command")

            except Exception as e:
                print(f"[AI Error] {e}")
                await message.channel.send("⚠️ Error: I encountered an issue processing your request.")

bot.run(TOKEN)
