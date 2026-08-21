import json
import os
import gspread
from google.oauth2.service_account import Credentials
import random
import string
import time
from google import genai  # Оставляем только новый пакет
import requests
import telebot
from telebot import types
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

# Безопасно подтягиваем все ключи из переменных окружения Render
TOKEN = os.environ.get("BOT_TOKEN")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "oiyres2026")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Настройка Google Таблиц
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_file('credentials.json', scopes=scope)
sheets_client = gspread.authorize(creds)  # Назвали отдельно для таблиц

sheet = sheets_client.open("BotDB").sheet1

# Инициализируем клиент Google GenAI отдельным именем
# Стало:
client = genai.Client(api_key=GEMINI_API_KEY)

bot = telebot.TeleBot(TOKEN, threaded=True)
DB_FILE = "database.json"

# Игровые стейты и состояния ввода
active_games = {}
tic_tac_toe_boards = {}
hangman_games = {}
quiz_games = {}

# --- БАЗА ДАННЫХ ---
def load_db():
    try:
        rows = sheet.get_all_records()
        # Превращаем список из таблицы в наш словарь для работы бота
        # Мы храним данные в формате: chat_id | username | pro | lang | notes
        db = {}
        for row in rows:
            cid = str(row['chat_id'])
            db[cid] = {
                "username": row['username'],
                "pro": bool(row['pro']),
                "lang": row['lang'],
                "notes": json.loads(row['notes'].replace("'", '"')) if row['notes'] else []
            }
        return db
    except:
        return {}

def save_db(db):
    try:
        sheet.clear()
        sheet.append_row(["chat_id", "username", "pro", "lang", "notes"])
        for cid, data in db.items():
            sheet.append_row([cid, data['username'], data['pro'], data['lang'], str(data['notes'])])
    except Exception as e:
        print(f"Ошибка сохранения: {e}")

db = load_db()

# --- СБРОС ВСЕХ СОСТОЯНИЙ (Исправление зависаний) ---
def reset_user_states(chat_id):
    chat_id_int = int(chat_id)
    chat_id_str = str(chat_id)
    hangman_games.pop(chat_id_int, None)
    active_games.pop(chat_id_str, None)
    tic_tac_toe_boards.pop(chat_id_int, None)
    quiz_games.pop(chat_id_int, None)

# --- ГЛАВНЫЕ МЕНЮ ---
def get_main_menu(lang="ru", is_pro=False):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    if lang == "ru":
        markup.add(
            types.KeyboardButton("🌤 Погода"),
            types.KeyboardButton("🧮 Калькулятор"),
            types.KeyboardButton("📝 Блокнот"),
            types.KeyboardButton("🎮 Все игры (16 шт)"),
            types.KeyboardButton("🛠 Утилиты"),
            types.KeyboardButton("🤖 О боте"),
            types.KeyboardButton("🇷🇺 Язык")
        )
        if is_pro:
            markup.add(types.KeyboardButton("⭐ Статус: PRO (Всё открыто!)"))
        else:
            markup.add(types.KeyboardButton("⭐ Купить PRO подписку"))
    else:
        markup.add(
            types.KeyboardButton("🌤 Weather"),
            types.KeyboardButton("🧮 Calculator"),
            types.KeyboardButton("📝 Notepad"),
            types.KeyboardButton("🎮 All Games (16)"),
            types.KeyboardButton("🛠 Utilities"),
            types.KeyboardButton("🤖 About"),
            types.KeyboardButton("🇺🇸 Language")
        )
        if is_pro:
            markup.add(types.KeyboardButton("⭐ Status: PRO"))
        else:
            markup.add(types.KeyboardButton("⭐ Buy PRO Sub"))
    return markup

def get_cancel_menu(lang="ru"):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    text = "❌ Выйти из режима" if lang == "ru" else "❌ Exit mode"
    markup.add(types.KeyboardButton(text))
    return markup

# --- КОМАНДЫ ---
@bot.message_handler(commands=["start"])
def start(message):
    chat_id = str(message.chat.id)
    reset_user_states(message.chat.id) # Сбрасываем всё при старте
    
    if chat_id not in db:
        # Добавили поля для ИИ-чата и памяти в структуру нового юзера
        db[chat_id] = {
            "username": message.from_user.username, 
            "pro": False, 
            "notes": [], 
            "lang": "ru",
            "in_ai_chat": False,
            "chat_history": []
        }
        save_db(db)
        send_lang_selection(message)
    else:
        # Если юзер уже был в базе (из старого файла), на всякий случай проверяем и дописываем новые ключи
        if "chat_history" not in db[chat_id]:
            db[chat_id]["chat_history"] = []
        if "in_ai_chat" not in db[chat_id]:
            db[chat_id]["in_ai_chat"] = False
        save_db(db)

        lang = db[chat_id].get("lang", "ru")
        is_pro = db[chat_id].get("pro", False)
        text_ru = "🔥 Йоу, шеф! Система загружена на 100%. Выбирай нужный раздел ниже:"
        text_en = "🔥 Yo, chief! System loaded 100%. Choose a section below:"
        bot.send_message(message.chat.id, text_ru if lang == "ru" else text_en, reply_markup=get_main_menu(lang, is_pro))

