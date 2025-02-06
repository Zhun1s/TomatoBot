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

# MongoDB setup
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "telegram_bot"
TASKS_COLLECTION = "tasks"

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
tasks_collection = db[TASKS_COLLECTION]

TOKEN = "8157321442:AAGTK8QsY5WXFxsZhM53XWbwpYAXcKVLivU"

# Conversation states
TITLE, DESCRIPTION, DUE_DATE = range(3)

timer_tasks = {}

async def start(update: Update, context: CallbackContext) -> None:
    """Bot welcome message"""
    await update.message.reply_text(
        "📝 Task Manager Bot\n\n"
        "Available commands:\n"
        "/addtask - Create a new task\n"
        "/tasks - List all your tasks\n"
        "/done - Mark task as completed\n"
        "/delete - Delete a task\n"
        "/pomodoro <work_minutes> <break_minutes> - Start a Pomodoro session\n"
        "/stop_pomodoro - Stop an ongoing Pomodoro session"
    )

### ADD TASK FUNCTIONS ###
async def add_task(update: Update, context: CallbackContext) -> int:
    """Start task creation"""
    await update.message.reply_text("Please enter the task title:")
    return TITLE

async def task_title(update: Update, context: CallbackContext) -> int:
    """Save task title and ask for description"""
    context.user_data['title'] = update.message.text
    await update.message.reply_text("Enter task description (or /skip):")
    return DESCRIPTION

async def task_description(update: Update, context: CallbackContext) -> int:
    """Save task description and ask for due date"""
    context.user_data['description'] = update.message.text
    await update.message.reply_text("Enter due date (YYYY-MM-DD):")
    return DUE_DATE

async def skip_description(update: Update, context: CallbackContext) -> int:
    """Skip description step"""
    context.user_data['description'] = None
    await update.message.reply_text("Enter due date (YYYY-MM-DD):")
    return DUE_DATE

