import html
import json
import logging
import os
import re
import sys
import traceback
from datetime import datetime, timedelta
# import openai
from sys import stdout
from unicodedata import normalize

import pytz
from completion.claude_completion_service import ClaudeCompletionService
from completion.completion_service import CompletionService
from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (Application, ApplicationBuilder, CommandHandler,
                          ContextTypes)
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

TELEGRAM_APP_API_ID = int(os.getenv('TELEGRAM_APP_API_ID', ""))
TELEGRAM_APP_API_HASH = os.getenv('TELEGRAM_APP_API_HASH', "")
TELEGRAM_BOT_API_TOKEN = os.getenv('TELEGRAM_BOT_API_TOKEN', "")
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', "")
CLAUDE_API_KEY = os.getenv('CLAUDE_API_KEY', "")
DEVELOPER_CHAT_ID = int(os.getenv('DEVELOPER_CHAT_ID', ""))
TELEGRAM_STRING_SESSION = os.getenv('TELEGRAM_STRING_SESSION', "")
LANGUAGE = os.getenv('LANGUAGE', 'ru')  # По умолчанию используется русский язык

dialog_id = 0

# Set up logger
logger = logging.getLogger(__name__)
handler = logging.StreamHandler(stdout)
formatter = logging.Formatter(
    '%(asctime)s [%(levelname)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.INFO)

# Init Application
app = ApplicationBuilder().token(TELEGRAM_BOT_API_TOKEN).build()

# Init telegram client
client = TelegramClient(
    StringSession(TELEGRAM_STRING_SESSION),
    TELEGRAM_APP_API_ID,
    TELEGRAM_APP_API_HASH)
app = Application.builder().token(TELEGRAM_BOT_API_TOKEN).build()


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a welcome message when the command /start is issued."""
    logger.info("GET - /start")
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='Hi! I am a summary bot. '
                                        'Invite me into your group and '
                                        'I will summarize them for you.')


async def help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message when the command /help is issued."""
    logger.info("GET - /help")
    await context.bot.send_message(chat_id=update.effective_chat.id,
                                   text='Following command are available'
                                        ': \n /start - Start the bot \n '
                                        '/help - Show this help message \n '
                                        '/echo [MESSAGE] - Echo the user message \n '
                                        '/show_chats - Show all chats the bot '
                                        'is currently in \n '
                                        '/set_chat_name [CHAT NAME] -'
                                        ' Set the chat name for the bot \n '
                                        '/summary - Summarize the chat')


async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Echo the user message."""
    logger.info("GET - /echo")

    if len(context.args) == 0:
        await update.effective_message.reply_text(text="echo command requires a message")
        return
    await update.effective_message.reply_text(text=context.args[0])


async def show_chats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all chats the bot is currently in."""
    logger.info("GET - /show_chats")
    await update.effective_message.reply_text(text=f"Current Chat: {update.effective_chat.id}")


async def set_chat_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set the chat name or ID for the bot."""
    logger.info("GET - /set_chat_name")

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("User is not authorized. Please check your session string.")
            await update.effective_message.reply_text("Error: Bot is not authorized. "
                                                      "Please check the session string.")
            return

        if len(context.args) == 0:
            await update.effective_message.reply_text(text="Please provide a chat name or ID")
            return

        target = " ".join(context.args)
        logger.info(f"Target: {target}")

        dialog_found = False
        async for dialog in client.iter_dialogs():
            if dialog.title == target or str(dialog.id) == target:
                global dialog_id
                dialog_id = dialog.id
                logger.info(f"Set dialog ID as: {dialog_id}")
                dialog_found = True
                await update.effective_message.reply_text(f"Chat set to: {dialog.title} "
                                                          f"(ID: {dialog.id})")
                break

        if not dialog_found:
            await update.effective_message.reply_text(f"Chat '{target}' not found.")

    except Exception as e:
        logger.error(f"Error setting chat: {e}")
        await update.effective_message.reply_text(f"Error setting chat: {str(e)}")
    finally:
        await client.disconnect()


# Добавьте эту функцию для отладки
async def list_dialogs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all available dialogs."""
    logger.info("GET - /list_dialogs")

    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("User is not authorized. Please check your session string.")
            await update.effective_message.reply_text("Error: Bot is not authorized. "
                                                      "Please check the session string.")
            return

        dialogs = []
        async for dialog in client.iter_dialogs():
            dialogs.append(f"{dialog.title} (ID: {dialog.id})")

        if dialogs:
            await update.effective_message.reply_text(
                # Ограничим вывод первыми 10 чатами
                "Available chats:\n" + "\n".join(dialogs[:10]))
        else:
            await update.effective_message.reply_text("No chats found.")

    except Exception as e:
        logger.error(f"Error listing dialogs: {e}")
        await update.effective_message.reply_text(f"Error listing dialogs: {str(e)}")
    finally:
        await client.disconnect()


async def get_messages_from_telegram_api():
    """Retrieve all messages from Telegram API within last 24 hours."""
    logger.info(f"Starting to retrieve messages for dialog_id: {dialog_id}")
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error("User is not authorized in get_messages_from_telegram_api.")
            return []

        recent_messages = []
        tz = pytz.timezone('UTC')
        daily_time_filter = datetime.now().astimezone(tz) - timedelta(days=1)
        logger.info(f"Fetching messages since: {daily_time_filter}")

        message_count = 0
        async for message in client.iter_messages(dialog_id):
            message_count += 1
            if message_count % 10 == 0:
                logger.info(f"Processed {message_count} messages")

            if message.date >= daily_time_filter:
                if message.text:
                    channel_to_parse = None
                    if hasattr(message.peer_id, 'channel_id'):
                        channel_to_parse = message.peer_id.channel_id
                        logger.info(f"Channel ID: {channel_to_parse}")
                        if str(channel_to_parse).startswith('-100'):
                            channel_to_parse = str(channel_to_parse)[4:]
                        logger.info(f"Channel ID after removing prefix: {channel_to_parse}")
                    recent_messages.append({
                        'msg_id': message.id,
                        'sender': message.sender_id,
                        'reply_to_msg_id': message.reply_to_msg_id,
                        'msg': message.text,
                        # 'channel_id': channel_to_parse,
                    })
            else:
                logger.info(f"Reached message older than 24 hours. "
                            f"Total messages processed: {message_count}")
                break

        logger.info(f"Retrieved {len(recent_messages)} messages")
        return recent_messages

    except Exception as e:
        logger.error(f"Error retrieving messages from Telegram API: {e}")
        return []
    finally:
        await client.disconnect()


# remove whitespace character from message


def remove_whitespace(message):
    message_with_half_width = normalize('NFKC', message)
    clean_msg = re.sub(r"[\s。，]+", " ", message_with_half_width).strip()
    return clean_msg


def summarize_messages(dialog_id, chat_messages, completion_service):
    """Summarize list of text messages using AI service."""

    try:
        if LANGUAGE == "ru":
            instruction = f"""
Ваша задача - извлечь ключевые моменты из разговора в чате Telegram.

ID_CHAT = {str(dialog_id)[4:] if str(dialog_id).startswith('-100') else str(dialog_id)}.

Из приведенной ниже беседы, разделенной тройными кавычками,
сообщения представлены в формате CSV, каждая строка - это отдельное сообщение.
Сообщения могут быть на любом языке.
Первый столбец - это msg_id, второй столбец - id отправителя,
третий столбец - id сообщения, на которое отвечают
(будет пустым, если это не ответ на другое сообщение),
четвертый столбец - содержание сообщения.
Пожалуйста, суммируйте сообщения в виде нескольких ключевых моментов
1-2 предоложения на русском языке, каждый момент в следующем формате:
<подходящий emoji> <название_темы> (https://t.me/c/<ID_CHAT>/<msg_id>).<пустая строка>
Каждое название_темы должно быть в пределах 1-2 предложений и изложено понятно.
"""
        else:
            instruction = """
Your task is to extract key points from a conversation in a Telegram chat room.

ID_CHAT = {str(dialog_id)[4:] if str(dialog_id).startswith('-100') else str(dialog_id)}.

From the conversation below, delimited by triple quotes,
messages are in CSV format, each row is a message.
Messages can be in any language.
The first column is the msg_id, the second column is the sender id,
the third column is the reply message id (will be empty if it doesn't quote and reply to anyone),
the fourth column is the message content, and the fifth column is the channel_id.
Please summarize the messages into a few key points (1-2 sentences) in English,
each point in the following format:
<appropriate emoji> <topic_name> (https://t.me/c/<ID_CHAT>/<msg_id>). <empty line>
Each topic_name must be within 1-2 sentences and should be clearly stated.
"""

        messages = f"""
{instruction}

Conversation: ```{chat_messages}```
"""

        # Combine chat_messages into single string
        chats_content = ""
        for chat in chat_messages:
            if chat['msg'] is None:
                continue
            # channel_id = chat['channel_id']
            if chat['reply_to_msg_id'] is None:
                chats_content += \
                    f"{chat['msg_id']},{chat['sender']},,{remove_whitespace(chat['msg'])}\n"
            else:
                chats_content += \
                    (f"{chat['msg_id']},{chat['sender']},{chat['reply_to_msg_id']},"
                     f"{remove_whitespace(chat['msg'])}\n")

        # Get result from AI
        logger.info(f"Messages to summarize: {messages}")
        result = completion_service.get_completion(messages=messages)
        logger.info(f"Summarized messages: {result}")
        return result

    except Exception as e:
        logging.error(f"Error summarizing messages: {e}")
        traceback.print_exc(file=sys.stdout)
        return (f"Произошла ошибка при суммаризации сообщений: "
                f"{str(e)}") if LANGUAGE == "ru" else (f"An error occurred while "
                                                       f"summarizing messages: {str(e)}")


async def summarize(update, context, completion_service: CompletionService):
    """Retrieve and send back stored key points."""
    logger.info("Starting summarize function")

    if dialog_id == 0:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="Please set chat name first."
        )
        return

    try:
        logger.info("Attempting to retrieve messages")
        result = await get_messages_from_telegram_api()
        logger.info(f"Retrieved {len(result)} messages")

        if not result:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="No messages found to summarize."
            )
            return

        logger.info("Starting message summarization")
        summarized_text_list = summarize_messages(
            dialog_id=dialog_id, chat_messages=result, completion_service=completion_service)
        logger.info("Summarization completed")

        await context.bot.send_message(chat_id=update.effective_chat.id, text=summarized_text_list)
        logger.info("Summary sent to user")

    except Exception as e:
        logger.error(f"Error in summarize function: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id,
                                       text=f"An error occurred while summarizing: {str(e)}")


