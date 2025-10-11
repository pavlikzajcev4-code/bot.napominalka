# Немного о боте
 __это бот партнерской программы который умеет генерировать qr-коды и показывать меню с ссылками так-же он обладает своими командами для администраторов__




# __Как запустить бота?__
__Для начала клонируем репозиторий "" (нужно для всех версий)__  
 __Для виртуальных машин:__   
__1 переходим в режми "root" (sudo su "пароль от входа в компьютер") 2 скачиваем модуль "Python" (apt install python3) и прописываем команду "python3 bot.py".__   

__для хостингов: 1 регистрируемся 2 переходим в "files" 3 нажимаем "upload file" и выбираем ранее загруженный файл 4 нажимаем на загруженный файл и на "run"__  

__для серверов: 1 скачиваем python(sudo apt install python3-pip) 2 загружаем файл 3 запускаем скрипт python3 bot.py__


# __Импорт и настройка ботов__
```
import logging
import sqlite3
import qrcode
import urllib.parse
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from io import BytesIO
from aiogram.dispatcher import FSMContext
from aiogram import Bot, Dispatcher, types
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.utils import executor
from aiogram.dispatcher.filters.state import State, StatesGroup
from config import BOT_TOKEN, BOT_USERNAME, ADMIN_ID, DB_PATH
```

**Важное примечание!!! config: это пользовательский модуль, содержащий конфигурационные данные:
BOT_TOKEN: Токен бота от Telegram.
BOT_USERNAME: Имя бота (например, @MyBot).
ADMIN_ID: Список ID администраторов.
DB_PATH: Путь к базе данных SQLite.**
  

**Ещё одно примечание: вам нужно заранее скачать библиотеку aiogram ("pip install aiogram")**  

# __Лог__

```
logging.basicConfig(level=logging.INFO)
```
**устанавливает лог чтобы фиксировать основные события и ошибки.**  

# Создаётся объект бота с токеном и режимом парсинга HTML (для форматирования текста).

```
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())
```   

# Определяет состояние awaiting_content для функции массовой рассылки сообщений администратором.

```
class BroadcastState(StatesGroup):
    awaiting_content = State()
```  

# Работа с базой данных
```
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id BIGINT PRIMARY KEY,
        username TEXT,
        is_active INTEGER DEFAULT 0,
        is_partner INTEGER DEFAULT 0,
        referrer BIGINT,
        referrals_count INTEGER DEFAULT 0,
        paid_referrals_count INTEGER DEFAULT 0,
        total_earned REAL DEFAULT 0.0,
        available_to_withdraw REAL DEFAULT 0.0,
        bonus_awarded INTEGER DEFAULT 0,
        phone TEXT
    )
    """)
    conn.commit()
    conn.close()
```   

__Создаёт таблицу users__  
**Примечание** Бот использует SQLite для хранения информации о пользователях.  

___

__Возвращает данные пользователя по user_id в виде словаря или None, если пользователь не найден.__
```
def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None
```
___

__Создаёт нового пользователя или обновляет имя существующего.
Новые пользователи по умолчанию активны (is_active=1) и не участвуют в партнерской программе (is_partner=0).__
```
def create_or_update_user(user_id: int, username: str = ""):
    user_record = get_user(user_id)
    if not user_record:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (user_id, username, is_active, is_partner) VALUES (?, ?, 1, 0)", (user_id, username)
        )
        conn.commit()
        conn.close()
    else:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "UPDATE users SET username=? WHERE user_id=?", (username, user_id)
        )
        conn.commit()
        conn.close()
```
___
__Обновляет данные пользователя, указанные в kwargs (например, is_active, phone, available_to_withdraw).
Если пользователь не существует, создаёт его.__
```
def update_user(user_id: int, **kwargs):
    if not get_user(user_id):
        create_or_update_user(user_id)
    set_clause = ", ".join([f"{k}=?" for k in kwargs.keys()])
    values = list(kwargs.values())
    values.append(user_id)
    sql = f"UPDATE users SET {set_clause} WHERE user_id=?"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(sql, values)
    conn.commit()
    conn.close()
```
___

__Проверяет, активен ли пользователь__

```
def check_member_status(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    return (user["is_active"] == 1)
```

___

__Возвращает статистику по партнерской программе для пользователя.__

