import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import time
from datetime import datetime
import threading
import queue
import os
from flask import Flask
from threading import Thread
from pymongo import MongoClient
from bson import ObjectId
import json

# Initialize Flask app for keeping alive
app = Flask('')

@app.route('/')
def home():
    return "Bot is alive and running!"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# ==================== DATABASE SETUP ====================
# MongoDB connection
def get_database():
    try:
        # Get connection string from environment variable
        mongodb_uri = os.environ.get('mongodb+srv://kaushiktadavi167_db_user:<Kauzma$1908>@cluster0.7awxfky.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')
        client = MongoClient(mongodb_uri)
        db = client.telegram_bot
        return db
    except Exception as e:
        logging.error(f"Database connection error: {e}")
        return None

# Custom JSON encoder to handle ObjectId
class CustomJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, ObjectId):
            return str(o)
        return super().default(o)

# ==================== SETUP ====================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
# Get bot token from environment variable
BOT_TOKEN = os.environ.get('BOT_TOKEN')

# ==================== INITIALIZE BOT ====================
bot = telebot.TeleBot(BOT_TOKEN)

# ==================== DATA STRUCTURES ====================
# Initialize database connection
db = get_database()

# Collections
users_collection = db.users if db else None
conversations_collection = db.conversations if db else None
queues_collection = db.queues if db else None

# ==================== DATA MANAGEMENT FUNCTIONS ====================
def save_user(user_id, user_data):
    """Save user data to database"""
    if users_collection:
        users_collection.update_one(
            {'user_id': user_id},
            {'$set': user_data},
            upsert=True
        )

def get_user(user_id):
    """Get user data from database"""
    if users_collection:
        return users_collection.find_one({'user_id': user_id})
    return None

def save_conversation(user1_id, user2_id):
    """Save conversation to database"""
    if conversations_collection:
        conversations_collection.insert_one({
            'user1_id': user1_id,
            'user2_id': user2_id,
            'started_at': datetime.now(),
            'active': True
        })

def end_conversation_in_db(user_id):
    """Mark conversation as ended in database"""
    if conversations_collection:
        conversations_collection.update_one(
            {'$or': [{'user1_id': user_id}, {'user2_id': user_id}], 'active': True},
            {'$set': {'active': False, 'ended_at': datetime.now()}}
        )

def save_queue_state():
    """Save queue state to database"""
    if queues_collection:
        queues_collection.update_one(
            {'name': 'waiting_queues'},
            {'$set': {
                'listener_male': waiting_queues['listener']['male'],
                'listener_female': waiting_queues['listener']['female'],
                'talker_male': waiting_queues['talker']['male'],
                'talker_female': waiting_queues['talker']['female'],
                'mommy': waiting_queues['mommy'],
                'daddy': waiting_queues['daddy'],
                'last_updated': datetime.now()
            }},
            upsert=True
        )

def load_queue_state():
    """Load queue state from database"""
    if queues_collection:
        queue_data = queues_collection.find_one({'name': 'waiting_queues'})
        if queue_data:
            waiting_queues['listener']['male'] = queue_data.get('listener_male', [])
            waiting_queues['listener']['female'] = queue_data.get('listener_female', [])
            waiting_queues['talker']['male'] = queue_data.get('talker_male', [])
            waiting_queues['talker']['female'] = queue_data.get('talker_female', [])
            waiting_queues['mommy'] = queue_data.get('mommy', [])
            waiting_queues['daddy'] = queue_data.get('daddy', [])

# ==================== DATA STRUCTURES ====================
# Waiting queues for different roles
waiting_queues = {
    'listener': {'male': [], 'female': []},
    'talker': {'male': [], 'female': []},
    'mommy': [],
    'daddy': []
}

# Load queue state from database on startup
load_queue_state()

# Matchmaking queue for processing matches
matchmaking_queue = queue.Queue()

# ==================== KEYBOARDS ====================
def main_menu_keyboard():
    """Create the main menu keyboard"""
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("👂 Listener/Talker 👄", callback_data='section_listener_talker'),
        InlineKeyboardButton("👩 Mommy/Daddy 👨", callback_data='section_mommy_daddy')
    )
    return keyboard

