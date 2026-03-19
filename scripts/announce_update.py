#!/usr/bin/env python3
"""Send a one-time before/after scoreboard update announcement to Discord."""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
import discord


async def main():
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    token = config["discord"]["token"]
    channel_id = config["discord"]["channel_id"]

    intents = discord.Intents.default()
    client = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"Logged in as {client.user}")
        channel = client.get_channel(channel_id)
        if channel is None:
            channel = await client.fetch_channel(channel_id)

        embed = discord.Embed(
            title="\U0001f3a8 Scoreboard Visual Update",
            description=(
                "The match scoreboard just got a major visual overhaul. "
                "Here's what changed:\n\n"
                "\u2022 **Player spotlight** with champion splash art background\n"
                "\u2022 **Circular champion icons** with rank-colored borders\n"
                "\u2022 **Banned champions** row with red X overlays\n"
                "\u2022 **Game info bar** with kill score and gold difference\n"
                "\u2022 **MVP highlighting** (gold text + dot indicators for best stats)\n"
                "\u2022 **Gradient team headers** with team KDA and gold totals\n"
                "\u2022 **Rank-tier colors** (Diamond blue, Gold yellow, Emerald green, etc.)\n"
                "\u2022 **Rounded corners** and refined dark theme\n\n"
                "Scroll down for the before/after comparison \u2b07\ufe0f"
            ),
            colour=discord.Colour.gold(),
        )

        await channel.send(embed=embed)

        # Before image
        before_embed = discord.Embed(
            title="\u274c Before",
            colour=discord.Colour.dark_gray(),
        )
        before_embed.set_image(url="attachment://before.png")
        await channel.send(
            embed=before_embed,
            file=discord.File("/tmp/scoreboard_before.png", filename="before.png"),
        )

        # After image
        after_embed = discord.Embed(
            title="\u2705 After",
            colour=discord.Colour.green(),
        )
        after_embed.set_image(url="attachment://after.png")
        await channel.send(
            embed=after_embed,
            file=discord.File("/tmp/scoreboard_after.png", filename="after.png"),
        )

        print("Announcement sent!")
        await client.close()

    await client.start(token)


if __name__ == "__main__":
    asyncio.run(main())