```
def get_partner_stats(user_id: int) -> dict:
    user = get_user(user_id)
    if not user:
        return {}
    return {
        "referrals_count": user["referrals_count"],
        "paid_referrals_count": user["paid_referrals_count"],
        "total_earned": user["total_earned"],
        "available_to_withdraw": user["available_to_withdraw"],
        "bonus_awarded": user["bonus_awarded"]
    }
```
___
__Возвращает список всех пользователей в виде словарей.__
```
def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]
```


# Клавиатуры

```
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("КАНАЛЫ И ГРУППЫ"))
    kb.add(KeyboardButton("ЗАКАЗАТЬ УСЛУГИ"))
    kb.add(KeyboardButton("ПАРТНЕРСКАЯ ПРОГРАММА"))
    return kb
```
**Создаёт меню с тремя кнопками "Каналы и группы", "Заказать услуги",
"Партнерская программа"**

___

__Создаёт клавиатуру для запроса номера телефона с кнопками "Отправить номер телефона" (запрашивает контакт) и "⏩" (пропуск).__
```
def request_phone_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(
        KeyboardButton("☎ Отправить номер телефона", request_contact=True),
        KeyboardButton("⏩")
    )
    return kb
```
# Обработчики команд и сообщений

__Инициализирует базу данных.
Создаёт или обновляет пользователя.
Проверяет, есть ли реферальный ID в аргументе команды, и если да, сохраняет его как referrer.
Отправляет приветственное сообщение с запросом номера телефона.__
```
@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    init_db()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "друг"
    create_or_update_user(user_id, username)

    parts = message.text.split()
    if len(parts) > 1:
        referrer_str = parts[1]
        try:
            referrer_id = int(referrer_str)
            if referrer_id != user_id:
                current_user = get_user(user_id)
                if current_user and current_user["referrer"] is None:
                    update_user(user_id, referrer=referrer_id)
        except ValueError:
            pass

    welcome_text = (
        f"Привет, <b>{first_name}</b>! ✋\n\n"
        "Меня зовут Виктор, приветствую тебя в боте моей экосистемы.\n\n"
        "Здесь ты можешь:\n"
        "- ознакомиться с нашими продуктами,\n"
        "- оставить заявку на консультацию,\n"
        "- узнать больше о автоматизации и путешествиях.\n\n"
        "Для регистрации, пожалуйста, отправьте свой номер по кнопке ниже"
    )
    await message.answer(welcome_text, reply_markup=request_phone_kb())
```

___
__Обрабатывает текст, фото или видео для рассылки всем активным пользователям.
Логирует успешные и неуспешные отправки.
По завершении сообщает статистику (успешно/ошибки).__

```
@dp.message_handler(commands=["broadcast"])
async def cmd_broadcast(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return
    await message.answer(
        "Отправьте мне сообщение (текст/фото/видео), которое хотите разослать всем пользователям"
    )
    await BroadcastState.awaiting_content.set()
```
__Доступна только администраторам (ADMIN_ID).
Запрашивает контент для массовой рассылки__

___
```
@dp.message_handler(state=BroadcastState.awaiting_content, content_types=types.ContentType.ANY)
async def handle_broadcast_content(message: types.Message, state: FSMContext):
    if message.from_user.id not in ADMIN_ID:
        await state.finish()
        return
    users = [u for u in get_all_users() if u["is_active"] == 1]
    success, failed = 0, 0
    for user in users:
        try:
            if message.text:
                await bot.send_message(user["user_id"], message.text)
            elif message.photo:
                await bot.send_photo(user["user_id"], photo=message.photo[-1].file_id, caption=message.caption or "")
            elif message.video:
                await bot.send_video(user["user_id"], video=message.video.file_id, caption=message.caption or "")
            else:
                continue
            success += 1
        except Exception as e:
            logging.warning(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")
            failed += 1
    await message.answer(f"Рассылка завершена успешно ✅\n: {success}\nОшибка: {failed}")
    await state.finish()
```

