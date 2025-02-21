# Telegram Task Manager Bot

A Telegram bot that helps users manage tasks, track progress, and use the Pomodoro technique for productivity.

## Features
✅ Add, edit, and delete tasks  
✅ Track completed tasks  
✅ Pomodoro timer for focus sessions  
✅ User statistics and productivity tracking  
✅ Configurable settings and notifications  

## Tech Stack
- **Python** (asyncio, aiogram, python-telegram-bot)
- **MongoDB** (Atlas for database storage)
- **Telegram Bot API**

## Setup & Installation

### 1. Clone the Repository
```sh
git clone https://github.com/Zhun1s/TomatoBot.git
cd TomatoBot
```

### 2. Create a Virtual Environment (Optional)
```sh
python -m venv venv
source venv/bin/activate 
```

### 3. Install Dependencies
```sh
pip install -r requirements.txt
```

### 4. Create a `.env` File
Create a `.env` file in the project root and add the following:
```ini
MONGO_URI=mongodb+srv://yourusername:yourpassword@yourcluster.mongodb.net/?retryWrites=true&w=majority
BOT_TOKEN=your_telegram_bot_token
```

### 5. Run the Bot
```sh
python bot.py
```

## Security Measures
✅ **Environment Variables** for sensitive credentials  
✅ **.gitignore** configured to exclude `.env`  
✅ **GitHub Secrets** for deployment  

## Contributing
1. Fork the repository
2. Create a feature branch (`git checkout -b feature-name`)
3. Commit changes (`git commit -m 'Added new feature'`)
4. Push to branch (`git push origin feature-name`)
5. Open a pull request

## License
This project is licensed under the **MIT License**.

## Contact
For questions or suggestions, reach out via Telegram or open an issue on GitHub.

---
🚀 **Boost your productivity with the Tomato Bot!**

