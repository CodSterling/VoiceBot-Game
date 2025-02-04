import discord
from discord.ext import commands, tasks
import asyncio
import logging
import random
import requests
import json
from dotenv import load_dotenv
import os
from datetime import datetime, timedelta, timezone




# Access the environment variables directly
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()  # To also print logs to the console
    ]
)


# Discord Bot Configuration
intents = discord.Intents.default()
intents.members = True
intents.reactions = True
intents.message_content = True  # Required for reading message content
bot = commands.Bot(command_prefix='.', intents=intents)

# Dictionary to track user activity
user_activity = {}

# Dictionary to store user inventories
user_inventories = {}

INVENTORY_FILE = "player_inventories.json"


# Global variable to store the Guild ID
global_guild_id = None


@bot.event
async def on_ready():
    global global_guild_id

    # Check the guilds the bot is in
    if len(bot.guilds) == 1:  # Assuming the bot is in only one server
        guild = bot.guilds[0]
        global_guild_id = guild.id
        print(f"Bot is connected to guild: {guild.name} (ID: {global_guild_id})")
    else:
        print("Bot is in multiple guilds or none at all. Please specify manually.")

    print(f"Bot is ready. Logged in as {bot.user}")
    logging.info(f"Bot is ready and logged in as {bot.user.name}")
    print(f"Bot is ready and logged in as {bot.user.name}")
    check_inactivity.start()
    print(f"Bot is ready. Logged in as {bot.user}")

@bot.event
async def on_message(message):
    global user_activity
    user_activity[message.author.id] = datetime.now(timezone.utc)  # Use timezone-aware datetime
    await bot.process_commands(message)


@tasks.loop(minutes=1)  # Adjust interval as needed
async def check_inactivity():
    global user_activity
    now = datetime.now(timezone.utc)  # Use timezone-aware datetime
    timeout = timedelta(minutes=5)   # Adjust timeout duration as needed

    for user_id, last_activity in list(user_activity.items()):
        # Check for inactivity
        if now - last_activity > timeout:
            # Perform action for inactive users
            del user_activity[user_id]
            print(f"User {user_id} marked as inactive due to timeout.")