___
__Сохраняет номер телефона пользователя и активирует его (is_active=1).
Показывает основное меню с ресурсами.__
```
@dp.message_handler(content_types=types.ContentType.CONTACT)
async def handle_contact(message: types.Message):
    phone = message.contact.phone_number
    update_user(message.from_user.id, is_active=1, phone=phone)
    await show_main_resources(message)
```
___
__Если пользователь пропускает ввод номера, активирует его и показывает основное меню.__
```
@dp.message_handler(lambda m: m.text == "⏩")
async def handle_skip(message: types.Message):
    update_user(message.from_user.id, is_active=1)
    await show_main_resources(message)
```
___
__Показывает инлайн-клавиатуру с ссылками на социальные сети, услуги и партнерскую программу.__
```async def show_main_resources(message: types.Message):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📣VK", url="https://m.vk.com/suppervictor"),
        InlineKeyboardButton("📸INSTAGRAM", url="https://www.instagram.com/supervictorr?igsh=NWw2MDRrcDBtMjdw&utm_source=qr"),
        InlineKeyboardButton("📢TELEGRAM-КАНАЛ", url="https://t.me/supervictor"),
        InlineKeyboardButton("🎬TIKTOK", url="https://www.tiktok.com/@superv1ctor?_t=ZS-8yaq0BNfI88&_r=1"),
        InlineKeyboardButton("▶️YOUTUBE", url="https://m.youtube.com/@FrAnkYbboy61"),
        InlineKeyboardButton("🚀ЗАКАЗАТЬ УСЛУГИ", url="https://t.me/verusya1287"),
        InlineKeyboardButton("🤝ПАРТНЕРСКАЯ ПРОГРАММА", callback_data="open_partners")
    )
    await message.answer("<b>Выбери, что тебе интересно:</b>", reply_markup=kb)
```
___
__Проверяет, является ли пользователь партнером. Если да, показывает панель партнера. Если нет, предлагает активировать программу.__

```
@dp.message_handler(lambda m: m.text == "ПАРТНЕРСКАЯ ПРОГРАММА")
async def partner_menu(user_id: int, username: str = ""):
    user_data = get_user(user_id)
    if not user_data:
        create_or_update_user(user_id, username=username or "")
        user_data = get_user(user_id)
    if int(user_data.get("is_partner") or 0) == 1:
        await show_partner_dashboard(user_id)
    else:
        kb = InlineKeyboardMarkup()
        kb.add(InlineKeyboardButton("Активировать программу", callback_data="activate_partner"))
        await bot.send_message(
            user_id,
            "Вы еще не являетесь партнером. Хотите активировать партнерскую программу",
            reply_markup=kb
        )
```
___

__Активирует партнерскую программу для пользователя и показывает панель партнера.__

```
async def show_partner_dashboard(user_id: int):
    partner_link = f"https://t.me/{BOT_USERNAME}?start={user_id}"
    stats = get_partner_stats(user_id)
    referrals_count = stats.get("referrals_count", 0)
    paid_referrals_count = stats.get("paid_referrals_count", 0)
    total_earned = stats.get("total_earned", 0.0)
    available_to_withdraw = stats.get("available_to_withdraw", 0.0)
    qr_image = generate_qr_code(partner_link)
    text = (
        "<b>ПАРТНЕРСКАЯ ПРОГРАММА </b>\n\n"
        "🤝Приводи друзей и зарабатывай <b>20%</b> с их покупок!\n\n"
        f"🔗 <b>Твоя партнерская ссылка:</b>\n{partner_link}\n\n"
        "📊<b>СТАТИСТИКА</b>\n"
        f"◉ ПРИВЕДЕНО ЛЮДЕЙ: {referrals_count}\n"
        f"◉ ЛЮДЕЙ, ОПЛАТИВШИХ ПОДПИСКУ: {paid_referrals_count}\n"
        f"◉ ВСЕГО ЗАРАБОТАНО: {total_earned:.2f}₽\n"
        f"◉ ДОСТУПНО К ВЫВОДУ: {available_to_withdraw:.2f}₽"
    )
    kb = InlineKeyboardMarkup(row_width=2)
    share_url = f"https://t.me/share/url?url={urllib.parse.quote(partner_link)}"
    btn_share = InlineKeyboardButton("Поделиться ссылкой", url=share_url)
    btn_withdraw = InlineKeyboardButton("Вывод средств", callback_data="withdraw_funds")
    kb.add(btn_share, btn_withdraw)
    await bot.send_photo(
        chat_id=user_id,
        photo=qr_image,
        caption=text,
        parse_mode="HTML",
        reply_markup=kb
    )
```
___

