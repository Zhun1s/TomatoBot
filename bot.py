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
users_collection = db["users"]

TOKEN = "8157321442:AAGTK8QsY5WXFxsZhM53XWbwpYAXcKVLivU"

# Conversation states
TITLE, DESCRIPTION, DUE_DATE = range(3)

timer_tasks = {}

async def start(update: Update, context: CallbackContext) -> None:
    """Register user and send a welcome message"""
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
        "/pomodoro <work_minutes> <break_minutes> - Start a Pomodoro session\n"
        "/stop_pomodoro - Stop an ongoing Pomodoro session"
    )



### REGISTER USERS ###
async def register_user_message(update: Update, context: CallbackContext) -> None:
    """Register a user when they send any message"""
    user = update.message.from_user

    if not users_collection.find_one({"user_id": user.id}):
        users_collection.insert_one({
            "user_id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "joined_at": datetime.utcnow(),
        })




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

async def show_completed_tasks(update: Update, context: CallbackContext) -> None:
    """Show completed tasks from the database"""
    user_id = update.message.from_user.id
    completed_tasks = tasks_collection.find({"user_id": user_id, "status": "completed"}).sort("due_date", 1)

    tasks_list = list(completed_tasks)  # Convert cursor to list to check if empty

    if not tasks_list:
        await update.message.reply_text("✅ You have no completed tasks!")
        return

    message = "✅ **Completed Tasks:**\n"
    for task in tasks_list:
        message += f"- {task['title']}\n"

    await update.message.reply_text(message)





### POMODORO TIMER ###
NUM_SESSIONS, WORK_TIME, BREAK_TIME = range(3, 6)

async def pomodoro(update: Update, context: CallbackContext) -> int:
    """Start a Pomodoro session after selecting a task."""
    global timer_tasks  # Declare timer_tasks as global
    user_id = update.message.from_user.id

    if user_id in timer_tasks:
        await update.message.reply_text("You already have a Pomodoro session running!")
        return

    # Show available tasks for the user to choose
    tasks = tasks_collection.find({"user_id": user_id, "status": "pending"}).sort("due_date", 1)

    if not tasks:
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
        task = tasks_collection.find_one({"_id": ObjectId(task_id), "user_id": update.message.from_user.id})
        context.user_data['selected_task'] = task
        await query.edit_message_text(f"Starting Pomodoro session for task: {task['title']}")
    else:
        await query.edit_message_text("You selected 'Other'. Please specify the task title:")
        return TITLE

    # Ask for Pomodoro session details
    await query.message.reply_text("How many Pomodoro sessions would you like to complete?")
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
    selected_task = context.user_data['selected_task']

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

        # Ask if task is done
        await update.message.reply_text(f"Did you complete the task: {selected_task['title']}? (Yes/No)")
        return "task_done"
    
    return ConversationHandler.END

async def task_done(update: Update, context: CallbackContext) -> int:
    """Mark task as done or leave it pending"""
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
        await update.message.reply_text(f"✅ Task '{selected_task['title']}' marked as completed!")
    else:
        await update.message.reply_text(f"❌ Task '{selected_task['title']}' left as pending.")

    context.user_data.clear()
    return ConversationHandler.END


# Modify conversation handler to include new task-related steps
pomodoro_handler = ConversationHandler(
    entry_points=[CommandHandler("pomodoro", pomodoro)],
    states={
        TITLE: [CallbackQueryHandler(task_selected, pattern="^task_.*")],
        NUM_SESSIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, num_sessions)],
        WORK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, work_time)],
        BREAK_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, break_time)],
        "task_done": [MessageHandler(filters.TEXT & ~filters.COMMAND, task_done)],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
)





async def stop_pomodoro(update: Update, context: CallbackContext) -> None:
    """Stop an active Pomodoro session."""
    global timer_tasks  
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
    app.add_handler(MessageHandler(filters.ALL, register_user_message))
    app.add_handler(pomodoro_handler)
    app.add_handler(CommandHandler("tasks", list_tasks))
    app.add_handler(CommandHandler("done", show_mark_done_tasks))
    app.add_handler(CallbackQueryHandler(mark_done_callback, pattern="^done_"))
    app.add_handler(CommandHandler("completed_tasks", show_completed_tasks))
    app.add_handler(CommandHandler("stop_pomodoro", stop_pomodoro))

    app.add_handler(conv_handler)

    print("Task Manager Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
