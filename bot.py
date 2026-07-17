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

# ── ROLE SELECTOR CONFIG (Program Roles) ────────────────
SELECTOR_ROLES = {
    "role_bsa":    1527371244960485578,
    "role_bsce":   1527371249494523924,
    "role_bscpe":  1527371253898416311,
    "role_bsee":   1527371258088394973,
    "role_bsece":  1527371261942960279,
    "role_bsge":   1527371265944457426,
    "role_bsme":   1527371270268653748,
    "role_bsmet":  1527371275092099112,
    "role_bscs":   1527371279953301576,
    "role_bsit":   1527371283921240136,
    "role_bsds":   1527371288375459871,
    "role_bstcm":  1527371292137885769,
    "role_bsam":   1527371296458146044,
    "role_bsap":   1527371300694265916,
    "role_bschem": 1527371304905212065,
    "role_bses":   1527371308898320414,
    "role_bsft":   1527371312958279951,
    "role_bsauto": 1527371316947324988,
    "role_bsetech":1527371320730456184,
    "role_bsesm":  1527371324626833480,
    "role_bsemt":  1527371329215529101,
    "role_btom":   1527371333581934773,
    "role_guest":  1527313017736400978,
}

ROLE_LABELS = {
    "role_bsa":    "BS Architecture",
    "role_bsce":   "BS Civil Engineering",
    "role_bscpe":  "BS Computer Engineering",
    "role_bsee":   "BS Electrical Engineering",
    "role_bsece":  "BS Electronics Engineering",
    "role_bsge":   "BS Geodetic Engineering",
    "role_bsme":   "BS Mechanical Engineering",
    "role_bsmet":  "BS Manufacturing Eng. Technology",
    "role_bscs":   "BS Computer Science",
    "role_bsit":   "BS Information Technology",
    "role_bsds":   "BS Data Science",
    "role_bstcm":  "BS Tech. Communication Management",
    "role_bsam":   "BS Applied Mathematics",
    "role_bsap":   "BS Applied Physics",
    "role_bschem": "BS Chemistry",
    "role_bses":   "BS Environmental Science",
    "role_bsft":   "BS Food Technology",
    "role_bsauto": "BS Autotronics",
    "role_bsetech":"BS Electronics Technology",
    "role_bsesm":  "BS Energy Systems and Management",
    "role_bsemt":  "BS Electro-Mechanical Technology",
    "role_btom":   "Bachelor of Technology, Operations, and Management",
    "role_guest":  "Guest",
}

# ── COLLEGE UMBRELLA MAPPING ─────────────────────────────
# Maps each program role key → the college umbrella role NAME in your server
# Guest gets Verified but no college role
PROGRAM_TO_COLLEGE = {
    "role_bsa":    "CEA",
    "role_bsce":   "CEA",
    "role_bscpe":  "CEA",
    "role_bsee":   "CEA",
    "role_bsece":  "CEA",
    "role_bsge":   "CEA",
    "role_bsme":   "CEA",
    "role_bsmet":  "CEA",
    "role_bscs":   "CITC",
    "role_bsit":   "CITC",
    "role_bsds":   "CITC",
    "role_bstcm":  "CITC",
    "role_bsam":   "CSM",
    "role_bsap":   "CSM",
    "role_bschem": "CSM",
    "role_bses":   "CSM",
    "role_bsft":   "COT",
    "role_bsauto": "COT",
    "role_bsetech":"COT",
    "role_bsesm":  "COT",
    "role_bsemt":  "COT",
    "role_btom":   "COT",
    "role_guest":  None,   # Guests get Verified only, no college role
}

# All college role names (used for explicit denies in academic categories)
COLLEGE_ROLE_NAMES = ["CEA", "CITC", "CSM", "COT"]

# ── CHANNEL → PROGRAM ROLE MAPPING ──────────────────────
# Maps a keyword found in a channel name → the program role key in SELECTOR_ROLES.
# Used to grant per-channel send_messages rights inside academic categories.
# Each program member can VIEW all channels in their college, but only SEND in theirs.
CHANNEL_TO_PROGRAM = {
    # CEA
    "architecture":        "role_bsa",
    "civil":               "role_bsce",
    "computer-eng":        "role_bscpe",
    "electrical":          "role_bsee",
    "electronics-eng":     "role_bsece",
    "geodetic":            "role_bsge",
    "mechanical":          "role_bsme",
    "manufacturing":       "role_bsmet",
    # CITC
    "computer-science":    "role_bscs",
    "information-tech":    "role_bsit",
    "data-science":        "role_bsds",
    "tech-comm":           "role_bstcm",
    # CSM
    "applied-math":        "role_bsam",
    "applied-physics":     "role_bsap",
    "chemistry":           "role_bschem",
    "environmental":       "role_bses",
    # COT
    "food-tech":           "role_bsft",
    "autotronics":         "role_bsauto",
    "electronics-tech":    "role_bsetech",
    "energy-systems":      "role_bsesm",
    "electro-mechanical":  "role_bsemt",
    "btom":                "role_btom",
}

