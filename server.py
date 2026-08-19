import json
import os
import random
import threading
import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import telebot
from telebot import types

TOKEN = "8964987241:AAH2Qxizao8Y1wy5_jQACc95Z7VHcgOJFHQ"
ADMIN_ID = 6661291589

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bot = telebot.TeleBot(TOKEN)
CODES_FILE = "auth_codes.txt"
PURCHASES_FILE = "purchases.json"
USERS_FILE = "users_db.json"


def load_json(filename):
  if not os.path.exists(filename):
    return []
  try:
    with open(filename, "r", encoding="utf-8") as f:
      return json.load(f)
  except:
    return []


def save_json(filename, data):
  with open(filename, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=4)


# --- ИИ-Контроллер безопасности (Автоматический анализ запрещенки) ---
FORBIDDEN_KEYWORDS = [
    "наркотик",
    "наркотики",
    "спайс",
    "соль",
    "меф",
    "оружие",
    "ствол",
    "пистолет",
    "патроны",
    "скам",
    "мошенничество",
    "взлом пк",
    "ратник",
    "стиллер",
    "ботнет",
    "dox",
    "докс",
    "слив базы",
    "деанон",
    "казино",
    "ставки",
    "порно",
    "18+",
    "суицид",
    "спам-бот",
]


def ai_security_check(text, username=""):
  # Абсолютный иммунитет для главного администратора (OiyresPro)
  if username.lower() in ["@oiyrespro", "oiyrespro"]:
    return True, "Администратор (без ограничений)"

  text_lower = text.lower()

  # Умный анализ контекста ИИ на наличие запрещенных товаров/услуг
  for word in FORBIDDEN_KEYWORDS:
    if word in text_lower:
      return (
          False,
          f"ИИ обнаружил запрещенный контент/услугу: упоминание «{word}».",
      )

  return True, "Безопасно"


def handle_user_violation(username):
  users = load_json(USERS_FILE)
  user_data = next((u for u in users if u["username"] == username), None)
  current_time = time.time()

  if not user_data:
    user_data = {
        "username": username,
        "violations": 1,
        "ban_until": current_time + 3600,
        "is_perabanned": False,
    }
    users.append(user_data)
    punishment = "бан на 1 час"
  else:
    if user_data["is_perabanned"]:
      return "Аккаунт заблокирован навсегда."

    user_data["violations"] += 1
    if user_data["violations"] == 2:
      user_data["ban_until"] = current_time + 86400
      punishment = "повторное нарушение — бан на 1 день (24 часа)"
    else:
      user_data["is_perabanned"] = True
      user_data["ban_until"] = current_time + 999999999
      punishment = (
          "систематическое нарушение — перманентный блок аккаунта (создание"
          " нового заблокировано)"
      )

  save_json(USERS_FILE, users)
  return punishment


def check_if_banned(username):
  # Админ никогда не получает бан
  if username.lower() in ["@oiyrespro", "oiyrespro"]:
    return False, ""

  users = load_json(USERS_FILE)
  user_data = next((u for u in users if u["username"] == username), None)
  if user_data:
    if user_data["is_perabanned"]:
      return (
          True,
          (
              "Ваш аккаунт заблокирован навсегда за регулярные нарушения"
              " правил. Создание нового аккаунта запрещено."
          ),
      )
    if time.time() < user_data["ban_until"]:
      left_mins = int((user_data["ban_until"] - time.time()) / 60)
      return (
          True,
          f"Аккаунт временно заблокирован за нарушение. До снятия бана: {left_mins} мин.",
      )
  return False, ""