def role_selection_keyboard(section):
    """Create role selection keyboard based on section"""
    keyboard = InlineKeyboardMarkup()
    if section == 'listener_talker':
        keyboard.row(
            InlineKeyboardButton("👂 Listener", callback_data='role_listener'),
            InlineKeyboardButton("👄 Talker", callback_data='role_talker')
        )
    else:  # mommy_daddy section
        keyboard.row(
            InlineKeyboardButton("👩 Mommy", callback_data='role_mommy'),
            InlineKeyboardButton("👨 Daddy", callback_data='role_daddy')
        )
    keyboard.row(InlineKeyboardButton("🔙 Back", callback_data='back_to_main'))
    return keyboard

def gender_selection_keyboard():
    """Create gender selection keyboard"""
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("♂️ Male", callback_data='gender_male'),
        InlineKeyboardButton("♀️ Female", callback_data='gender_female')
    )
    keyboard.row(InlineKeyboardButton("🔙 Back", callback_data='back_to_role'))
    return keyboard

def conversation_controls_keyboard():
    """Create keyboard for conversation controls"""
    keyboard = InlineKeyboardMarkup()
    keyboard.row(InlineKeyboardButton("❌ End Conversation", callback_data='end_conversation'))
    return keyboard

# ==================== MATCHMAKING THREAD ====================
def matchmaking_worker():
    """Background worker to process matches"""
    while True:
        try:
            user_id = matchmaking_queue.get(timeout=1)
            user_data = get_user(user_id)
            if user_data and user_data.get('state') == 'waiting':
                try_to_match(user_id)
            matchmaking_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Error in matchmaking worker: {e}")
            time.sleep(1)

# Start the matchmaking thread
matchmaking_thread = threading.Thread(target=matchmaking_worker, daemon=True)
matchmaking_thread.start()

# ==================== COMMAND HANDLERS ====================
@bot.message_handler(commands=['start'])
def start_command(message):
    """Handle /start command"""
    user_id = message.from_user.id
    user_name = message.from_user.first_name
    
    # Initialize user data
    user_data = {
        'user_id': user_id,
        'name': user_name,
        'state': 'main_menu',
        'section': None,
        'role': None,
        'gender': None,
        'partner': None,
        'joined_at': datetime.now(),
        'last_activity': datetime.now()
    }
    
    save_user(user_id, user_data)
    
    welcome_text = f"""
👋 Hello {user_name}! Welcome to Anonymous Matchmaking Bot!

✨ **Features:**
- 👂 Listeners & 👄 Talkers section
- 👩 Mommies & 👨 Daddies section
- 🔒 Fully anonymous chatting
- ⚡ Instant matching

Choose a section to get started:
    """
    
    bot.send_message(user_id, welcome_text, reply_markup=main_menu_keyboard())

@bot.message_handler(commands=['help'])
def help_command(message):
    """Handle /help command"""
    help_text = """
🤖 **Bot Commands:**
/start - Start the bot and show main menu
/help - Show this help message
/end - End current conversation
/stop - Stop searching for a match

📋 **How to use:**
1. Choose a section (Listener/Talker or Mommy/Daddy)
2. Select your role
3. For Listener/Talker, select your gender
4. Wait for a match
5. Start chatting anonymously!

🔒 **Privacy:** Your messages are anonymous. No personal information is shared.
    """
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['end', 'stop'])
def end_command(message):
    """Handle /end and /stop commands"""
    user_id = message.from_user.id
    
    user_data = get_user(user_id)
    if not user_data:
        bot.send_message(user_id, "Please start the bot first with /start")
        return
    
    if user_data['state'] == 'in_conversation' and user_data['partner']:
        end_conversation(user_id)
    elif user_data['state'] == 'waiting':
        stop_searching(user_id)
    else:
        bot.send_message(user_id, "You're not in a conversation or searching for a match.")

# ==================== CALLBACK QUERY HANDLER ====================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    """Handle all callback queries"""
    user_id = call.from_user.id
    
    user_data = get_user(user_id)
    if not user_data:
        bot.answer_callback_query(call.id, "Please start the bot with /start first")
        return
    
    data = call.data
    
    if data == 'back_to_main':
        handle_back_to_main(user_id, call)
    elif data == 'back_to_role':
        handle_back_to_role(user_id, call)
    elif data.startswith('section_'):
        handle_section_selection(user_id, call, data)
    elif data.startswith('role_'):
        handle_role_selection(user_id, call, data)
    elif data.startswith('gender_'):
        handle_gender_selection(user_id, call, data)
    elif data == 'end_conversation':
        handle_end_conversation(user_id, call)
    else:
        bot.answer_callback_query(call.id, "Unknown action")