# Load inventories from JSON file
def load_inventories():
    try:
        with open(INVENTORY_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

# Save inventories to JSON file
def save_inventories(inventories):
    with open(INVENTORY_FILE, "w") as f:
        json.dump(inventories, f)

# Initialize inventories
player_inventories = load_inventories()




@tasks.loop(seconds=30)  # Run every 30 seconds
async def check_inactivity():
    global user_activity
    now = datetime.now(timezone.utc)  # Use timezone-aware UTC datetime
    timeout = timedelta(minutes=5)

    to_remove = []

    for user_id, last_activity in user_activity.items():
        if now - last_activity > timeout:
            guild = bot.get_guild(global_guild_id)  # Replace with your actual Guild ID
            member = guild.get_member(user_id)

            if member:
                # Clean up the user's game
                text_channel = discord.utils.get(guild.channels, name=f"game-{member.name.lower()}")
                voice_channel = discord.utils.get(guild.channels, name=f"game-voice-{member.name.lower()}")

                if text_channel:
                    await text_channel.delete()
                if voice_channel:
                    await voice_channel.delete()

                vc = discord.utils.get(bot.voice_clients, guild=guild)
                if vc:
                    await vc.disconnect()

                # Notify the user (if possible)
                try:
                    await member.send("Your game has ended due to inactivity.")
                except discord.Forbidden:
                    pass

                # Mark for removal from the activity tracker
                to_remove.append(user_id)

    # Remove inactive users from the tracker
    for user_id in to_remove:
        del user_activity[user_id]



@bot.event
async def on_voice_state_update(member, before, after):
    # Ignore bot's own updates
    if member.bot:
        return

    guild = member.guild
    bot_vc = discord.utils.get(bot.voice_clients, guild=guild)

    # User leaves the voice channel
    if before.channel and not after.channel:
        if bot_vc and bot_vc.channel == before.channel:
            # Wait for a delay before disconnecting the bot
            await asyncio.sleep(10)  # Adjust delay as needed
            if len(before.channel.members) == 0:  # Check if the channel is empty
                await bot_vc.disconnect()

    # User moves to another voice channel
    elif after.channel and bot_vc:
        if bot_vc.channel != after.channel:
            await bot_vc.move_to(after.channel)


# Audio files mapped to outcomes
audio_files = {
    "hallway": "audio/hallway.mp3",
    "fall": "audio/fall.mp3",
    "trapped": "audio/trapped.mp3",
    "door": "audio/door.mp3",
    "menu": "audio/menu.mp3",
    "start": "audio/start.mp3",
    "key": "audio/key.mp3",
    "rare_coin": "audio/rare_coin.mp3",
    "treasure": "audio/treasure.mp3"
}

# Track the currently playing audio
current_audio_task = None


async def play_audio(ctx, file_path):
    global current_audio_task
    if current_audio_task:
        current_audio_task.cancel()
        try:
            await current_audio_task
        except asyncio.CancelledError:
            pass

    if ctx.author.voice:
        voice_channel = ctx.author.voice.channel
        existing_vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if existing_vc:
            await existing_vc.disconnect()

        vc = await voice_channel.connect()

        absolute_path = os.path.abspath(file_path)
        if not os.path.exists(absolute_path):
            await ctx.send(f"Audio file not found: {absolute_path}")
            await vc.disconnect()
            return

        vc.play(discord.FFmpegPCMAudio(absolute_path))
        current_audio_task = asyncio.create_task(audio_completion_handler(vc))
    else:
        await ctx.send("You need to be in a voice channel for audio playback.")


async def audio_completion_handler(vc):
    while vc.is_playing():
        await asyncio.sleep(1)
    await vc.disconnect()


# Function to create the expanded game commands menu embed
def get_command_menu():
    embed = discord.Embed(
        title="Game Commands Menu",
        description="Here are all the available game commands:",
        color=discord.Color.gold()
    )

    # General Gameplay Commands
    embed.add_field(name=".start", value="Start a new game and create your private game channel.", inline=False)
    embed.add_field(name=".end", value="End your game and delete the associated channels.", inline=False)
    embed.add_field(name=".open", value="Open a door and discover a random outcome.", inline=False)

    # Inventory and Items
    embed.add_field(name=".inventory", value="View your current inventory of items and rare coins.", inline=False)
    embed.add_field(name=".collect_coin", value="Collect a rare coin (one of five).", inline=False)
    embed.add_field(name=".collect_key", value="Collect a key for unlocking special doors.", inline=False)
    embed.add_field(name=".unlock", value="Use a key to unlock a special door.", inline=False)

    # Treasures
    embed.add_field(name=".collect_treasure", value="Collect a random mystical treasure.", inline=False)
    embed.add_field(name=".collect_all_treasures", value="Collect all mystical treasures at once.", inline=False)
    embed.add_field(name=".treasure_list", value="View the full list of mystical treasures and their descriptions.", inline=False)

    # Special Features
    embed.add_field(name=".open_sesame", value="Unlock the ultimate door if all five rare coins are collected.", inline=False)

    embed.set_footer(text="Use these commands wisely to explore the game and collect treasures!")
    return embed



@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return  # Ignore bot updates

    guild = member.guild
    bot_vc = discord.utils.get(bot.voice_clients, guild=guild)

    # User joins a new voice channel
    if after.channel and (not bot_vc or bot_vc.channel != after.channel):
        # Move the bot to the user's new channel
        if bot_vc:
            await bot_vc.move_to(after.channel)
        else:
            vc = await after.channel.connect()
            # Play the "start" music if not already playing
            audio_file = audio_files.get("start")
            if audio_file and os.path.exists(audio_file):
                vc.play(discord.FFmpegPCMAudio(audio_file))
            else:
                print("The starting music file is missing or cannot be played.")

        # Send a message to a specific text channel by ID
        text_channel = guild.get_channel(1332567997667086389)  # Replace with your channel ID
        if text_channel:
            embed = discord.Embed(
                title=f"{member.name} has joined {after.channel.name}! 🎮",
                description=("Join your TEXT-CHANNEL and use `.menu` to START! 🎮\n\n"
                             "Collect 20 MYTHICAL TREASURES!\n"
                             "Open 3 PRIZE DOORS!\n"
                             "Collect a KEY and use .unlock a HIDDEN DOOR!\n"
                             "The object of the game is to collect\n"
                             "All 5 RARE COINS and use `.open_sesame` to open the SECRET DOOR!\n\n"
                             "Complete all PRIZE DOORS, HIDDEN DOOR and SECRET DOOR to collect the FULL SOUNDTRACK!"),
                color=discord.Color.green()
            )
            await text_channel.send(embed=embed)
        else:
            print("Text channel not found. Check the channel ID.")

    # User leaves a voice channel
    elif before.channel and not after.channel and bot_vc and bot_vc.channel == before.channel:
        # Disconnect if the channel is empty after the user leaves
        if len(before.channel.members) == 0:
            await bot_vc.disconnect()



@bot.command(name="start")
async def start(ctx):
    guild = ctx.guild
    user_name = ctx.author.name.lower()

    # Check if the user already has a game text channel
    text_channel_name = f"game-text-{user_name}"
    text_channel = discord.utils.get(guild.text_channels, name=text_channel_name)

    if not text_channel:
        # Create a new text channel
        text_channel = await guild.create_text_channel(text_channel_name)
        await ctx.send(f"Your game text channel is ready: {text_channel.mention}")

    # Check if the user already has a game voice channel
    voice_channel_name = f"game-voice-{user_name}"
    voice_channel = discord.utils.get(guild.voice_channels, name=voice_channel_name)

    if not voice_channel:
        # Create a new voice channel
        voice_channel = await guild.create_voice_channel(voice_channel_name)
        await ctx.send(f"Your game voice channel is ready: {voice_channel.mention}")

    # Move user message to the new text channel
    try:
        await ctx.message.delete()  # Delete original message
    except discord.Forbidden:
        pass  # Bot lacks permission to delete messages

    await text_channel.send(f"{ctx.author.mention}, your game session has started here!")

    # Call `get_command_menu` in the user's new text channel
    command_menu = bot.get_command("get_command_menu")
    if command_menu:
        await command_menu.callback(ctx)
    else:
        await text_channel.send("Command menu not found.")

    # Check if the bot is already connected to a voice channel
    bot_vc = discord.utils.get(bot.voice_clients, guild=guild)

    if bot_vc:
        # Move bot to user's voice channel if necessary
        if ctx.author.voice and ctx.author.voice.channel:
            if bot_vc.channel.id != ctx.author.voice.channel.id:
                await bot_vc.move_to(ctx.author.voice.channel)
                await text_channel.send("The bot has moved to your voice channel.")
        else:
            await text_channel.send("The bot is already connected to your voice channel!")
    else:
        # Connect the bot to the user's voice channel
        if ctx.author.voice and ctx.author.voice.channel:
            vc = await ctx.author.voice.channel.connect()
            assert isinstance(vc, discord.VoiceClient), "Failed to connect as a VoiceClient"

            # Play starting audio if available
            audio_file = audio_files.get("start")
            if audio_file and os.path.exists(audio_file):
                vc.play(discord.FFmpegPCMAudio(audio_file))
            else:
                await text_channel.send("Starting audio not found or cannot be played.")
        else:
            await text_channel.send("You need to join a voice channel to start the game!")



# The .menu command
@bot.command(name="menu")
async def menu(ctx):
    # Display the command menu
    embed = get_command_menu()
    await ctx.send(embed=embed)

    # Define the audio path for menu music
    menu_audio_path = "audio/menu.mp3"

    # Ensure the bot connects to the user's voice channel
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if not vc or not vc.channel:
        if ctx.author.voice and ctx.author.voice.channel:
            vc = await ctx.author.voice.channel.connect()
            assert isinstance(vc, discord.VoiceClient), "Failed to obtain a valid VoiceClient"
        else:
            await ctx.send("You must be in a voice channel to play menu music.")
            return

    # Play the menu music
    if os.path.exists(menu_audio_path):
        vc.stop()  # Stop any current audio
        vc.play(discord.FFmpegPCMAudio(menu_audio_path))
    else:
        await ctx.send("Menu music file not found.")


# Dictionary mapping outcomes to their corresponding image files
image_files = {
    "hallway": "img/hallway.jpg",
    "fall": "img/fall.jpg",
    "trapped": "img/trapped.jpg",
    "door": "img/door.jpg",
    "treasure": "img/treasure.jpg",
    "key": "img/key.jpg",
    "rare_coin": "img/rare_coin.jpg"
}

# Dictionary mapping outcomes to their corresponding image folders
image_folders = {
    "hallway": "img/hallway/",
    "fall": "img/fall/",
    "trapped": "img/trapped/",
    "door": "img/door/",
    "treasure": "img/treasure/",
    "key": "img/key/",
    "rare_coin": "img/rare_coin/"
}

# Dictionary of treasures with descriptions
mystical_items = {
    "Ruby of Radiance": "A gem that glows with the fiery light of dawn.",
    "Sapphire of Serenity": "A tranquil blue gem that calms the soul.",
    "Emerald of Eternity": "A deep green gem said to hold the secret of everlasting life.",
    "Diamond of Destiny": "A brilliant diamond that sparkles with glimpses of the future.",
    "Amethyst of Ambition": "A regal purple gem that inspires greatness.",
    "Golden Idol of the Sun": "A golden figurine that radiates warmth and light.",
    "Crystal Orb of Visions": "A clear orb said to reveal glimpses of hidden truths.",
    "Silver Chalice of Eternity": "A finely crafted cup that never runs dry.",
    "Enchanted Scroll of Wisdom": "A magical scroll containing knowledge of ancient times.",
    "Obsidian Dagger of Shadows": "A sleek blade that blends with the darkness.",
    "Wand of Starlight": "A wand that sparkles with celestial magic.",
    "Ring of Infinite Echoes": "A mysterious ring that whispers forgotten secrets.",
    "Pendant of the Forgotten Realm": "A jeweled pendant that connects to another world.",
    "Tome of the Ancients": "A leather-bound book brimming with arcane power.",
    "Cloak of Hidden Paths": "A shadowy cloak that conceals the wearer.",
    "Dragon Scale": "A shimmering scale from a mighty dragon.",
    "Phoenix Feather": "A blazing feather from an immortal phoenix.",
    "Starlit Crown": "A golden crown adorned with tiny stars.",
    "Moonlit Mirror": "A silver mirror that reflects only in moonlight.",
    "Eternal Flame in a Bottle": "A bottle that holds an undying flame.",
    "key": "A KEY to UNLOCK a HIDDEN DOOR!"
}

# Define outcomes and weights
outcomes = {
    "hallway": 50,
    "fall": 30,
    "trapped": 20,
    "door": 10,
    "treasure": 15,
    "key": 10,
    "rare_coin": 10
}

# Required coins
required_coins = ["coin1", "coin2", "coin3", "coin4", "coin5"]

key = {"keys": "This opens a HIDDEN DOOR! Use **.unlock!**"}

def get_audio_path(outcome):
    # Define the base path for audio
    BASE_AUDIO_PATH = "Voice Bot/audio/"

    # Construct the audio file path based on the outcome
    audio_path = os.path.join(BASE_AUDIO_PATH, f"{outcome}.mp3")

    # Check if the file exists
    if os.path.exists(audio_path):
        return audio_path
    else:
        print(f"Audio file not found: {audio_path}")
        return None


def get_image_path(outcome):
    # Retrieve the image file path for the outcome
    image_path = image_files.get(outcome, "Voice Bot/img/treasure.jpg")  # Default image if not found

    # Check if the image file exists
    if os.path.exists(image_path):
        return image_path
    else:
        print(f"Image file not found for outcome: {outcome}. Using fallback image.")
        return "Voice Bot/img/treasure.jpg"  # Fallback image


def get_random_image(outcome):
    # Retrieve the folder path for the outcome
    folder_path = image_folders.get(outcome)

    # Check if the folder exists
    if not folder_path or not os.path.exists(folder_path):
        print(f"Image folder not found for outcome: {outcome}")
        return "img/default.jpg"  # Fallback image

    # List all valid image files in the folder
    images = [f for f in os.listdir(folder_path) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]

    # Return a random image if available
    if images:
        chosen_image = random.choice(images)
        return os.path.join(folder_path, chosen_image)
    else:
        print(f"No valid images found in folder: {folder_path}")
        return "img/default.jpg"  # Fallback image


@bot.command(name="open")
async def open_door(ctx):
    global user_activity
    user_activity[ctx.author.id] = datetime.now(timezone.utc)  # Update user's last activity

    # Choose a random outcome
    outcome = random.choices(list(outcomes.keys()), weights=list(outcomes.values()), k=1)[0]

    # Fetch the image and audio paths
    image_path = get_random_image(outcome)
    audio_path = audio_files.get(outcome)

    # Customize the text based on the outcome
    outcome_texts = {
        "hallway": {"title": "You found a Hallway!",
                    "description": "The door creaks open, and you step into a dimly lit hallway. Where will it lead?"},
        "fall": {"title": "You Fell!",
                 "description": "The ground beneath your feet gives way, and you tumble down into the unknown. Ouch!"},
        "trapped": {"title": "You're Trapped!",
                    "description": "The door slams shut behind you. You're trapped! Look around for clues to escape."},
        "door": {"title": "You Found a Door to the Prize!",
                 "description": "Congratulations! Use `.choose` to claim your reward!"},
        "treasure": {"title": "You Found a Treasure Chest!",
                     "description": "Inside the chest, you discover something magical!"},
        "key": {"title": "You Found a Key!",
                "description": "A mysterious key lies on the ground. What door might it unlock? 🗝"},
        "rare_coin": {"title": "You Found a Rare Coin!",
                      "description": "One of the five rare coins glimmers in the corner. Collect them all! 🪙"}
    }

    # Initialize embed
    embed = discord.Embed(
        title=outcome_texts[outcome]["title"],
        description=outcome_texts[outcome]["description"],
        color=discord.Color.blue() if outcome != "trapped" else discord.Color.red()
    )

    # If outcome is treasure, select a random mystical item and add it to inventory
    player_id = str(ctx.author.id)
    if player_id not in player_inventories:
        player_inventories[player_id] = {"items": [], "coins": []}

    if outcome == "treasure":
        available_items = list(set(mystical_items.keys()) - set(player_inventories[player_id]["items"]))
        if available_items:
            item_name = random.choice(available_items)
            item_description = mystical_items[item_name]
            player_inventories[player_id]["items"].append(item_name)
            save_inventories(player_inventories)
            embed.add_field(name=f"You found: {item_name}!", value=item_description)
        else:
            embed.add_field(name="Duplicate Item", value="You've already collected all available treasures!")

    # If outcome is key, add it to the inventory
    if outcome == "key":
        player_inventories[player_id]["items"].append("key")
        save_inventories(player_inventories)
        embed.add_field(name="Inventory Update!", value="You have gained a key! 🗝")

    # If outcome is rare_coin, add a new unique coin to the inventory
    collected_coins = player_inventories[player_id]["coins"]
    available_coins = list(set(required_coins) - set(collected_coins))
    if outcome == "rare_coin" and available_coins:
        new_coin = random.choice(available_coins)
        collected_coins.append(new_coin)
        save_inventories(player_inventories)
        embed.add_field(name="Rare Coin Collected!", value=f"You have collected: **{new_coin}**! 🪙")

    # Add the image to the embed
    if image_path and os.path.exists(image_path):
        file = discord.File(image_path, filename=f"{outcome}.jpg")
        embed.set_image(url=f"attachment://{outcome}.jpg")
        await ctx.send(embed=embed, file=file)
    else:
        await ctx.send(embed=embed)

    # Play the audio file
    if audio_path:
        vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if vc and vc.channel:
            vc.stop()  # Stop current audio
            vc.play(discord.FFmpegPCMAudio(audio_path))
        else:
            if ctx.author.voice and ctx.author.voice.channel:
                vc = await ctx.author.voice.channel.connect()
                vc.play(discord.FFmpegPCMAudio(audio_path))
            else:
                await ctx.send("The bot is not connected to a voice channel to play audio.")


@bot.command(name="choose")
async def choose(ctx):
    # Define reactions and their corresponding prize channels
    prize_channels = {
        "🔴": "red-prize",
        "🟢": "green-prize",
        "🔵": "blue-prize"
    }

    # Embed for choosing the prize
    embed = discord.Embed(
        title="Choose Your Prize",
        description="React to pick a prize door:\n🔴 Red Prize Door\n🟢 Green Prize Door\n🔵 Blue Prize Door",
        color=discord.Color.purple()
    )
    message = await ctx.send(embed=embed)

    # Add reaction options
    for emoji in prize_channels.keys():
        await message.add_reaction(emoji)

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in prize_channels

    try:
        # Wait for the user to react within 30 seconds
        reaction, _ = await bot.wait_for("reaction_add", timeout=30.0, check=check)
        selected_emoji = str(reaction.emoji)

        # Find the corresponding prize channel
        prize_channel_name = prize_channels[selected_emoji]
        guild = ctx.guild
        prize_channel = discord.utils.get(guild.channels, name=prize_channel_name)

        if prize_channel:
            await ctx.send(
                f"You chose the {selected_emoji} prize door! Your prize awaits here: {prize_channel.mention}"
            )
        else:
            await ctx.send(
                f"Oops! The prize channel for {selected_emoji} doesn't exist. Please contact the admin."
            )
    except asyncio.TimeoutError:
        await ctx.send("You took too long to choose! Try again by running `.choose`.")


@bot.command(name="open_sesame")
async def open_sesame(ctx):
    player_id = str(ctx.author.id)
    inventory = player_inventories.get(player_id, {"items": [], "coins": []})

    # Check for all 5 coins
    required_coins = {"coin1", "coin2", "coin3", "coin4", "coin5"}
    if required_coins.issubset(set(inventory["coins"])):
        inventory["coins"] = []  # Reset coins after use
        save_inventories(player_inventories)

        # Create an embed for exiting the game
        embed = discord.Embed(
            title="You Opened the Final Door!",
            description=(
                "Congratulations! You've collected all the coins and unlocked the final door to freedom. "
                "Click the link below to open the special channel!"
            ),
            color=discord.Color.green()
        )
        # Define the image path
        image_path = "img/final_door/final_door.jpg"

        # Check if the image exists and attach it
        if os.path.exists(image_path):
            file = discord.File(image_path, filename="final_door.jpg")
            embed.set_image(url="attachment://final_door.jpg")
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send("🚪 The image for the final door could not be found. Please check the file path.")

        # Add a link to the specific channel
        special_channel = ctx.guild.get_channel(1332802606237487157)
        if special_channel:
            embed.add_field(
                name="🎉 Special Channel",
                value=f"[Click here to access the final door!]({special_channel.jump_url})",
                inline=False
            )
        else:
            embed.add_field(
                name="Error",
                value="Could not find the special channel. Please contact an admin.",
                inline=False
            )

        # Play a song (replace with your song file path)
        audio_path = "audio/final_song.mp3"
        vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if vc and vc.channel:
            vc.stop()
            vc.play(discord.FFmpegPCMAudio(audio_path))
        else:
            if ctx.author.voice and ctx.author.voice.channel:
                vc = await ctx.author.voice.channel.connect()
                vc.play(discord.FFmpegPCMAudio(audio_path))

        # Send the embed
        await ctx.send(embed=embed)
    else:
        await ctx.send("🪙 You don't have all the rare coins yet. Keep exploring!")


@bot.command(name="inventory")
async def inventory(ctx):
    player_id = str(ctx.author.id)

    # Ensure the player's inventory is initialized correctly
    if player_id not in player_inventories:
        player_inventories[player_id] = {"items": [], "coins": []}

    inventory = player_inventories[player_id]  # Get the player's inventory safely

    # Format treasures with their descriptions
    treasures = "\n".join([f"**{item}**: _{mystical_items.get(item, 'No description available')}_"
                           for item in inventory.get("items", [])]) or "None"

    # Format rare coins
    coins = ", ".join(inventory.get("coins", [])) or "None"


    # Send inventory details
    await ctx.send(f"📦 **Your Inventory:**\n\n"
                   f"**Treasures:**\n{treasures}\n\n"
                   f"**Rare Coins:** {coins}")





@bot.command(name="unlock")
async def unlock_door(ctx):
    player_id = str(ctx.author.id)

    # Check if the player has the key in their inventory
    inventory = player_inventories.get(player_id, {"items": [], "coins": []})

    if "key" in inventory["items"]:
        inventory["items"].remove("key")  # Use the key
        save_inventories(player_inventories)  # Save the updated inventory

        # Fetch the special channel
        special_channel = ctx.guild.get_channel(1332592958012133436)

        # Create an embed for the special door
        embed = discord.Embed(
            title="The Special Door Opens!",
            description="You unlock the mysterious door and step into the unknown. Congratulations, adventurer!",
            color=discord.Color.gold()
        )
        embed.set_image(url="attachment://special_door.jpg")  # Placeholder image

        # Add the link to the special channel
        if special_channel:
            embed.add_field(
                name="🎉 Open the Special Door",
                value=f"[Click here to access the special channel!]({special_channel.jump_url})",
                inline=False
            )
        else:
            embed.add_field(
                name="Error",
                value="The special channel could not be found. Please contact an admin.",
                inline=False
            )

        # Play a special song (replace with your song file path)
        audio_path = "audio/special_song.mp3"
        vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
        if vc and vc.channel:
            vc.stop()
            vc.play(discord.FFmpegPCMAudio(audio_path))
        else:
            if ctx.author.voice and ctx.author.voice.channel:
                vc = await ctx.author.voice.channel.connect()
                vc.play(discord.FFmpegPCMAudio(audio_path))

        # Send the embed
        await ctx.send(embed=embed)
    else:
        await ctx.send("🚪 You don't have a key to unlock this door. Try finding one!")







@bot.command(name="collect_all_treasures")
async def collect_all_treasures(ctx):
    player_id = str(ctx.author.id)

    # Initialize inventory if it doesn't exist
    if player_id not in player_inventories:
        player_inventories[player_id] = {"items": [], "coins": []}

    inventory = player_inventories[player_id]

    # Add all mystical items to the player's inventory
    collected_treasures = mystical_items.keys()  # All treasure names
    for treasure in collected_treasures:
        if treasure not in inventory["items"]:  # Prevent duplicates
            inventory["items"].append(treasure)

    # Save the updated inventory
    save_inventories(player_inventories)

    # Notify the user
    await ctx.send(f"✨ You have collected all mystical treasures!\n"
                   f"Check your inventory with `.inventory`.")


@bot.command(name="treasure_list")
async def treasure_list(ctx):
    treasures = "\n".join([f"**{name}**: {desc}" for name, desc in mystical_items.items()])
    await ctx.send(f"📜 **Mystical Treasures to Collect:**\n{treasures}")



@bot.command(name="collect_treasure")
async def collect_treasure(ctx):
    player_id = str(ctx.author.id)

    # Initialize inventory if it doesn't exist
    if player_id not in player_inventories:
        player_inventories[player_id] = {"items": [], "coins": []}

    inventory = player_inventories[player_id]
    mystical_items = ["gem", "ancient scroll", "golden idol", "crystal orb", "silver chalice"]
    new_treasure = random.choice(mystical_items)

    inventory["items"].append(new_treasure)
    save_inventories(player_inventories)

    await ctx.send(f"✨ You found a mystical treasure: **{new_treasure}**!\n"
                   f"Current treasures: {', '.join(inventory['items'])}")


@bot.command(name="collect_key")
async def collect_key(ctx):
    player_id = str(ctx.author.id)

    # Initialize inventory if it doesn't exist
    if player_id not in player_inventories:
        player_inventories[player_id] = {"items": [], "coins": []}

    inventory = player_inventories[player_id]

    # Check if the player already has a key
    if "key" in inventory["items"]:
        await ctx.send("🗝 You already have a key! Use it to unlock a special door before collecting another.")
        return

    # Add a key to the inventory
    inventory["items"].append("key")
    save_inventories(player_inventories)

    await ctx.send("🗝 You collected a key! Use it wisely to unlock a special door.\n"
                   "Use .unlock to OPEN the a special PRIZE DOOR!")


@bot.command(name="collect_coin")
async def collect_coin(ctx):
    player_id = str(ctx.author.id)

    # Initialize inventory if it doesn't exist
    if player_id not in player_inventories:
        player_inventories[player_id] = {"items": [], "coins": []}

    inventory = player_inventories[player_id]
    required_coins = ["coin1", "coin2", "coin3", "coin4", "coin5"]
    collected_coins = inventory["coins"]

    # Check if the player already has all 5 coins
    if set(required_coins).issubset(collected_coins):
        await ctx.send("🪙 You already have all the rare coins! Try using `.open_sesame` to unlock the special door.")
        return

    # Add a random coin that the player doesn't already have
    available_coins = list(set(required_coins) - set(collected_coins))
    if available_coins:
        new_coin = random.choice(available_coins)
        collected_coins.append(new_coin)
        save_inventories(player_inventories)  # Save the updated inventory

        await ctx.send(f"🎉 You collected a rare coin: **{new_coin}**!\n"
                       f"Current coins: {', '.join(collected_coins)}")
    else:
        await ctx.send("✨ You've collected all the rare coins already! Use `.open_sesame` to unlock the special door.")



@bot.command(name="testdoor")
async def test_door(ctx):
    # Simulate the "door" outcome directly
    outcome = "door"

    # Get a random image for the "door" outcome
    image_path = image_files.get(outcome)

    # Embed text for the "door" outcome
    embed = discord.Embed(
        title="You Found a Door to the Prize!",
        description=(
            "Congratulations! Behind this door lies a fantastic prize. 🎉\n\n"
            "Use the `.choose` command to select a prize door and claim your reward!"
        ),
        color=discord.Color.green()
    )

    # Attach the image if available
    if image_path:
        file = discord.File(image_path, filename="door.jpg")
        embed.set_image(url="attachment://door.jpg")
        await ctx.send(embed=embed, file=file)
    else:
        embed.add_field(name="Oops!", value="No images are available for this outcome.")
        await ctx.send(embed=embed)

    # Play the associated audio for the "door" outcome
    await play_audio(ctx, audio_files[outcome])


@bot.command(name="special_door")
async def special_door(ctx):
    # Fetch the special channel
    special_channel = ctx.guild.get_channel(1332802606237487157)

    # Create an embed for the special door
    embed = discord.Embed(
        title="The Special Door",
        description="You stand before the final door. Beyond it lies your freedom and the end of this journey.",
        color=discord.Color.gold()
    )
    embed.set_image(url="attachment://special_door.jpg")  # Placeholder image

    # Add the link to the special channel
    if special_channel:
        embed.add_field(
            name="🎉 Open the Special Door",
            value=f"[Click here to access the special channel!]({special_channel.jump_url})",
            inline=False
        )
    else:
        embed.add_field(
            name="Error",
            value="The special channel could not be found. Please contact an admin.",
            inline=False
        )

    # Play a special song (replace with your song file path)
    audio_path = "audio/special_song.mp3"
    vc = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if vc and vc.channel:
        vc.stop()
        vc.play(discord.FFmpegPCMAudio(audio_path))
    else:
        if ctx.author.voice and ctx.author.voice.channel:
            vc = await ctx.author.voice.channel.connect()
            vc.play(discord.FFmpegPCMAudio(audio_path))

    # Send the embed
    await ctx.send(embed=embed)



@bot.command(name="reset")
async def reset(ctx):
    guild = ctx.guild
    user_name = ctx.author.name.lower()
    user_id = str(ctx.author.id)

    # Get the user's text and voice channels
    text_channel = discord.utils.get(guild.channels, name=f"game-text-{user_name}")
    voice_channel = discord.utils.get(guild.channels, name=f"game-voice-{user_name}")

    # Clear the user's inventory
    if user_id in player_inventories:
        del player_inventories[user_id]
        save_inventories(player_inventories)  # Save updated inventories
        await ctx.send("Your game inventory has been cleared.")

    # Delete the voice channel if it exists
    if voice_channel:
        await voice_channel.delete()
        await ctx.send(f"Deleted your game voice channel: {voice_channel.name}")
    else:
        await ctx.send("No game voice channel found to delete.")

    # Delete the text channel if it exists
    if text_channel:
        await asyncio.sleep(3)  # Wait for 3 seconds before deleting
        await text_channel.delete()
        await ctx.send(f"Deleted your game text channel: {text_channel.name}")
    else:
        await ctx.send("No game text channel found to delete.")


    # Notify if no channels or inventory exist
    if not text_channel and not voice_channel and user_id not in player_inventories:
        await ctx.send("You don't have any saved game channels or inventory to reset.")


@bot.command(name="end")
async def end(ctx):
    guild = ctx.guild
    user_name = ctx.author.name.lower()
    user_id = str(ctx.author.id)

    # Get the user's text and voice channels
    text_channel = discord.utils.get(guild.channels, name=f"game-text-{user_name}")
    voice_channel = discord.utils.get(guild.channels, name=f"game-voice-{user_name}")

    # Delete the user's voice channel
    if voice_channel:
        await voice_channel.delete()
        await ctx.send(f"Your game voice channel `{voice_channel.name}` has been deleted.")
    else:
        await ctx.send("No game voice channel found to delete.")

    # Delete the user's text channel
    if text_channel:
        await text_channel.delete()
        await ctx.send(f"Your game text channel `{text_channel.name}` has been deleted.")
    else:
        await ctx.send("No game text channel found to delete.")



    # Disconnect the bot if it's in the voice channel
    existing_vc = discord.utils.get(bot.voice_clients, guild=guild)
    if existing_vc:
        await existing_vc.disconnect()
        await ctx.send("The bot has been disconnected from the voice channel.")


# Run the bot
bot.run(DISCORD_TOKEN)