def get_program_role_for_channel(guild: discord.Guild, channel_name: str) -> discord.Role | None:
    """Return the program role that owns this channel, or None if not matched."""
    name_lower = channel_name.lower()
    for keyword, role_key in CHANNEL_TO_PROGRAM.items():
        if keyword in name_lower:
            role_id = SELECTOR_ROLES.get(role_key)
            if role_id:
                return guild.get_role(role_id)
    return None

# ── CATEGORY PERMISSION CONFIG ───────────────────────────
# Maps a keyword (found anywhere in the category name, case-insensitive)
# → permission type. This handles emoji-prefixed names like "📋・INFORMATION".
# The bot checks each category name for these keywords in ORDER — first match wins.
# Keep more specific keywords BEFORE broader ones.
#
# Types:
#   "shared"   – Verified + Staff + Mod + Admin only
#   "academic" – Verified + matching college role + Staff + Mod + Admin
#                (rival college roles are explicitly denied)
#   "staff"    – Staff + Mod + Admin only
#
CATEGORY_CONFIG = [
    # keyword              type        college (only for academic)
    ("information",       "info",     None),   # read-only for members; only Mod+Admin can post
    ("study vc",          "shared",   None),
    ("general",           "shared",   None),
    ("gaming voice",      "shared",   None),   # must come BEFORE plain "gaming"
    ("gaming",            "shared",   None),
    ("academics",         "shared",   None),   # the overall academics hub category
    ("cea",               "academic", "CEA"),
    ("citc",              "academic", "CITC"),
    ("csm",               "academic", "CSM"),
    ("cot",               "academic", "COT"),
    ("staff",             "staff",    None),
]

def get_category_config(category_name: str):
    """Return (type, college) for a category by keyword-matching its name."""
    name_lower = category_name.lower()
    for keyword, cat_type, college in CATEGORY_CONFIG:
        if keyword in name_lower:
            return cat_type, college
    return None, None

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
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Local anti-spam records
user_message_timestamps = defaultdict(list)
SPAM_LIMIT  = 5    # Max messages
SPAM_WINDOW = 3.0  # seconds

# ── HELPER: Fetch role by name (case-insensitive) ────────
def get_role_by_name(guild: discord.Guild, name: str) -> discord.Role | None:
    return discord.utils.find(lambda r: r.name.lower() == name.lower(), guild.roles)

