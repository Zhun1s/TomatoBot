import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    CallbackContext,
    ConversationHandler,
)
from pymongo import MongoClient
from bson.objectid import ObjectId
from aiogram import Bot

import time
import requests
import threading


from bson import ObjectId
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ConversationHandler
from telegram import ReplyKeyboardMarkup

import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

# SET UP LOGGING
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# MONGO DB SETUP
MONGO_URI = os.getenv("MONGO_URI")
TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "telegram_bot"

# COLLECTIONS
COLLECTIONS = {
    "users": "users",
    "tasks": "tasks",
    "pomodoro_sessions": "pomodoro_sessions",
    "user_settings": "user_settings",
    "statistics": "statistics",
}

client = MongoClient(MONGO_URI)
db = client[DB_NAME]

users_collection = db[COLLECTIONS["users"]]
tasks_collection = db[COLLECTIONS["tasks"]]
pomodoro_collection = db[COLLECTIONS["pomodoro_sessions"]]
settings_collection = db[COLLECTIONS["user_settings"]]
stats_collection = db[COLLECTIONS["statistics"]]

bot = Bot(token=TOKEN)

# CONVVERSATION STATES
(
    TITLE, DESCRIPTION, DUE_DATE,
    NUM_SESSIONS, WORK_TIME, BREAK_TIME,
    TASK_DONE, SETTING_VALUE,
    TASK_SELECTED, SESSION_SETUP
) = range(10)

# Global dictionary for active timers
active_timers = {}

def init_db():
    tasks_collection.create_index([("user_id", 1), ("due_date", 1)])
    pomodoro_collection.create_index([("user_id", 1), ("start_time", -1)])
    settings_collection.create_index("user_id", unique=True)
    stats_collection.create_index("user_id", unique=True)

init_db()

# BASIC FUNCTIONS
async def get_user_settings(user_id: int) -> dict:
    settings = settings_collection.find_one({"user_id": user_id})
    if not settings:
        default_settings = {
            "user_id": user_id,
            "notifications": True
        }
        settings_collection.insert_one(default_settings)
        return default_settings
    return settings