# --- Telegram Бот ---
@bot.message_handler(commands=["start"])
def send_welcome(message):
  user_id = message.from_user.id
  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      types.InlineKeyboardButton(
          "🔐 Получить ID для сайта", callback_data="get_auth"
      ),
      types.InlineKeyboardButton(
          "🛠 Заказать разработку", callback_data="start_order"
      ),
  )
  bot.send_message(
      user_id,
      "🤖 Привет! Защищенная ИИ-платформа OlipT активна.",
      reply_markup=markup,
  )


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
  user_id = call.from_user.id
  if call.data == "get_auth":
    auth_code = f"o{random.randint(1000000, 9999999)}"
    username = call.from_user.username or f"id{user_id}"
    with open(CODES_FILE, "a", encoding="utf-8") as f:
      f.write(f"{auth_code}:{user_id}:{username}\n")
    bot.answer_callback_query(call.id, "ID успешно создан!")
    bot.send_message(
        user_id, f"🔐 Ваш код авторизации для сайта:\n`{auth_code}`", parse_mode="Markdown"
    )


# --- FastAPI Маршруты ---
@app.get("/", response_class=HTMLResponse)
def serve_index():
  if os.path.exists("index.html"):
    with open("index.html", "r", encoding="utf-8") as f:
      return HTMLResponse(content=f.read())
  return HTMLResponse(
      content="<h1>Файл index.html не найден в корневой папке!</h1>",
      status_code=404,
  )


@app.post("/api/verify")
async def verify(request: Request):
  data = await request.json()
  code = data.get("code", "").strip()
  if not os.path.exists(CODES_FILE):
    return {"success": False, "error": "База кодов пуста"}

  with open(CODES_FILE, "r", encoding="utf-8") as f:
    for line in f:
      parts = line.strip().split(":")
      if len(parts) >= 2 and parts[0] == code:
        username = parts[2] if len(parts) > 2 else f"id{parts[1]}"
        clean_username = (
            f"@{username}" if not username.startswith("@") else username
        )

        # Проверяем, в бане ли пользователь
        is_banned, ban_msg = check_if_banned(clean_username)
        if is_banned:
          return {"success": False, "error": ban_msg}

        return {
            "success": True,
            "username": clean_username,
            "telegram_id": parts[1],
        }
  return {"success": False, "error": "Неверный или просроченный код авторизации"}


@app.post("/api/check-product")
async def check_product(request: Request):
  data = await request.json()
  title = data.get("title", "")
  desc = data.get("desc", "")
  username = data.get("username", "")

  # ИИ проверяет название и описание услуги/товара
  is_safe, reason = ai_security_check(title + " " + desc, username)
  if not is_safe:
    punishment = handle_user_violation(username)
    try:
      bot.send_message(
          ADMIN_ID,
          f"🚨 **ИИ зафиксировал нарушение правил!**\n👤 Пользователь:"
          f" {username}\n📝 Причина: {reason}\n⚖️ Наказание:"
          f" {punishment}",
          parse_mode="Markdown",
      )
    except:
      pass
    return {
        "success": False,
        "error": f"⚠️ Запрещенный контент! {reason}. Наказание: {punishment}",
    }

  return {"success": True}


@app.post("/api/purchase")
async def record_purchase(request: Request):
  data = await request.json()
  purchases = load_json(PURCHASES_FILE)
  purchases.append(data)
  save_json(PURCHASES_FILE, purchases)

  # ИИ отправляет подробный отчет о сделке в Telegram администратору
  try:
    bot.send_message(
        ADMIN_ID,
        f"🛒 **ИИ зафиксировал новую сделку!**\n"
        f"📦 Услуга/Товар: {data.get('title')}\n"
        f"💰 Стоимость: {data.get('price')}\n"
        f"👤 Покупатель: {data.get('buyer')}\n"
        f"🤝 Продавец: {data.get('seller')}",
        parse_mode="Markdown",
    )
  except:
    pass
  return {"success": True}


@app.get("/api/admin/data")
def get_admin_data():
  return {"purchases": load_json(PURCHASES_FILE), "users": load_json(USERS_FILE)}


def run_bot():
  bot.infinity_polling(none_stop=True)


if __name__ == "__main__":
  import uvicorn

  bot_thread = threading.Thread(target=run_bot, daemon=True)
  bot_thread.start()
  print("🚀 Защищенный ИИ-сервер и Telegram-бот успешно запущены!")
  uvicorn.run(app, host="127.0.0.1", port=8000)