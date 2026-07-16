import sys
import os
import asyncio
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

sys.stdout.reconfigure(encoding='utf-8')

# ── CONFIG (loaded from environment variables) ──────────
TOKEN    = os.environ.get("DISCORD_TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID", "1527309915188891789"))

COURSE_ROLES = {
    "role_it":  1527339997802401802,   # 💻 IT
    "role_tcm": 1527340003758309426,   # 📡 TCM
    "role_cse": 1527340008787415042,   # 🖥️ CSE
    "role_ce":  1527340014567161856,   # ⚙️ CE
}

# ── KEEP-ALIVE WEB SERVER (prevents Render from sleeping) ──
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Night Class Bot is alive!")
    def log_message(self, format, *args):
        pass  # Suppress HTTP logs

def run_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[OK] Health server running on port {port}")
    server.serve_forever()

# Start health server in background thread
threading.Thread(target=run_health_server, daemon=True).start()

# ── BOT SETUP ────────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[OK] {bot.user} is online and ready!")
    print(f"   Serving guild: {GUILD_ID}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    if custom_id not in COURSE_ROLES:
        return

    guild  = bot.get_guild(GUILD_ID)
    member = interaction.member

    if not member:
        await interaction.response.send_message("Could not find your member profile.", ephemeral=True)
        return

    # Remove all other course roles first (one role at a time)
    all_course_role_ids = set(COURSE_ROLES.values())
    roles_to_remove = [r for r in member.roles if r.id in all_course_role_ids]
    if roles_to_remove:
        await member.remove_roles(*roles_to_remove)

    # Assign the selected role
    new_role_id = COURSE_ROLES[custom_id]
    new_role    = guild.get_role(new_role_id)

    if new_role:
        await member.add_roles(new_role)
        role_names = {
            "role_it":  "💻 IT",
            "role_tcm": "📡 TCM",
            "role_cse": "🖥️ CSE",
            "role_ce":  "⚙️ CE",
        }
        await interaction.response.send_message(
            f"You got the **{role_names[custom_id]}** role!",
            ephemeral=True
        )
        print(f"[Role] {member.display_name} -> {role_names[custom_id]}")
    else:
        await interaction.response.send_message("Role not found. Contact an admin.", ephemeral=True)

bot.run(TOKEN)