def send_lang_selection(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru"),
        types.InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")
    )
    bot.send_message(message.chat.id, "🌐 Выбери язык интерфейса / Choose interface language:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("lang_"))
def callback_lang(call):
    chat_id = str(call.message.chat.id)
    lang = call.data.split("_")[1]
    if chat_id not in db:
        db[chat_id] = {"pro": False, "notes": [], "lang": lang}
    else:
        db[chat_id]["lang"] = lang
    save_db(db)
    is_pro = db[chat_id].get("pro", False)
    text = "🚀 Язык успешно изменен!" if lang == "ru" else "🚀 Language successfully updated!"
    bot.answer_callback_query(call.id, text)
    bot.send_message(call.message.chat.id, text, reply_markup=get_main_menu(lang, is_pro))

@bot.message_handler(commands=["cancel"])
def emergency_cancel(message):
    chat_id = message.chat.id
    reset_user_states(chat_id)
    lang = db.get(str(chat_id), {}).get("lang", "ru")
    is_pro = db.get(str(chat_id), {}).get("pro", False)
    text = "🔄 Все процессы сброшены. Возврат в главное меню." if lang == "ru" else "🔄 All processes reset. Returning to main menu."
    bot.send_message(chat_id, text, reply_markup=get_main_menu(lang, is_pro))

# --- УМНЫЙ РОУТЕР СООБЩЕНИЙ С ЗАЩИТОЙ ---
@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    text = message.text if message.text else ""
    chat_id = message.chat.id
    str_chat_id = str(chat_id)
    username = message.from_user.username or ""

    # 1. Запоминаем username в базе
    if str_chat_id in db:
        db[str_chat_id]["username"] = username

    # 2. ПРОВЕРКА НА БАН
    MY_ID = "6661291589"
    banned_until = db.get(str_chat_id, {}).get("banned_until", 0)
    import time
    if time.time() < banned_until and str_chat_id != MY_ID:
        remaining_sec = int(banned_until - time.time())
        return bot.send_message(chat_id, f"⛔ **Вы забанены!** Осталось: {remaining_sec // 60} мин.", parse_mode="Markdown")

    # 3. ПЕРЕХВАТ КОМАНДЫ /broadcast (Создатель)
    if text.startswith("/broadcast"):
        if str_chat_id != MY_ID and username.lower() != "oiyrespro":
            return bot.send_message(chat_id, "⛔ Доступ запрещен!")
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            return bot.send_message(chat_id, "⚠️ Использование: `/broadcast [Текст]`", parse_mode="Markdown")
        
        success_count = 0
        for uid in db.keys():
            try:
                bot.send_message(uid, f"📢 **Объявление:**\n\n{parts[1]}", parse_mode="Markdown")
                success_count += 1
            except:
                pass
        return bot.send_message(chat_id, f"✅ Рассылка завершена! Успешно: {success_count}")

    # 🤖 ВХОД В РЕЖИМ ИИ-ЧАТА С GEMINI
    if text.startswith("/chatai"):
        db[str_chat_id]["in_ai_chat"] = True
        return bot.send_message(chat_id, "🤖 **Режим чата с Gemini 3.6 запущен!**\nПиши любые вопросы. Для выхода напиши `/exit`.", parse_mode="Markdown")

    # 🚪 ВЫХОД
    if text.startswith("/exit"):
        db[str_chat_id]["in_ai_chat"] = False
        db[str_chat_id]["chat_history"] = []  # Очищаем память при выходе
        return bot.send_message(chat_id, "✅ Вышли из режима ИИ, память стерта.")

# 🧠 ОБРАБОТКА СООБЩЕНИЙ В РЕЖИМЕ ИИ С DUCKDUCKGO ПОИСКОМ
    if db.get(str_chat_id, {}).get("in_ai_chat", False):
        try:
            from google import genai
            from duckduckgo_search import DDGS

            local_client = genai.Client(api_key=GEMINI_API_KEY)
            user_data = db[str_chat_id]
            if "chat_history" not in user_data:
                user_data["chat_history"] = []

            # Делаем быстрый поиск через DuckDuckGo по тексту пользователя
            search_results_text = ""
            try:
                with DDGS() as ddgs:
                    results = [r for r in ddgs.text(text, max_results=3)]
                    if results:
                        search_results_text = "\n".join([f"- {r['title']}: {r['body']} ({r['href']})" for r in results])
            except Exception as search_err:
                print(f"⚠️ Ошибка поиска DDG: {search_err}")

            # Формируем финальный промпт для модели
            final_prompt = text
            if search_results_text:
                final_prompt = f"Информация из интернета (DuckDuckGo):\n{search_results_text}\n\nВопрос пользователя: {text}"

            # Создаем чат на самой быстрой 3.5 Flash-Lite
            chat = local_client.chats.create(
                model="gemini-3.5-flash-lite",
                history=user_data["chat_history"]
            )
            
            response = chat.send_message(final_prompt)
            ai_reply = response.text
            
            # Сохраняем в историю оригинальный текст пользователя и ответ ИИ
            user_data["chat_history"].append({"role": "user", "parts": [{"text": text}]})
            user_data["chat_history"].append({"role": "model", "parts": [{"text": ai_reply}]})
            
            save_db(db)

            try:
                return bot.send_message(chat_id, ai_reply, parse_mode="Markdown")
            except Exception:
                return bot.send_message(chat_id, ai_reply)

        except Exception as e:
            ai_reply = f"⚠️ Ошибка ИИ: {str(e)}"
            return bot.send_message(chat_id, ai_reply)

# 4. ПЕРЕХВАТ КОМАНДЫ /freepro ИЛИ /pro С ПАРОЛЕМ
    if text.startswith("/freepro") or text.startswith("/pro"):
        parts = text.split(maxsplit=1)
        
        # Проверяем, ввел ли пользователь пароль
        if len(parts) < 2 or parts[1] != "oiyres26pro":
            return bot.send_message(
                chat_id, 
                "🔒 **Неверный пароль!**`", 
                parse_mode="Markdown"
            )
        
        # Если пароль правильный — активируем PRO
        if str_chat_id not in db:
            db[str_chat_id] = {
                "username": username, 
                "pro": True, 
                "notes": [], 
                "lang": "ru",
                "in_ai_chat": False,
                "chat_history": []
            }
        else:
            db[str_chat_id]["pro"] = True
            
        save_db(db)
        
        lang = db[str_chat_id].get("lang", "ru")
        text_ru = "🎉 **Поздравляю, шеф!** Секретный пароль принят, PRO-подписка активирована! 🚀 Все премиум-фичи разблокированы."
        text_en = "🎉 **Congrats, chief!** Secret password accepted, PRO subscription activated! 🚀 All premium features unlocked."
        return bot.send_message(
            chat_id, 
            text_ru if lang == "ru" else text_en, 
            reply_markup=get_main_menu(lang, is_pro=True),
            parse_mode="Markdown"
        )

    # 4. ПЕРЕХВАТ /stats (Создатель)
    if text.startswith("/stats"):
        if str_chat_id != MY_ID and username.lower() != "oiyrespro":
            return bot.send_message(chat_id, "⛔ Доступ запрещен!")
        total = len(db)
        ru = sum(1 for u in db.values() if u.get("lang") == "ru")
        en = sum(1 for u in db.values() if u.get("lang") == "en")
        pro = sum(1 for u in db.values() if u.get("pro", False))
        return bot.send_message(chat_id, f"📊 Статистика:\n👥 Всего: {total}\n🇷🇺 RU: {ru} | 🇬🇧 EN: {en}\n⭐ PRO: {pro}")

    # 5. ПЕРЕХВАТ /ban
    if text.startswith("/ban"):
        if str_chat_id != MY_ID and username.lower() != "oiyrespro":
            return bot.send_message(chat_id, "⛔ Доступ запрещен!")
        parts = text.split()
        if len(parts) < 2:
            return bot.send_message(chat_id, "⚠️ Использование: `/ban @username`", parse_mode="Markdown")
        target_name = parts[1].replace("@", "").lower()
        target_id = next((uid for uid, u in db.items() if u.get("username", "").lower() == target_name), None)
        if not target_id:
            return bot.send_message(chat_id, "❌ Пользователь не найден в базе!")
        db[target_id]["banned_until"] = time.time() + 1800 # 30 минут
        return bot.send_message(chat_id, f"🔨 Пользователь @{target_name} забанен на 30 минут.")

    # 6. ПЕРЕХВАТ /unban
    if text.startswith("/unban"):
        if str_chat_id != MY_ID and username.lower() != "oiyrespro":
            return bot.send_message(chat_id, "⛔ Доступ запрещен!")
        parts = text.split()
        if len(parts) < 2:
            return bot.send_message(chat_id, "⚠️ Использование: `/unban @username`", parse_mode="Markdown")
        target_name = parts[1].replace("@", "").lower()
        target_id = next((uid for uid, u in db.items() if u.get("username", "").lower() == target_name), None)
        if not target_id:
            return bot.send_message(chat_id, "❌ Пользователь не найден!")
        db[target_id]["banned_until"] = 0
        return bot.send_message(chat_id, f"✅ Пользователь @{target_name} разбанен.")

    # 7. ЗАЩИТА ОТ СЛУЧАЙНЫХ СЛЕШЕЙ (если ввели просто "/" или несуществующую команду)
    if text.startswith("/"):
        return bot.send_message(chat_id, "❌ Такой команды не существует. Проверь меню!")

    # 8. РЕАКЦИЯ НА ПЛОХИЕ СЛОВА ИЛИ ОБКАТКУ (например, "дурак")
    bad_words = ["дурак", "тупой", "бот дурак", "идиот"]
    if any(word in text.lower() for word in bad_words):
        return bot.send_message(chat_id, "Эй-эй, полегче! Я же просто код, давай жить дружно 😉 Лучше нажми кнопку меню.")

    # 9. ОБЫЧНАЯ ПРОВЕРКА БАЗЫ
    if str_chat_id not in db:
        return start(message)
    
    lang = db[str_chat_id].get("lang", "ru")
    is_pro = db[str_chat_id].get("pro", False)
    text = message.text

    # Проверка выхода на любом языке
    if text in ["❌ Выйти из режима", "❌ Exit mode", "❌ Exit game"]:
        reset_user_states(chat_id)
        msg_text = "🔄 Возврат в главное меню." if lang == "ru" else "🔄 Returned to main menu."
        return bot.send_message(chat_id, msg_text, reply_markup=get_main_menu(lang, is_pro))

    # Активные обработчики ввода игр
    if chat_id in hangman_games:
        return handle_hangman_input(message)
    if str_chat_id in active_games and "guess" in active_games[str_chat_id]:
        return handle_guess_input(message)
    if str_chat_id in active_games and "sprint" in active_games[str_chat_id]:
        return handle_sprint_input(message)
    if chat_id in quiz_games:
        return handle_quiz_input(message)

    # Перехват ввода погоды
    if str_chat_id in active_games and active_games[str_chat_id].get("mode") == "weather":
        return process_weather(message, lang)
    # Перехват ввода калькулятора
    if str_chat_id in active_games and active_games[str_chat_id].get("mode") == "calc":
        return process_calc(message, lang)

    if text in ["🇷🇺 Язык", "🇺🇸 Language"]:
        return send_lang_selection(message)

    # Погода
    if text in ["🌤 Погода", "🌤 Weather"]:
        active_games[str_chat_id] = {"mode": "weather"}
        prompt_text = "🌍 Напиши название города для проверки погоды:" if lang == "ru" else "🌍 Enter city name for weather check:"
        bot.send_message(chat_id, prompt_text, reply_markup=get_cancel_menu(lang))
        return

    # Калькулятор
    if text in ["🧮 Калькулятор", "🧮 Calculator"]:
        active_games[str_chat_id] = {"mode": "calc"}
        prompt_text = "🔢 Введи пример (например, 145 * 2 / 5):" if lang == "ru" else "🔢 Enter math expression (e.g. 145 * 2 / 5):"
        bot.send_message(chat_id, prompt_text, reply_markup=get_cancel_menu(lang))
        return

    # Блокнот
    if text in ["📝 Блокнот", "📝 Notepad"]:
        markup = types.InlineKeyboardMarkup()
        if lang == "ru":
            markup.add(
                types.InlineKeyboardButton("➕ Добавить заметку", callback_data="note_add"),
                types.InlineKeyboardButton("👀 Посмотреть заметки", callback_data="note_show"),
                types.InlineKeyboardButton("🗑 Очистить блокнот", callback_data="note_clear")
            )
            bot.send_message(chat_id, "📝 Твой личный блокнот:", reply_markup=markup)
        else:
            markup.add(
                types.InlineKeyboardButton("➕ Add note", callback_data="note_add"),
                types.InlineKeyboardButton("👀 Show notes", callback_data="note_show"),
                types.InlineKeyboardButton("🗑 Clear notepad", callback_data="note_clear")
            )
            bot.send_message(chat_id, "📝 Your personal notepad:", reply_markup=markup)
        return

    # Утилиты
    if text in ["🛠 Утилиты", "🛠 Utilities"]:
        markup = types.InlineKeyboardMarkup(row_width=2)
        if lang == "ru":
            markup.add(
                types.InlineKeyboardButton("⚡ Пинг сервера", callback_data="util_ping"),
                types.InlineKeyboardButton("🔐 Генератор паролей", callback_data="util_pass"),
                types.InlineKeyboardButton("🎲 Случайное число", callback_data="util_rand"),
                types.InlineKeyboardButton("⏱ Секундомер", callback_data="util_time")
            )
            bot.send_message(chat_id, "🛠 Набор полезных инструментов:", reply_markup=markup)
        else:
            markup.add(
                types.InlineKeyboardButton("⚡ Server Ping", callback_data="util_ping"),
                types.InlineKeyboardButton("🔐 Password Gen", callback_data="util_pass"),
                types.InlineKeyboardButton("🎲 Random Num", callback_data="util_rand"),
                types.InlineKeyboardButton("⏱ Stopwatch", callback_data="util_time")
            )
            bot.send_message(chat_id, "🛠 Useful utilities kit:", reply_markup=markup)
        return

    # Меню всех 16 игр
    if text in ["🎮 Все игры (16 шт)", "🎮 All Games (16)"]:
        markup = types.InlineKeyboardMarkup(row_width=1)
        if lang == "ru":
            markup.add(
                types.InlineKeyboardButton("🎮 1. Угадай число (1-10)", callback_data="game_guess"),
                types.InlineKeyboardButton("✂️ 2. Камень, ножницы, бумага", callback_data="game_rps"),
                types.InlineKeyboardButton("❌ 3. Крестики-нолики (Умный ИИ)", callback_data="game_ttt"),
                types.InlineKeyboardButton("🎲 4. Чет или нечет", callback_data="game_evenodd"),
                types.InlineKeyboardButton("🪙 5. Орёл или решка", callback_data="game_coin"),
                types.InlineKeyboardButton("🎯 6. Угадай цвет", callback_data="game_color"),
                types.InlineKeyboardButton("💻 7. IT-Виселица [PRO]", callback_data="game_hangman"),
                types.InlineKeyboardButton("⚡ 8. Математический спринт [PRO]", callback_data="game_sprint"),
                types.InlineKeyboardButton("🧠 9. IT Квиз-викторина [PRO]", callback_data="game_quiz"),
                types.InlineKeyboardButton("🧮 10. Быстрый счет [PRO]", callback_data="game_fastmath"),
                types.InlineKeyboardButton("🧩 11. Угадай слово по буквам [PRO]", callback_data="game_wordscramble"),
                types.InlineKeyboardButton("🚀 12. Космический кликер [PRO]", callback_data="game_clicker"),
                types.InlineKeyboardButton("🔮 13. Магический шар судьбы [PRO]", callback_data="game_magic8"),
                types.InlineKeyboardButton("🔐 14. Взломай сейф (Цифры) [PRO]", callback_data="game_safe"),
                types.InlineKeyboardButton("🕹️ 15. Угадай карту [PRO]", callback_data="game_cards"),
                types.InlineKeyboardButton("🏆 16. Дуэль с ботом [PRO]", callback_data="game_duel")
            )
            bot.send_message(chat_id, "🎮 Аркадный зал (16 игр):", reply_markup=markup)
        else:
            markup.add(
                types.InlineKeyboardButton("🎮 1. Guess Number (1-10)", callback_data="game_guess"),
                types.InlineKeyboardButton("✂️ 2. Rock, Paper, Scissors", callback_data="game_rps"),
                types.InlineKeyboardButton("❌ 3. Tic-Tac-Toe (Smart AI)", callback_data="game_ttt"),
                types.InlineKeyboardButton("🎲 4. Even or Odd", callback_data="game_evenodd"),
                types.InlineKeyboardButton("🪙 5. Eagle or Tails", callback_data="game_coin"),
                types.InlineKeyboardButton("🎯 6. Guess Color", callback_data="game_color"),
                types.InlineKeyboardButton("💻 7. IT Hangman [PRO]", callback_data="game_hangman"),
                types.InlineKeyboardButton("⚡ 8. Math Sprint [PRO]", callback_data="game_sprint"),
                types.InlineKeyboardButton("🧠 9. IT Quiz [PRO]", callback_data="game_quiz"),
                types.InlineKeyboardButton("🧮 10. Fast Math [PRO]", callback_data="game_fastmath"),
                types.InlineKeyboardButton("🧩 11. Word Scramble [PRO]", callback_data="game_wordscramble"),
                types.InlineKeyboardButton("🚀 12. Space Clicker [PRO]", callback_data="game_clicker"),
                types.InlineKeyboardButton("🔮 13. Magic 8 Ball [PRO]", callback_data="game_magic8"),
                types.InlineKeyboardButton("🔐 14. Crack Safe [PRO]", callback_data="game_safe"),
                types.InlineKeyboardButton("🕹️ 15. Guess Card [PRO]", callback_data="game_cards"),
                types.InlineKeyboardButton("🏆 16. Bot Duel [PRO]", callback_data="game_duel")
            )
            bot.send_message(chat_id, "🎮 Arcade Hall (16 games):", reply_markup=markup)
        return

    if text in ["⭐ Купить PRO подписку", "⭐ Buy PRO Sub"]:
        prices = [types.LabeledPrice(label="Подписка PRO (Все 16 игр)", amount=100)]
        bot.send_invoice(chat_id, title="PRO Подписка", description="Разблокировка всех 10 элитных игр и утилит!", invoice_payload="pro_sub", provider_token="", currency="XTR", prices=prices)
        return

    if text in ["⭐ Статус: PRO (Всё открыто!)", "⭐ Status: PRO"]:
        msg = "⭐ У тебя элитный PRO-статус." if lang == "ru" else "⭐ You have elite PRO status."
        bot.send_message(chat_id, msg)
        return

    if text in ["🤖 О боте", "🤖 About"]:
        msg = "🤖 Супер-бот помощник с 16 играми, умным ИИ для крестиков-ноликов и утилитами!" if lang == "ru" else "🤖 Super assistant bot with 16 games and smart AI!"
        bot.send_message(chat_id, msg)
        return

    fallback_msg = "🤔 Интересный запрос! Используй кнопки меню." if lang == "ru" else "🤔 Interesting query! Use menu buttons."
    bot.send_message(chat_id, fallback_msg)

# --- УТИЛИТЫ ---
@bot.callback_query_handler(func=lambda call: call.data.startswith("util_"))
def callback_utils(call):
    chat_id = call.message.chat.id
    lang = db.get(str(chat_id), {}).get("lang", "ru")
    data = call.data.split("_")[1]
    if data == "ping":
        t1 = time.time()
        m = bot.send_message(chat_id, "🛰 Пингуем..." if lang=="ru" else "🛰 Pinging...")
        t2 = time.time()
        res = f"⚡ Отклик сети: {round((t2-t1)*1000)} мс." if lang=="ru" else f"⚡ Network ping: {round((t2-t1)*1000)} ms."
        bot.edit_message_text(res, chat_id, m.message_id)
    elif data == "pass":
        pwd = "".join(random.choice(string.ascii_letters + string.digits + "!@#$") for _ in range(12))
        res = f"🔐 Пароль:\n`{pwd}`" if lang=="ru" else f"🔐 Password:\n`{pwd}`"
        bot.send_message(chat_id, res, parse_mode="Markdown")
    elif data == "rand":
        num = random.randint(1, 1000)
        res = f"🎲 Число (1-1000): **{num}**" if lang=="ru" else f"🎲 Number (1-1000): **{num}**"
        bot.send_message(chat_id, res, parse_mode="Markdown")
    elif data == "time":
        res = f"⏱ Время: `{time.strftime('%H:%M:%S')}`" if lang=="ru" else f"⏱ Time: `{time.strftime('%H:%M:%S')}`"
        bot.send_message(chat_id, res, parse_mode="Markdown")

# --- ПОГОДА И КАЛЬКУЛЯТОР (С защитой выхода) ---
def process_weather(message, lang):
    text = message.text
    if text in ["❌ Выйти из режима", "❌ Exit mode", "❌ Exit game"]:
        return emergency_cancel(message)
    
    city = text
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang={lang}"
    try:
        res = requests.get(url).json()
        if res.get("cod") == 200:
            t = res['main']['temp']
            desc = res['weather'][0]['description']
            msg = f"🌤 Погода в {city.capitalize()}: {desc}, {t}°C" if lang == "ru" else f"🌤 Weather in {city.capitalize()}: {desc}, {t}°C"
            bot.send_message(message.chat.id, msg, reply_markup=get_main_menu(lang, db.get(str(message.chat.id), {}).get("pro", False)))
            active_games.pop(str(message.chat.id), None)
        else:
            err_msg = "❌ Город не найден. Напиши название еще раз или нажми кнопку выхода:" if lang == "ru" else "❌ City not found. Try again or click exit button:"
            bot.send_message(message.chat.id, err_msg, reply_markup=get_cancel_menu(lang))
    except:
        err_conn = "⚠️ Ошибка связи с сервером погоды." if lang == "ru" else "⚠️ Weather server connection error."
        bot.send_message(message.chat.id, err_conn)

def process_calc(message, lang):
    text = message.text
    if text in ["❌ Выйти из режима", "❌ Exit mode", "❌ Exit game"]:
        return emergency_cancel(message)
    try:
        res = eval(text, {"__builtins__": {}}, {})
        msg = f"🧮 Результат: `{text} = {res}`" if lang == "ru" else f"🧮 Result: `{text} = {res}`"
        bot.send_message(message.chat.id, msg, parse_mode="Markdown", reply_markup=get_main_menu(lang, db.get(str(message.chat.id), {}).get("pro", False)))
        active_games.pop(str(message.chat.id), None)
    except:
        err_msg = "❌ Ошибка в формуле. Попробуй еще раз:" if lang == "ru" else "❌ Math error. Try again:"
        bot.send_message(message.chat.id, err_msg, reply_markup=get_cancel_menu(lang))

# ==========================================
# БЕСПЛАТНЫЕ ИГРЫ (1 - 6)
# ==========================================

@bot.callback_query_handler(func=lambda call: call.data == "game_guess")
def cb_guess(call):
    chat_id = call.message.chat.id
    active_games[str(chat_id)] = {"guess": random.randint(1, 10)}
    bot.send_message(chat_id, "🎯 Я загадал число от 1 до 10. Напиши свой вариант:", reply_markup=get_cancel_menu("ru"))

def handle_guess_input(message):
    chat_id = message.chat.id
    str_id = str(chat_id)
    try:
        val = int(message.text)
        sec = active_games[str_id]["guess"]
        if val == sec:
            bot.send_message(chat_id, f"🎉 Ура! Ты угадал число {sec}!", reply_markup=get_main_menu("ru", db.get(str_id, {}).get("pro", False)))
            active_games.pop(str_id, None)
        else:
            hint = "📈 Мое число больше!" if val < sec else "📉 Мое число меньше!"
            bot.send_message(chat_id, f"❌ Не угадал! {hint} Введи еще раз:")
    except ValueError:
        bot.send_message(chat_id, "⚠️ Введи цифру от 1 до 10:")

@bot.callback_query_handler(func=lambda call: call.data == "game_rps")
def cb_rps(call):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add("✊ Камень", "✌️ Ножницы", "🖐 Бумага", "❌ Выйти из режима")
    bot.send_message(call.message.chat.id, "Сделай свой выбор:", reply_markup=markup)
    bot.register_next_step_handler(call.message, check_rps)

def check_rps(message):
    chat_id = message.chat.id
    user = message.text
    if user in ["❌ Выйти из режима", "❌ Exit mode"]:
        return emergency_cancel(message)
    if user not in ["✊ Камень", "✌️ Ножницы", "🖐 Бумага"]:
        return
    bot_c = random.choice(["✊ Камень", "✌️ Ножницы", "🖐 Бумага"])
    if user == bot_c:
        res = f"🤝 Ничья! У бота тоже {bot_c}."
    elif (user == "✊ Камень" and bot_c == "✌️ Ножницы") or (user == "✌️ Ножницы" and bot_c == "🖐 Бумага") or (user == "🖐 Бумага" and bot_c == "✊ Камень"):
        res = f"🏆 Ты победил! У бота был {bot_c}."
    else:
        res = f"😢 Победа бота! У него был {bot_c}."
    is_pro = db.get(str(chat_id), {}).get("pro", False)
    bot.send_message(chat_id, res, reply_markup=get_main_menu("ru", is_pro))

# Крестики-нолики
@bot.callback_query_handler(func=lambda call: call.data == "game_ttt")
def cb_ttt(call):
    chat_id = call.message.chat.id
    tic_tac_toe_boards[chat_id] = [" "]*9
    send_ttt_board(chat_id, call.message.message_id)

def send_ttt_board(chat_id, msg_id=None):
    board = tic_tac_toe_boards[chat_id]
    markup = types.InlineKeyboardMarkup(row_width=3)
    buttons = [types.InlineKeyboardButton(board[i] if board[i] != " " else "·", callback_data=f"ttt_{i}") for i in range(9)]
    markup.add(*buttons)
    if msg_id:
        try:
            bot.edit_message_text("❌ Крестики-нолики (Ты — X, Умный ИИ — O):", chat_id, msg_id, reply_markup=markup)
        except:
            bot.send_message(chat_id, "❌ Крестики-нолики:", reply_markup=markup)
    else:
        bot.send_message(chat_id, "❌ Крестики-нолики:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("ttt_"))
def callback_ttt_turn(call):
    chat_id = call.message.chat.id
    if chat_id not in tic_tac_toe_boards:
        return
    idx = int(call.data.split("_")[1])
    board = tic_tac_toe_boards[chat_id]
    if board[idx] == " ":
        board[idx] = "❌"
        if check_ttt_win(board, "❌"):
            send_ttt_board(chat_id, call.message.message_id)
            bot.send_message(chat_id, "🎉 Невероятно! Ты обыграл умный ИИ!")
            tic_tac_toe_boards.pop(chat_id, None)
            return
        elif " " not in board:
            send_ttt_board(chat_id, call.message.message_id)
            bot.send_message(chat_id, "🤝 Ничья!")
            tic_tac_toe_boards.pop(chat_id, None)
            return

        ai_move = get_smart_ai_move(board)
        if ai_move is not None:
            board[ai_move] = "⭕"

        send_ttt_board(chat_id, call.message.message_id)
        if check_ttt_win(board, "⭕"):
            bot.send_message(chat_id, "🤖 ИИ просчитал тебя и победил!")
            tic_tac_toe_boards.pop(chat_id, None)
        elif " " not in board:
            bot.send_message(chat_id, "🤝 Ничья!")
            tic_tac_toe_boards.pop(chat_id, None)

def get_smart_ai_move(b):
    for i in range(9):
        if b[i] == " ":
            b[i] = "O"
            if check_ttt_win(b, "O"):
                b[i] = " "
                return i
            b[i] = " "
    for i in range(9):
        if b[i] == " ":
            b[i] = "X"
            if check_ttt_win(b, "X"):
                b[i] = " "
                return i
            b[i] = " "
    if b[4] == " ":
        return 4
    empty = [i for i, v in enumerate(b) if v == " "]
    return random.choice(empty) if empty else None

def check_ttt_win(b, p):
    wins = [(0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6)]
    return any(b[x] == p and b[y] == p and b[z] == p for x,y,z in wins)

@bot.callback_query_handler(func=lambda call: call.data == "game_evenodd")
def cb_evenodd(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Четное", callback_data="eo_even"), types.InlineKeyboardButton("Нечетное", callback_data="eo_odd"))
    bot.send_message(call.message.chat.id, "🎲 Выбери четность:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("eo_"))
def callback_eo(call):
    chat_id = call.message.chat.id
    choice = call.data.split("_")[1]
    num = random.randint(1, 50)
    is_even = (num % 2 == 0)
    user_won = (choice == "even" and is_even) or (choice == "odd" and not is_even)
    res = f"Число было: **{num}**. " + ("🎉 Ты угадал!" if user_won else "😢 Ты проиграл!")
    bot.send_message(chat_id, res, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data == "game_coin")
def cb_coin(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🪙 Орёл", callback_data="coin_eagle"), types.InlineKeyboardButton("🪙 Решка", callback_data="coin_tails"))
    bot.send_message(call.message.chat.id, "🪙 Орёл или решка?", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("coin_"))
def callback_coin(call):
    chat_id = call.message.chat.id
    choice = call.data.split("_")[1]
    result = random.choice(["eagle", "tails"])
    res_text = "Орёл 🦅" if result == "eagle" else "Решка 🪙"
    won = (choice == result)
    bot.send_message(chat_id, f"Выпало: {res_text}! " + ("🏆 Победа!" if won else "❌ Мимо!"))

@bot.callback_query_handler(func=lambda call: call.data == "game_color")
def cb_color(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🔴 Красный", callback_data="col_red"), types.InlineKeyboardButton("🟢 Зеленый", callback_data="col_green"), types.InlineKeyboardButton("🔵 Синий", callback_data="col_blue"))
    bot.send_message(call.message.chat.id, "🎨 Угадай цвет:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("col_"))
def callback_col(call):
    chat_id = call.message.chat.id
    choice = call.data.split("_")[1]
    secret = random.choice(["red", "green", "blue"])
    names = {"red": "🔴 Красный", "green": "🟢 Зеленый", "blue": "🔵 Синий"}
    won = (choice == secret)
    bot.send_message(chat_id, f"Бот загадал: {names[secret]}. " + ("🎉 Угадал!" if won else "❌ Не угадал!"))

# ==========================================
# PRO ИГРЫ (7 - 16)
# ==========================================

def check_pro_access(call_or_message):
    chat_id = call_or_message.message.chat.id if hasattr(call_or_message, "message") else call_or_message.chat.id
    if not db.get(str(chat_id), {}).get("pro", False):
        bot.send_message(chat_id, "⭐ Эта мини-игра доступна только с подпиской PRO!")
        return False
    return True

@bot.callback_query_handler(func=lambda call: call.data == "game_hangman")
def cb_hangman(call):
    if not check_pro_access(call): return
    chat_id = call.message.chat.id
    words = ["программист", "алгоритм", "разработчик", "клавиатура", "сервер", "интернет"]
    word = random.choice(words)
    hangman_games[chat_id] = {"word": word, "guessed": set(), "mistakes": 0, "max_mistakes": 6}
    send_hangman_board(chat_id)

def send_hangman_board(chat_id):
    data = hangman_games[chat_id]
    display = "".join([c if c in data["guessed"] else " _ " for c in data["word"]])
    text = f"💻 **IT-Виселица [PRO]**\nСлово: `{display}`\nОшибки: {data['mistakes']}/6\n👉 Отправь букву:"
    bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=get_cancel_menu("ru"))

def handle_hangman_input(message):
    chat_id = message.chat.id
    if chat_id not in hangman_games: return
    text = message.text.strip().lower()
    data = hangman_games[chat_id]
    if len(text) != 1 or not text.isalpha():
        return bot.send_message(chat_id, "⚠️ Отправь одну букву!")
    if text in data["guessed"]:
        return bot.send_message(chat_id, "⚠️ Ты уже называл её.")
    data["guessed"].add(text)
    if text in data["word"]:
        if all(c in data["guessed"] for c in data["word"]):
            bot.send_message(chat_id, f"🎉 Победа! Слово: `{data['word']}`", parse_mode="Markdown")
            hangman_games.pop(chat_id, None)
        else:
            send_hangman_board(chat_id)
    else:
        data["mistakes"] += 1
        if data["mistakes"] >= data["max_mistakes"]:
            bot.send_message(chat_id, f"💀 Поражение! Слово: `{data['word']}`", parse_mode="Markdown")
            hangman_games.pop(chat_id, None)
        else:
            send_hangman_board(chat_id)

@bot.callback_query_handler(func=lambda call: call.data == "game_sprint")
def cb_sprint(call):
    if not check_pro_access(call): return
    chat_id = call.message.chat.id
    a, b = random.randint(10, 99), random.randint(10, 99)
    op = random.choice(["+", "-", "*"])
    ans = eval(f"{a} {op} {b}")
    active_games[str(chat_id)] = {"sprint": ans}
    bot.send_message(chat_id, f"⚡ Спринт [PRO]: `{a} {op} {b} = ?`", parse_mode="Markdown", reply_markup=get_cancel_menu("ru"))

def handle_sprint_input(message):
    chat_id = message.chat.id
    str_id = str(chat_id)
    try:
        val = int(message.text)
        correct = active_games[str_id]["sprint"]
        if val == correct:
            bot.send_message(chat_id, "⚡ Отлично! Верно!")
        else:
            bot.send_message(chat_id, f"❌ Ошибка! Ответ был: {correct}")
        active_games.pop(str_id, None)
    except ValueError:
        bot.send_message(chat_id, "⚠️ Введи число:")

@bot.callback_query_handler(func=lambda call: call.data == "game_quiz")
def cb_quiz(call):
    if not check_pro_access(call): return
    chat_id = call.message.chat.id
    questions = [
        ("Кто создал Python?", "гиво ван россум"),
        ("Что такое HTML?", "язык разметки"),
        ("Что такое RAM?", "память")
    ]
    q, a = random.choice(questions)
    quiz_games[chat_id] = {"answer": a}
    bot.send_message(chat_id, f"🧠 **IT Квиз [PRO]**\n{q}", parse_mode="Markdown", reply_markup=get_cancel_menu("ru"))

def handle_quiz_input(message):
    chat_id = message.chat.id
    if chat_id not in quiz_games: return
    ans = message.text.strip().lower()
    correct = quiz_games[chat_id]["answer"]
    if correct in ans:
        bot.send_message(chat_id, "🎉 Верно!")
    else:
        bot.send_message(chat_id, f"❌ Неверно!")
    quiz_games.pop(chat_id, None)

@bot.callback_query_handler(func=lambda call: call.data in ["game_fastmath", "game_wordscramble", "game_clicker", "game_magic8", "game_safe", "game_cards", "game_duel"])
def cb_pro_games_handler(call):
    if not check_pro_access(call): return
    chat_id = call.message.chat.id
    g_type = call.data
    if g_type == "game_fastmath":
        bot.send_message(chat_id, "🧮 Быстрый счет [PRO]: 12 * 5 - 10 = **50**", parse_mode="Markdown")
    elif g_type == "game_wordscramble":
        bot.send_message(chat_id, "🧩 Анаграмма [PRO]: `онтон` -> Антон", parse_mode="Markdown")
    elif g_type == "game_clicker":
        bot.send_message(chat_id, "🚀 Клик! +100 очков энергии!", parse_mode="Markdown")
    elif g_type == "game_magic8":
        answers = ["Бесспорно", "Предрешено", "Спроси позже", "Сконцентрируйся и спроси снова"]
        bot.send_message(chat_id, f"🔮 Шар судьбы: *{random.choice(answers)}*", parse_mode="Markdown")
    elif g_type == "game_safe":
        code = random.randint(100, 999)
        bot.send_message(chat_id, f"🔐 Сейф [PRO]: Код (для теста: {code})", parse_mode="Markdown")
    elif g_type == "game_cards":
        card = random.choice(["Туз пик ♠️", "Король червей ❤️"])
        bot.send_message(chat_id, f"🕹️ Карточная игра [PRO]: {card}")
    elif g_type == "game_duel":
        bot.send_message(chat_id, f"🏆 Дуэль с ботом [PRO]: Победа за тобой! 🎯")

@bot.message_handler(commands=["joke"])
def cmd_joke(message):
    chat_id = str(message.chat.id)
    lang = db.get(chat_id, {}).get("lang", "ru")
    
    jokes_ru = [
        "👨‍💻 Есть 10 типов людей: те, кто понимает двоичный код, и те, кто его не понимает.",
        "👨‍💻 Настоящий программист — это устройство, которое превращает кофе в рабочий код.",
        "👨‍💻 Баг — это не ошибка, это неожиданная фича, добавленная разработчиком!",
        "👨‍💻 Код без комментариев — это увлекательный квест для разработчика уровня 'Хардкор'."
    ]
    jokes_en = [
        "👨‍💻 There are 10 types of people: those who understand binary and those who don't.",
        "👨‍💻 A programmer is a device that turns coffee into code.",
        "👨‍💻 It's not a bug, it's an undocumented feature!",
    ]
    
    joke = random.choice(jokes_ru if lang == "ru" else jokes_en)
    bot.send_message(message.chat.id, joke)

@bot.message_handler(commands=["broadcast"])
def cmd_broadcast(message):
    chat_id = str(message.chat.id)
    username = message.from_user.username
    
    # Твой реальный ID (можешь заменить на свой числовой ID, если он другой)
    MY_ID = "6661291589" # например, "123456789"
    
    # Проверяем: либо твой ID, либо твой юзернейм
    if chat_id != MY_ID and username != "oiyrespro":
        return bot.send_message(message.chat.id, "⛔ Доступ запрещен! Эта команда только для создателя.")
    
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return bot.send_message(message.chat.id, "⚠️ Использование: `/broadcast [Текст]`", parse_mode="Markdown")
    
    broadcast_text = parts[1]
    success_count = 0
    fail_count = 0
    
    for uid in db.keys():
        try:
            bot.send_message(uid, f"📢 **Объявление от разработчика:**\n\n{broadcast_text}", parse_mode="Markdown")
            success_count += 1
        except:
            fail_count += 1
            
    bot.send_message(message.chat.id, f"✅ Рассылка завершена!\n📩 Успешно: {success_count}\n❌ Ошибок: {fail_count}")

@bot.pre_checkout_query_handler(func=lambda query: True)
def pre_checkout(query):
    bot.answer_pre_checkout_query(query.id, ok=True)

@bot.message_handler(commands=["profile"])
def cmd_profile(message):
    chat_id = str(message.chat.id)
    if chat_id not in db:
        return
    user_data = db[chat_id]
    lang = user_data.get("lang", "ru")
    is_pro = user_data.get("pro", False)
    notes_count = len(user_data.get("notes", []))
    username = message.from_user.username or "Без имени"

    if lang == "ru":
        text = (
            f"👤 **Твой профиль в системе:**\n"
            f"▫️ Имя: @{username}\n"
            f"▫️ ID: `{chat_id}`\n"
            f"▫️ Статус: {'⭐ PRO-аккаунт' if is_pro else '🆓 Базовый'}\n"
            f"▫️ Заметок в блокноте: {notes_count}"
        )
    else:
        text = (
            f"👤 **Your System Profile:**\n"
            f"▫️ Username: @{username}\n"
            f"▫️ ID: `{chat_id}`\n"
            f"▫️ Status: {'⭐ PRO Account' if is_pro else '🆓 Free'}\n"
            f"▫️ Saved notes: {notes_count}"
        )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(content_types=['successful_payment'])
def success_pay(message):
    chat_id = str(message.chat.id)
    db[chat_id]["pro"] = True
    save_db(db)
    lang = db[chat_id].get("lang", "ru")
    msg = "🎉 Оплата прошла успешно! PRO разблокирован!" if lang=="ru" else "🎉 Payment successful! PRO unlocked!"
    bot.send_message(message.chat.id, msg, reply_markup=get_main_menu(lang, True))

if __name__ == "__main__":
    print("🚀 Имба-бот успешно запущен и работает!")
    
    # Запуск веб-сервера для удержания бота в активном состоянии на Render
    Thread(target=run_web).start()
    
    # Запускаем бота с защитой от конфликтов
    while True:
        try:
            bot.infinity_polling(none_stop=True, interval=1, timeout=20)
        except Exception as e:
            print(f"⚠️ Ошибка поллинга: {e}")
            time.sleep(5)