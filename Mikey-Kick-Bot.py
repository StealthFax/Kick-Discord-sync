import discord
from discord.ext import commands, tasks
import sqlite3
import random
from selenium import webdriver
from bs4 import BeautifulSoup
from collections import deque
import time
import threading
import logging
from asyncio import Queue

# Constants
subscriber_badges = [{'id': 640, 'channel_id': 24, 'months': 1, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/640/original'}}, {'id': 668, 'channel_id': 24, 'months': 2, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/668/original'}}, {'id': 669, 'channel_id': 24, 'months': 3, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/669/original'}}, {'id': 671, 'channel_id': 24, 'months': 6, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/671/original'}}, {'id': 673, 'channel_id': 24, 'months': 9, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/673/original'}}, {'id': 674, 'channel_id': 24, 'months': 12, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/674/original'}}, {'id': 676, 'channel_id': 24, 'months': 18, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/676/original'}}, {'id': 678, 'channel_id': 24, 'months': 24, 'badge_image': {'srcset': '', 'src': 'https://files.kick.com/channel_subscriber_badges/678/original'}}]
badge_lookup = {badge['badge_image']['src']: badge['months'] for badge in subscriber_badges}

# Additional constants
GUILD_ID = 1049752011953930362  # Your guild ID
LOG_CHANNEL_ID = 1139259472477429830  # Your log channel ID
MODERATOR_ROLE_ID = 1049754098276253736  # Your moderator role ID
# Mapping of subscription months to Discord Role IDs
ROLE_MAPPING = {
    0: 1124365579264999538,  # Non-subscribers
    1: 1127577585652605070,  # 1 month
    2: 1127578587483099237,  # 2 months
    3: 1127579036877586524,  # 3 months
    6: 1127579682016083988   # 6 months
    # Add more mappings as needed
}
# Create a queue to hold commands
command_queue = Queue()

#Discord bot function from kick command initiations
async def send_pokemon_message(user_name):
    guild = bot.get_guild(GUILD_ID)
    logging_channel = discord.utils.get(guild.channels, id=LOG_CHANNEL_ID)

    message = f"User {user_name} really wants pokemon back"
    await logging_channel.send(message)
#Kick command handlers
command_handlers = {
    "!pokemon": send_pokemon_message,
    # Add more commands and handlers as needed
}

DATABASE_NAME = 'kick_discord_bot.db'
CHAT_URL = 'https://www.kick.com/mikey/chatroom'
TOKEN = 'XXXX'
deque_processed_messages = deque(maxlen=300)

# Database connection function
def connect_to_database():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            discord_id TEXT PRIMARY KEY,
            kick_username TEXT NOT NULL,
            verification_token TEXT NOT NULL,
            is_subscriber BOOLEAN DEFAULT 0,
            months_subscribed INTEGER DEFAULT 0,
            discord_verified BOOLEAN DEFAULT 0
        )
    ''')
    conn.commit()
    return conn, cursor

# Chat monitor functions
def init_browser():
    options = webdriver.ChromeOptions()
    return webdriver.Chrome(options=options)

def extract_data_from_html(html_source, cursor):
    soup = BeautifulSoup(html_source, 'html.parser')
    chat_entries = soup.find_all('div', class_='chat-entry')
    print(f"Found {len(chat_entries)} chat entries")
    for entry in chat_entries:
        check_and_verify(entry, cursor)

# Lookup dictionary for badge image URLs and their corresponding subscription months
badge_months_lookup = {
    'https://files.kick.com/channel_subscriber_badges/640/original': 1,
    'https://files.kick.com/channel_subscriber_badges/668/original': 2,
    'https://files.kick.com/channel_subscriber_badges/669/original': 3,
    'https://files.kick.com/channel_subscriber_badges/671/original': 6,
    'https://files.kick.com/channel_subscriber_badges/673/original': 9,
    'https://files.kick.com/channel_subscriber_badges/674/original': 12,
    'https://files.kick.com/channel_subscriber_badges/676/original': 18,
    'https://files.kick.com/channel_subscriber_badges/678/original': 24
}

def check_and_verify(chat_entry, cursor):
    username = chat_entry.find(class_='chat-entry-username').text.strip()
    print(f"[DEV LOG] Detected chat entry from user: {username}")

    # Directly fetching the verification status from the database
    cursor.execute('SELECT discord_verified FROM users WHERE kick_username=?', (username,))
    result = cursor.fetchone()
    if not result:
        print(f"[DEV LOG] No data found for user: {username}. Skipping verification.")
        return
    discord_verified = result[0]

    # If the user is not verified, check the message against the verification token
    message = chat_entry.find(class_='chat-entry-content')
    if not message or not message.text.strip():
        print(f"[DEV LOG] Ignoring empty message or non-text content from user: {username}")
        return
    message = message.text.strip()
    if not discord_verified:
        cursor.execute('SELECT verification_token FROM users WHERE kick_username=?', (username,))
        verification_token = cursor.fetchone()[0]
        if message == verification_token:
            cursor.execute('UPDATE users SET discord_verified=1 WHERE kick_username=?', (username,))
            cursor.connection.commit()
            print(f"[DEV LOG] User {username} verified successfully.")
        return

    message = chat_entry.find(class_='chat-entry-content')
    if not message or not message.text.strip():
        print(f"[DEV LOG] Ignoring empty message or non-text content from user: {username}")
        return
    message = message.text.strip()
    print(f"[DEV LOG] Message content from user {username}: {message}")

    # Check if message is already processed
    if (username, message) in deque_processed_messages:
        print(f"[DEV LOG] Message from user {username} already processed. Skipping.")
        return

    # Add the message to deque
    deque_processed_messages.append((username, message))

    # Check for registered commands
    for command, handler in command_handlers.items():
        if message == command:
            command_queue.put_nowait((command, username))
            break  # Only handle the first matched command

    # Check for subscriber badge
    badge_img_tag = chat_entry.find('button', class_='base-custom-badge')
    if badge_img_tag and badge_img_tag.find('img') and 'src' in badge_img_tag.find('img').attrs:
        badge_img_src = badge_img_tag.find('img')['src']
        if badge_img_src in badge_months_lookup:
            months_subscribed = badge_months_lookup[badge_img_src]
            cursor.execute('UPDATE users SET is_subscriber=1, months_subscribed=? WHERE kick_username=?', (months_subscribed, username))
            cursor.connection.commit()
            print(f"[DEV LOG] Updated subscriber status for user {username} to {months_subscribed} months.")
        else:
            cursor.execute('UPDATE users SET is_subscriber=0, months_subscribed=0 WHERE kick_username=?', (username,))
            cursor.connection.commit()
            print(f"[DEV LOG] Updated subscriber status for user {username} to not subscribed.")
    else:
        cursor.execute('UPDATE users SET is_subscriber=0, months_subscribed=0 WHERE kick_username=?', (username,))
        cursor.connection.commit()
        print(f"[DEV LOG] Updated subscriber status for user {username} to not subscribed.")



def chat_monitor_loop():
    conn, cursor = connect_to_database()
    browser = init_browser()
    browser.get(CHAT_URL)
    try:
        while True:
            html_source = browser.page_source
            extract_data_from_html(html_source, cursor)
            time.sleep(30)
    except Exception as e:
        print(f"Chat monitor error: {e}")
    finally:
        conn.close()
        browser.quit()

# Discord bot functions
intents = discord.Intents.default()
intents.message_content = True
intents.messages = True
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')

@bot.command(name='verify', help='Verify your kick.com username.')
async def verify(ctx, kick_username: str = None):
    conn, cursor = connect_to_database()

    # Check if the user is already verified
    cursor.execute('SELECT * FROM users WHERE discord_id=? AND discord_verified=1', (ctx.author.id,))
    verified_user = cursor.fetchone()

    if verified_user:
        await ctx.send(f"{ctx.author.mention} You are already verified with the username {verified_user[1]}.")
        return

    # Check if the user is pending verification
    cursor.execute('SELECT * FROM users WHERE discord_id=? AND discord_verified=0', (ctx.author.id,))
    pending_user = cursor.fetchone()

    if pending_user:
        if kick_username:
            # Update kick username for pending user
            cursor.execute('UPDATE users SET kick_username=? WHERE discord_id=?', (kick_username, ctx.author.id))
            conn.commit()
            await ctx.send(f"{ctx.author.mention} Kick username updated to {kick_username}. "
                           f"Please re-verify with the new username.")
        else:
            await ctx.send(f"{ctx.author.mention} You are pending verification. Please provide a KickUsername to update.")
    else:
        if not kick_username:
            await ctx.send(f"{ctx.author.mention} Please provide a KickUsername to verify. Example: `!verify KickUsername`")
            return

        # Perform the verification process as before
        token = random.randint(1000, 9999)
        cursor.execute('INSERT INTO users (discord_id, kick_username, verification_token) VALUES (?, ?, ?)',
                       (ctx.author.id, kick_username, token))
        conn.commit()
        await ctx.send(f"{ctx.author.mention} To verify, please type the following token in Mikey's Kick.com chat: {token}")

    conn.close()

#async def remind_pending_verification():
#    conn, cursor = connect_to_database()
#
#    # Fetch all pending verified users
#    cursor.execute('SELECT discord_id, kick_username, verification_token FROM users WHERE discord_verified=0')
#    pending_users = cursor.fetchall()
#
#    for user_id, kick_username, verification_token in pending_users:
#        user = await bot.fetch_user(user_id)
#        await user.send(f"Hello {user.mention}! Your Kick verification is still pending. "
#                        f"Please type the following token in Mikey's Kick.com chat: {verification_token}")
#
#    conn.close()

	
def get_all_verified_users_data():
    conn, cursor = connect_to_database()
    cursor.execute('SELECT discord_id, months_subscribed FROM users WHERE discord_verified=1')
    data = cursor.fetchall()
    conn.close()
    return data

async def update_discord_role_for_user(user_id, months_subscribed):
    print(f"Updating roles for user with ID {user_id}...")
    
    GUILD_ID = 1049752011953930362
    guild = discord.utils.get(bot.guilds, id=GUILD_ID)
    print(f"Target guild fetched: {guild.name} ({guild.id})")

    user_id = int(user_id)  # Ensure user_id is an integer
    print(f"User ID verified as integer: {user_id}")

    try:
        member = await guild.fetch_member(user_id)
        print(f"Fetched member with name: {member.name} and ID: {user_id}")
    except discord.NotFound:
        print(f"Member with ID {user_id} not found in guild.")
        return
    except discord.HTTPException:
        print(f"Failed to fetch member with ID {user_id}.")
        return

    # Check and update the member's display name if necessary
    conn, cursor = connect_to_database()
    cursor.execute('SELECT kick_username FROM users WHERE discord_id=?', (user_id,))
    kick_username = cursor.fetchone()
    display_name_changed = False
    try:
        if kick_username and member.display_name != kick_username[0]:
            old_display_name = member.display_name
            await member.edit(nick=kick_username[0])
            print(f"Updated Discord nickname for {member.name} from '{old_display_name}' to '{kick_username[0]}'.")
            display_name_changed = True
    except discord.Forbidden:
        print(f"Permission denied: Bot does not have sufficient permissions to change nickname for {member.name}")

    # Determine the appropriate role based on subscription months
    role_id = ROLE_MAPPING.get(months_subscribed, ROLE_MAPPING[0])  # Default to non-subscriber role
    target_role = discord.utils.get(guild.roles, id=role_id)

    # Check if the member already has the target role
    if target_role in member.roles:
        print(f"Member {member.name} already has the role {target_role.name}. Skipping role update.")
        return

    # Log the role change
    change_log_channel = discord.utils.get(guild.channels, id=1139259472477429830)  # Your desired channel ID
    log_message = f"Role change for user: {member.name}"
    if display_name_changed:
        log_message += f" (Nickname changed from '{old_display_name}' to '{kick_username[0]}')"
    log_message += f", Role: {target_role.name}"
    await change_log_channel.send(log_message)

    # Remove all subscriber roles from user
    for role_id in ROLE_MAPPING.values():
        role = discord.utils.get(guild.roles, id=role_id)
        try:
            if role in member.roles:
                await member.remove_roles(role)
                print(f"Removed role {role.name} from member {member.name}")
        except discord.Forbidden:
            print(f"Permission denied: Bot does not have sufficient permissions to remove role {role.name} from {member.name}")
    
    # Assign the appropriate role based on subscription months
    try:
        await member.add_roles(target_role)
        print(f"Assigned role {target_role.name} to member {member.name} based on {months_subscribed} months of subscription.")
    except discord.Forbidden:
        print(f"Permission denied: Bot does not have sufficient permissions to assign role {target_role.name} to {member.name}")



from discord.ext import tasks
from discord.utils import get


@bot.command(name='pending', help='List all pending verifications (moderator only)')
@commands.has_role(MODERATOR_ROLE_ID)
async def list_pending_verifications(ctx):
    conn, cursor = connect_to_database()

    # Fetch all pending verified users
    cursor.execute('SELECT discord_id, kick_username, verification_token FROM users WHERE discord_verified=0')
    pending_users = cursor.fetchall()

    if not pending_users:
        await ctx.send("No pending verifications found.")
    else:
        response = "Pending verifications:\n"
        for user_id, kick_username, verification_token in pending_users:
            user = await bot.fetch_user(user_id)
            response += f"User: {kick_username} ({user.mention}), Token: {verification_token}\n"
        await ctx.send(response)

    conn.close()
	
# New command to check Kick username
@bot.command(name='checkkick', help='Check user details by Kick username')
async def check_kick(ctx, kick_username: str):
    conn, cursor = connect_to_database()

    # Fetch user details from the database using the provided Kick username
    cursor.execute('SELECT discord_id, is_subscriber, months_subscribed, discord_verified FROM users WHERE kick_username=?', (kick_username,))
    user_details = cursor.fetchone()

    if user_details:
        discord_id, is_subscriber, months_subscribed, discord_verified = user_details
        mention = f'<@{discord_id}>' if discord_id else "Not linked"  # Mention the user by their Discord ID if available

        subscriber_status = "Subscriber" if is_subscriber else "Non-Subscriber"
        subscription_months = months_subscribed if is_subscriber else 0

        verification_status = "Verified" if discord_verified else "Not Verified"

        response = (f"Kick Username: {kick_username}\n"
                    f"Discord User: {mention}\n"
                    f"Subscription Status: {subscriber_status} ({subscription_months} months)\n"
                    f"Verification Status: {verification_status}")
    else:
        response = "User not found in the database."

    await ctx.send(response)

    conn.close()

# New command to check Discord user by mention
@bot.command(name='checkdiscord', help='Check user details by Discord mention (moderator only)')
@commands.has_role(MODERATOR_ROLE_ID)
async def check_discord(ctx, user: discord.User):
    conn, cursor = connect_to_database()

    # Fetch user details from the database using the provided Discord ID
    cursor.execute('SELECT kick_username, is_subscriber, months_subscribed, discord_verified FROM users WHERE discord_id=?', (user.id,))
    user_details = cursor.fetchone()

    if user_details:
        kick_username, is_subscriber, months_subscribed, discord_verified = user_details

        subscriber_status = "Subscriber" if is_subscriber else "Non-Subscriber"
        subscription_months = months_subscribed if is_subscriber else 0

        verification_status = "Verified" if discord_verified else "Not Verified"

        response = (f"Discord User: {user.mention}\n"
                    f"Kick Username: {kick_username}\n"
                    f"Subscription Status: {subscriber_status} ({subscription_months} months)\n"
                    f"Verification Status: {verification_status}")
    else:
        response = "User not found in the database."

    await ctx.send(response)

    conn.close()

@bot.command(name='compare_roles', help='Compare users\' roles in Discord with roles managed by the bot (moderator only)')
@commands.has_role(MODERATOR_ROLE_ID)
async def compare_roles(ctx):
    conn, cursor = connect_to_database()

    # Fetch all users from the database
    cursor.execute('SELECT discord_id, kick_username, months_subscribed FROM users')
    db_users = cursor.fetchall()

    # Fetch the guild dynamically using the GUILD_ID constant
    guild = get(bot.guilds, id=GUILD_ID)

    # Fetch all members from the Discord server
    discord_members = [member for member in guild.members if not member.bot]

    discrepancies = []
    user_details = []

    user_details.append("Starting role comparison...")

    for member in discord_members:
        db_user = None

        # Find the database user based on Discord user ID
        for db_user_id, kick_username, months_subscribed in db_users:
            if member.id == db_user_id:
                db_user = (kick_username, months_subscribed)
                break

        if db_user is not None:
            # Skip users already in the database with managed roles
            member_roles = [role.id for role in member.roles if role.id in ROLE_MAPPING.values()]
            if any(role_id in member_roles for role_id in ROLE_MAPPING.values()):
                continue

        # Check if the user has any roles from ROLE_MAPPING
        member_roles = [role.id for role in member.roles if role.id in ROLE_MAPPING.values()]

        if not member_roles:
            print(f"Skipping {member.name}#{member.discriminator} ({member.id}): No relevant roles.")
            continue  # Skip users without relevant roles

        print(f"Checking roles for {member.name}#{member.discriminator} ({member.id}): {', '.join(role.name for role in member.roles if role.id in ROLE_MAPPING.values())}")

        discrepancies.append(member)

    if not discrepancies:
        user_details.append("No users with discrepancies found.")
    else:
        user_details.append("Users with discrepancies:")
        for member in discrepancies:
            user_details.append(f"User: {member.name}#{member.discriminator} ({member.id}), Roles: {', '.join(role.name for role in member.roles if role.id in ROLE_MAPPING.values())}")
            print(f"User {member.name}#{member.discriminator} ({member.id}) has roles not managed by the bot: {', '.join(role.name for role in member.roles if role.id in ROLE_MAPPING.values())}")

    user_details.append("Role comparison complete.")

    for detail in user_details:
        if len(detail) > 2000:
            await ctx.send(detail)  # Send the long detail separately
        else:
            await ctx.send(detail)
            print(detail)

    conn.close()

# New command to list available commands (restricted to moderator role)
@bot.command(name='commands', help='List all available bot commands (moderator only)')
@commands.has_role(MODERATOR_ROLE_ID)
async def list_commands(ctx):
    command_list = "\n".join([f"!{command.name}: {command.help}" for command in bot.commands])
    response = f"Available commands:\n{command_list}"
    await ctx.send(response)


@tasks.loop(minutes=1)  # Adjust the interval as needed
async def periodic_role_update():
    users_data = get_all_verified_users_data()
    for user_id, months_subscribed in users_data:
        await update_discord_role_for_user(user_id, months_subscribed)

## Set up the daily reminder task
#@tasks.loop(hours=24)  # Adjust the interval as needed
#async def daily_verification_reminder():
#    await remind_pending_verification()

@tasks.loop(seconds=1)  # Check every second
async def process_commands():
    while not command_queue.empty():
        command, user_name = command_queue.get_nowait()
        handler = command_handlers.get(command)
        if handler:
            await handler(user_name)

# Start the periodic task when the bot is ready
@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    periodic_role_update.start()
    process_commands.start()  # Start the command processing loop
#    daily_verification_reminder.start()
    compare_roles.start()  # Start the compare_roles loop


if __name__ == '__main__':
    chat_thread = threading.Thread(target=chat_monitor_loop)
    chat_thread.start()
    bot.run(TOKEN)