def handle_back_to_main(user_id, call):
    """Handle back to main menu action"""
    user_data = {
        'state': 'main_menu',
        'section': None,
        'role': None,
        'gender': None,
        'last_activity': datetime.now()
    }
    save_user(user_id, user_data)
    
    bot.edit_message_text(
        "Choose a section to continue:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=main_menu_keyboard()
    )

def handle_back_to_role(user_id, call):
    """Handle back to role selection action"""
    user_data = get_user(user_id)
    section = user_data.get('section')
    
    update_data = {
        'state': 'choosing_role',
        'gender': None,
        'last_activity': datetime.now()
    }
    save_user(user_id, update_data)
    
    bot.edit_message_text(
        "Choose your role:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=role_selection_keyboard(section)
    )

def handle_section_selection(user_id, call, data):
    """Handle section selection"""
    section = data.split('_')[1]
    
    update_data = {
        'state': 'choosing_role',
        'section': section,
        'last_activity': datetime.now()
    }
    save_user(user_id, update_data)
    
    bot.edit_message_text(
        "Choose your role:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=role_selection_keyboard(section)
    )

def handle_role_selection(user_id, call, data):
    """Handle role selection"""
    role = data.split('_')[1]
    
    user_data = get_user(user_id)
    section = user_data.get('section')
    
    update_data = {
        'role': role,
        'last_activity': datetime.now()
    }
    
    if section == 'listener_talker':
        update_data['state'] = 'choosing_gender'
        save_user(user_id, update_data)
        
        bot.edit_message_text(
            "Select your gender:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=gender_selection_keyboard()
        )
    else:
        # Mommy/Daddy section doesn't require gender
        update_data['state'] = 'waiting'
        update_data['gender'] = None
        save_user(user_id, update_data)
        
        bot.edit_message_text(
            "⏳ Searching for a match... Please wait.\n\n"
            "You can send messages now and they'll be delivered once you're matched!",
            call.message.chat.id,
            call.message.message_id
        )
        
        add_to_waiting_queue(user_id)
        matchmaking_queue.put(user_id)

def handle_gender_selection(user_id, call, data):
    """Handle gender selection"""
    gender = data.split('_')[1]
    
    update_data = {
        'gender': gender,
        'state': 'waiting',
        'last_activity': datetime.now()
    }
    save_user(user_id, update_data)
    
    bot.edit_message_text(
        "⏳ Searching for a match... Please wait.\n\n"
        "You can send messages now and they'll be delivered once you're matched!",
        call.message.chat.id,
        call.message.message_id
    )
    
    add_to_waiting_queue(user_id)
    matchmaking_queue.put(user_id)

def handle_end_conversation(user_id, call):
    """Handle end conversation action"""
    end_conversation(user_id)
    bot.answer_callback_query(call.id, "Conversation ended")

# ==================== MESSAGE HANDLING ====================
@bot.message_handler(func=lambda message: True, content_types=['text'])
def handle_message(message):
    """Handle all text messages"""
    user_id = message.from_user.id
    
    user_data = get_user(user_id)
    if not user_data:
        bot.send_message(user_id, "Please start the bot first with /start")
        return
    
    if user_data['state'] == 'in_conversation' and user_data['partner']:
        # Forward message to partner
        forward_message_to_partner(user_id, message.text)
    elif user_data['state'] == 'waiting':
        # Store message for later delivery
        if 'message_queue' not in user_data:
            user_data['message_queue'] = []
        user_data['message_queue'].append(message.text)
        save_user(user_id, user_data)
        bot.send_message(user_id, "💾 Message saved. It will be delivered when you're matched!")
    else:
        bot.send_message(user_id, "Please select a section and role first using /start")

# ==================== MATCHMAKING LOGIC ====================
def add_to_waiting_queue(user_id):
    """Add user to the appropriate waiting queue"""
    user_data = get_user(user_id)
    if not user_data:
        return
    
    if user_data['section'] == 'listener_talker':
        if user_id not in waiting_queues[user_data['role']][user_data['gender']]:
            waiting_queues[user_data['role']][user_data['gender']].append(user_id)
    else:
        if user_id not in waiting_queues[user_data['role']]:
            waiting_queues[user_data['role']].append(user_id)
    
    save_queue_state()

