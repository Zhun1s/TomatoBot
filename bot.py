import logging
import asyncio
from datetime import datetime
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

# Set up logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# MongoDB setup
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "telegram_bot"
TASKS_COLLECTION = "tasks"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
tasks_collection = db[TASKS_COLLECTION]
users_collection = db["users"]

TOKEN = "8157321442:AAGTK8QsY5WXFxsZhM53XWbwpYAXcKVLivU"

# Conversation states
TITLE, DESCRIPTION, DUE_DATE, NUM_SESSIONS, WORK_TIME, BREAK_TIME, TASK_DONE = range(7)

# Global dictionary to store active Pomodoro sessions
timer_tasks = {}

# Start command
async def start(update: Update, context: CallbackContext) -> None:
    """Handle the /start command."""
    logger.info("User started the bot.")
    user = update.message.from_user
    existing_user = users_collection.find_one({"user_id": user.id})

    if not existing_user:
        users_collection.insert_one({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "joined_at": datetime.utcnow(),
        })

    await update.message.reply_text(
        "📝 Task Manager Bot\n\n"
        "Available commands:\n"
        "/addtask - Create a new task\n"
        "/tasks - List all your tasks\n"
        "/done - Mark task as completed\n"
        "/completed_tasks - List all completed tasks\n"
        "/pomodoro - Start a Pomodoro session\n"
        "/stop_pomodoro - Stop an ongoing Pomodoro session"
    )

# Add task command
async def add_task(update: Update, context: CallbackContext) -> int:
    """Handle the /addtask command."""
    logger.info("User triggered /addtask.")
    await update.message.reply_text("Please enter the title of the task:")
    return TITLE

async def task_title(update: Update, context: CallbackContext) -> int:
    """Save the task title and ask for description."""
    context.user_data["title"] = update.message.text
    await update.message.reply_text("Please enter the description of the task (or /skip to skip):")
    return DESCRIPTION

async def task_description(update: Update, context: CallbackContext) -> int:
    """Save the task description and ask for due date."""
    context.user_data["description"] = update.message.text
    await update.message.reply_text("Please enter the due date (e.g., 2023-12-31):")
    return DUE_DATE

async def skip_description(update: Update, context: CallbackContext) -> int:
    """Skip the description and ask for due date."""
    context.user_data["description"] = ""
    await update.message.reply_text("Please enter the due date (e.g., 2023-12-31):")
    return DUE_DATE