# ── PERMISSION ENGINE ────────────────────────────────────
async def configure_category_permissions(guild: discord.Guild, category: discord.CategoryChannel) -> tuple[bool, str]:
    """
    Applies permission overwrites to a category based on CATEGORY_CONFIG keyword matching.
    Handles emoji-prefixed names like '📋・INFORMATION' or '💻・CITC'.
    All child channels are synced to inherit the category permissions.

    Returns (success: bool, message: str)
    """
    cat_type, college = get_category_config(category.name)

    if cat_type is None:
        return False, f"Category '{category.name}' did not match any config keyword — skipped."
    everyone  = guild.default_role

    # Resolve the special roles we need
    verified_role  = get_role_by_name(guild, "Verified")
    staff_role     = get_role_by_name(guild, "Staff")
    mod_role       = get_role_by_name(guild, "Moderator")
    admin_role     = get_role_by_name(guild, "Admin")  # Role is named 'Admin' in this server
    college_roles  = {name: get_role_by_name(guild, name) for name in COLLEGE_ROLE_NAMES}

    # Start with a clean slate for this category's overwrites
    overwrites: dict[discord.Role, discord.PermissionOverwrite] = {}

    if cat_type == "public":
        # @everyone can view but not send messages
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=True, send_messages=False)

    elif cat_type == "info":
        # INFORMATION category — read-only for all members.
        # Only Moderator and Admin can post. Verified/Staff can only read.
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)
        if verified_role:
            overwrites[verified_role] = discord.PermissionOverwrite(view_channel=True, send_messages=False)
        if staff_role:
            overwrites[staff_role]    = discord.PermissionOverwrite(view_channel=True, send_messages=False)
        if mod_role:
            overwrites[mod_role]      = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if admin_role:
            overwrites[admin_role]    = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    elif cat_type == "shared":
        # @everyone denied; Verified + Staff + Mod + Admin allowed
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)
        if verified_role:
            overwrites[verified_role] = discord.PermissionOverwrite(view_channel=True)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True)
        if mod_role:
            overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)

    elif cat_type == "academic":
        # ACCESS RULES for academic categories:
        # - @everyone           → view DENIED
        # - Verified            → NO override (Verified alone does NOT grant academic access)
        # - Matching college    → view ALLOWED, send DENIED at category level
        # - Rival college roles → view DENIED
        # - Staff / Mod / Admin → view + send ALLOWED
        #
        # Per-channel: the matching PROGRAM role gets send_messages=True
        # so each member can only type in their own program channel.
        target_college_name = college
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)

        # NOTE: Verified intentionally NOT added here.
        # Academic access is gated on the college role only.

        for college_name, college_role in college_roles.items():
            if college_role is None:
                print(f"[Permissions] Warning: Role '{college_name}' not found in guild.")
                continue
            if college_name == target_college_name:
                # Can VIEW all channels in this college; send is denied at category level
                overwrites[college_role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=False
                )
            else:
                # Explicitly deny rival college roles
                overwrites[college_role] = discord.PermissionOverwrite(view_channel=False)

        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if mod_role:
            overwrites[mod_role]   = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    elif cat_type == "staff":
        # @everyone denied; Verified denied; Staff + Mod + Admin allowed
        overwrites[everyone] = discord.PermissionOverwrite(view_channel=False)
        if verified_role:
            overwrites[verified_role] = discord.PermissionOverwrite(view_channel=False)
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if mod_role:
            overwrites[mod_role]   = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        if admin_role:
            overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    else:
        return False, f"Unknown category type '{cat_type}' for '{category.name}'."

    try:
        await category.edit(overwrites=overwrites)

        synced_count   = 0
        skipped_count  = 0

        if cat_type == "academic":
            # Academic channels: do NOT sync (we apply per-channel send overrides).
            # Each channel gets send_messages=True ONLY for its matching program role.
            for channel in category.channels:
                try:
                    program_role = get_program_role_for_channel(guild, channel.name)
                    # Build per-channel overwrites: start from category overwrites
                    ch_overwrites = dict(overwrites)  # copy category overwrites
                    if program_role:
                        # Only this program's members can send here
                        ch_overwrites[program_role] = discord.PermissionOverwrite(
                            view_channel=True, send_messages=True
                        )
                        print(f"  [Channel] #{channel.name} → send allowed for '{program_role.name}'")
                    else:
                        print(f"  [Channel] #{channel.name} → no program role matched (view-only for all)")
                    await channel.edit(overwrites=ch_overwrites)
                    synced_count += 1
                except Exception as ch_err:
                    print(f"[Permissions] Error configuring #{channel.name}: {ch_err}")
                    skipped_count += 1
        else:
            # Shared / staff / public: just sync all channels to the category
            for channel in category.channels:
                try:
                    await channel.edit(sync_permissions=True)
                    synced_count += 1
                except Exception as ch_err:
                    print(f"[Permissions] Error syncing #{channel.name}: {ch_err}")
                    skipped_count += 1

        return True, f"✅ **{category.name}** ({cat_type}) — {synced_count} channel(s) configured."
    except Exception as e:
        return False, f"❌ Failed to configure **{category.name}**: {e}"


async def configure_public_channels(guild: discord.Guild) -> list[str]:
    """
    Applies read-only @everyone access to the four pre-verification channels:
    #welcome, #rules, #announcements, #pick-your-role
    These channels get individual overrides so they are visible before verification.
    """
    PUBLIC_CHANNEL_NAMES = ["welcome", "rules", "announcements", "pick-your-role"]
    everyone = guild.default_role
    results  = []

    for channel in guild.text_channels:
        if channel.name.lower() in PUBLIC_CHANNEL_NAMES:
            try:
                await channel.set_permissions(
                    everyone,
                    view_channel=True,
                    send_messages=False,
                    add_reactions=False,
                )
                results.append(f"✅ #{channel.name} — @everyone can view (read-only).")
            except Exception as e:
                results.append(f"❌ #{channel.name} — {e}")

    return results


