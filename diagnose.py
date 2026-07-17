"""
diagnose.py  —  One-shot Discord permission checker
Connects to the guild, reads every category's overwrites, and prints a
colour-coded report so you can see what's actually configured.

Usage:
    Set DISCORD_TOKEN and GUILD_ID env vars, then run:
    python diagnose.py
"""
import os
import sys
import asyncio
import discord

# Force UTF-8 output on Windows to handle emoji in role names
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TOKEN    = os.environ.get("DISCORD_TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID", "1527309915188891789"))

PUBLIC_CHANNELS = {"welcome", "rules", "announcements", "pick-your-role"}

EXPECTED_TYPES = {
    "information":           "shared",
    "study vc rooms":        "shared",
    "general":               "shared",
    "gaming":                "shared",
    "gaming voice channels": "shared",
    "cea":                   "academic (CEA)",
    "citc":                  "academic (CITC)",
    "csm":                   "academic (CSM)",
    "cot":                   "academic (COT)",
    "staff":                 "staff",
}

intents = discord.Intents.default()
client  = discord.Client(intents=intents)

def safe(s):
    """Encode string safely, replacing unencodable chars."""
    return s.encode("utf-8", errors="replace").decode("utf-8")

@client.event
async def on_ready():
    print(f"\n{'='*60}")
    print(f"  DISCORD PERMISSION DIAGNOSTIC")
    print(f"  Bot: {safe(str(client.user))}")
    print(f"{'='*60}\n")

    guild = client.get_guild(GUILD_ID)
    if not guild:
        print(f"[ERROR] Guild {GUILD_ID} not found. Check GUILD_ID env var.")
        await client.close()
        return

    print(f"Guild : {safe(guild.name)} ({guild.id})")
    role_names = ", ".join(safe(r.name) for r in reversed(guild.roles))
    print(f"Roles : {role_names}\n")

    # -- Check roles exist --
    required_roles = ["Verified", "CEA", "CITC", "CSM", "COT", "Staff", "Moderator", "Admin"]
    print("-- Role Presence Check --")
    for name in required_roles:
        role = discord.utils.find(lambda r: r.name.lower() == name.lower(), guild.roles)
        status = f"OK  Found  (id={role.id}, pos={role.position})" if role else "MISSING -- bot cannot apply permissions for this role!"
        print(f"  {name:15s} {status}")
    print()

    # -- Check @everyone base permission --
    everyone = guild.default_role
    vc = everyone.permissions.view_channel
    print("-- @everyone Base Permission --")
    print(f"  View Channels = {'OFF (correct)' if not vc else 'ON  -- members can see everything! Turn this OFF in Server Settings.'}")
    print()

    # -- Check public channels --
    print("-- Public Channels (@everyone should see these) --")
    for ch in guild.text_channels:
        if ch.name.lower() in PUBLIC_CHANNELS:
            ow = ch.overwrites_for(everyone)
            view = ow.view_channel
            send = ow.send_messages
            view_str = "Allow" if view is True  else ("Deny" if view is False else "inherit")
            send_str = "Allow" if send is True  else ("Deny" if send is False else "inherit")
            print(f"  #{safe(ch.name):30s}  view={view_str}  send={send_str}")
    print()

    # -- Check category overwrites --
    print("-- Category Permission Overwrites --")
    for cat in guild.categories:
        key      = cat.name.strip().lower()
        expected = EXPECTED_TYPES.get(key, "NOT IN CONFIG (will be skipped by bot)")
        print(f"\n  [{safe(cat.name)}]  expected_type={expected}")
        if not cat.overwrites:
            print(f"    (no overwrites set -- inherits from @everyone default)")
        for target, overwrite in cat.overwrites.items():
            tname  = safe(target.name) if hasattr(target, "name") else str(target)
            values = []
            if overwrite.view_channel is True:  values.append("view=Allow")
            if overwrite.view_channel is False: values.append("view=Deny")
            if overwrite.view_channel is None:  values.append("view=inherit")
            print(f"    {tname:20s}  {', '.join(values)}")

    print(f"\n{'='*60}")
    print("  Diagnostic complete.")
    print(f"{'='*60}\n")
    await client.close()

client.run(TOKEN)
