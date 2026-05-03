import asyncio
import logging
import os
import random
import sqlite3
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, List

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# ==================== ГОРОДА ====================
class City:
    def __init__(self, id, name, emoji, min_level, taxi_price, description, crime_rate=0.1, income_mult=1.0, start_chance=0.1):
        self.id = id
        self.name = name
        self.emoji = emoji
        self.min_level = min_level
        self.taxi_price = taxi_price
        self.description = description
        self.crime_rate = crime_rate
        self.income_mult = income_mult
        self.start_chance = start_chance

CITIES = {
    "newark": City("newark", "Нью-Арк", "🌆", 1, 25, "Промышленный город", 0.3, 1.0, 0.35),
    "moscow": City("moscow", "Москоу", "❄️", 3, 75, "Столица России", 0.2, 1.5, 0.25),
    "yerevan": City("yerevan", "Ереван", "⛰️", 2, 50, "Древний город", 0.08, 1.2, 0.15),
    "tokyo": City("tokyo", "Токио", "🗾", 4, 90, "Город будущего", 0.05, 1.8, 0.1),
    "losangeles": City("losangeles", "Лос-Анжела", "🌴", 5, 100, "Город ангелов", 0.15, 2.0, 0.08),
    "dubai": City("dubai", "Дубай", "🏜️", 8, 200, "Город роскоши", 0.02, 4.0, 0.005)
}

# ==================== ПРЕДМЕТЫ ====================
FOOD = {
    "bread": {"name": "🍞 Хлеб", "price": 20, "hunger": 20},
    "doshirak": {"name": "🍜 Доширак", "price": 35, "hunger": 30},
    "shaurma": {"name": "🌯 Шаурма", "price": 150, "hunger": 50}
}

DRINKS = {
    "water": {"name": "💧 Вода", "price": 15, "thirst": 35},
    "coffee": {"name": "☕ Кофе", "price": 50, "thirst": 20, "energy": 25},
    "energy": {"name": "⚡ Энергетик", "price": 60, "thirst": 15, "energy": 45}
}

MEDICAL = {
    "bandage": {"name": "🩹 Бинт", "price": 100, "health": 20},
    "painkiller": {"name": "💊 Обезбол", "price": 200, "health": 35},
    "antibiotic": {"name": "💉 Антибиотик", "price": 500, "health": 60}
}

WEAPONS = {
    "knife": {"name": "🔪 Нож", "price": 300, "damage": 15},
    "bat": {"name": "🏏 Бита", "price": 500, "damage": 20},
    "pistol": {"name": "🔫 Пистолет", "price": 1500, "damage": 35, "illegal": True},
    "ak47": {"name": "🔫 АК-47", "price": 5000, "damage": 70, "illegal": True}
}

