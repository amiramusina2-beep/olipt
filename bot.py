import os
import time
import telebot
from telebot import types

# Твои сохраненные данные
TOKEN = "8964987241:AAH2Qxizao8Y1wy5_jQACc95Z7VHcgOJFHQ"
ADMIN_ID = 6661291589

bot = telebot.TeleBot(TOKEN)

# Файл для сохранения кодов авторизации
CODES_FILE = "auth_codes.txt"
active_chats = {}  # {user_id: "active"}
ban_list = {}  # {user_id: timestamp_until_unban}


def save_code_to_file(code, user_id, username):
  # Записываем в файл в формате: КОД | USER_ID | USERNAME
  with open(CODES_FILE, "a", encoding="utf-8") as f:
    f.write(f"{code}:{user_id}:{username}\n")


def check_code_in_file(input_code):
  if not os.path.exists(CODES_FILE):
    return None
  with open(CODES_FILE, "r", encoding="utf-8") as f:
    for line in f:
      parts = line.strip().split(":")
      if len(parts) >= 2:
        file_code, user_id, username = (
            parts[0],
            parts[1],
            parts[2] if len(parts) > 2 else "unknown",
        )
        if file_code == input_code:
          return username  # кен возвращаем юзернейм
  return None


@bot.message_handler(commands=["start"])
def send_welcome(message):
  user_id = message.from_user.id

  if user_id in ban_list:
    if time.time() < ban_list[user_id]:
      bot.send_message(
          user_id, "🚫 Вы заблокированы на этой платформе на 10 минут."
      )
      return
    else:
      del ban_list[user_id]

  markup = types.InlineKeyboardMarkup(row_width=1)
  markup.add(
      types.InlineKeyboardButton(
          "🔐 Получить ID для авторизации на сайте", callback_data="get_auth"
      ),
      types.InlineKeyboardButton(
          "🛠 Заказать разработку (Чат с админом)",
          callback_data="start_order",
      ),
  )

  bot.send_message(
      user_id,
      "Привет! Добро пожаловать в официальный бот платформы **DetOnlyBot**.",
      reply_markup=markup,
      parse_mode="Markdown",
  )


@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
  user_id = call.from_user.id

  if user_id in ban_list and time.time() < ban_list[user_id]:
    bot.answer_callback_query(call.id, "Вы заблокированы!", show_alert=True)
    return

  if call.data == "get_auth":
    import random

    auth_code = f"o{random.randint(1000000, 9999999)}"
    username = call.from_user.username or f"id{user_id}"

    # Сохраняем в текстовый файл
    save_code_to_file(auth_code, user_id, username)

    bot.answer_callback_query(call.id, "ID успешно сгенерирован!")
    bot.send_message(
        user_id,
        f"🔐 Ваш персональный код авторизации для сайта:\n`{auth_code}`\n\nВведите"
        " его в Личном кабинете на сайте OlipT.",
        parse_mode="Markdown",
    )

  elif call.data == "start_order":
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("❌ 3", callback_data="captcha_wrong"),
        types.InlineKeyboardButton("✅ 5", callback_data="captcha_correct"),
        types.InlineKeyboardButton("❌ 7", callback_data="captcha_wrong"),
    )
    bot.send_message(
        user_id,
        "🤖 **Защита от спама (Капча):**\nСколько будет 2 + 3?",
        reply_markup=markup,
        parse_mode="Markdown",
    )

  elif call.data == "captcha_correct":
    active_chats[user_id] = "active"
    bot.edit_message_text(
        "✅ Капча пройдена! Напишите вашу задачу одним сообщением, и она"
        " сразу отправится разработчику.",
        user_id,
        call.message.message_id,
    )

    admin_markup = types.InlineKeyboardMarkup(row_width=2)
    admin_markup.add(
        types.InlineKeyboardButton(
            "🛑 Завершить диалог", callback_data=f"close_{user_id}"
        ),
        types.InlineKeyboardButton(
            "🔨 Бан 10 мин", callback_data=f"ban_{user_id}"
        ),
        types.InlineKeyboardButton(
            "🔓 Разблокировать", callback_data=f"unban_{user_id}"
        ),
    )
    bot.send_message(
        ADMIN_ID,
        f"🔔 Новый заказ от пользователя @{call.from_user.username or user_id}"
        f" (ID: `{user_id}`)",
        reply_markup=admin_markup,
        parse_mode="Markdown",
    )

  elif call.data == "captcha_wrong":
    bot.answer_callback_query(
        call.id, "Неверно! Попробуйте снова.", show_alert=True
    )

  elif call.data.startswith("close_"):
    target_id = int(call.data.split("_")[1])
    if target_id in active_chats:
      del active_chats[target_id]
    bot.send_message(target_id, "🔒 Диалог с разработчиком завершен.")
    bot.answer_callback_query(call.id, "Диалог закрыт.")

  elif call.data.startswith("ban_"):
    target_id = int(call.data.split("_")[1])
    ban_list[target_id] = time.time() + 600  # Бан на 10 минут
    if target_id in active_chats:
      del active_chats[target_id]
    bot.send_message(target_id, "🚫 Вы были заблокированы администратором.")
    bot.answer_callback_query(call.id, "Пользователь забанен на 10 минут.")

  elif call.data.startswith("unban_"):
    target_id = int(call.data.split("_")[1])
    if target_id in ban_list:
      del ban_list[target_id]
    bot.send_message(target_id, "🔓 Вы разблокированы администратором.")
    bot.answer_callback_query(call.id, "Пользователь разблокирован.")


@bot.message_handler(func=lambda message: True)
def handle_chat(message):
  user_id = message.from_user.id

  if user_id == ADMIN_ID:
    return

  if user_id in ban_list:
    if time.time() < ban_list[user_id]:
      bot.send_message(
          user_id, "🚫 Вы заблокированы. Сообщения не доставляются."
      )
      return
    else:
      del ban_list[user_id]

  if user_id in active_chats and active_chats[user_id] == "active":
    bot.forward_message(ADMIN_ID, user_id, message.message_id)
    bot.reply_to(message, "📩 Ваше сообщение передано разработчику.")


print("🤖 Бот DetOnlyBot запущен и записывает коды в auth_codes.txt...")
bot.infinity_polling()