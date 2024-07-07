from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import os

load_dotenv()

TELEGRAM_APP_API_ID = int(os.getenv('TELEGRAM_APP_API_ID', ""))
TELEGRAM_APP_API_HASH = os.getenv('TELEGRAM_APP_API_HASH', "")

with TelegramClient(StringSession(), TELEGRAM_APP_API_ID, TELEGRAM_APP_API_HASH) as client:
    print(client.session.save())