async def task_due_date(update: Update, context: CallbackContext) -> int:
    """Save the due date and create the task."""
    due_date = update.message.text
    try:
        due_date = datetime.strptime(due_date, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD.")
        return DUE_DATE

    task = {
        "user_id": update.message.from_user.id,
        "title": context.user_data["title"],
        "description": context.user_data["description"],
        "due_date": due_date,
        "status": "pending",
        "created_at": datetime.utcnow(),
    }
    tasks_collection.insert_one(task)

    await update.message.reply_text("Task added successfully!")
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the conversation."""
    await update.message.reply_text("Operation canceled.")
    return ConversationHandler.END

# List tasks command
async def list_tasks(update: Update, context: CallbackContext) -> None:
    """Handle the /tasks command."""
    user_id = update.message.from_user.id
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"})

    if tasks_collection.count_documents({"user_id": user_id, "status": "pending"}) == 0:
        await update.message.reply_text("You have no pending tasks.")
    else:
        tasks_list = []
        for task in tasks:
            tasks_list.append(
                f"📌 {task['title']}\n"
                f"📝 {task['description']}\n"
                f"📅 Due: {task['due_date'].strftime('%Y-%m-%d')}\n"
            )
        await update.message.reply_text("Your tasks:\n" + "\n".join(tasks_list))

# Mark task as done command
async def show_mark_done_tasks(update: Update, context: CallbackContext) -> None:
    """Handle the /done command."""
    user_id = update.message.from_user.id
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"})

    if tasks_collection.count_documents({"user_id": user_id, "status": "pending"}) == 0:
        await update.message.reply_text("You have no tasks to mark as done.")
    else:
        keyboard = []
        for task in tasks:
            keyboard.append([InlineKeyboardButton(task["title"], callback_data=f"done_{task['_id']}")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Select a task to mark as done:", reply_markup=reply_markup)

async def mark_done_callback(update: Update, context: CallbackContext) -> None:
    """Handle the callback query for marking a task as done."""
    query = update.callback_query
    task_id = query.data.split("_")[1]
    tasks_collection.update_one({"_id": ObjectId(task_id)}, {"$set": {"status": "completed"}})
    await query.answer("Task marked as done!")
    await query.edit_message_text("Task marked as done.")

# Show completed tasks command
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

# Pomodoro command
async def pomodoro(update: Update, context: CallbackContext) -> int:
    """Start a Pomodoro session after selecting a task."""
    user_id = update.message.from_user.id

    if user_id in timer_tasks:
        await update.message.reply_text("You already have a Pomodoro session running!")
        return ConversationHandler.END

    # Show available tasks for the user to choose
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"}).sort("due_date", 1)

    if tasks_collection.count_documents({"user_id": user_id, "status": "pending"}) == 0:
        await update.message.reply_text("You have no pending tasks to choose from!")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"{task['title']} - {task['due_date'].strftime('%Y-%m-%d')}", callback_data=f"task_{task['_id']}")]
        for task in tasks
    ]
    keyboard.append([InlineKeyboardButton("Other", callback_data="other")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please choose a task for your Pomodoro session:", reply_markup=reply_markup)

    return TITLE

async def task_selected(update: Update, context: CallbackContext) -> int:
    """Handle task selection and start Pomodoro timer."""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split("_")[1] if query.data != "other" else None

    if task_id:
        task = tasks_collection.find_one({"_id": ObjectId(task_id), "user_id": query.from_user.id})
        context.user_data['selected_task'] = task
        await query.edit_message_text(f"Starting Pomodoro session for task: {task['title']}")
    else:
        await query.edit_message_text("You selected 'Other'. Please specify the task title:")
        return TITLE

    # Ask for Pomodoro session details
    await query.message.reply_text("How many Pomodoro sessions would you like to complete?")
    return NUM_SESSIONS

async def num_sessions(update: Update, context: CallbackContext) -> int:
    """Save the number of sessions and ask for work duration."""
    try:
        num_sessions = int(update.message.text)
        if num_sessions <= 0:
            raise ValueError
        context.user_data['num_sessions'] = num_sessions
        await update.message.reply_text("How many minutes will each work session last?")
        return WORK_TIME
    except ValueError:
        await update.message.reply_text("Please enter a valid number for sessions.")
        return NUM_SESSIONS

async def work_time(update: Update, context: CallbackContext) -> int:
    """Save work duration and ask for break duration."""
    try:
        work_time = int(update.message.text)
        if work_time <= 0:
            raise ValueError
        context.user_data['work_time'] = work_time
        await update.message.reply_text("How many minutes will each break session last?")
        return BREAK_TIME
    except ValueError:
        await update.message.reply_text("Please enter a valid number for work duration.")
        return WORK_TIME

# Добавим новую коллекцию для Pomodoro сессий
POMODORO_SESSIONS_COLLECTION = "pomodoro_sessions"
pomodoro_sessions_collection = db[POMODORO_SESSIONS_COLLECTION]

async def break_time(update: Update, context: CallbackContext) -> int:
    """Save break duration and start the Pomodoro timer."""
    try:
        break_time = int(update.message.text)
        if break_time <= 0:
            raise ValueError
        context.user_data['break_time'] = break_time
    except ValueError:
        await update.message.reply_text("Please enter a valid number for break duration.")
        return BREAK_TIME

    num_sessions = context.user_data['num_sessions']
    work_time = context.user_data['work_time']
    break_time = context.user_data['break_time']
    selected_task = context.user_data['selected_task']
    user_id = update.message.from_user.id

    await update.message.reply_text(
        f"⏳ Pomodoro started: {num_sessions} sessions, {work_time} min work, {break_time} min break."
    )
    timer_tasks[user_id] = True  # Store active timer

    # Perform the Pomodoro sessions
    for i in range(num_sessions):
        await update.message.reply_text(f"Starting session {i + 1}...")
        await asyncio.sleep(work_time * 60)
        if user_id in timer_tasks:
            await update.message.reply_text("⏰ Time's up! Take a break now.")
            await asyncio.sleep(break_time * 60)
        if user_id in timer_tasks:
            await update.message.reply_text("☕ Break over! Ready for the next session?")

    if user_id in timer_tasks:
        del timer_tasks[user_id]
        await update.message.reply_text("All sessions completed! Great job!")

        # Save the Pomodoro session to the database
        pomodoro_session = {
            "user_id": user_id,
            "task_id": selected_task['_id'],
            "num_sessions": num_sessions,
            "work_time": work_time,
            "break_time": break_time,
            "completed_at": datetime.utcnow(),
        }
        pomodoro_sessions_collection.insert_one(pomodoro_session)

        # Ask if task is done
        await update.message.reply_text(f"Did you complete the task: {selected_task['title']}? (Yes/No)")
        return TASK_DONE

    return ConversationHandler.END

async def task_done(update: Update, context: CallbackContext) -> int:
    """Mark task as done or leave it pending."""
    response = update.message.text.lower()

    if 'selected_task' not in context.user_data:
        await update.message.reply_text("No task selected for completion.")
        return ConversationHandler.END

    selected_task = context.user_data['selected_task']

    if response == "yes":
        tasks_collection.update_one(
            {"_id": ObjectId(selected_task['_id']), "user_id": update.message.from_user.id},
            {"$set": {"status": "completed"}}
        )
        await update.message.reply_text(f"✅ Task '{selected_task['title']}' marked as completed! Great job!")
    elif response == "no":
        await update.message.reply_text(f"❌ Task '{selected_task['title']}' left as pending. Keep working on it!")
    else:
        await update.message.reply_text("Please answer with 'Yes' or 'No'.")
        return TASK_DONE

    context.user_data.clear()
    return ConversationHandler.END


# Stop Pomodoro command
async def stop_pomodoro(update: Update, context: CallbackContext) -> None:
    """Stop an active Pomodoro session."""
    user_id = update.message.from_user.id
    if user_id in timer_tasks:
        del timer_tasks[user_id]
        await update.message.reply_text("🛑 Pomodoro session stopped.")
    else:
        await update.message.reply_text("You have no active Pomodoro sessions.")

# Main function
def main():
    """Start the bot."""
    app = Application.builder().token(TOKEN).build()

    # Add command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(CommandHandler("done", show_mark_done_tasks))
    app.add_handler(CommandHandler("completed_tasks", show_completed_tasks))
    app.add_handler(CommandHandler("stop_pomodoro", stop_pomodoro))

    # Add conversation handler for /addtask
    add_task_handler = ConversationHandler(
        entry_points=[CommandHandler("addtask", add_task)],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_title)],
            DESCRIPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, task_description),
                CommandHandler("skip", skip_description),
            ],
            DUE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_due_date)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(add_task_handler)

    # Add callback query handler for marking tasks as done
    app.add_handler(CallbackQueryHandler(mark_done_callback, pattern="^done_"))

    # Add Pomodoro conversation handler
    pomodoro_handler = ConversationHandler(
        entry_points=[CommandHandler("pomodoro", pomodoro)],
        states={
            TITLE: [CallbackQueryHandler(task_selected, pattern="^task_.*")],
            NUM_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, num_sessions)],
            WORK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, work_time)],
            BREAK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, break_time)],
            TASK_DONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, task_done)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(pomodoro_handler)

    # Log when the bot starts
    logger.info("Task Manager Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
