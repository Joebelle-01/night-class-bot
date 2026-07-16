import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

# ── CONFIG ──────────────────────────────────────────────
TOKEN     = os.environ.get("DISCORD_TOKEN")
GUILD_ID  = int(os.environ.get("GUILD_ID", "1527309915188891789"))
MEMBER_ROLE_ID = 1527356179704057948  # Unlocks full server access

COURSE_ROLES = {
    "role_it":  1527339997802401802,
    "role_tcm": 1527340003758309426,
    "role_cse": 1527340008787415042,
    "role_ce":  1527340014567161856,
}

ROLE_LABELS = {
    "role_it":  "💻 IT",
    "role_tcm": "📡 TCM",
    "role_cse": "🖥️ CSE",
    "role_ce":  "⚙️ CE",
}

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

# ── BOT ──────────────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id", "")
    if custom_id not in COURSE_ROLES:
        return

    member = interaction.user
    guild  = interaction.guild

    if not member or not guild:
        await interaction.response.send_message("Error: could not find your profile.", ephemeral=True)
        return

    # Remove existing course roles
    all_course_ids = set(COURSE_ROLES.values())
    to_remove = [r for r in member.roles if r.id in all_course_ids]
    if to_remove:
        await member.remove_roles(*to_remove)

    # Assign selected course role
    new_role = guild.get_role(COURSE_ROLES[custom_id])
    if new_role:
        await member.add_roles(new_role)

    # Assign Member role → unlocks full server access
    member_role = guild.get_role(MEMBER_ROLE_ID)
    if member_role and member_role not in member.roles:
        await member.add_roles(member_role)

    await interaction.response.send_message(
        f"Welcome! You've been given the **{ROLE_LABELS[custom_id]}** role.\nYou now have full access to the server! 🎉",
        ephemeral=True
    )
    print(f"[Gate] {member.display_name} -> {ROLE_LABELS[custom_id]} + Member")

bot.run(TOKEN)
