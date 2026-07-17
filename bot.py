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

def find_matching_role_key(name: str):
    name = name.lower()
    # Normalize name (remove spaces, hyphens, etc.)
    norm = "".join(c for c in name if c.isalnum())
    
    # Check exact abbreviation matches first (e.g. bscs, bsit, bschem)
    for key in SELECTOR_ROLES.keys():
        abbr = key.replace("role_", "") # e.g. bscs, bsit
        if abbr in norm:
            return key
            
    # Check keyword matches
    keywords = {
        "role_bsa": ["architecture", "bsa"],
        "role_bsce": ["civil", "bsce"],
        "role_bscpe": ["computereng", "bscpe", "cpe"],
        "role_bsee": ["electrical", "bsee", "ee"],
        "role_bsece": ["electronicseng", "bsece", "ece"],
        "role_bsge": ["geodetic", "bsge"],
        "role_bsme": ["mechanical", "bsme", "me"],
        "role_bsmet": ["manufacturing", "bsmet"],
        "role_bscs": ["computerscience", "bscs", "cs"],
        "role_bsit": ["informationtech", "bsit", "it"],
        "role_bsds": ["datascience", "bsds", "ds"],
        "role_bstcm": ["techcomm", "bstcm", "tcm"],
        "role_bsam": ["appliedmath", "bsam", "math"],
        "role_bsap": ["appliedphys", "bsap", "physics"],
        "role_bschem": ["chemistry", "bschem", "chem"],
        "role_bses": ["environmental", "bses", "es"],
        "role_bsft": ["foodtech", "bsft", "ft"],
        "role_bsauto": ["autotronics", "bsauto"],
        "role_bsetech": ["electech", "bsetech"],
        "role_bsesm": ["energysystems", "bsesm"],
        "role_bsemt": ["electromechanical", "bsemt"],
        "role_btom": ["btom", "operationsmanagement"]
    }
    for key, words in keywords.items():
        for word in words:
            if word in norm:
                return key
    return None

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

