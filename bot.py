import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands

# ── CONFIG ──────────────────────────────────────────────
TOKEN    = os.environ.get("DISCORD_TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID", "1527309915188891789"))

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
    if custom_id not in SELECTOR_ROLES:
        return

    member = interaction.user
    guild  = interaction.guild

    if not member or not guild:
        await interaction.response.send_message("Error: could not find your profile.", ephemeral=True)
        return

    # Remove existing selector roles (all 22 program roles + guest role)
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

bot.run(TOKEN)
