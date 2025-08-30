import telebot # type: ignore

# REPLACE THIS WITH YOUR ACTUAL BOT TOKEN FROM BOTFATHER
TOKEN = "8443032865:AAEdlwegVR6hnFoljqgQLc2NOR3zS45hUOU"

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# Simple start command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Hello! The bot is working correctly!")

print("Testing bot connection...")
try:
    bot.infinity_polling()
    print("Bot is running successfully!")
except Exception as e:
    print(f"Error: {e}")


import telebot # type: ignore
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton # pyright: ignore[reportMissingImports]
import logging

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)

# REPLACE THIS WITH YOUR ACTUAL BOT TOKEN FROM BOTFATHER
TOKEN = "8443032865:AAEdlwegVR6hnFoljqgQLc2NOR3zS45hUOU"

# Initialize bot
bot = telebot.TeleBot(TOKEN)

# Store user data and matches
users = {}
waiting_queue = {
    'listener': {'male': [], 'female': []},
    'talker': {'male': [], 'female': []},
    'mommy': [],
    'daddy': []
}
active_matches = {}

# Main menu keyboard
def main_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("Listener/Talker", callback_data='section_listener_talker'),
        InlineKeyboardButton("Mommy/Daddy", callback_data='section_mommy_daddy')
    )
    return keyboard

# Role selection keyboard
def role_selection_keyboard(section):
    keyboard = InlineKeyboardMarkup()
    if section == 'listener_talker':
        keyboard.row(
            InlineKeyboardButton("Listener", callback_data='role_listener'),
            InlineKeyboardButton("Talker", callback_data='role_talker')
        )
    else:
        keyboard.row(
            InlineKeyboardButton("Mommy", callback_data='role_mommy'),
            InlineKeyboardButton("Daddy", callback_data='role_daddy')
        )
    return keyboard

# Gender selection keyboard
def gender_selection_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("Male", callback_data='gender_male'),
        InlineKeyboardButton("Female", callback_data='gender_female')
    )
    return keyboard

# Start command
@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    users[user_id] = {'state': 'main_menu'}
    
    bot.send_message(
        message.chat.id, 
        f"Hi {message.from_user.first_name}! Welcome to Anonymous Matchmaking Bot.\n\n"
        "Choose a section to continue:",
        reply_markup=main_menu_keyboard()
    )

# Handle callback queries
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    user_id = call.from_user.id
    data = call.data
    
    if data.startswith('section_'):
        section = data.split('_')[1]
        users[user_id] = {'state': 'choosing_role', 'section': section}
        
        bot.edit_message_text(
            "Choose your role:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=role_selection_keyboard(section)
        )
        
    elif data.startswith('role_'):
        role = data.split('_')[1]
        users[user_id]['role'] = role
        
        if users[user_id]['section'] == 'listener_talker':
            users[user_id]['state'] = 'choosing_gender'
            
            bot.edit_message_text(
                "Select your gender:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=gender_selection_keyboard()
            )
        else:
            # For mommy/daddy section, no gender selection needed
            users[user_id]['state'] = 'waiting'
            users[user_id]['gender'] = None
            
            bot.edit_message_text(
                "Looking for a match... Please wait.",
                call.message.chat.id,
                call.message.message_id
            )
            
            # Add to queue
            add_to_waiting_queue(user_id)
            try_match(user_id)
            
    elif data.startswith('gender_'):
        gender = data.split('_')[1]
        users[user_id]['gender'] = gender
        users[user_id]['state'] = 'waiting'
        
        bot.edit_message_text(
            "Looking for a match... Please wait.",
            call.message.chat.id,
            call.message.message_id
        )
        
        # Add to queue
        add_to_waiting_queue(user_id)
        try_match(user_id)

# Add user to waiting queue
def add_to_waiting_queue(user_id):
    user_data = users[user_id]
    
    if user_data['section'] == 'listener_talker':
        waiting_queue[user_data['role']][user_data['gender']].append(user_id)
    else:
        waiting_queue[user_data['role']].append(user_id)

# Try to match users
def try_match(user_id):
    user_data = users[user_id]
    
    if user_data['section'] == 'listener_talker':
        # Find opposite role
        target_role = 'talker' if user_data['role'] == 'listener' else 'listener'
        
        # Check for matches
        if waiting_queue[target_role][user_data['gender']]:
            partner_id = waiting_queue[target_role][user_data['gender']].pop(0)
            create_match(user_id, partner_id)
    else:
        # Mommy/Daddy section
        target_role = 'daddy' if user_data['role'] == 'mommy' else 'mommy'
        
        if waiting_queue[target_role]:
            partner_id = waiting_queue[target_role].pop(0)
            create_match(user_id, partner_id)

# Create a match between two users
def create_match(user1_id, user2_id):
    user1_data = users[user1_id]
    user2_data = users[user2_id]
    
    active_matches[user1_id] = user2_id
    active_matches[user2_id] = user1_id
    
    user1_data['state'] = 'in_conversation'
    user2_data['state'] = 'in_conversation'
    user1_data['partner'] = user2_id
    user2_data['partner'] = user1_id
    
    # Notify both users
    bot.send_message(
        user1_id, 
        "🎉 You've been matched with a partner! Start chatting now.\n\n"
        "Use /end to end the conversation."
    )
    bot.send_message(
        user2_id, 
        "🎉 You've been matched with a partner! Start chatting now.\n\n"
        "Use /end to end the conversation."
    )

# Handle text messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    
    if user_id not in users:
        bot.send_message(user_id, "Please start the bot with /start first")
        return
    
    user_data = users[user_id]
    
    if user_data['state'] == 'in_conversation' and 'partner' in user_data:
        # Forward message to partner
        try:
            bot.send_message(user_data['partner'], f"💬 {message.text}")
        except:
            bot.send_message(user_id, "Failed to send message. Your partner may have left the conversation.")
    else:
        bot.send_message(user_id, "You're not in an active conversation. Use /start to find a match.")

# End conversation command
@bot.message_handler(commands=['end'])
def end_conversation(message):
    user_id = message.from_user.id
    
    if user_id not in users:
        bot.send_message(user_id, "Please start the bot with /start first")
        return
    
    user_data = users[user_id]
    
    if user_data['state'] == 'in_conversation' and 'partner' in user_data:
        partner_id = user_data['partner']
        
        # Notify both users
        bot.send_message(user_id, "Conversation ended. Returning to main menu.")
        
        try:
            bot.send_message(partner_id, "Your partner has ended the conversation. Returning to main menu.")
        except:
            pass
        
        # Clean up
        if user_id in active_matches:
            del active_matches[user_id]
        if partner_id in active_matches:
            del active_matches[partner_id]
        
        if partner_id in users:
            users[partner_id]['state'] = 'main_menu'
            if 'partner' in users[partner_id]:
                del users[partner_id]['partner']
            
            # Send main menu to partner
            bot.send_message(
                partner_id, 
                "Choose a section to continue:",
                reply_markup=main_menu_keyboard()
            )
        
        user_data['state'] = 'main_menu'
        if 'partner' in user_data:
            del user_data['partner']
        
        # Send main menu to user
        bot.send_message(
            user_id, 
            "Choose a section to continue:",
            reply_markup=main_menu_keyboard()
        )
    else:
        bot.send_message(user_id, "You're not in an active conversation.")

# Start the bot
if __name__ == '__main__':
    print("Bot is starting...")
    bot.infinity_polling()