async def configure_category_permissions(guild, category, force_all_roles=False):
    everyone = guild.default_role
    overwrites = category.overwrites.copy()
    
    # 1. Deny view_channel for @everyone
    everyone_overwrite = overwrites.get(everyone, discord.PermissionOverwrite())
    everyone_overwrite.view_channel = False
    overwrites[everyone] = everyone_overwrite
    
    # 2. Determine which roles should have access
    target_roles = []
    is_general_or_gaming = "gaming" in category.name.lower() or force_all_roles
    
    if is_general_or_gaming:
        # General/Gaming category: grant access to all SELECTOR_ROLES
        for r_id in SELECTOR_ROLES.values():
            role = guild.get_role(r_id)
            if role:
                target_roles.append(role)
    else:
        # Course category: check if it matches a specific role key
        role_key = find_matching_role_key(category.name)
        if role_key:
            role_id = SELECTOR_ROLES[role_key]
            role = guild.get_role(role_id)
            if role:
                target_roles.append(role)
                
    if not target_roles and not is_general_or_gaming:
        return False, f"Category '{category.name}' is not a gaming or course-specific category."
        
    # 3. Apply permissions for the target roles
    for role in target_roles:
        role_overwrite = overwrites.get(role, discord.PermissionOverwrite())
        role_overwrite.view_channel = True
        role_overwrite.connect = True
        role_overwrite.speak = True
        role_overwrite.send_messages = True
        role_overwrite.read_message_history = True
        overwrites[role] = role_overwrite
        
    try:
        await category.edit(overwrites=overwrites)
        
        # 4. Sync channels
        synced_count = 0
        for channel in category.channels:
            try:
                await channel.edit(sync_permissions=True)
                synced_count += 1
            except Exception as ch_err:
                print(f"[Permissions] Error syncing channel {channel.name}: {ch_err}")
                
        if is_general_or_gaming:
            return True, f"Configured general/gaming category **{category.name}** for all roles (synced {synced_count} channels)"
        else:
            role_names = ", ".join(r.name for r in target_roles)
            return True, f"Configured category **{category.name}** for role **{role_names}** (synced {synced_count} channels)"
    except Exception as e:
        return False, f"Failed to configure category **{category.name}**: {e}"

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    # Print all roles and their hierarchy positions to assist debugging
    guild = bot.get_guild(GUILD_ID)
    if guild:
        print(f"\n--- Roles in Guild: {guild.name} ({guild.id}) ---")
        for role in reversed(guild.roles):
            print(f"Position {role.position}: {role.name} (ID: {role.id})")
        print("---------------------------------------------------\n")
        
        # Print all categories and channels to assist debugging
        print(f"\n--- Categories and Channels in Guild ---")
        for category in guild.categories:
            print(f"Category: {category.name} (ID: {category.id})")
            for channel in category.channels:
                print(f"  - {channel.name} (ID: {channel.id}, Type: {channel.type})")
        print("---------------------------------------------------\n")
        
        # Automatically fix channel permissions on startup
        print("Starting auto-configuration of channel permissions...")
        for category in guild.categories:
            success, msg = await configure_category_permissions(guild, category)
            if success:
                print(f"[Auto-Permissions] {msg}")
        print("Auto-configuration of channel permissions complete.")
    else:
        print(f"\n[Warning] Guild with ID {GUILD_ID} not found or bot is not in it.\n")

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

    # Remove existing selector roles and add the new one atomically
    all_selector_ids = set(SELECTOR_ROLES.values())
    new_roles = [r for r in member.roles if r.id not in all_selector_ids]

    new_role = guild.get_role(SELECTOR_ROLES[custom_id])
    if not new_role:
        await interaction.response.send_message("Role not found in the server. Please contact an admin.", ephemeral=True)
        return

    new_roles.append(new_role)

    try:
        await member.edit(roles=new_roles)
        await interaction.response.send_message(
            f"You got the **{ROLE_LABELS[custom_id]}** role and now have access to the server! 🎉",
            ephemeral=True
        )
        print(f"[Role Selector] {member.display_name} -> {ROLE_LABELS[custom_id]}")
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Error: I do not have permission to manage this role. Please ask an administrator to move my bot's role ABOVE the program roles in Server Settings.",
            ephemeral=True
        )
        print(f"[Role Selector Error] Cannot manage role {new_role.name} due to hierarchy limitations.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error updating roles: {e}", ephemeral=True)
        print(f"[Role Selector Error] {e}")

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

    # 1b. Fix Permissions Command
    content = message.content.strip()
    if content.startswith("!fixpermissions"):
        # Check permissions: Only Server Owner or Administrator role can run commands
        member = message.author
        is_admin = member.guild_permissions.administrator or member.id == message.guild.owner_id
        if not is_admin:
            await message.channel.send("❌ Sorry, only administrators can run this command.")
            return

        async with message.channel.typing():
            log_messages = []
            guild = message.guild

            for category in guild.categories:
                success, msg = await configure_category_permissions(guild, category)
                if success:
                    log_messages.append(msg)
            
            if not log_messages:
                await message.channel.send("ℹ️ No managed categories (gaming or course-specific) found in this server.")
            else:
                response_text = "\n".join(log_messages)
                if len(response_text) > 2000:
                    response_text = response_text[:1990] + "\n..."
                await message.channel.send(response_text)
        return

    # 1c. Unlock Category Command
    if content.startswith("!unlockcategory") or content.startswith("!unlock_category"):
        # Check permissions: Only Server Owner or Administrator role can run commands
        member = message.author
        is_admin = member.guild_permissions.administrator or member.id == message.guild.owner_id
        if not is_admin:
            await message.channel.send("❌ Sorry, only administrators can run this command.")
            return

        parts = content.split(" ", 1)
        if len(parts) < 2:
            await message.channel.send("ℹ️ Usage: `!unlockcategory <category name or ID>`")
            return

        category_name = parts[1].strip()
        guild = message.guild
        category = None

        if category_name.isdigit():
            category = discord.utils.get(guild.categories, id=int(category_name))
        else:
            category = discord.utils.get(guild.categories, name=category_name)
            if not category:
                # Case insensitive partial match
                category = next((c for c in guild.categories if category_name.lower() in c.name.lower()), None)

        if not category:
            await message.channel.send(f"❌ Category '{category_name}' not found.")
            return

        async with message.channel.typing():
            success, msg = await configure_category_permissions(guild, category, force_all_roles=True)
            await message.channel.send(msg)
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
                    model='gemini-2.5-flash',
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
                        ch_id = act.get("channel_id")
                        if ch_id is not None:
                            target_ch = message.guild.get_channel(int(ch_id))
                            if target_ch:
                                await target_ch.send(act.get("content"))

                    elif action_type == "lock_channel":
                        ch_id = act.get("channel_id")
                        if ch_id is not None:
                            target_ch = message.guild.get_channel(int(ch_id))
                            if target_ch:
                                # Deny Send Messages override for @everyone
                                everyone = message.guild.default_role
                                await target_ch.set_permissions(everyone, send_messages=False)

                    elif action_type == "unlock_channel":
                        ch_id = act.get("channel_id")
                        if ch_id is not None:
                            target_ch = message.guild.get_channel(int(ch_id))
                            if target_ch:
                                # Reset override
                                everyone = message.guild.default_role
                                await target_ch.set_permissions(everyone, send_messages=None)

                    elif action_type == "clear_messages":
                        ch_id = act.get("channel_id")
                        if ch_id is not None:
                            target_ch = message.guild.get_channel(int(ch_id))
                            if target_ch:
                                count = int(act.get("count", 10))
                                await target_ch.purge(limit=count + 1) # include command message if current

                    elif action_type == "mute_member":
                        mem_id = act.get("member_id")
                        if mem_id is not None:
                            target_member = message.guild.get_member(int(mem_id))
                            duration = int(act.get("duration_minutes", 10))
                            if target_member:
                                until = discord.utils.utcnow() + discord.utils.datetime.timedelta(minutes=duration)
                                await target_member.timeout(until, reason="AI Moderator Command")

                    elif action_type == "unmute_member":
                        mem_id = act.get("member_id")
                        if mem_id is not None:
                            target_member = message.guild.get_member(int(mem_id))
                            if target_member:
                                await target_member.timeout(None, reason="AI Moderator Command")

            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                print(f"[AI Error] {tb}")
                error_msg = f"⚠️ Error: I encountered an issue processing your request.\n```python\n{tb}\n```"
                if len(error_msg) > 2000:
                    error_msg = error_msg[:1990] + "\n```"
                await message.channel.send(error_msg)

bot.run(TOKEN)
