import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext
from pymongo import MongoClient

# Replace with your actual MongoDB connection string
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "telegram_bot"
COLLECTION_NAME = "messages"

# Connect to MongoDB
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

TOKEN = "8157321442:AAGTK8QsY5WXFxsZhM53XWbwpYAXcKVLivU"

async def start(update: Update, context: CallbackContext) -> None:
    user = update.message.from_user
    collection.update_one(
        {"user_id": user.id},
        {"$set": {"username": user.username, "first_name": user.first_name}},
        upsert=True,
    )
    await update.message.reply_text("Hello! I'm your bot. How can I help you?")

async def echo(update: Update, context: CallbackContext) -> None:
    user_message = update.message.text
    user = update.message.from_user

    # Store message in MongoDB
    collection.insert_one({
        "user_id": user.id,
        "username": user.username,
        "message": user_message
    })

    await update.message.reply_text(f"You said: {user_message}")

def main():
    app = Application.builder().token(TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, echo))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