async def task_due_date(update: Update, context: CallbackContext) -> int:
    """Save task to database"""
    user_data = context.user_data
    try:
        due_date = datetime.strptime(update.message.text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Invalid date format. Please use YYYY-MM-DD")
        return DUE_DATE

    task = {
        "user_id": update.message.from_user.id,
        "title": user_data['title'],
        "description": user_data.get('description'),
        "due_date": due_date,
        "created_at": datetime.now(),
        "status": "pending"
    }
    
    tasks_collection.insert_one(task)
    await update.message.reply_text("✅ Task added successfully!")
    
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel task creation"""
    context.user_data.clear()
    await update.message.reply_text("Task creation cancelled.")
    return ConversationHandler.END

### LIST TASKS FUNCTION ###
async def list_tasks(update: Update, context: CallbackContext) -> None:
    """Show tasks (no buttons, just listing)"""
    user_id = update.message.from_user.id
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"}).sort("due_date", 1)

    if not tasks:
        await update.message.reply_text("You have no pending tasks!")
    else:
        message = "📋 Your tasks:\n"
        for task in tasks:
            message += f"- {task['title']} (Due: {task['due_date'].strftime('%Y-%m-%d')})\n"
        await update.message.reply_text(message)

### SHOW TASKS WITH BUTTONS FOR MARKING DONE ###
async def show_mark_done_tasks(update: Update, context: CallbackContext) -> None:
    """Show tasks with inline buttons to mark as done"""
    user_id = update.message.from_user.id
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"}).sort("due_date", 1)

    keyboard = []
    for task in tasks:
        button = InlineKeyboardButton(
            f"{task['title']} - {task['due_date'].strftime('%Y-%m-%d')}",
            callback_data=f"done_{task['_id']}"
        )
        keyboard.append([button])

    if not keyboard:
        await update.message.reply_text("You have no pending tasks to mark as done!")
    else:
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("✅ Select a task to mark as completed:", reply_markup=reply_markup)

### MARK TASK AS DONE ###
async def mark_done_callback(update: Update, context: CallbackContext) -> None:
    """Mark a task as completed from inline button"""
    query = update.callback_query
    await query.answer()

    task_id = query.data.split("_")[1]
    user_id = query.from_user.id

    result = tasks_collection.update_one(
        {"_id": ObjectId(task_id), "user_id": user_id},
        {"$set": {"status": "completed"}}
    )

    if result.modified_count:
        await query.edit_message_text("✅ Task marked as completed!")
    else:
        await query.edit_message_text("⚠️ Task not found or already completed.")

### DELETE TASK FUNCTION ###
async def delete_task(update: Update, context: CallbackContext) -> None:
    """Delete a task"""
    try:
        task_id = context.args[0]
        result = tasks_collection.delete_one(
            {"_id": ObjectId(task_id), "user_id": update.message.from_user.id}
        )
        if result.deleted_count:
            await update.message.reply_text("Task deleted successfully!")
        else:
            await update.message.reply_text("Task not found.")
    except (IndexError, ValueError):
        await update.message.reply_text("Please provide a valid task ID.\nUsage: /delete <task_id>")

### POMODORO TIMER ###
NUM_SESSIONS, WORK_TIME, BREAK_TIME = range(3, 6)

async def pomodoro(update: Update, context: CallbackContext) -> int:
    """Start a Pomodoro session."""
    global timer_tasks  # Declare timer_tasks as global
    user_id = update.message.from_user.id

    if user_id in timer_tasks:
        await update.message.reply_text("You already have a Pomodoro session running!")
        return

    # Ask for number of sessions
    await update.message.reply_text("How many Pomodoro sessions would you like to complete?")
    return NUM_SESSIONS

async def num_sessions(update: Update, context: CallbackContext) -> int:
    """Save the number of sessions and ask for work duration"""
    try:
        num_sessions = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number for sessions.")
        return NUM_SESSIONS

    context.user_data['num_sessions'] = num_sessions
    await update.message.reply_text("How many minutes will each work session last?")
    return WORK_TIME

async def work_time(update: Update, context: CallbackContext) -> int:
    """Save work duration and ask for break duration"""
    try:
        work_time = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number for work duration.")
        return WORK_TIME

    context.user_data['work_time'] = work_time
    await update.message.reply_text("How many minutes will each break session last?")
    return BREAK_TIME

async def break_time(update: Update, context: CallbackContext) -> int:
    """Save break duration and start the Pomodoro timer"""
    try:
        break_time = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number for break duration.")
        return BREAK_TIME

    context.user_data['break_time'] = break_time
    num_sessions = context.user_data['num_sessions']
    work_time = context.user_data['work_time']
    break_time = context.user_data['break_time']

    user_id = update.message.from_user.id  # Define user_id here

    await update.message.reply_text(f"🔔 Pomodoro started: {num_sessions} sessions, {work_time} min work, {break_time} min break.")
    timer_tasks[user_id] = True  # Store active timer
    
    # Perform the Pomodoro sessions
    for i in range(num_sessions):
        await update.message.reply_text(f"Starting session {i + 1}...")
        await asyncio.sleep(work_time * 60)
        if user_id in timer_tasks:
            await update.message.reply_text("⏳ Time's up! Take a break now.")
            await asyncio.sleep(break_time * 60)
        if user_id in timer_tasks:
            await update.message.reply_text("🚀 Break over! Ready for the next session?")
    
    if user_id in timer_tasks:
        del timer_tasks[user_id]
        await update.message.reply_text("All sessions completed! Great job!")
    
    return ConversationHandler.END


# ConversationHandler for Pomodoro
pomodoro_handler = ConversationHandler(
    entry_points=[CommandHandler("pomodoro", pomodoro)],
    states={
        NUM_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, num_sessions)],
        WORK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, work_time)],
        BREAK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, break_time)],
    },
    fallbacks=[],
)



async def stop_pomodoro(update: Update, context: CallbackContext) -> None:
    """Stop an active Pomodoro session."""
    global timer_tasks  # Declare timer_tasks as global
    user_id = update.message.from_user.id
    if user_id in timer_tasks:
        del timer_tasks[user_id]
        await update.message.reply_text("🛑 Pomodoro session stopped.")
    else:
        await update.message.reply_text("You have no active Pomodoro sessions.")

### BOT SETUP ###
def main():
    """Bot entry point"""
    app = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
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

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    app.add_handler(pomodoro_handler)  # Add pomodoro handler
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(CommandHandler("done", show_mark_done_tasks))
    app.add_handler(CallbackQueryHandler(mark_done_callback, pattern="^done_"))
    app.add_handler(CommandHandler("delete", delete_task))
    app.add_handler(CommandHandler("stop_pomodoro", stop_pomodoro))

    print("Task Manager Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