__Проверяет, есть ли средства для вывода. Если да, просит написать администратору.__
```
@dp.callback_query_handler(lambda c: c.data == "withdraw_funds")
async def on_withdraw_funds(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    stats = get_partner_stats(user_id)
    available = stats.get("available_to_withdraw", 0.0)
    if available <= 0:
        await callback.answer("У вас пока нет доступных средств для вывода", show_alert=True)
        return
    text = (
        "Напишите, пожалуйста, в личные сообщения @supervictorrr:\n"
        "\"Здравствуйте, я хочу вывести X\""
    )
    await callback.message.edit_text(text)
    await callback.answer()
```
# Админ-команды

__Выводит список всех пользователей с их данными.__
```
@dp.message_handler(commands=["admin_all"])
async def cmd_admin_all(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return
    users = get_all_users()
    if not users:
        await message.answer("В базе нет ни одного пользователя")
        return
    lines = []
    for u in users:
        lines.append(
            f"ID: {u['user_id']}, user: @{u['username']}, active={u['is_active']}, "
            f"partner={u['is_partner']}, earned={u['total_earned']}, balance={u['available_to_withdraw']}"
        )
    text = "<b>ВСЕ ПОЛЬЗОВАТЕЛИ:</b>\n" + "\n".join(lines)
    await message.answer(text)
```
___

__ыводит подробную информацию о пользователе по его user_id.__
```
@dp.message_handler(commands=["admin_user"])
async def cmd_admin_user(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("Использование: /admin_user <user_id>")
        return
    try:
        uid = int(parts[1])
    except ValueError:
        await message.answer("Неверный user_id")
        return
    user = get_user(uid)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    text = (
        f"<b>Пользователь {uid}</b>\n\n"
        f"Username: {user['username']}\n"
        f"is_active: {user['is_active']}\n"
        f"is_partner: {user['is_partner']}\n"
        f"referrer: {user['referrer']}\n"
        f"referrals_count: {user['referrals_count']}\n"
        f"paid_referrals_count: {user['paid_referrals_count']}\n"
        f"total_earned {user['total_earned']}\n"
        f"available_to_withdraw: {user['available_to_withdraw']}\n"
    )
    await message.answer(text)
```
___

__Начисляет указанную сумму на баланс пользователя__
```
@dp.message_handler(commands=["admin_add_balance"])
async def cmd_admin_add_balance(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Использование: /admin_add_balance <user_id> <sum>")
        return
    try:
        uid = int(parts[1])
        amount = float(parts[2])
    except ValueError:
        await message.answer("Неверный формат аргументов.")
        return
    user = get_user(uid)
    if not user:
        await message.answer("Пользователь не найден.")
        return
    new_balance = user["available_to_withdraw"] + amount
    new_earned = user["total_earned"] + amount
    update_user(uid, available_to_withdraw=new_balance, total_earned=new_earned)
    await message.answer(
        f"Начислено {amount:.2f} руб пользователю {uid}.\n"
        f"Новый баланс: {new_balance:.2f}, всего заработано: {new_earned:.2f}"
    )
```
___

__Списывает указанную сумму с баланса пользователя.__

```
@dp.message_handler(commands=["admin_withdraw"])
async def cmd_admin_withdraw(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Использование: /admin_withdraw <user_id> <sum>")
        return
    try:
        uid = int(parts[1])
        amount = float(parts[2])
    except ValueError:
        await message.answer("Неверный формат аргументов.")
        return
    user = get_user(uid)
    if not user:
        await message.answer("Пользователь не найден")
        return
    balance = user["available_to_withdraw"]
    if amount > balance:
        await message.answer("Недостаточно средств на балансе")
        return
    new_balance = balance - amount
    update_user(uid, available_to_withdraw=new_balance)
    await message.answer(
        f"Списано {amount:.2f} руб у пользователя {uid}.\n"
        f"Новый баланс: {new_balance:.2f}"
    )
```

# Генерация qr-кода
__Создаёт QR-код для переданной ссылки (например, реферальной).
Сохраняет изображение в байтовый поток (BytesIO) для отправки в Telegram.__
```
def generate_qr_code(link: str):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    bio = BytesIO()
    bio.name = 'qr.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio
```
# Запуск бота
__Инициализирует базу данных при запуске.
Запускает бота в режиме опроса, игнорируя старые обновления (skip_updates=True).__
```
if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
```