async def update_stats(user_id: int, field: str, value: int):
    stats_collection.update_one(
        {"user_id": user_id},
        {"$inc": {field: value}},
        upsert=True
    )

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the current conversation."""
    await update.message.reply_text("🚫 Operation cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

async def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    if not users_collection.find_one({"user_id": user.id}):
        users_collection.insert_one({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "joined_at": datetime.utcnow(),
        })
    
    await get_user_settings(user.id)
    if not stats_collection.find_one({"user_id": user.id}):
        stats_collection.insert_one({
            "user_id": user.id,
            "total_sessions": 0,
            "total_focus": 0,
            "completed_tasks": 0,
            "daily_sessions": 0,
            "last_updated": datetime.utcnow()
        })

    # BUTTONS
    keyboard = [
        ["/addtask", "/tasks"],
        ["/edit_task", "/done"],
        ["/completed_tasks", "/stats"],
        ["/settings", "/pomodoro"],
        ["/stop"]
    ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    await update.message.reply_text(
        "🎯 Task Manager with Pomodoro\n\n"
        "Choose a command below:",
        reply_markup=reply_markup
    )


# TASK ADDING
async def add_task(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text("Enter task title:")
    return TITLE

async def task_title(update: Update, context: CallbackContext) -> int:
    context.user_data["title"] = update.message.text
    await update.message.reply_text("Enter description (or /skip):")
    return DESCRIPTION

async def task_description(update: Update, context: CallbackContext) -> int:
    context.user_data["description"] = update.message.text
    await update.message.reply_text("Due date (YYYY-MM-DD):")
    return DUE_DATE

async def skip_description(update: Update, context: CallbackContext) -> int:
    context.user_data["description"] = ""
    await update.message.reply_text("Due date (YYYY-MM-DD):")
    return DUE_DATE

async def task_due_date(update: Update, context: CallbackContext) -> int:
    try:
        due_date = datetime.strptime(update.message.text, "%Y-%m-%d")
        task = {
            "user_id": update.message.from_user.id,
            "title": context.user_data["title"],
            "description": context.user_data["description"],
            "due_date": due_date,
            "status": "pending",
            "created_at": datetime.utcnow()
        }
        tasks_collection.insert_one(task)
        await update.message.reply_text("✅ Task added!")
    except ValueError:
        await update.message.reply_text("❌ Invalid date format!")
        return DUE_DATE
    context.user_data.clear()
    return ConversationHandler.END

async def list_tasks(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"})
    
    if tasks_collection.count_documents({"user_id": user_id, "status": "pending"}) == 0:
        await update.message.reply_text("You have no pending tasks.")
        return
    
    tasks_list = []
    for task in tasks:
        tasks_list.append(
            f"📌 {task['title']}\n"
            f"📝 {task.get('description', 'No description')}\n"
            f"📅 Due: {task['due_date'].strftime('%Y-%m-%d')}"
        )
    await update.message.reply_text("Your tasks:\n" + "\n\n".join(tasks_list))



SELECT_TASK, SELECT_FIELD, EDIT_FIELD = range(3)

# TASK EDITING
async def edit_task(update: Update, context: CallbackContext) -> int:
    """Send a list of tasks to select one for editing."""
    user_id = update.message.from_user.id
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"})

    if tasks_collection.count_documents({"user_id": user_id, "status": "pending"}) == 0:
        await update.message.reply_text("You have no pending tasks to edit.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(task["title"], callback_data=f"edit_{task['_id']}")] for task in tasks]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Select a task to edit:", reply_markup=reply_markup)
    return SELECT_TASK

async def select_task(update: Update, context: CallbackContext) -> int:
    """Store selected task ID and ask what to edit."""
    query = update.callback_query
    task_id = query.data.split("_")[1]
    context.user_data["task_id"] = task_id 

    keyboard = [
        [InlineKeyboardButton("✏ Title", callback_data="edit_title")],
        [InlineKeyboardButton("📝 Description", callback_data="edit_description")],
        [InlineKeyboardButton("📅 Due Date", callback_data="edit_due_date")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.answer()
    await query.edit_message_text("What do you want to edit?", reply_markup=reply_markup)
    return SELECT_FIELD

async def select_field(update: Update, context: CallbackContext) -> int:
    """Ask for new input based on the selected field."""
    query = update.callback_query
    field = query.data.split("_")[1]
    context.user_data["field"] = field 

    if field == "title":
        await query.edit_message_text("Enter the new title:")
    elif field == "description":
        await query.edit_message_text("Enter the new description:")
    elif field == "due_date":
        await query.edit_message_text("Enter the new due date (YYYY-MM-DD):")

    return EDIT_FIELD

async def edit_field(update: Update, context: CallbackContext) -> int:
    """Update the selected field in MongoDB."""
    task_id = context.user_data["task_id"]
    field = context.user_data["field"]
    new_value = update.message.text

    update_data = {}
    if field == "title":
        update_data["title"] = new_value
    elif field == "description":
        update_data["description"] = new_value
    elif field == "due_date":
        try:
            new_value = datetime.strptime(new_value, "%Y-%m-%d")
            update_data["due_date"] = new_value
        except ValueError:
            await update.message.reply_text("❌ Invalid date format! Please use YYYY-MM-DD.")
            return EDIT_FIELD

    tasks_collection.update_one({"_id": ObjectId(task_id)}, {"$set": update_data})
    await update.message.reply_text("✅ Task updated successfully!")

    return ConversationHandler.END

async def cancel_edit(update: Update, context: CallbackContext) -> int:
    """Cancel the editing process."""
    await update.message.reply_text("❌ Task editing canceled.")
    return ConversationHandler.END




#DONE TASKS

async def show_mark_done_tasks(update: Update, context: CallbackContext) -> None:
    """Handle the /done command."""
    user_id = update.message.from_user.id
    tasks = list(tasks_collection.find({"user_id": user_id, "status": "pending"}))  # Convert cursor to list

    if not tasks:
        await update.message.reply_text("You have no tasks to mark as done.")
        return

    keyboard = [[InlineKeyboardButton(task["title"], callback_data=f"done_{str(task['_id'])}")] for task in tasks]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Select a task to mark as done:", reply_markup=reply_markup)

async def mark_done_callback(update: Update, context: CallbackContext) -> None:
    """Handle the callback query for marking a task as done."""
    query = update.callback_query
    user_id = query.from_user.id
    task_id = query.data.split("_")[1]  

    try:
        task_object_id = ObjectId(task_id)
    except Exception as e:
        await query.answer("Invalid task ID.")
        return

    task = tasks_collection.find_one({"_id": task_object_id, "user_id": user_id})
    
    if not task:
        await query.answer("Task not found or already completed.")
        return

    tasks_collection.update_one({"_id": task_object_id}, {"$set": {"status": "completed"}})

    await query.answer("✅ Task marked as done!")
    await query.edit_message_text(f"✅ Task '{task['title']}' marked as done.")




# TASK HISTORY
async def show_completed_tasks(update: Update, context: CallbackContext) -> None:
    """Handle the /completed_tasks command."""
    user_id = update.message.from_user.id
    tasks = tasks_collection.find({"user_id": user_id, "status": "completed"})

    if tasks_collection.count_documents({"user_id": user_id, "status": "completed"}) == 0:
        await update.message.reply_text("You have no completed tasks.")
    else:
        tasks_list = []
        for task in tasks:
            tasks_list.append(
                f"✅ {task['title']}\n"
                f"📝 {task['description']}\n"
                f"📅 Due: {task['due_date'].strftime('%Y-%m-%d')}\n"
            )
        await update.message.reply_text("Your completed tasks:\n" + "\n".join(tasks_list))

# POMODORO SESSIONS
async def pomodoro(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    if user_id in active_timers:
        await update.message.reply_text("❗ You have an active session!")
        return ConversationHandler.END
    
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"})
    if tasks_collection.count_documents({"user_id": user_id, "status": "pending"}) == 0:
        await update.message.reply_text("❌ No pending tasks!")
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton(task["title"], callback_data=f"task_{task['_id']}")]
        for task in tasks
    ]
    await update.message.reply_text(
        "Select task for session:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return TASK_SELECTED

async def task_selected(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    await query.answer()
    task_id = query.data.split("_")[1]
    
    context.user_data["pomodoro_task"] = task_id
    await query.edit_message_text("How many Pomodoro sessions would you like to do?")
    return NUM_SESSIONS

async def get_num_sessions(update: Update, context: CallbackContext) -> int:
    try:
        num_sessions = int(update.message.text)
        if num_sessions < 1:
            raise ValueError
        context.user_data["num_sessions"] = num_sessions
        await update.message.reply_text("Enter work duration per session (minutes):")
        return WORK_TIME
    except ValueError:
        await update.message.reply_text("Please enter a valid number greater than 0")
        return NUM_SESSIONS

async def get_work_time(update: Update, context: CallbackContext) -> int:
    try:
        work_time = int(update.message.text)
        if work_time < 1:
            raise ValueError
        context.user_data["work_time"] = work_time
        await update.message.reply_text("Enter break duration between sessions (minutes):")
        return BREAK_TIME
    except ValueError:
        await update.message.reply_text("Please enter a valid number greater than 0")
        return WORK_TIME

async def get_break_time(update: Update, context: CallbackContext) -> int:
    try:
        break_time = int(update.message.text)
        if break_time < 1:
            raise ValueError
        
        context.user_data["break_time"] = break_time
        settings = context.user_data
        
        await update.message.reply_text(
            f"Starting {settings['num_sessions']} sessions\n"
            f"Work: {settings['work_time']}min\n"
            f"Break: {settings['break_time']}min\n"
            "Let's begin!"
        )
        
        return await start_pomodoro_session(update, context)
    except ValueError:
        await update.message.reply_text("Please enter a valid number greater than 0")
        return BREAK_TIME

async def start_pomodoro_session(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    settings = context.user_data
    task_id = settings["pomodoro_task"]
    
    session_data = {
        "start_time": datetime.utcnow(),
        "work_time": settings["work_time"],
        "break_time": settings["break_time"],
        "num_sessions": settings["num_sessions"],
        "sessions_completed": 0,
        "task_id": task_id,
        "active": True,
        "task": None
    }
    
    timer_task = asyncio.create_task(run_pomodoro_cycle(update, context, user_id))
    session_data["task"] = timer_task
    active_timers[user_id] = session_data
    
    return ConversationHandler.END

async def run_pomodoro_cycle(update: Update, context: CallbackContext, user_id: int):
    session_data = active_timers.get(user_id)
    if not session_data:
        return

    try:
        for session in range(session_data["num_sessions"]):
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"Session {session+1}/{session_data['num_sessions']} started! 🎯"
            )
            await asyncio.sleep(session_data["work_time"] * 60)
            
            if not active_timers.get(user_id):
                return
                
            session_data["sessions_completed"] += 1
            
            if session < session_data["num_sessions"] - 1:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"⏰ Break time! ({session_data['break_time']} minutes)"
                )
                await asyncio.sleep(session_data["break_time"] * 60)
                
                if not active_timers.get(user_id):
                    return
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="Back to work! 💪"
                )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🎉 All sessions completed!"
        )
        await ask_task_completion(update, context, user_id)
        
    except asyncio.CancelledError:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🛑 Session interrupted!"
        )

async def ask_task_completion(update: Update, context: CallbackContext, user_id: int):
    session_data = active_timers.get(user_id)
    if not session_data:
        return

    task_id = session_data["task_id"]
    task = tasks_collection.find_one({"_id": ObjectId(task_id)})
    
    keyboard = [
        [InlineKeyboardButton("Yes", callback_data="task_done_yes"),
         InlineKeyboardButton("No", callback_data="task_done_no")]
    ]
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Did you complete the task: {task['title']}?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def stop_pomodoro(update: Update, context: CallbackContext) -> None:
    """Stop an active Pomodoro session."""
    user_id = update.message.from_user.id
    session_data = active_timers.get(user_id)
    
    if not session_data:
        await update.message.reply_text("❌ No active session to stop!")
        return

    if session_data.get("task"):
        session_data["task"].cancel()
    
    pomodoro_collection.insert_one({
        "user_id": user_id,
        "task_id": ObjectId(session_data["task_id"]),
        "start_time": session_data["start_time"],
        "end_time": datetime.utcnow(),
        "work_duration": session_data["work_time"],
        "break_duration": session_data["break_time"],
        "sessions_completed": session_data["sessions_completed"],
        "total_sessions": session_data["num_sessions"],
        "completed": False
    })
    
    active_timers.pop(user_id, None)
    await update.message.reply_text("🛑 Session stopped. Progress saved!")

async def handle_task_completion(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    session_data = active_timers.get(user_id)
    
    if not session_data:
        await query.edit_message_text("Session data not found!")
        return

    task_id = session_data["task_id"]

    active_timers.pop(user_id, None)
    
    if query.data == "task_done_yes":
        tasks_collection.update_one(
            {"_id": ObjectId(task_id)},
            {"$set": {"status": "completed"}}
        )
        await query.edit_message_text("✅ Task marked as completed!")
        await update_stats(user_id, "completed_tasks", 1)
    else:
        await query.edit_message_text("Task remains pending. Keep working!")

    context.user_data.clear()

# USER STATS
async def show_stats(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    stats = stats_collection.find_one({"user_id": user_id})
    
    if not stats:
        await update.message.reply_text("No statistics available yet.")
        return
    
    message = (
        "📊 Your Productivity Stats:\n"
        f"🏋️ Total Pomodoro Sessions: {stats['total_sessions']}\n"
        f"⏱️ Total Focus Time: {stats['total_focus']} minutes\n"
        f"✅ Completed Tasks: {stats['completed_tasks']}\n"
        f"🔥 Today's Sessions: {stats['daily_sessions']}"
    )
    await update.message.reply_text(message)

# SETTINGS
async def show_settings(update: Update, context: CallbackContext) -> None:
    user_id = update.message.from_user.id
    settings = await get_user_settings(user_id) or {}  

    message = (
        "⚙️ Current Settings:\n"
        f"🔔 Notifications: {'Enabled' if settings.get('notifications', True) else 'Disabled'}"
    )
    
    keyboard = [
        [InlineKeyboardButton("Toggle Notifications", callback_data="toggle_notifications")]
    ]
    
    await update.message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def toggle_notifications(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    current_setting = await get_user_settings(user_id)
    new_value = not current_setting.get("notifications", True)  

    settings_collection.update_one(
        {"user_id": user_id},
        {"$set": {"notifications": new_value}},
        upsert=True
    )

    await query.edit_message_text(
        f"🔔 Notifications {'Enabled' if new_value else 'Disabled'}!"
    )


# NOTIFICATIONS
def send_telegram_message(user_id, task_name, due_time):
    message = f"🔔Reminder: Task '{task_name}' is due at {due_time}!"
    telegram_url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    params = {
        "chat_id": user_id,  
        "text": message
    }

    response = requests.post(telegram_url, params=params)
    if response.status_code == 200:
        print(f"Notification sent to {user_id}")
    else:
        print(f"Failed to send message: {response.text}")

def schedule_notifications():
    while True:
        try:
            print("Checking for upcoming tasks...")
            now = datetime.utcnow()
            upcoming_time = now + timedelta(minutes=2000) 

            tasks = tasks_collection.find({
                "due_date": {"$gte": now, "$lte": upcoming_time},  
                "status": "pending"  
            })

            for task in tasks:
                settings = settings_collection.find_one({"user_id": task["user_id"]})

                if settings and settings.get("notifications", False):  
                    user = users_collection.find_one({"user_id": task["user_id"]})
                    if user:
                        send_telegram_message(user["user_id"], task["title"], task["due_date"])
                else:
                    print(f"User {task['user_id']} has notifications disabled or settings not found")


        except Exception as e:
            print(f"Error in schedule_notifications: {e}")
        
        time.sleep(6000)


# MAIN
def main():
    application = Application.builder().token(TOKEN).build()
    
    # Task conversation handler
    task_handler = ConversationHandler(
        entry_points=[CommandHandler("addtask", add_task)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_title)],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_description),
                CommandHandler("skip", skip_description)
            ],
            DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_due_date)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    
    # Pomodoro conversation handler
    pomodoro_handler = ConversationHandler(
        entry_points=[CommandHandler("pomodoro", pomodoro)],
        states={
            TASK_SELECTED: [CallbackQueryHandler(task_selected, pattern="^task_")],
            NUM_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_num_sessions)],
            WORK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_work_time)],
            BREAK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_break_time)]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Add to ConversationHandler
    edit_task_handler = ConversationHandler(
        entry_points=[CommandHandler("edit_task", edit_task)],
        states={
            SELECT_TASK: [CallbackQueryHandler(select_task, pattern="^edit_")],
            SELECT_FIELD: [CallbackQueryHandler(select_field, pattern="^edit_(title|description|due_date)")],
            EDIT_FIELD: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_field)]
        },
        fallbacks=[CommandHandler("cancel", cancel_edit)]
    )

    # HANDLERS
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tasks", list_tasks))
    application.add_handler(CommandHandler("stats", show_stats))
    application.add_handler(CommandHandler("settings", show_settings))
    application.add_handler(CommandHandler("stop", stop_pomodoro))
    application.add_handler(task_handler)
    application.add_handler(CallbackQueryHandler(toggle_notifications, pattern="toggle_notifications"))

    application.add_handler(pomodoro_handler)
    application.add_handler(CallbackQueryHandler(handle_task_completion, pattern="^task_done_"))

    application.add_handler(CommandHandler("done", show_mark_done_tasks))
    application.add_handler(CallbackQueryHandler(mark_done_callback, pattern="^done_"))
    application.add_handler(CommandHandler("completed_tasks", show_completed_tasks))

    application.add_handler(edit_task_handler)


    application.run_polling()

if __name__ == "__main__":

    notification_thread = threading.Thread(target=schedule_notifications, daemon=True)
    notification_thread.start()

    main()