def remove_from_waiting_queue(user_id):
    """Remove user from waiting queue"""
    user_data = get_user(user_id)
    if not user_data:
        return
    
    if user_data['section'] == 'listener_talker':
        if user_id in waiting_queues[user_data['role']][user_data['gender']]:
            waiting_queues[user_data['role']][user_data['gender']].remove(user_id)
    else:
        if user_id in waiting_queues[user_data['role']]:
            waiting_queues[user_data['role']].remove(user_id)
    
    save_queue_state()

def try_to_match(user_id):
    """Try to find a match for the user"""
    user_data = get_user(user_id)
    if not user_data or user_data.get('state') != 'waiting':
        return False
    
    if user_data['section'] == 'listener_talker':
        # Find opposite role
        target_role = 'talker' if user_data['role'] == 'listener' else 'listener'
        
        # Try to match with same gender first
        if waiting_queues[target_role][user_data['gender']]:
            for partner_id in waiting_queues[target_role][user_data['gender']]:
                partner_data = get_user(partner_id)
                if (partner_id != user_id and partner_data and 
                    partner_data.get('state') == 'waiting'):
                    waiting_queues[target_role][user_data['gender']].remove(partner_id)
                    remove_from_waiting_queue(user_id)
                    create_conversation(user_id, partner_id)
                    return True
        
        # Try to match with opposite gender
        opposite_gender = 'female' if user_data['gender'] == 'male' else 'male'
        if waiting_queues[target_role][opposite_gender]:
            for partner_id in waiting_queues[target_role][opposite_gender]:
                partner_data = get_user(partner_id)
                if (partner_id != user_id and partner_data and 
                    partner_data.get('state') == 'waiting'):
                    waiting_queues[target_role][opposite_gender].remove(partner_id)
                    remove_from_waiting_queue(user_id)
                    create_conversation(user_id, partner_id)
                    return True
    else:
        # Mommy/Daddy section
        target_role = 'daddy' if user_data['role'] == 'mommy' else 'mommy'
        
        if waiting_queues[target_role]:
            for partner_id in waiting_queues[target_role]:
                partner_data = get_user(partner_id)
                if (partner_id != user_id and partner_data and 
                    partner_data.get('state') == 'waiting'):
                    waiting_queues[target_role].remove(partner_id)
                    remove_from_waiting_queue(user_id)
                    create_conversation(user_id, partner_id)
                    return True
    
    # If no match found, add back to queue for future matching
    add_to_waiting_queue(user_id)
    return False

def create_conversation(user1_id, user2_id):
    """Create a conversation between two users"""
    # Update user states
    update_data1 = {
        'state': 'in_conversation',
        'partner': user2_id,
        'last_activity': datetime.now()
    }
    update_data2 = {
        'state': 'in_conversation',
        'partner': user1_id,
        'last_activity': datetime.now()
    }
    save_user(user1_id, update_data1)
    save_user(user2_id, update_data2)
    
    # Save conversation to database
    save_conversation(user1_id, user2_id)
    
    # Notify both users
    notify_match(user1_id, user2_id)
    notify_match(user2_id, user1_id)
    
    # Deliver any queued messages
    deliver_queued_messages(user1_id, user2_id)
    deliver_queued_messages(user2_id, user1_id)

def notify_match(user_id, partner_id):
    """Notify user about the match"""
    partner_data = get_user(partner_id)
    if not partner_data:
        return
    
    user_data = get_user(user_id)
    if not user_data:
        return
    
    if user_data['section'] == 'listener_talker':
        role_text = "👂 Listener" if partner_data['role'] == 'listener' else "👄 Talker"
        gender_text = "♂️ Male" if partner_data['gender'] == 'male' else "♀️ Female"
        match_info = f"{role_text} | {gender_text}"
    else:
        role_text = "👩 Mommy" if partner_data['role'] == 'mommy' else "👨 Daddy"
        match_info = role_text
    
    try:
        bot.send_message(
            user_id,
            f"🎉 You've been matched with a partner!\n"
            f"📋 Partner info: {match_info}\n\n"
            f"💬 Start chatting now!\n"
            f"❌ Use /end to end the conversation",
            reply_markup=conversation_controls_keyboard()
        )
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")

def deliver_queued_messages(sender_id, receiver_id):
    """Deliver any queued messages from sender to receiver"""
    sender_data = get_user(sender_id)
    if not sender_data:
        return
    
    if 'message_queue' in sender_data and sender_data['message_queue']:
        try:
            bot.send_message(receiver_id, "📨 Messages received while you were matching:")
            for message in sender_data['message_queue']:
                bot.send_message(receiver_id, f"💬 {message}")
            # Clear message queue
            update_data = {'message_queue': []}
            save_user(sender_id, update_data)
        except Exception as e:
            logger.error(f"Error delivering queued messages: {e}")

