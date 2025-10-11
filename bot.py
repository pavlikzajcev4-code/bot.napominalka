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

class BroadcastState(StatesGroup):
    awaiting_content = State()


logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(bot, storage=MemoryStorage())


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


def get_user(user_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None

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

def check_member_status(user_id: int) -> bool:
    user = get_user(user_id)
    if not user:
        return False
    return (user["is_active"] == 1)


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

def get_all_users():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


################# МЕНЮ ##################
def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("КАНАЛЫ И ГРУППЫ"))
    kb.add(KeyboardButton("ЗАКАЗАТЬ УСЛУГИ"))
    kb.add(KeyboardButton("ПАРТНЕРСКАЯ ПРОГРАММА"))
    return kb


def request_phone_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(
        KeyboardButton("☎ Отправить номер телефона", request_contact=True),
        KeyboardButton("⏩")
    )
    return kb

########## /start ###########

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    init_db()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or "друг"


    # is_active = check_member_status(user_id)
    # if is_active:
    create_or_update_user(user_id, username)

    # Проверяем аргумент (реферальный?)
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
    # else:
    #     await message.answer("У вас нет активной подписки. Обратитесь к администратору")

@dp.message_handler(commands=["broadcast"])
async def cmd_broadcast(message: types.Message):
    if message.from_user.id not in ADMIN_ID:
        return

    await message.answer(
        "Отправьте мне сообщение (текст/фото/видео), которое хотите разослать всем пользователям"
    )
#    dp.current_state(chat=message.chat.id, user=message.from_user.id).set_state("awaiting_broadcast_content")
    await BroadcastState.awaiting_content.set()


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
            logging.warning(f"Не удалось отправиить сообщение пользователю {user['user_id']}: {e}")
            failed += 1

    await message.answer(f"Рассылка завершена успешно ✅\n: {success}\Ошибка: {failed}")
    await state.finish()                                  







@dp.message_handler(content_types=types.ContentType.CONTACT)
async def handle_contact(message: types.Message):
    phone = message.contact.phone_number
    update_user(message.from_user.id, is_active=1, phone=phone)
    await show_main_resources(message)


@dp.message_handler(lambda m: m.text == "⏩")
async def handle_skip(message: types.Message):
    update_user(message.from_user.id, is_active=1)
    await show_main_resources(message)


async def show_main_resources(message: types. Message):
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("📣VK", url="https://m.vk.com/suppervictor"),
        #InlineKeyboardButton("👥VK(сообщество)", url="https://vk.com/club220568489"),
        InlineKeyboardButton("📸INSTAGRAM", url="https://www.instagram.com/supervictorr?igsh=NWw2MDRrcDBtMjdw&utm_source=qr"),
        InlineKeyboardButton("📢TELEGRAM-КАНАЛ", url="https://t.me/supervictor"),
        InlineKeyboardButton("🎬TIKTOK", url="https://www.tiktok.com/@superv1ctor?_t=ZS-8yaq0BNfI88&_r=1"),
        InlineKeyboardButton("▶️YOUTUBE", url="https://m.youtube.com/@FrAnkYbboy61"),
        InlineKeyboardButton("🚀ЗАКАЗАТЬ УСЛУГИ", url="https://t.me/verusya1287"),
        #InlineKeyboardButton("🌎ПОДРОБНЕЕ ОБО МНЕ", url="https://sergeygomenyuk.ru/"),
        #InlineKeyboardButton("✈️САЙТ БИЗНЕС-ТУРА", url="https://wbcantonfair.ru/"),
        InlineKeyboardButton("🤝ПАРТНЕРСКАЯ ПРОГРАММА", callback_data="open_partners")
    )

    await message.answer("<b>Выбери, что тебе интересно:</b>", reply_markup=kb)


@dp.callback_query_handler(lambda c: c.data == "open_partners")
async def open_partners_callback(callback: types.CallbackQuery):
    await partner_menu(callback.from_user.id, callback.from_user.username)
    await callback.answer()


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

@dp.callback_query_handler(lambda c: c.data == "activate_partner")
async def on_activate_partner(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    update_user(user_id, is_partner=1)
    
    await callback.answer("Партнерская программа активирована!")
    await callback.message.delete()

    await show_partner_dashboard(user_id)
    


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
    import  urllib.parse
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


@dp.message_handler(commands=["admin_all"])
async def cmd_admin_all(message: types.Message):
    logging.info(f"ADMIN COMMAND /admin_all from {message.from_user.id}")
    if message.from_user.id not in ADMIN_ID:
        logging.info("Not an admin!")
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



def generate_qr_code(link: str):
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    #Сохраняет картинку в байтовый поток
    bio = BytesIO()
    bio.name = 'qr.png'
    img.save(bio, 'PNG')
    bio.seek(0)
    return bio


if __name__ == "__main__":
    init_db()
    executor.start_polling(dp, skip_updates=True)