# ── BOT EVENTS ───────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    guild = bot.get_guild(GUILD_ID)
    if not guild:
        print(f"\n[Warning] Guild with ID {GUILD_ID} not found or bot is not in it.\n")
        return

    # Print role hierarchy
    print(f"\n--- Roles in Guild: {guild.name} ({guild.id}) ---")
    for role in reversed(guild.roles):
        print(f"Position {role.position}: {role.name} (ID: {role.id})")
    print("---------------------------------------------------\n")

    # Print categories and channels
    print("\n--- Categories and Channels in Guild ---")
    for category in guild.categories:
        print(f"Category: {category.name} (ID: {category.id})")
        for channel in category.channels:
            print(f"  - {channel.name} (ID: {channel.id}, Type: {channel.type})")
    print("---------------------------------------------------\n")

    # Auto-configure permissions on startup
    print("Starting auto-configuration of channel permissions...")

    # 1. Fix the four public channels first
    public_results = await configure_public_channels(guild)
    for msg in public_results:
        print(f"[Public Channels] {msg}")

    # 2. Configure all categories
    for category in guild.categories:
        success, msg = await configure_category_permissions(guild, category)
        print(f"[Auto-Permissions] {msg}")

    print("Auto-configuration complete.")


# ── BUTTON ROLE SELECTOR ─────────────────────────────────
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

    # ── Step 1: Remove all existing selector roles ─────────
    all_selector_ids = set(SELECTOR_ROLES.values())
    # Also strip previous college umbrella roles so users don't stack them
    all_college_roles = {r.id for r in guild.roles if r.name in COLLEGE_ROLE_NAMES}
    strip_ids = all_selector_ids | all_college_roles

    new_roles = [r for r in member.roles if r.id not in strip_ids]

    # ── Step 2: Add the new program role ───────────────────
    new_program_role = guild.get_role(SELECTOR_ROLES[custom_id])
    if not new_program_role:
        await interaction.response.send_message("Role not found in the server. Please contact an admin.", ephemeral=True)
        return
    new_roles.append(new_program_role)

    # ── Step 3: Add the Verified role ──────────────────────
    verified_role = get_role_by_name(guild, "Verified")
    if verified_role and verified_role not in new_roles:
        new_roles.append(verified_role)

    # ── Step 4: Add the matching college umbrella role ─────
    college_name = PROGRAM_TO_COLLEGE.get(custom_id)
    if college_name:
        college_role = get_role_by_name(guild, college_name)
        if college_role and college_role not in new_roles:
            new_roles.append(college_role)

    # ── Step 5: Apply roles ────────────────────────────────
    try:
        await member.edit(roles=new_roles)

        college_display = f" ({college_name})" if college_name else ""
        await interaction.response.send_message(
            f"✅ You now have the **{ROLE_LABELS[custom_id]}**{college_display} role and full server access! 🎉",
            ephemeral=True
        )
        print(f"[Role Selector] {member.display_name} → {ROLE_LABELS[custom_id]}{college_display} + Verified")
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ Error: I do not have permission to manage this role. "
            "Please ask an administrator to move my bot's role ABOVE the program roles in Server Settings.",
            ephemeral=True
        )
        print(f"[Role Selector Error] Cannot manage role {new_program_role.name} due to hierarchy limitations.")
    except Exception as e:
        await interaction.response.send_message(f"❌ Error updating roles: {e}", ephemeral=True)
        print(f"[Role Selector Error] {e}")