def forward_message_to_partner(sender_id, message_text):
    """Forward a message to the partner"""
    sender_data = get_user(sender_id)
    if not sender_data or 'partner' not in sender_data:
        return
    
    partner_id = sender_data['partner']
    
    try:
        bot.send_message(partner_id, f"💬 {message_text}")
    except Exception as e:
        logger.error(f"Error sending message to partner: {e}")
        bot.send_message(sender_id, "❌ Failed to send message. Your partner may have left the conversation.")
        end_conversation(sender_id)

# ==================== CONVERSATION MANAGEMENT ====================
def end_conversation(user_id):
    """End the current conversation"""
    user_data = get_user(user_id)
    if not user_data or user_data.get('state') != 'in_conversation':
        return
    
    partner_id = user_data.get('partner')
    
    # Notify both users
    try:
        bot.send_message(user_id, "❌ Conversation ended. Returning to main menu.", reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.error(f"Error notifying user {user_id}: {e}")
    
    if partner_id:
        partner_data = get_user(partner_id)
        if partner_data:
            try:
                bot.send_message(partner_id, "❌ Your partner ended the conversation. Returning to main menu.", reply_markup=main_menu_keyboard())
            except Exception as e:
                logger.error(f"Error notifying partner {partner_id}: {e}")
            
            # Reset partner's state
            update_data = {
                'state': 'main_menu',
                'partner': None,
                'last_activity': datetime.now()
            }
            save_user(partner_id, update_data)
    
    # Mark conversation as ended in database
    end_conversation_in_db(user_id)
    
    # Reset user's state
    update_data = {
        'state': 'main_menu',
        'partner': None,
        'last_activity': datetime.now()
    }
    save_user(user_id, update_data)

def stop_searching(user_id):
    """Stop searching for a match"""
    user_data = get_user(user_id)
    if not user_data or user_data.get('state') != 'waiting':
        return
    
    remove_from_waiting_queue(user_id)
    
    update_data = {
        'state': 'main_menu',
        'last_activity': datetime.now()
    }
    save_user(user_id, update_data)
    
    bot.send_message(
        user_id,
        "⏹️ Search stopped. Returning to main menu.",
        reply_markup=main_menu_keyboard()
    )

# ==================== ERROR HANDLING ====================
@bot.message_handler(func=lambda message: True, content_types=['audio', 'video', 'document', 'photo', 'sticker'])
def handle_unsupported_content(message):
    """Handle unsupported content types"""
    bot.send_message(
        message.chat.id,
        "❌ This bot only supports text messages for now.\n"
        "Please send text messages only."
    )

# ==================== CLEANUP THREAD ====================
def cleanup_worker():
    """Background worker to clean up inactive users"""
    while True:
        try:
            time.sleep(300)  # Run every 5 minutes
            
            # Find users who haven't been active for more than 30 minutes
            cutoff_time = datetime.now() - timedelta(minutes=30)
            
            if users_collection:
                inactive_users = users_collection.find({
                    'last_activity': {'$lt': cutoff_time}
                })
                
                for user in inactive_users:
                    user_id = user['user_id']
                    
                    # Remove from waiting queues
                    if user.get('state') == 'waiting':
                        remove_from_waiting_queue(user_id)
                    
                    # End conversation if in one
                    if user.get('state') == 'in_conversation':
                        end_conversation(user_id)
                    
                    # Update state to inactive
                    users_collection.update_one(
                        {'user_id': user_id},
                        {'$set': {'state': 'inactive'}}
                    )
                    
                    logger.info(f"Marked user {user_id} as inactive due to inactivity")
        
        except Exception as e:
            logger.error(f"Error in cleanup worker: {e}")
            time.sleep(60)

# Start the cleanup thread
cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
cleanup_thread.start()

# ==================== MAIN EXECUTION ====================
if __name__ == '__main__':
    # Start the keep-alive server
    keep_alive()
    
    print("🤖 Starting Telegram Matchmaking Bot...")
    print("✅ Bot is ready and waiting for messages...")
    print("⚠️  Press Ctrl+C to stop the bot")
    
    try:
        bot.infinity_polling()
    except Exception as e:
        logger.error(f"Bot stopped with error: {e}")
        print(f"❌ Bot stopped with error: {e}")