# ==================== БАЗА ДАННЫХ ====================
class Database:
    def __init__(self, db_path="game.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._create_tables()
    
    def _create_tables(self):
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                money INTEGER DEFAULT 500,
                energy INTEGER DEFAULT 100,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                reputation INTEGER DEFAULT 0,
                current_city TEXT DEFAULT 'newark',
                house_id TEXT,
                last_work TIMESTAMP,
                referral_code TEXT UNIQUE,
                total_referrals INTEGER DEFAULT 0,
                hunger INTEGER DEFAULT 100,
                thirst INTEGER DEFAULT 100,
                health INTEGER DEFAULT 100,
                sleep INTEGER DEFAULT 100,
                mood INTEGER DEFAULT 100,
                weapon TEXT DEFAULT 'fists',
                crimes INTEGER DEFAULT 0,
                stolen INTEGER DEFAULT 0,
                gang_id INTEGER,
                gang_rank TEXT DEFAULT 'none'
            );
            
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_id TEXT,
                item_type TEXT,
                quantity INTEGER DEFAULT 1
            );
            
            CREATE TABLE IF NOT EXISTS gangs (
                gang_id INTEGER PRIMARY KEY AUTOINCREMENT,
                gang_name TEXT UNIQUE,
                gang_tag TEXT UNIQUE,
                owner_id INTEGER,
                gang_money INTEGER DEFAULT 0,
                max_members INTEGER DEFAULT 10
            );
        """)
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def create_user(self, user_id, username, first_name, ref=None):
        cities = list(CITIES.keys())
        weights = [CITIES[c].start_chance for c in cities]
        city = random.choices(cities, weights=weights, k=1)[0]
        money = random.choices([100, 250, 500, 750, 1000], weights=[0.1, 0.2, 0.4, 0.2, 0.1], k=1)[0]
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        ref_id = None
        if ref:
            self.cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (ref,))
            r = self.cursor.fetchone()
            if r and r[0] != user_id:
                ref_id = r[0]
        
        self.cursor.execute(
            "INSERT INTO users (user_id, username, first_name, money, current_city, referral_code, referred_by) VALUES (?,?,?,?,?,?,?)",
            (user_id, username, first_name, money, city, code, ref_id)
        )
        
        if ref_id:
            self.cursor.execute("UPDATE users SET money=money+50, total_referrals=total_referrals+1 WHERE user_id=?", (ref_id,))
            self.cursor.execute("UPDATE users SET money=money+25 WHERE user_id=?", (user_id,))
        
        self.conn.commit()
        return city, money
    
    def update(self, user_id, **kwargs):
        if not kwargs:
            return
        set_clause = ", ".join([f"{k}=?" for k in kwargs])
        values = list(kwargs.values()) + [user_id]
        self.cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id=?", values)
        self.conn.commit()
    
    def add_money(self, user_id, amount):
        self.cursor.execute("UPDATE users SET money=money+? WHERE user_id=?", (amount, user_id))
        self.conn.commit()
    
    def get_inventory(self, user_id):
        self.cursor.execute("SELECT * FROM inventory WHERE user_id=? AND quantity>0", (user_id,))
        return [dict(r) for r in self.cursor.fetchall()]
    
    def add_item(self, user_id, item_id, item_type, qty=1):
        self.cursor.execute("SELECT id, quantity FROM inventory WHERE user_id=? AND item_id=?", (user_id, item_id))
        row = self.cursor.fetchone()
        if row:
            self.cursor.execute("UPDATE inventory SET quantity=quantity+? WHERE id=?", (qty, row['id']))
        else:
            self.cursor.execute("INSERT INTO inventory (user_id,item_id,item_type,quantity) VALUES (?,?,?,?)", (user_id, item_id, item_type, qty))
        self.conn.commit()
    
    def use_item(self, user_id, item_id):
        self.cursor.execute("SELECT id, quantity FROM inventory WHERE user_id=? AND item_id=? AND quantity>0", (user_id, item_id))
        row = self.cursor.fetchone()
        if not row:
            return False
        if row['quantity'] > 1:
            self.cursor.execute("UPDATE inventory SET quantity=quantity-1 WHERE id=?", (row['id'],))
        else:
            self.cursor.execute("DELETE FROM inventory WHERE id=?", (row['id'],))
        self.conn.commit()
        return True
    
    def create_gang(self, name, tag, owner):
        try:
            self.cursor.execute("INSERT INTO gangs (gang_name,gang_tag,owner_id) VALUES (?,?,?)", (name, tag, owner))
            gid = self.cursor.lastrowid
            self.update(owner, gang_id=gid, gang_rank='leader')
            self.conn.commit()
            return gid
        except:
            return None
    
    def get_gang(self, gid):
        self.cursor.execute("SELECT * FROM gangs WHERE gang_id=?", (gid,))
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def get_members(self, gid):
        self.cursor.execute("SELECT user_id,first_name,level,gang_rank FROM users WHERE gang_id=? ORDER BY CASE gang_rank WHEN 'leader' THEN 1 WHEN 'vice' THEN 2 ELSE 3 END", (gid,))
        return [dict(r) for r in self.cursor.fetchall()]
    
    def leave_gang(self, user_id):
        u = self.get_user(user_id)
        if not u or not u['gang_id']:
            return False
        if u['gang_rank'] == 'leader':
            self.cursor.execute("DELETE FROM gangs WHERE gang_id=?", (u['gang_id'],))
            self.cursor.execute("UPDATE users SET gang_id=NULL, gang_rank='none' WHERE gang_id=?", (u['gang_id'],))
        else:
            self.cursor.execute("UPDATE users SET gang_id=NULL, gang_rank='none' WHERE user_id=?", (user_id,))
        self.conn.commit()
        return True

db = Database()

# ==================== КЛАВИАТУРЫ ====================
def main_menu():
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="💼 РАБОТА"), KeyboardButton(text="🎰 КАЗИНО"))
    builder.row(KeyboardButton(text="🛒 МАГАЗИН"), KeyboardButton(text="🏠 ДОМ"))
    builder.row(KeyboardButton(text="🗺 ГОРОД"), KeyboardButton(text="🎒 ИНВЕНТАРЬ"))
    builder.row(KeyboardButton(text="🏴 БАНДА"), KeyboardButton(text="🕵️ КРИМИНАЛ"))
    builder.row(KeyboardButton(text="📊 СТАТУС"), KeyboardButton(text="🗺 КАРТА"))
    builder.row(KeyboardButton(text="🏆 ТОП"), KeyboardButton(text="❓ ПОМОЩЬ"))
    return builder.as_markup(resize_keyboard=True)

def back_button():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Назад", callback_data="back")
    return builder.as_markup()

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

# ==================== /start ====================
@router.message(Command("start"))
async def start(message: Message, command: CommandObject = None):
    uid = message.from_user.id
    name = message.from_user.first_name or "Игрок"
    uname = message.from_user.username or "Player"
    
    user = db.get_user(uid)
    
    if not user:
        ref = command.args if command.args else None
        city_id, money = db.create_user(uid, uname, name, ref)
        city = CITIES[city_id]
        text = f"🎉 *{name}, ты в {city.emoji} {city.name}!*\n\n💰 ${money}\n\nИспользуй кнопки меню!"
    else:
        city = CITIES.get(user['current_city'], CITIES['newark'])
        text = f"👋 *{name}*\n📍 {city.emoji} {city.name}\n💰 ${user['money']}"
    
    await message.answer(text, reply_markup=main_menu(), parse_mode="Markdown")

# ==================== КНОПКИ ГЛАВНОГО МЕНЮ ====================

@router.message(F.text == "💼 РАБОТА")
async def work_btn(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        return await message.answer("❌ /start сначала!")
    
    builder = InlineKeyboardBuilder()
    jobs = [("📦 Курьер", 30), ("🍽 Официант", 45), ("💂 Охранник", 60), ("👔 Менеджер", 80), ("💻 Разработчик", 120)]
    for name, pay in jobs:
        builder.button(text=f"{name} (+${pay})", callback_data=f"work_{pay}")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    
    await message.answer("💼 *Выбери работу:*", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("work_"))
async def do_work(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    pay = int(callback.data.split("_")[1])
    
    if user['energy'] < 20:
        return await callback.answer("❌ Мало энергии!", show_alert=True)
    
    if user['last_work']:
        last = datetime.fromisoformat(user['last_work'])
        if (datetime.now() - last).seconds < 900:
            return await callback.answer("⏳ Подожди 15 минут!", show_alert=True)
    
    city = CITIES.get(user['current_city'], CITIES['newark'])
    total = int(pay * city.income_mult)
    
    db.add_money(user['user_id'], total)
    db.update(user['user_id'], last_work=datetime.now().isoformat(), energy=user['energy']-20, xp=user['xp']+10)
    
    await callback.message.edit_text(f"✅ *Работа выполнена!*\n💰 +${total}", parse_mode="Markdown")

@router.message(F.text == "🎰 КАЗИНО")
async def casino_btn(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🎲 Рулетка ($50)", callback_data="casino_roulette")
    builder.button(text="🎰 Слоты ($10)", callback_data="casino_slots")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(2)
    await message.answer("🎰 *Казино*", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "casino_roulette")
async def roulette(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    if u['money'] < 50: return await callback.answer("❌ $50 нужно!", show_alert=True)
    win = random.random() < 0.4
    w = random.choice([100, 200, 500]) if win else -50
    db.update(callback.from_user.id, money=u['money']+w)
    await callback.message.edit_text(f"🎲 {'Выигрыш' if win else 'Проигрыш'}: ${abs(w)}\n💰 ${u['money']+w}", parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "casino_slots")
async def slots(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    if u['money'] < 10: return await callback.answer("❌ $10 нужно!", show_alert=True)
    s = ["🍒","🍋","🍊","⭐","💎","7️⃣"]
    r = [random.choice(s) for _ in range(3)]
    if r[0]==r[1]==r[2]: win, txt = 100, "ДЖЕКПОТ! +$100"
    elif len(set(r))==2: win, txt = 20, "Повезло! +$20"
    else: win, txt = -10, "Мимо! -$10"
    db.update(callback.from_user.id, money=u['money']+win)
    await callback.message.edit_text(f"🎰 [{'|'.join(r)}]\n{txt}\n💰 ${u['money']+win}", parse_mode="Markdown")

@router.message(F.text == "🛒 МАГАЗИН")
async def shop_btn(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🍞 Еда", callback_data="shop_food")
    builder.button(text="💧 Напитки", callback_data="shop_drinks")
    builder.button(text="💊 Медикаменты", callback_data="shop_medical")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(2)
    await message.answer("🛒 *Магазин*", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data in ["shop_food", "shop_drinks", "shop_medical"])
async def shop_cat(callback: CallbackQuery):
    cat = callback.data.split("_")[1]
    items = {"food": FOOD, "drinks": DRINKS, "medical": MEDICAL}[cat]
    names = {"food": "🍞 Еда", "drinks": "💧 Напитки", "medical": "💊 Медикаменты"}
    
    builder = InlineKeyboardBuilder()
    text = f"{names[cat]}:\n\n"
    for iid, item in items.items():
        text += f"{item['name']} — ${item['price']}\n"
        builder.button(text=f"{item['name']} (${item['price']})", callback_data=f"buy_{iid}")
    builder.button(text="🔙 Назад", callback_data="back_to_shop")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_item(callback: CallbackQuery):
    item_id = callback.data.replace("buy_", "")
    user = db.get_user(callback.from_user.id)
    
    item = FOOD.get(item_id) or DRINKS.get(item_id) or MEDICAL.get(item_id)
    if not item: return await callback.answer("❌ Нет товара!", show_alert=True)
    
    if user['money'] < item['price']: return await callback.answer(f"❌ ${item['price']} нужно!", show_alert=True)
    
    db.add_money(user['user_id'], -item['price'])
    itype = "food" if item_id in FOOD else "drink" if item_id in DRINKS else "medical"
    db.add_item(user['user_id'], item_id, itype)
    
    await callback.answer(f"✅ {item['name']} куплен!", show_alert=True)

@router.callback_query(lambda c: c.data == "back_to_shop")
async def back_shop(callback: CallbackQuery):
    builder = InlineKeyboardBuilder()
    builder.button(text="🍞 Еда", callback_data="shop_food")
    builder.button(text="💧 Напитки", callback_data="shop_drinks")
    builder.button(text="💊 Медикаменты", callback_data="shop_medical")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(2)
    await callback.message.edit_text("🛒 *Магазин*", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.message(F.text == "🏠 ДОМ")
async def house_btn(message: Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 Квартира ($500)", callback_data="house_apartment")
    builder.button(text="🏡 Дом ($2000)", callback_data="house_house")
    builder.button(text="🏰 Вилла ($10000)", callback_data="house_villa")
    builder.button(text="💰 Собрать доход", callback_data="house_collect")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    await message.answer("🏠 *Недвижимость*", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("house_"))
async def house_act(callback: CallbackQuery):
    act = callback.data.replace("house_", "")
    u = db.get_user(callback.from_user.id)
    
    if act == "collect":
        if not u['house_id']: return await callback.answer("❌ Нет дома!", show_alert=True)
        inc = {"apartment": 10, "house": 40, "villa": 200}.get(u['house_id'], 10)
        db.add_money(u['user_id'], inc)
        return await callback.answer(f"💰 +${inc}!", show_alert=True)
    
    prices = {"apartment": 500, "house": 2000, "villa": 10000}
    if u['money'] < prices[act]: return await callback.answer(f"❌ ${prices[act]} нужно!", show_alert=True)
    db.add_money(u['user_id'], -prices[act])
    db.update(u['user_id'], house_id=act)
    await callback.answer("✅ Куплен!", show_alert=True)

@router.message(F.text == "🗺 ГОРОД")
async def city_btn(message: Message):
    u = db.get_user(message.from_user.id)
    cid = u['current_city']
    city = CITIES.get(cid, CITIES['newark'])
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏪 Супермаркет", callback_data=f"loc_shop_{cid}")
    builder.button(text="🏥 Больница", callback_data=f"loc_hospital_{cid}")
    builder.button(text="🔫 Оружейный", callback_data=f"loc_weapons_{cid}")
    builder.button(text="🌑 Чёрный рынок", callback_data=f"loc_black_{cid}")
    builder.button(text="🍻 Бар", callback_data=f"loc_bar_{cid}")
    builder.button(text="🚔 Полиция", callback_data=f"loc_police_{cid}")
    builder.button(text="🏠 Домой", callback_data=f"loc_home_{cid}")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(2)
    
    await message.answer(f"🏙 *{city.emoji} {city.name}*\nКуда идём?", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("loc_"))
async def location(callback: CallbackQuery):
    parts = callback.data.split("_")
    loc = parts[1]
    cid = parts[2]
    u = db.get_user(callback.from_user.id)
    
    if loc == "shop":
        await back_shop(callback)
        return
    
    actions = {
        "hospital": ("🏥 Больница", [("💊 Лечить ($500)", f"heal_{cid}")]),
        "weapons": ("🔫 Оружейный", [(f"{w['name']} (${w['price']})", f"buyw_{wid}_{cid}") for wid, w in WEAPONS.items() if not w.get('illegal')]),
        "black": ("🌑 Чёрный рынок", [(f"{w['name']} (${int(w['price']*0.6)})", f"buyw_{wid}_{cid}") for wid, w in WEAPONS.items() if w.get('illegal')]),
        "bar": ("🍻 Бар", [("🍺 Выпить ($20)", f"bar_drink_{cid}"), ("👊 Драка", f"bar_fight_{cid}")]),
        "police": ("🚔 Полиция", [("💰 Взятка ($100)", f"bribe_{cid}")]),
        "home": ("🏠 Дом", [("😴 Спать", f"sleep_{cid}")])
    }
    
    if loc not in actions:
        return await callback.answer("🚧 В разработке!", show_alert=True)
    
    if loc == "black" and u['reputation'] > -10:
        return await callback.answer("❌ Репутация < -10 нужна!", show_alert=True)
    
    title, btns = actions[loc]
    builder = InlineKeyboardBuilder()
    for txt, cb in btns:
        builder.button(text=txt, callback_data=cb)
    builder.button(text="🔙 Назад", callback_data=f"back_city_{cid}")
    builder.adjust(1)
    
    await callback.message.edit_text(f"{title}", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("heal_"))
async def heal(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    if u['money'] < 500: return await callback.answer("❌ $500 нужно!", show_alert=True)
    db.add_money(u['user_id'], -500)
    db.update(u['user_id'], health=100)
    await callback.answer("✅ Здоровье 100%!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("buyw_"))
async def buy_weapon(callback: CallbackQuery):
    parts = callback.data.split("_")
    wid = parts[1]
    cid = parts[2]
    u = db.get_user(callback.from_user.id)
    w = WEAPONS.get(wid)
    if not w: return await callback.answer("❌ Нет!", show_alert=True)
    
    city = CITIES.get(cid, CITIES['newark'])
    price = int(w['price'] * city.income_mult * (0.6 if w.get('illegal') else 0.8))
    
    if u['money'] < price: return await callback.answer(f"❌ ${price} нужно!", show_alert=True)
    db.add_money(u['user_id'], -price)
    db.update(u['user_id'], weapon=wid)
    await callback.answer(f"✅ {w['name']} куплен!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("bar_drink_"))
async def bar_drink(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    if u['money'] < 20: return await callback.answer("❌ $20 нужно!", show_alert=True)
    db.add_money(u['user_id'], -20)
    db.update(u['user_id'], mood=min(100, u['mood']+20), thirst=min(100, u['thirst']+30))
    await callback.answer("🍺 Выпито! +Настроение", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("bar_fight_"))
async def bar_fight(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    if random.random() < 0.5:
        db.update(u['user_id'], xp=u['xp']+15, reputation=u['reputation']+5)
        await callback.answer("👊 Победа! +15 XP", show_alert=True)
    else:
        db.update(u['user_id'], health=max(10, u['health']-20))
        await callback.answer("👊 Поражение! -20 HP", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("bribe_"))
async def bribe(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    if u['money'] < 100: return await callback.answer("❌ $100 нужно!", show_alert=True)
    db.add_money(u['user_id'], -100)
    await callback.answer("🤝 Договорились!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("sleep_"))
async def sleep(callback: CallbackQuery):
    db.update(callback.from_user.id, sleep=100, energy=100)
    await callback.answer("😴 Поспал! +Энергия +Сон", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("back_city_"))
async def back_city(callback: CallbackQuery):
    cid = callback.data.split("_")[2]
    city = CITIES.get(cid, CITIES['newark'])
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏪 Супермаркет", callback_data=f"loc_shop_{cid}")
    builder.button(text="🏥 Больница", callback_data=f"loc_hospital_{cid}")
    builder.button(text="🔫 Оружейный", callback_data=f"loc_weapons_{cid}")
    builder.button(text="🌑 Чёрный рынок", callback_data=f"loc_black_{cid}")
    builder.button(text="🍻 Бар", callback_data=f"loc_bar_{cid}")
    builder.button(text="🚔 Полиция", callback_data=f"loc_police_{cid}")
    builder.button(text="🏠 Домой", callback_data=f"loc_home_{cid}")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(2)
    
    await callback.message.edit_text(f"🏙 *{city.emoji} {city.name}*", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.message(F.text == "🎒 ИНВЕНТАРЬ")
async def inv_btn(message: Message):
    u = db.get_user(message.from_user.id)
    items = db.get_inventory(u['user_id'])
    
    if not items:
        return await message.answer("🎒 *Пусто*\nКупи в магазине!", parse_mode="Markdown")
    
    builder = InlineKeyboardBuilder()
    text = "🎒 *Инвентарь:*\n\n"
    all_items = {**FOOD, **DRINKS, **MEDICAL}
    
    for item in items:
        data = all_items.get(item['item_id'], {})
        text += f"{data.get('name', item['item_id'])} x{item['quantity']}\n"
        builder.button(text=f"Использовать {data.get('name', item['item_id'])}", callback_data=f"use_{item['item_id']}")
    
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("use_"))
async def use_item(callback: CallbackQuery):
    item_id = callback.data.replace("use_", "")
    u = db.get_user(callback.from_user.id)
    
    if not db.use_item(u['user_id'], item_id):
        return await callback.answer("❌ Нет предмета!", show_alert=True)
    
    if item_id in FOOD:
        db.update(u['user_id'], hunger=min(100, u['hunger']+FOOD[item_id]['hunger']))
        await callback.answer(f"🍞 +{FOOD[item_id]['hunger']} голода", show_alert=True)
    elif item_id in DRINKS:
        d = DRINKS[item_id]
        upd = {'thirst': min(100, u['thirst']+d.get('thirst', 0))}
        if 'energy' in d: upd['energy'] = min(100, u['energy']+d['energy'])
        db.update(u['user_id'], **upd)
        await callback.answer("💧 Выпито!", show_alert=True)
    elif item_id in MEDICAL:
        db.update(u['user_id'], health=min(100, u['health']+MEDICAL[item_id]['health']))
        await callback.answer(f"💊 +{MEDICAL[item_id]['health']} HP", show_alert=True)

@router.message(F.text == "🏴 БАНДА")
async def gang_btn(message: Message):
    u = db.get_user(message.from_user.id)
    
    if u['gang_id']:
        g = db.get_gang(u['gang_id'])
        m = db.get_members(u['gang_id'])
        text = f"🏴 *{g['gang_name']} [{g['gang_tag']}]*\n👥 {len(m)}/{g['max_members']}\n\n"
        for mb in m:
            rk = {"leader": "👑", "vice": "🎩", "soldier": "🗡", "recruit": "🔰"}
            text += f"{rk.get(mb['gang_rank'], '🔰')} {mb['first_name']} Ур.{mb['level']}\n"
    else:
        text = "🏴 *Банды*\n\nНет банды.\nСоздать: /gang_create [имя] [тег]\n💰 Стоимость: $1000"
    
    builder = InlineKeyboardBuilder()
    if u['gang_id']:
        builder.button(text="🚪 Покинуть", callback_data="gang_leave")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.message(Command("gang_create"))
async def gang_create(message: Message):
    args = message.text.split()
    if len(args) < 2: return await message.answer("❌ /gang_create [имя] [тег]")
    
    u = db.get_user(message.from_user.id)
    if u['money'] < 1000: return await message.answer("❌ $1000 нужно!")
    if u['gang_id']: return await message.answer("❌ Ты уже в банде!")
    
    name = args[1]
    tag = args[2] if len(args) > 2 else name[:4].upper()
    
    gid = db.create_gang(name, tag, message.from_user.id)
    if gid:
        db.add_money(u['user_id'], -1000)
        await message.answer(f"✅ Банда *{name}* [{tag}] создана!", parse_mode="Markdown")
    else:
        await message.answer("❌ Имя или тег заняты!")

@router.callback_query(lambda c: c.data == "gang_leave")
async def gang_leave(callback: CallbackQuery):
    if db.leave_gang(callback.from_user.id):
        await callback.answer("🚪 Покинул банду!", show_alert=True)
        await callback.message.edit_text("✅ Ты вне банды.")
    else:
        await callback.answer("❌ Ошибка!", show_alert=True)

@router.message(F.text == "🕵️ КРИМИНАЛ")
async def crime_btn(message: Message):
    u = db.get_user(message.from_user.id)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔫 Ограбить игрока", callback_data="crime_player")
    builder.button(text="🏪 Ограбить магазин", callback_data="crime_store")
    builder.button(text="🚗 Угнать машину", callback_data="crime_car")
    builder.button(text="🏠 Кража со взломом", callback_data="crime_house")
    builder.button(text="💰 Продать краденое", callback_data="crime_sell")
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    
    text = f"🕵️ *Криминал*\n🗡 Оружие: {u['weapon']}\n📊 Преступлений: {u['crimes']}\n💰 Краденого: ${u['stolen']}"
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.message(Command("rob"))
async def rob_player(message: Message):
    args = message.text.split()
    if len(args) < 2: return await message.answer("❌ /rob [ID игрока]")
    
    try:
        vid = int(args[1])
    except:
        return await message.answer("❌ Неверный ID!")
    
    if vid == message.from_user.id: return await message.answer("❌ Нельзя себя!")
    
    victim = db.get_user(vid)
    if not victim: return await message.answer("❌ Игрок не найден!")
    if victim['money'] < 50: return await message.answer("❌ У жертвы < $50!")
    
    u = db.get_user(message.from_user.id)
    wd = WEAPONS.get(u['weapon'], {"damage": 5})['damage']
    vd = WEAPONS.get(victim['weapon'], {"damage": 5})['damage']
    chance = max(0.1, min(0.9, 0.3 + wd*0.01 - vd*0.005))
    
    if random.random() < chance:
        stolen = int(victim['money'] * random.uniform(0.1, 0.3))
        db.add_money(vid, -stolen)
        db.add_money(u['user_id'], stolen)
        db.update(u['user_id'], crimes=u['crimes']+1, stolen=u['stolen']+stolen)
        await message.answer(f"✅ +${stolen}!")
    else:
        fine = random.randint(50, 200)
        db.add_money(u['user_id'], -fine)
        await message.answer(f"🚔 Штраф: ${fine}")

@router.callback_query(lambda c: c.data in ["crime_store", "crime_car", "crime_house"])
async def crimes(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    ct = callback.data
    
    costs = {"crime_store": 30, "crime_car": 25, "crime_house": 40}
    if u['energy'] < costs[ct]: return await callback.answer("❌ Мало энергии!", show_alert=True)
    
    db.update(u['user_id'], energy=u['energy']-costs[ct])
    
    if random.random() < 0.35:
        loot = {"crime_store": (100,500), "crime_car": (200,800), "crime_house": (500,2000)}[ct]
        amount = random.randint(*loot)
        db.add_money(u['user_id'], amount)
        db.update(u['user_id'], crimes=u['crimes']+1, stolen=u['stolen']+amount)
        await callback.answer(f"✅ +${amount}!", show_alert=True)
    else:
        fine = random.randint(50, 300)
        db.add_money(u['user_id'], -fine)
        await callback.answer(f"🚔 Штраф: ${fine}", show_alert=True)

@router.callback_query(lambda c: c.data == "crime_sell")
async def sell_stolen(callback: CallbackQuery):
    u = db.get_user(callback.from_user.id)
    if u['stolen'] < 100: return await callback.answer("❌ Мало краденого!", show_alert=True)
    amount = int(u['stolen'] * 0.7)
    db.add_money(u['user_id'], amount)
    db.update(u['user_id'], stolen=0)
    await callback.answer(f"💰 +${amount}!", show_alert=True)

@router.message(F.text == "📊 СТАТУС")
async def status_btn(message: Message):
    u = db.get_user(message.from_user.id)
    city = CITIES.get(u['current_city'], CITIES['newark'])
    
    def bar(v):
        f = int(v/10)
        return "█"*f + "░"*(10-f)
    
    text = (
        f"📊 *Статус*\n\n"
        f"👤 {u['first_name']} Ур.{u['level']}\n"
        f"📍 {city.emoji} {city.name}\n\n"
        f"🍞 [{bar(u['hunger'])}] {u['hunger']}%\n"
        f"💧 [{bar(u['thirst'])}] {u['thirst']}%\n"
        f"❤️ [{bar(u['health'])}] {u['health']}%\n"
        f"😴 [{bar(u['sleep'])}] {u['sleep']}%\n"
        f"😊 [{bar(u['mood'])}] {u['mood']}%\n\n"
        f"💰 ${u['money']} ⚡ {u['energy']}\n"
        f"🗡 {u['weapon']} 🏠 {u['house_id'] or 'Нет'}"
    )
    await message.answer(text, reply_markup=back_button(), parse_mode="Markdown")

@router.message(F.text == "🗺 КАРТА")
async def map_btn(message: Message):
    u = db.get_user(message.from_user.id)
    cur = CITIES.get(u['current_city'], CITIES['newark'])
    
    builder = InlineKeyboardBuilder()
    text = f"🗺 *Карта*\n📍 {cur.emoji} {cur.name}\n\n"
    
    for cid, city in CITIES.items():
        if cid != u['current_city']:
            if u['level'] >= city.min_level:
                text += f"🟢 {city.emoji} {city.name} — 🚕 ${city.taxi_price}\n"
                builder.button(text=f"{city.emoji} {city.name}", callback_data=f"travel_{cid}")
            else:
                text += f"🔒 {city.emoji} {city.name} — Ур.{city.min_level}\n"
    
    builder.button(text="🔙 Назад", callback_data="back")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("travel_"))
async def travel(callback: CallbackQuery):
    cid = callback.data.replace("travel_", "")
    u = db.get_user(callback.from_user.id)
    city = CITIES.get(cid)
    
    if not city: return await callback.answer("❌ Город не найден!", show_alert=True)
    if u['level'] < city.min_level: return await callback.answer(f"❌ Ур.{city.min_level} нужен!", show_alert=True)
    if u['money'] < city.taxi_price: return await callback.answer(f"❌ ${city.taxi_price} нужно!", show_alert=True)
    
    db.add_money(u['user_id'], -city.taxi_price)
    db.update(u['user_id'], current_city=cid)
    
    await callback.message.edit_text(f"🚕 *{city.emoji} {city.name}!*\n{city.description}\n💰 -${city.taxi_price}", parse_mode="Markdown")

@router.message(F.text == "🏆 ТОП")
async def top_btn(message: Message):
    db.cursor.execute("SELECT first_name, money, level, current_city FROM users ORDER BY money DESC LIMIT 10")
    top = db.cursor.fetchall()
    
    text = "🏆 *Топ-10*\n\n"
    for i, p in enumerate(top, 1):
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        med = medals.get(i, f"{i}.")
        city = CITIES.get(p['current_city'], CITIES['newark'])
        text += f"{med} {p['first_name']} [{city.emoji}] — ${p['money']}\n"
    
    db.cursor.execute("SELECT COUNT(*)+1 FROM users WHERE money>(SELECT money FROM users WHERE user_id=?)", (message.from_user.id,))
    rank = db.cursor.fetchone()[0]
    text += f"\n📊 Ты: #{rank}"
    
    await message.answer(text, parse_mode="Markdown")

@router.message(F.text == "❓ ПОМОЩЬ")
@router.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "📚 *Помощь*\n\n"
        "💼 РАБОТА — заработок\n"
        "🎰 КАЗИНО — игры\n"
        "🛒 МАГАЗИН — товары\n"
        "🏠 ДОМ — недвижимость\n"
        "🗺 ГОРОД — локации\n"
        "🎒 ИНВЕНТАРЬ — вещи\n"
        "🏴 БАНДА — банды\n"
        "🕵️ КРИМИНАЛ — преступления\n"
        "📊 СТАТУС — показатели\n"
        "🗺 КАРТА — города\n"
        "🏆 ТОП — рейтинг\n\n"
        "/profile /gang_create /rob /ref",
        parse_mode="Markdown"
    )

@router.message(Command("profile"))
async def profile(message: Message):
    u = db.get_user(message.from_user.id)
    if not u: return await message.answer("❌ /start сначала!")
    city = CITIES.get(u['current_city'], CITIES['newark'])
    g = db.get_gang(u['gang_id']) if u['gang_id'] else None
    
    await message.answer(
        f"👤 *{u['first_name']}*\n"
        f"📍 {city.emoji} {city.name}\n"
        f"💰 ${u['money']} ⭐ Ур.{u['level']}\n"
        f"🏴 {g['gang_name'] if g else 'Нет'}\n"
        f"🗡 {u['weapon']} 🕵️ {u['crimes']} прест.",
        parse_mode="Markdown"
    )

@router.message(Command("ref"))
async def ref_cmd(message: Message):
    u = db.get_user(message.from_user.id)
    if not u: return await message.answer("❌ /start сначала!")
    bi = await bot.get_me()
    link = f"https://t.me/{bi.username}?start={u['referral_code']}"
    await message.answer(f"👥 *Рефералы*\n🔗 `{link}`\n📊 {u['total_referrals']} чел.", parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "back")
async def back(callback: CallbackQuery):
    await callback.message.edit_text("📋 *Меню*\nИспользуй кнопки внизу!", parse_mode="Markdown")

# ==================== ЗАПУСК ====================
async def main():
    logging.basicConfig(level=logging.INFO)
    
    await bot.set_my_commands([
        BotCommand(command="start", description="Начать"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="gang_create", description="Создать банду"),
        BotCommand(command="rob", description="Ограбить"),
        BotCommand(command="ref", description="Рефералы"),
    ])
    
    print("✅ Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