# ── MESSAGE MODERATION & AI COMMANDS ─────────────────────
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # 1. Anti-Spam Check
    now       = time.time()
    author_id = message.author.id
    timestamps = user_message_timestamps[author_id]
    timestamps.append(now)
    user_message_timestamps[author_id] = [t for t in timestamps if now - t < SPAM_WINDOW]

    if len(user_message_timestamps[author_id]) > SPAM_LIMIT:
        try:
            duration = discord.utils.utcnow() + discord.utils.datetime.timedelta(minutes=10)
            await message.author.timeout(duration, reason="Anti-Spam Triggered")
            await message.channel.send(
                f"⚠️ {message.author.mention} has been timed out for 10 minutes due to spamming."
            )
            print(f"[Anti-Spam] Timed out {message.author.display_name}")
        except Exception as e:
            print(f"[Anti-Spam] Failed to mute: {e}")
        return

    content = message.content.strip()

    # ── !fixpermissions ─────────────────────────────────────
    if content.startswith("!fixpermissions"):
        member   = message.author
        is_admin = member.guild_permissions.administrator or member.id == message.guild.owner_id
        if not is_admin:
            await message.channel.send("❌ Sorry, only administrators can run this command.")
            return

        async with message.channel.typing():
            guild   = message.guild
            results = []

            # Fix public channels
            public_results = await configure_public_channels(guild)
            results.extend(public_results)

            # Fix all categories
            for category in guild.categories:
                success, msg = await configure_category_permissions(guild, category)
                results.append(msg)

            response_text = "\n".join(results)
            if len(response_text) > 2000:
                response_text = response_text[:1990] + "\n..."
            await message.channel.send(response_text)
        return

    # ── !unlockcategory ─────────────────────────────────────
    if content.startswith("!unlockcategory") or content.startswith("!unlock_category"):
        member   = message.author
        is_admin = member.guild_permissions.administrator or member.id == message.guild.owner_id
        if not is_admin:
            await message.channel.send("❌ Sorry, only administrators can run this command.")
            return

        parts = content.split(" ", 1)
        if len(parts) < 2:
            await message.channel.send("ℹ️ Usage: `!unlockcategory <category name or ID>`")
            return

        category_name = parts[1].strip()
        guild         = message.guild
        category      = None

        if category_name.isdigit():
            category = discord.utils.get(guild.categories, id=int(category_name))
        else:
            category = discord.utils.get(guild.categories, name=category_name)
            if not category:
                category = next(
                    (c for c in guild.categories if category_name.lower() in c.name.lower()), None
                )

        if not category:
            await message.channel.send(f"❌ Category '{category_name}' not found.")
            return

        async with message.channel.typing():
            success, msg = await configure_category_permissions(guild, category)
            await message.channel.send(msg)
        return

    # ── AI Assistant ────────────────────────────────────────
    content    = message.content.strip()
    is_command = content.lower().startswith("bot,") or bot.user.mentioned_in(message)

    if is_command:
        member   = message.author
        is_admin = member.guild_permissions.administrator or member.id == message.guild.owner_id
        if not is_admin:
            await message.channel.send("❌ Sorry, only administrators can command me.")
            return

        if not ai_client:
            await message.channel.send("❌ AI functionality is currently offline (API key missing).")
            return

        async with message.channel.typing():
            if content.lower().startswith("bot,"):
                request = content[4:].strip()
            else:
                request = content.replace(f"<@!{bot.user.id}>", "").replace(f"<@{bot.user.id}>", "").strip()

            channels          = [{"id": ch.id, "name": ch.name} for ch in message.guild.text_channels]
            mentioned_members = [{"id": m.id, "name": m.display_name} for m in message.mentions]

            context = {
                "request":            request,
                "current_channel_id": message.channel.id,
                "channels":           channels,
                "mentioned_members":  mentioned_members,
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
                response = await asyncio.to_thread(
                    ai_client.models.generate_content,
                    model='gemini-2.5-flash',
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json"
                    )
                )
                actions = json.loads(response.text)

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
                                everyone = message.guild.default_role
                                await target_ch.set_permissions(everyone, send_messages=False)

                    elif action_type == "unlock_channel":
                        ch_id = act.get("channel_id")
                        if ch_id is not None:
                            target_ch = message.guild.get_channel(int(ch_id))
                            if target_ch:
                                everyone = message.guild.default_role
                                await target_ch.set_permissions(everyone, send_messages=None)

                    elif action_type == "clear_messages":
                        ch_id = act.get("channel_id")
                        if ch_id is not None:
                            target_ch = message.guild.get_channel(int(ch_id))
                            if target_ch:
                                count = int(act.get("count", 10))
                                await target_ch.purge(limit=count + 1)

                    elif action_type == "mute_member":
                        mem_id = act.get("member_id")
                        if mem_id is not None:
                            target_member = message.guild.get_member(int(mem_id))
                            duration      = int(act.get("duration_minutes", 10))
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
                tb        = traceback.format_exc()
                print(f"[AI Error] {tb}")
                error_msg = f"⚠️ Error: I encountered an issue processing your request.\n```python\n{tb}\n```"
                if len(error_msg) > 2000:
                    error_msg = error_msg[:1990] + "\n```"
                await message.channel.send(error_msg)

bot.run(TOKEN)