# From
# https://github.com/python-telegram-bot/python-telegram-bot/blob/master/examples/errorhandlerbot.py
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    # Log the error before we do anything else, so we can see it even if something breaks.
    logger.error("Exception while handling an update:", exc_info=context.error)

    # traceback.format_exception returns the usual python message about an exception, but as a
    # list of strings rather than a single string, so we have to join them together.
    tb_list = traceback.format_exception(
        None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    # Build the message with some markup and additional information about what happened.
    # You might need to add some logic to deal with messages longer than the 4096 character limit.
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
        "</pre>\n\n"
        f"<pre>context.chat_data = {html.escape(str(context.chat_data))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )

    # Finally, send the message to developer channel
    await context.bot.send_message(
        chat_id=DEVELOPER_CHAT_ID, text=message, parse_mode=ParseMode.HTML
    )


if __name__ == '__main__':
    # Inject dependencies for completion service
    completion_service = ClaudeCompletionService(
        api_key=CLAUDE_API_KEY, predefined_context="")

    # Add handlers
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('help', help))
    app.add_handler(
        CommandHandler(
            'summary',
            lambda update,
            context: summarize(
                update,
                context,
                completion_service
            )
        )
    )
    app.add_handler(CommandHandler('set_chat_name', set_chat_name))
    app.add_handler(CommandHandler('show_chats', show_chats))
    app.add_handler(CommandHandler('echo', echo))
    app.add_handler(CommandHandler('list_dialogs', list_dialogs))

    # app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), echo))
    app.add_error_handler(error_handler)

    app.run_polling()
