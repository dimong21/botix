import asyncio
import logging
import os
import random
import sqlite3
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from enum import Enum

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
moscow_tz = pytz.timezone('Europe/Moscow')

# ==================== ГОРОДА ====================
class City:
    def __init__(self, id, name, emoji, country, min_level, living_cost,
                 taxi_price, description, crime_rate, disease_risk,
                 temperature, income_mult, start_chance, npc_count=5):
        self.id = id
        self.name = name
        self.emoji = emoji
        self.country = country
        self.min_level = min_level
        self.living_cost = living_cost
        self.taxi_price = taxi_price
        self.description = description
        self.crime_rate = crime_rate
        self.disease_risk = disease_risk
        self.temperature = temperature
        self.income_mult = income_mult
        self.start_chance = start_chance
        self.npc_count = npc_count

CITIES = {
    "newark": City("newark", "Нью-Арк", "🌆", "🇺🇸 США", 1, 10, 25,
                   "Суровый промышленный город. Высокая преступность.", 0.3, 0.08, 15, 1.0, 0.35, 8),
    "moscow": City("moscow", "Москоу", "❄️", "🇷🇺 Россия", 3, 35, 75,
                   "Величественная столица. Медведи — миф.", 0.2, 0.06, 5, 1.5, 0.25, 6),
    "yerevan": City("yerevan", "Ереван", "⛰️", "🇦🇲 Армения", 2, 20, 50,
                    "Древний город с вкусным кофе.", 0.08, 0.04, 20, 1.2, 0.15, 4),
    "tokyo": City("tokyo", "Токио", "🗾", "🇯🇵 Япония", 4, 45, 90,
                  "Город будущего.", 0.05, 0.03, 18, 1.8, 0.1, 5),
    "losangeles": City("losangeles", "Лос-Анжела", "🌴", "🇺🇸 США", 5, 50, 100,
                       "Город ангелов.", 0.15, 0.04, 25, 2.0, 0.08, 5),
    "london": City("london", "Лондон", "☔", "🇬🇧 Великобритания", 6, 60, 120,
                   "Финансовое сердце Европы.", 0.12, 0.05, 12, 2.5, 0.05, 4),
    "shanghai": City("shanghai", "Шанхай", "🏮", "🇨🇳 Китай", 7, 80, 150,
                     "Экономический гигант Азии.", 0.03, 0.07, 22, 3.0, 0.015, 3),
    "dubai": City("dubai", "Дубай", "🏜️", "🇦🇪 ОАЭ", 8, 100, 200,
                  "Город роскоши.", 0.02, 0.01, 35, 4.0, 0.005, 3)
}

# ==================== NPC ГЕНЕРАТОР ====================
class NPCNames:
    FIRST = [
        "Дмитрий", "Алексей", "Сергей", "Максим", "Артём", "Виктор", "Игорь",
        "Михаил", "Александр", "Владимир", "Джон", "Майкл", "Джеймс", "Роберт",
        "Такеши", "Хироши", "Кенджи", "Юки", "Пьер", "Жан", "Хуан", "Ли", "Чен",
        "Ахмед", "Омар", "Мохаммед", "Карим", "Сурен", "Армен", "Тигран", "Геворг"
    ]
    LAST = [
        "Иванов", "Петров", "Сидоров", "Кузнецов", "Смирнов", "Джонсон",
        "Смит", "Вильямс", "Браун", "Танака", "Сато", "Сузуки",
        "Ямамото", "Дюбуа", "Бернар", "Чжан", "Ли", "Ван", "Аль-Рашид",
        "Аль-Файед", "Мкртчян", "Оганесян", "Саркисян", "Акопян"
    ]
    
    @classmethod
    def random_name(cls):
        return f"{random.choice(cls.FIRST)} {random.choice(cls.LAST)}"

class NPC:
    def __init__(self, npc_id, name, city_id, level, money, weapon, activity):
        self.npc_id = npc_id
        self.name = name
        self.city_id = city_id
        self.level = level
        self.money = money
        self.weapon = weapon
        self.activity = activity
        self.hp = 100
        self.is_online = True
    
    def to_dict(self):
        return {
            "npc_id": self.npc_id,
            "name": self.name,
            "city_id": self.city_id,
            "level": self.level,
            "money": self.money,
            "weapon": self.weapon,
            "activity": self.activity,
            "hp": self.hp,
            "is_online": self.is_online
        }

class NPCManager:
    def __init__(self):
        self.npcs: Dict[int, NPC] = {}
        self._generate_initial_npcs()
    
    def _generate_initial_npcs(self):
        """Генерация NPC для всех городов"""
        npc_id = 1000
        for city_id, city in CITIES.items():
            for _ in range(city.npc_count):
                name = NPCNames.random_name()
                level = random.randint(city.min_level, city.min_level + 5)
                money = random.randint(100, 5000)
                weapon = random.choice(['fists', 'knife', 'bat', 'pistol'])
                activity = random.choice(['working', 'walking', 'drinking', 'trading'])
                
                npc = NPC(npc_id, name, city_id, level, money, weapon, activity)
                self.npcs[npc_id] = npc
                npc_id += 1
    
    def get_npcs_in_city(self, city_id: str) -> List[NPC]:
        """Получить NPC в городе"""
        return [npc for npc in self.npcs.values() if npc.city_id == city_id and npc.is_online]
    
    def get_npc(self, npc_id: int) -> Optional[NPC]:
        return self.npcs.get(npc_id)
    
    def update_npc_activities(self):
        """Обновить активности NPC"""
        for npc in self.npcs.values():
            if random.random() < 0.3:
                npc.activity = random.choice(['working', 'walking', 'drinking', 'trading', 'sleeping'])
            npc.money += random.randint(-50, 100)
            npc.money = max(0, npc.money)
            npc.hp = min(100, npc.hp + random.randint(-5, 5))
            if npc.hp <= 0:
                npc.hp = 50
                npc.money = max(0, npc.money - 100)
    
    def rob_npc(self, player_id: int, npc_id: int, player_weapon: str) -> Dict:
        """Ограбить NPC"""
        npc = self.get_npc(npc_id)
        if not npc:
            return {"success": False, "message": "NPC не найден!"}
        
        if npc.hp <= 0:
            return {"success": False, "message": "NPC без сознания!"}
        
        weapon_damage = {"fists": 5, "knife": 15, "bat": 20, "pistol": 35, "shotgun": 50, "ak47": 70}
        player_dmg = weapon_damage.get(player_weapon, 5)
        npc_dmg = weapon_damage.get(npc.weapon, 5)
        
        success_chance = (player_dmg / (player_dmg + npc_dmg)) * 0.8
        success = random.random() < success_chance
        
        if success:
            stolen = int(npc.money * random.uniform(0.1, 0.4))
            npc.money -= stolen
            npc.hp -= random.randint(10, 30)
            return {"success": True, "message": f"✅ Ограблен {npc.name}! +${stolen}", "amount": stolen}
        else:
            npc.hp -= random.randint(5, 15)
            return {"success": False, "message": f"❌ {npc.name} дал отпор!", "amount": 0}

npc_manager = NPCManager()

# ==================== ПРЕДМЕТЫ ====================
FOOD_ITEMS = {
    "bread": {"name": "🍞 Хлеб", "price": 20, "hunger": 20},
    "doshirak": {"name": "🍜 Доширак", "price": 35, "hunger": 30},
    "shaurma": {"name": "🌯 Шаурма", "price": 150, "hunger": 50},
    "steak": {"name": "🥩 Стейк", "price": 500, "hunger": 80},
    "sushi": {"name": "🍣 Суши", "price": 300, "hunger": 45},
    "pizza": {"name": "🍕 Пицца", "price": 400, "hunger": 60}
}

DRINK_ITEMS = {
    "water": {"name": "💧 Вода", "price": 15, "thirst": 35},
    "coffee": {"name": "☕ Кофе", "price": 50, "thirst": 20, "energy": 25},
    "juice": {"name": "🧃 Сок", "price": 30, "thirst": 40},
    "energy": {"name": "⚡ Энергетик", "price": 60, "thirst": 15, "energy": 45},
    "vodka": {"name": "🍸 Водка", "price": 200, "thirst": 10, "mood": 25}
}

MEDICAL_ITEMS = {
    "bandage": {"name": "🩹 Бинт", "price": 100, "health": 20},
    "painkiller": {"name": "💊 Обезбол", "price": 200, "health": 35},
    "antibiotic": {"name": "💉 Антибиотик", "price": 500, "health": 60, "cures_disease": True}
}

WEAPONS = {
    "knife": {"name": "🔪 Нож", "price": 300, "damage": 15},
    "bat": {"name": "🏏 Бита", "price": 500, "damage": 20},
    "pistol": {"name": "🔫 Пистолет", "price": 1500, "damage": 35, "illegal": True},
    "shotgun": {"name": "💥 Дробовик", "price": 3000, "damage": 50, "illegal": True},
    "ak47": {"name": "🔫 АК-47", "price": 5000, "damage": 70, "illegal": True}
}

# ==================== БАЗА ДАННЫХ ====================
class Database:
    def __init__(self, db_path="game.db"):
        self.db_path = db_path
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
                referred_by INTEGER,
                total_referrals INTEGER DEFAULT 0,
                hunger INTEGER DEFAULT 100,
                thirst INTEGER DEFAULT 100,
                health INTEGER DEFAULT 100,
                sleep INTEGER DEFAULT 100,
                mood INTEGER DEFAULT 100,
                disease TEXT,
                weapon TEXT DEFAULT 'fists',
                crimes_committed INTEGER DEFAULT 0,
                stolen_total INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                gang_id INTEGER,
                gang_rank TEXT DEFAULT 'none',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (gang_id) REFERENCES gangs(gang_id)
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
                gang_level INTEGER DEFAULT 1,
                gang_money INTEGER DEFAULT 0,
                max_members INTEGER DEFAULT 10,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS gang_invites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gang_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'pending'
            );
            
            CREATE TABLE IF NOT EXISTS npc_relations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                npc_id INTEGER,
                relation TEXT DEFAULT 'neutral',
                interactions INTEGER DEFAULT 0
            );
        """)
        self.conn.commit()
    
    def get_user(self, user_id):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def create_user(self, user_id, username, first_name, referral_code=None):
        city_choices = list(CITIES.keys())
        city_weights = [CITIES[c].start_chance for c in city_choices]
        start_city = random.choices(city_choices, weights=city_weights, k=1)[0]
        start_money = random.choices([100, 250, 500, 750, 1000], weights=[0.1, 0.2, 0.4, 0.2, 0.1], k=1)[0]
        own_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        referrer_id = None
        if referral_code:
            self.cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
            referrer = self.cursor.fetchone()
            if referrer and referrer[0] != user_id:
                referrer_id = referrer[0]
        
        self.cursor.execute("""
            INSERT INTO users (user_id, username, first_name, money, current_city, referral_code, referred_by)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, first_name, start_money, start_city, own_code, referrer_id))
        
        if referrer_id:
            self.cursor.execute("UPDATE users SET money = money + 50, total_referrals = total_referrals + 1 WHERE user_id = ?", (referrer_id,))
            self.cursor.execute("UPDATE users SET money = money + 25 WHERE user_id = ?", (user_id,))
        
        self.conn.commit()
        return start_city, start_money
    
    def update_user(self, user_id, **kwargs):
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        self.cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
        self.conn.commit()
    
    def add_money(self, user_id, amount):
        self.cursor.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        self.conn.commit()
    
    def get_inventory(self, user_id):
        self.cursor.execute("SELECT * FROM inventory WHERE user_id = ? AND quantity > 0", (user_id,))
        return [dict(row) for row in self.cursor.fetchall()]
    
    def add_item(self, user_id, item_id, item_type, quantity=1):
        self.cursor.execute("SELECT id, quantity FROM inventory WHERE user_id = ? AND item_id = ?", (user_id, item_id))
        existing = self.cursor.fetchone()
        if existing:
            self.cursor.execute("UPDATE inventory SET quantity = quantity + ? WHERE id = ?", (quantity, existing['id']))
        else:
            self.cursor.execute("INSERT INTO inventory (user_id, item_id, item_type, quantity) VALUES (?, ?, ?, ?)", (user_id, item_id, item_type, quantity))
        self.conn.commit()
    
    def use_item(self, user_id, item_id):
        self.cursor.execute("SELECT id, quantity FROM inventory WHERE user_id = ? AND item_id = ? AND quantity > 0", (user_id, item_id))
        item = self.cursor.fetchone()
        if not item:
            return False
        if item['quantity'] > 1:
            self.cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE id = ?", (item['id'],))
        else:
            self.cursor.execute("DELETE FROM inventory WHERE id = ?", (item['id'],))
        self.conn.commit()
        return True
    
    def create_gang(self, gang_name, gang_tag, owner_id):
        try:
            self.cursor.execute("INSERT INTO gangs (gang_name, gang_tag, owner_id) VALUES (?, ?, ?)", (gang_name, gang_tag, owner_id))
            gang_id = self.cursor.lastrowid
            self.cursor.execute("UPDATE users SET gang_id = ?, gang_rank = 'leader' WHERE user_id = ?", (gang_id, owner_id))
            self.conn.commit()
            return gang_id
        except:
            return None
    
    def get_gang(self, gang_id):
        self.cursor.execute("SELECT * FROM gangs WHERE gang_id = ?", (gang_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def get_gang_members(self, gang_id):
        self.cursor.execute("""
            SELECT user_id, first_name, level, gang_rank 
            FROM users WHERE gang_id = ?
            ORDER BY CASE gang_rank WHEN 'leader' THEN 1 WHEN 'vice' THEN 2 ELSE 3 END
        """, (gang_id,))
        return [dict(row) for row in self.cursor.fetchall()]
    
    def get_pending_invites(self, user_id):
        self.cursor.execute("""
            SELECT gi.*, g.gang_name, g.gang_tag FROM gang_invites gi
            JOIN gangs g ON gi.gang_id = g.gang_id
            WHERE gi.user_id = ? AND gi.status = 'pending'
        """, (user_id,))
        return [dict(row) for row in self.cursor.fetchall()]
    
    def accept_invite(self, invite_id, user_id):
        self.cursor.execute("SELECT * FROM gang_invites WHERE id = ? AND user_id = ?", (invite_id, user_id))
        invite = self.cursor.fetchone()
        if not invite:
            return False
        self.cursor.execute("UPDATE gang_invites SET status = 'accepted' WHERE id = ?", (invite_id,))
        self.cursor.execute("UPDATE users SET gang_id = ?, gang_rank = 'recruit' WHERE user_id = ?", (invite['gang_id'], user_id))
        self.conn.commit()
        return True
    
    def leave_gang(self, user_id):
        user = self.get_user(user_id)
        if not user or not user['gang_id']:
            return False
        if user['gang_rank'] == 'leader':
            self.cursor.execute("DELETE FROM gangs WHERE gang_id = ?", (user['gang_id'],))
            self.cursor.execute("UPDATE users SET gang_id = NULL, gang_rank = 'none' WHERE gang_id = ?", (user['gang_id'],))
        else:
            self.cursor.execute("UPDATE users SET gang_id = NULL, gang_rank = 'none' WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return True

db = Database()

# ==================== КЛАВИАТУРЫ ====================
class Keyboards:
    @staticmethod
    def main_navigation():
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="💼 РАБОТА"), KeyboardButton(text="🎰 КАЗИНО"))
        builder.row(KeyboardButton(text="🛒 МАГАЗИН"), KeyboardButton(text="🏠 ДОМ"))
        builder.row(KeyboardButton(text="🗺 ГОРОД"), KeyboardButton(text="🎒 ИНВЕНТАРЬ"))
        builder.row(KeyboardButton(text="🏴 БАНДА"), KeyboardButton(text="🕵️ КРИМИНАЛ"))
        builder.row(KeyboardButton(text="👥 NPC"), KeyboardButton(text="📊 СТАТУС"))
        builder.row(KeyboardButton(text="🗺 КАРТА"), KeyboardButton(text="🏆 ТОП"))
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def city_locations(city_id):
        builder = InlineKeyboardBuilder()
        builder.button(text="🏪 Супермаркет", callback_data=f"loc_supermarket_{city_id}")
        builder.button(text="🏥 Больница", callback_data=f"loc_hospital_{city_id}")
        builder.button(text="🔫 Оружейный", callback_data=f"loc_weapons_{city_id}")
        builder.button(text="🌑 Чёрный рынок", callback_data=f"loc_blackmarket_{city_id}")
        builder.button(text="🍻 Бар", callback_data=f"loc_bar_{city_id}")
        builder.button(text="🚔 Полиция", callback_data=f"loc_police_{city_id}")
        builder.button(text="🏠 Домой", callback_data=f"loc_home_{city_id}")
        builder.button(text="🔙 В меню", callback_data="back_to_main")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def npc_menu(city_id):
        builder = InlineKeyboardBuilder()
        builder.button(text="👥 Список NPC", callback_data=f"npc_list_{city_id}")
        builder.button(text="🔫 Ограбить NPC", callback_data=f"npc_rob_{city_id}")
        builder.button(text="💬 Поговорить с NPC", callback_data=f"npc_talk_{city_id}")
        builder.button(text="🤝 Подружиться", callback_data=f"npc_befriend_{city_id}")
        builder.button(text="🔙 В меню", callback_data="back_to_main")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def npc_list_keyboard(npcs, city_id):
        builder = InlineKeyboardBuilder()
        for npc in npcs:
            activity_emoji = {"working": "💼", "walking": "🚶", "drinking": "🍺", "trading": "💰", "sleeping": "😴"}
            emoji = activity_emoji.get(npc.activity, "❓")
            builder.button(
                text=f"{emoji} {npc.name} (Ур.{npc.level})",
                callback_data=f"npc_info_{npc.npc_id}"
            )
        builder.button(text="🔙 Назад", callback_data=f"back_to_npc_{city_id}")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def work_menu(city_id):
        builder = InlineKeyboardBuilder()
        works = [("📦 Курьер", 30), ("🍽 Официант", 45), ("💂 Охранник", 60), ("👔 Менеджер", 80), ("💻 Разработчик", 120)]
        for name, salary in works:
            builder.button(text=f"{name} (+${salary})", callback_data=f"work_{name.split()[1].lower()}_{city_id}")
        builder.button(text="🔙 В меню", callback_data="back_to_main")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def shop_menu(city_id):
        builder = InlineKeyboardBuilder()
        builder.button(text="🍞 Еда", callback_data=f"shopcat_food_{city_id}")
        builder.button(text="💧 Напитки", callback_data=f"shopcat_drinks_{city_id}")
        builder.button(text="💊 Медикаменты", callback_data=f"shopcat_medical_{city_id}")
        builder.button(text="🔙 В меню", callback_data="back_to_main")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def casino_menu():
        builder = InlineKeyboardBuilder()
        builder.button(text="🎲 Рулетка ($50)", callback_data="casino_roulette")
        builder.button(text="🎰 Слоты ($10)", callback_data="casino_slots")
        builder.button(text="🔙 В меню", callback_data="back_to_main")
        return builder.as_markup()
    
    @staticmethod
    def gang_menu():
        builder = InlineKeyboardBuilder()
        builder.button(text="🏴 Моя банда", callback_data="gang_my")
        builder.button(text="📨 Приглашения", callback_data="gang_invites")
        builder.button(text="🚪 Покинуть", callback_data="gang_leave")
        builder.button(text="🔙 В меню", callback_data="back_to_main")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def crime_menu():
        builder = InlineKeyboardBuilder()
        builder.button(text="🔫 Ограбить игрока", callback_data="crime_robplayer")
        builder.button(text="👤 Ограбить NPC", callback_data="crime_robnpc")
        builder.button(text="🏪 Ограбить магазин", callback_data="crime_robstore")
        builder.button(text="🚗 Угнать машину", callback_data="crime_carjack")
        builder.button(text="🏠 Кража со взломом", callback_data="crime_burglary")
        builder.button(text="💰 Продать краденое", callback_data="crime_sellstolen")
        builder.button(text="🔙 В меню", callback_data="back_to_main")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def black_market_menu(city_id):
        builder = InlineKeyboardBuilder()
        for weapon_id, weapon in WEAPONS.items():
            if weapon.get('illegal'):
                city = CITIES.get(city_id, CITIES['newark'])
                price = int(weapon['price'] * city.income_mult * 0.6)
                builder.button(text=f"{weapon['name']} (${price})", callback_data=f"buyweapon_{weapon_id}_{city_id}")
        builder.button(text="🔙 Назад", callback_data=f"back_to_city_{city_id}")
        builder.adjust(1)
        return builder.as_markup()

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
scheduler = AsyncIOScheduler()

def check_user(func):
    async def wrapper(message, *args, **kwargs):
        if not db.get_user(message.from_user.id):
            await message.answer("❌ Сначала /start")
            return
        return await func(message, *args, **kwargs)
    return wrapper

# ==================== СТАРТ ====================
@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject = None):
    user_id = message.from_user.id
    username = message.from_user.username or "Player"
    first_name = message.from_user.first_name or "Игрок"
    
    user = db.get_user(user_id)
    
    if not user:
        referral_code = command.args if command.args else None
        start_city, start_money = db.create_user(user_id, username, first_name, referral_code)
        city = CITIES[start_city]
        
        npcs = npc_manager.get_npcs_in_city(start_city)
        npc_names = ", ".join([n.name for n in npcs[:3]])
        
        await message.answer(
            f"🎉 *Ты родился в {city.emoji} {city.name}!*\n\n"
            f"📝 {city.description}\n"
            f"💰 Капитал: *${start_money}*\n"
            f"👥 Жители: {npc_names}...\n\n"
            f"🎯 Начни с РАБОТЫ или вступи в БАНДУ!\n"
            f"💡 Совет: общайся с NPC и зарабатывай!",
            reply_markup=Keyboards.main_navigation(),
            parse_mode="Markdown"
        )
    else:
        city = CITIES.get(user['current_city'], CITIES['newark'])
        gang_text = ""
        if user['gang_id']:
            gang = db.get_gang(user['gang_id'])
            if gang:
                gang_text = f"\n🏴 {gang['gang_name']}"
        
        await message.answer(
            f"👋 *С возвращением, {first_name}!*\n"
            f"📍 {city.emoji} {city.name}\n"
            f"💰 ${user['money']} | ⭐ Ур.{user['level']}{gang_text}",
            reply_markup=Keyboards.main_navigation(),
            parse_mode="Markdown"
        )

# ==================== ПОМОЩЬ ====================
@router.message(Command("help"))
@router.message(F.text == "❓ ПОМОЩЬ")
async def help_cmd(message: Message):
    await message.answer(
        "📚 *Помощь*\n\n"
        "💼 РАБОТА — легальный заработок\n"
        "🎰 КАЗИНО — азартные игры\n"
        "🛒 МАГАЗИН — еда, напитки, лекарства\n"
        "🏠 ДОМ — недвижимость\n"
        "🗺 ГОРОД — локации\n"
        "🎒 ИНВЕНТАРЬ — предметы\n"
        "🏴 БАНДА — создать/вступить\n"
        "🕵️ КРИМИНАЛ — грабежи\n"
        "👥 NPC — общение с жителями\n"
        "📊 СТАТУС — выживание\n"
        "🗺 КАРТА — города\n"
        "🏆 ТОП — рейтинг\n\n"
        "📋 Команды:\n"
        "/profile, /gang_create, /rob",
        parse_mode="Markdown"
    )

# ==================== NPC КНОПКА ====================
@router.message(F.text == "👥 NPC")
@check_user
async def npc_button(message: Message):
    user = db.get_user(message.from_user.id)
    city = CITIES.get(user['current_city'], CITIES['newark'])
    npcs = npc_manager.get_npcs_in_city(user['current_city'])
    
    await message.answer(
        f"👥 *Жители {city.emoji} {city.name}*\n\n"
        f"В городе {len(npcs)} жителей.\n"
        f"Выбери действие:",
        reply_markup=Keyboards.npc_menu(user['current_city']),
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("npc_list_"))
async def npc_list(callback: CallbackQuery):
    city_id = callback.data.replace("npc_list_", "")
    npcs = npc_manager.get_npcs_in_city(city_id)
    
    if not npcs:
        await callback.answer("❌ В городе никого нет!", show_alert=True)
        return
    
    text = f"👥 *Жители города:*\n\n"
    for npc in npcs:
        activity_text = {"working": "💼 Работает", "walking": "🚶 Гуляет", "drinking": "🍺 Пьёт", "trading": "💰 Торгует", "sleeping": "😴 Спит"}
        text += f"• {npc.name} — {activity_text.get(npc.activity, '❓')} (Ур.{npc.level})\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=Keyboards.npc_list_keyboard(npcs, city_id),
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("npc_info_"))
async def npc_info(callback: CallbackQuery):
    npc_id = int(callback.data.replace("npc_info_", ""))
    npc = npc_manager.get_npc(npc_id)
    
    if not npc:
        await callback.answer("❌ NPC не найден!", show_alert=True)
        return
    
    text = (
        f"👤 *{npc.name}*\n\n"
        f"📍 Город: {CITIES[npc.city_id].name}\n"
        f"⭐ Уровень: {npc.level}\n"
        f"❤️ HP: {npc.hp}/100\n"
        f"💰 Деньги: ${npc.money}\n"
        f"🗡 Оружие: {npc.weapon}\n"
        f"🎯 Активность: {npc.activity}\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔫 Ограбить", callback_data=f"npc_rob_action_{npc_id}")
    builder.button(text="💬 Поговорить", callback_data=f"npc_talk_action_{npc_id}")
    builder.button(text="🔙 Назад", callback_data=f"npc_list_{npc.city_id}")
    builder.adjust(2)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("npc_rob_action_"))
async def npc_rob_action(callback: CallbackQuery):
    npc_id = int(callback.data.replace("npc_rob_action_", ""))
    user = db.get_user(callback.from_user.id)
    
    result = npc_manager.rob_npc(user['user_id'], npc_id, user['weapon'])
    
    if result['success']:
        db.add_money(user['user_id'], result['amount'])
        db.update_user(user['user_id'], crimes_committed=user['crimes_committed'] + 1, stolen_total=user['stolen_total'] + result['amount'])
    else:
        db.update_user(user['user_id'], health=max(10, user['health'] - 10))
    
    await callback.answer(result['message'], show_alert=True)

@router.callback_query(lambda c: c.data.startswith("npc_talk_action_"))
async def npc_talk_action(callback: CallbackQuery):
    npc_id = int(callback.data.replace("npc_talk_action_", ""))
    npc = npc_manager.get_npc(npc_id)
    
    if not npc:
        await callback.answer("❌ NPC не найден!", show_alert=True)
        return
    
    phrases = [
        f"«Привет! В этом городе можно неплохо заработать.»",
        f"«Слышал про чёрный рынок? Туда не всех пускают...»",
        f"«Будь осторожен на улицах, тут всякое бывает.»",
        f"«Работай усердно и сможешь переехать в Дубай!»",
        f"«Я вчера в казино $500 выиграл. Или проиграл... не помню.»",
        f"«Хочешь в банду? У нас тут есть парочка.»",
        f"«Не лезь на рожон, новичок.»"
    ]
    
    await callback.answer(f"{npc.name}: {random.choice(phrases)}", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("npc_rob_"))
async def npc_rob_menu(callback: CallbackQuery):
    city_id = callback.data.replace("npc_rob_", "")
    npcs = npc_manager.get_npcs_in_city(city_id)
    
    if not npcs:
        await callback.answer("❌ Некого грабить!", show_alert=True)
        return
    
    builder = InlineKeyboardBuilder()
    text = "🔫 *Выбери жертву:*\n\n"
    for npc in npcs:
        text += f"• {npc.name} (${npc.money}) — Ур.{npc.level}\n"
        builder.button(text=f"Ограбить {npc.name}", callback_data=f"npc_rob_action_{npc.npc_id}")
    
    builder.button(text="🔙 Назад", callback_data=f"back_to_npc_{city_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("npc_befriend_"))
async def npc_befriend(callback: CallbackQuery):
    city_id = callback.data.replace("npc_befriend_", "")
    npcs = npc_manager.get_npcs_in_city(city_id)
    
    if not npcs:
        await callback.answer("❌ Некого!", show_alert=True)
        return
    
    npc = random.choice(npcs)
    await callback.answer(f"🤝 {npc.name} согласился дружить! +Репутация", show_alert=True)
    db.update_user(callback.from_user.id, reputation=db.get_user(callback.from_user.id)['reputation'] + 3)

@router.callback_query(lambda c: c.data.startswith("back_to_npc_"))
async def back_to_npc(callback: CallbackQuery):
    city_id = callback.data.replace("back_to_npc_", "")
    await callback.message.edit_text(
        f"👥 *Жители города*\nВыбери действие:",
        reply_markup=Keyboards.npc_menu(city_id),
        parse_mode="Markdown"
    )

# ==================== РАБОТА ====================
@router.message(F.text == "💼 РАБОТА")
@check_user
async def work_button(message: Message):
    user = db.get_user(message.from_user.id)
    await message.answer("💼 *Выбери работу:*", reply_markup=Keyboards.work_menu(user['current_city']), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("work_"))
async def process_work(callback: CallbackQuery):
    parts = callback.data.split("_")
    job = parts[1]
    city_id = parts[2]
    user = db.get_user(callback.from_user.id)
    
    if user['energy'] < 20:
        await callback.answer("❌ Мало энергии!", show_alert=True)
        return
    
    if user['last_work']:
        last = datetime.fromisoformat(user['last_work'])
        if (datetime.now() - last).total_seconds() < 900:
            remaining = 900 - int((datetime.now() - last).total_seconds())
            await callback.answer(f"⏳ Жди {remaining//60}м {remaining%60}с!", show_alert=True)
            return
    
    salaries = {"курьер": 30, "официант": 45, "охранник": 60, "менеджер": 80, "разработчик": 120}
    base = salaries.get(job, 30)
    city = CITIES.get(city_id, CITIES['newark'])
    total = int(base * city.income_mult * (1 + user['level'] * 0.05))
    
    db.add_money(user['user_id'], total)
    db.update_user(user['user_id'], last_work=datetime.now().isoformat(), energy=user['energy'] - 20, xp=user['xp'] + 10)
    
    await callback.message.edit_text(
        f"✅ *Работа: {job}*\n💰 +${total}\n✨ +10 XP",
        parse_mode="Markdown"
    )

# ==================== КАЗИНО ====================
@router.message(F.text == "🎰 КАЗИНО")
@check_user
async def casino_button(message: Message):
    await message.answer("🎰 *Казино*", reply_markup=Keyboards.casino_menu(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "casino_roulette")
async def roulette(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user['money'] < 50:
        await callback.answer("❌ Нужно $50!", show_alert=True)
        return
    win = random.random() < 0.4
    winnings = random.choice([100, 200, 500]) if win else -50
    db.update_user(callback.from_user.id, money=user['money'] + winnings)
    await callback.message.edit_text(f"🎲 {'Выигрыш' if win else 'Проигрыш'}: ${abs(winnings)}\n💰 ${user['money'] + winnings}", parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "casino_slots")
async def slots(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user['money'] < 10:
        await callback.answer("❌ Нужно $10!", show_alert=True)
        return
    symbols = ["🍒", "🍋", "🍊", "⭐", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    if result[0] == result[1] == result[2]:
        win, text = 100, "🎉 ДЖЕКПОТ! +$100"
    elif len(set(result)) == 2:
        win, text = 20, "✨ Повезло! +$20"
    else:
        win, text = -10, "😢 Мимо! -$10"
    db.update_user(callback.from_user.id, money=user['money'] + win)
    await callback.message.edit_text(f"🎰 [{' | '.join(result)}]\n{text}\n💰 ${user['money'] + win}", parse_mode="Markdown")

# ==================== МАГАЗИН ====================
@router.message(F.text == "🛒 МАГАЗИН")
@check_user
async def shop_button(message: Message):
    user = db.get_user(message.from_user.id)
    await message.answer(f"🛒 *Магазин*\n💰 ${user['money']}", reply_markup=Keyboards.shop_menu(user['current_city']), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("shopcat_"))
async def shop_category(callback: CallbackQuery):
    parts = callback.data.split("_")
    category = parts[1]
    city_id = parts[2]
    user = db.get_user(callback.from_user.id)
    city = CITIES.get(city_id, CITIES['newark'])
    
    items = {"food": FOOD_ITEMS, "drinks": DRINK_ITEMS, "medical": MEDICAL_ITEMS}
    item_list = items.get(category, {})
    
    builder = InlineKeyboardBuilder()
    text = {"food": "🍞 Еда", "drinks": "💧 Напитки", "medical": "💊 Медикаменты"}[category] + ":\n\n"
    
    for item_id, item in item_list.items():
        price = int(item['price'] * city.income_mult * 0.5)
        text += f"• {item['name']} — ${price}\n"
        builder.button(text=f"{item['name']} (${price})", callback_data=f"buy_{item_id}_{city_id}")
    
    builder.button(text="🔙 Назад", callback_data=f"back_to_shop_{city_id}")
    builder.adjust(1)
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("buy_"))
async def buy_item(callback: CallbackQuery):
    parts = callback.data.split("_")
    item_id = parts[1]
    city_id = parts[2]
    user = db.get_user(callback.from_user.id)
    city = CITIES.get(city_id, CITIES['newark'])
    
    item = FOOD_ITEMS.get(item_id) or DRINK_ITEMS.get(item_id) or MEDICAL_ITEMS.get(item_id)
    if not item:
        await callback.answer("❌ Товар не найден!", show_alert=True)
        return
    
    price = int(item['price'] * city.income_mult * 0.5)
    if user['money'] < price:
        await callback.answer(f"❌ Нужно ${price}!", show_alert=True)
        return
    
    db.add_money(user['user_id'], -price)
    item_type = "food" if item_id in FOOD_ITEMS else "drink" if item_id in DRINK_ITEMS else "medical"
    db.add_item(user['user_id'], item_id, item_type)
    
    await callback.answer(f"✅ {item['name']} куплен!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("back_to_shop_"))
async def back_to_shop(callback: CallbackQuery):
    city_id = callback.data.split("_")[3]
    user = db.get_user(callback.from_user.id)
    await callback.message.edit_text(f"🛒 *Магазин*\n💰 ${user['money']}", reply_markup=Keyboards.shop_menu(city_id), parse_mode="Markdown")

# ==================== ОСТАЛЬНЫЕ КНОПКИ ====================
@router.message(F.text == "🏠 ДОМ")
@check_user
async def house_button(message: Message):
    user = db.get_user(message.from_user.id)
    builder = InlineKeyboardBuilder()
    houses = {"apartment": ("Квартира", 500), "house": ("Дом", 2000), "villa": ("Вилла", 10000)}
    text = "🏠 *Недвижимость*\n\n"
    for hid, (name, price) in houses.items():
        text += f"🏠 {name} — ${price}\n"
        builder.button(text=f"Купить {name} (${price})", callback_data=f"house_buy_{hid}")
    builder.button(text="💰 Собрать доход", callback_data="house_collect")
    builder.button(text="🔙 В меню", callback_data="back_to_main")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("house_"))
async def house_action(callback: CallbackQuery):
    action = callback.data.replace("house_", "")
    user = db.get_user(callback.from_user.id)
    if action.startswith("buy_"):
        prices = {"apartment": 500, "house": 2000, "villa": 10000}
        price = prices.get(action.replace("buy_", ""), 500)
        if user['money'] < price:
            await callback.answer(f"❌ Нужно ${price}!", show_alert=True)
            return
        db.add_money(user['user_id'], -price)
        db.update_user(user['user_id'], house_id=action.replace("buy_", ""))
        await callback.answer(f"✅ Куплен!", show_alert=True)
    elif action == "collect":
        if not user['house_id']:
            await callback.answer("❌ Нет дома!", show_alert=True)
            return
        incomes = {"apartment": 10, "house": 40, "villa": 200}
        income = incomes.get(user['house_id'], 10)
        db.add_money(user['user_id'], income)
        await callback.answer(f"💰 +${income}!", show_alert=True)

@router.message(F.text == "🗺 ГОРОД")
@check_user
async def city_button(message: Message):
    user = db.get_user(message.from_user.id)
    city = CITIES.get(user['current_city'], CITIES['newark'])
    await message.answer(f"🏙 *{city.emoji} {city.name}*\nКуда пойдёшь?", reply_markup=Keyboards.city_locations(user['current_city']), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("loc_"))
async def city_location(callback: CallbackQuery):
    parts = callback.data.split("_")
    location = parts[1]
    city_id = parts[2]
    user = db.get_user(callback.from_user.id)
    
    if location == "supermarket":
        await callback.message.edit_text("🏪 *Супермаркет*", reply_markup=Keyboards.shop_menu(city_id), parse_mode="Markdown")
    elif location == "hospital":
        builder = InlineKeyboardBuilder()
        builder.button(text="💊 Лечиться ($500)", callback_data=f"hospital_heal_{city_id}")
        builder.button(text="🔙 Назад", callback_data=f"back_to_city_{city_id}")
        await callback.message.edit_text(f"🏥 *Больница*\n❤️ HP: {user['health']}/100", reply_markup=builder.as_markup(), parse_mode="Markdown")
    elif location == "weapons":
        builder = InlineKeyboardBuilder()
        text = "🔫 *Оружейный*\n\n"
        for wid, w in WEAPONS.items():
            if not w.get('illegal'):
                price = int(w['price'] * CITIES[city_id].income_mult * 0.8)
                text += f"{w['name']} — ${price}\n"
                builder.button(text=f"{w['name']} (${price})", callback_data=f"buyweapon_{wid}_{city_id}")
        builder.button(text="🔙 Назад", callback_data=f"back_to_city_{city_id}")
        builder.adjust(1)
        await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    elif location == "blackmarket":
        if user['reputation'] > -10:
            await callback.answer("❌ Нужна репутация < -10!", show_alert=True)
            return
        await callback.message.edit_text("🌑 *Чёрный рынок*", reply_markup=Keyboards.black_market_menu(city_id), parse_mode="Markdown")
    elif location == "bar":
        builder = InlineKeyboardBuilder()
        builder.button(text="🍺 Выпить ($20)", callback_data=f"bar_drink_{city_id}")
        builder.button(text="👊 Драка", callback_data=f"bar_fight_{city_id}")
        builder.button(text="🔙 Назад", callback_data=f"back_to_city_{city_id}")
        await callback.message.edit_text("🍻 *Бар*", reply_markup=builder.as_markup(), parse_mode="Markdown")
    elif location == "police":
        builder = InlineKeyboardBuilder()
        builder.button(text="💰 Взятка ($100)", callback_data=f"police_bribe_{city_id}")
        builder.button(text="🔙 Назад", callback_data=f"back_to_city_{city_id}")
        await callback.message.edit_text("🚔 *Полиция*", reply_markup=builder.as_markup(), parse_mode="Markdown")
    elif location == "home":
        builder = InlineKeyboardBuilder()
        builder.button(text="😴 Спать", callback_data=f"home_sleep_{city_id}")
        builder.button(text="🔙 Назад", callback_data=f"back_to_city_{city_id}")
        await callback.message.edit_text("🏠 *Дом*", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("hospital_heal_"))
async def hospital_heal(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user['money'] < 500:
        await callback.answer("❌ Нужно $500!", show_alert=True)
        return
    db.add_money(user['user_id'], -500)
    db.update_user(user['user_id'], health=100)
    await callback.answer("✅ HP восстановлено!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("bar_drink_"))
async def bar_drink(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user['money'] < 20:
        await callback.answer("❌ Нужно $20!", show_alert=True)
        return
    db.add_money(user['user_id'], -20)
    db.update_user(user['user_id'], mood=min(100, user['mood'] + 20), thirst=min(100, user['thirst'] + 30))
    await callback.answer("🍺 Выпито! +Настроение", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("bar_fight_"))
async def bar_fight(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if random.random() < 0.5:
        db.update_user(user['user_id'], xp=user['xp'] + 15, reputation=user['reputation'] + 5)
        await callback.answer("👊 Победа! +15 XP", show_alert=True)
    else:
        db.update_user(user['user_id'], health=max(10, user['health'] - 20))
        await callback.answer("👊 Поражение! -20 HP", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("police_bribe_"))
async def police_bribe(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user['money'] < 100:
        await callback.answer("❌ Нужно $100!", show_alert=True)
        return
    db.add_money(user['user_id'], -100)
    db.update_user(user['user_id'], reputation=user['reputation'] - 3)
    await callback.answer("🤝 Взятка дана!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("home_sleep_"))
async def home_sleep(callback: CallbackQuery):
    db.update_user(callback.from_user.id, sleep=100, energy=100)
    await callback.answer("😴 Сон +Энергия!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("buyweapon_"))
async def buy_weapon(callback: CallbackQuery):
    parts = callback.data.split("_")
    weapon_id = parts[1]
    city_id = parts[2]
    user = db.get_user(callback.from_user.id)
    weapon = WEAPONS.get(weapon_id)
    city = CITIES.get(city_id, CITIES['newark'])
    
    if not weapon:
        await callback.answer("❌ Оружие не найдено!", show_alert=True)
        return
    
    mult = 0.6 if weapon.get('illegal') else 0.8
    price = int(weapon['price'] * city.income_mult * mult)
    
    if user['money'] < price:
        await callback.answer(f"❌ Нужно ${price}!", show_alert=True)
        return
    
    db.add_money(user['user_id'], -price)
    db.update_user(user['user_id'], weapon=weapon_id)
    await callback.answer(f"✅ {weapon['name']} куплен!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("back_to_city_"))
async def back_to_city(callback: CallbackQuery):
    city_id = callback.data.split("_")[3]
    city = CITIES.get(city_id, CITIES['newark'])
    await callback.message.edit_text(f"🏙 *{city.emoji} {city.name}*\nКуда пойдёшь?", reply_markup=Keyboards.city_locations(city_id), parse_mode="Markdown")

# ==================== ИНВЕНТАРЬ ====================
@router.message(F.text == "🎒 ИНВЕНТАРЬ")
@check_user
async def inventory_button(message: Message):
    user = db.get_user(message.from_user.id)
    items = db.get_inventory(user['user_id'])
    
    if not items:
        await message.answer("🎒 *Пусто*")
        return
    
    text = "🎒 *Инвентарь:*\n\n"
    builder = InlineKeyboardBuilder()
    all_items = {**FOOD_ITEMS, **DRINK_ITEMS, **MEDICAL_ITEMS}
    
    for item in items:
        item_data = all_items.get(item['item_id'], {})
        text += f"• {item_data.get('name', item['item_id'])} x{item['quantity']}\n"
        builder.button(text=f"Использовать {item_data.get('name', item['item_id'])}", callback_data=f"use_{item['item_id']}")
    
    builder.button(text="🔙 В меню", callback_data="back_to_main")
    builder.adjust(1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("use_"))
async def use_item(callback: CallbackQuery):
    item_id = callback.data.replace("use_", "")
    user = db.get_user(callback.from_user.id)
    
    if not db.use_item(user['user_id'], item_id):
        await callback.answer("❌ Нет предмета!", show_alert=True)
        return
    
    if item_id in FOOD_ITEMS:
        db.update_user(user['user_id'], hunger=min(100, user['hunger'] + FOOD_ITEMS[item_id]['hunger']))
        await callback.answer(f"🍞 +{FOOD_ITEMS[item_id]['hunger']} голода", show_alert=True)
    elif item_id in DRINK_ITEMS:
        drink = DRINK_ITEMS[item_id]
        updates = {'thirst': min(100, user['thirst'] + drink.get('thirst', 0))}
        if 'energy' in drink:
            updates['energy'] = min(100, user['energy'] + drink['energy'])
        db.update_user(user['user_id'], **updates)
        await callback.answer("💧 Выпито!", show_alert=True)
    elif item_id in MEDICAL_ITEMS:
        db.update_user(user['user_id'], health=min(100, user['health'] + MEDICAL_ITEMS[item_id]['health']))
        await callback.answer(f"💊 +{MEDICAL_ITEMS[item_id]['health']} HP", show_alert=True)

# ==================== БАНДА ====================
@router.message(F.text == "🏴 БАНДА")
@check_user
async def gang_button(message: Message):
    user = db.get_user(message.from_user.id)
    
    if user['gang_id']:
        gang = db.get_gang(user['gang_id'])
        members = db.get_gang_members(user['gang_id'])
        text = f"🏴 *{gang['gang_name']} [{gang['gang_tag']}]*\n\n"
        text += f"👥 {len(members)}/{gang['max_members']} чел.\n\n*Участники:*\n"
        for m in members:
            rank_emoji = {"leader": "👑", "vice": "🎩", "veteran": "⭐", "soldier": "🗡", "recruit": "🔰"}
            text += f"{rank_emoji.get(m['gang_rank'], '🔰')} {m['first_name']}\n"
    else:
        text = "🏴 *Банды*\n\nНет банды.\nСоздай: /gang_create [название] [тег]"
    
    await message.answer(text, reply_markup=Keyboards.gang_menu(), parse_mode="Markdown")

@router.message(Command("gang_create"))
@check_user
async def gang_create(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ /gang_create [название] [тег]")
        return
    
    user = db.get_user(message.from_user.id)
    if user['money'] < 1000:
        await message.answer("❌ Нужно $1000!")
        return
    if user['gang_id']:
        await message.answer("❌ Ты уже в банде!")
        return
    
    gang_name = args[1]
    gang_tag = args[2] if len(args) > 2 else gang_name[:4].upper()
    
    gang_id = db.create_gang(gang_name, gang_tag, message.from_user.id)
    if gang_id:
        db.add_money(message.from_user.id, -1000)
        await message.answer(f"✅ Банда *{gang_name}* [{gang_tag}] создана!", parse_mode="Markdown")
    else:
        await message.answer("❌ Имя или тег заняты!")

@router.callback_query(lambda c: c.data == "gang_my")
async def gang_my(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if not user['gang_id']:
        await callback.answer("❌ Нет банды!", show_alert=True)
        return
    gang = db.get_gang(user['gang_id'])
    members = db.get_gang_members(user['gang_id'])
    text = f"🏴 *{gang['gang_name']} [{gang['gang_tag']}]*\n👥 {len(members)}/{gang['max_members']}\n"
    for m in members:
        text += f"• {m['first_name']} ({m['gang_rank']})\n"
    await callback.message.edit_text(text, parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "gang_invites")
async def gang_invites(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    invites = db.get_pending_invites(user['user_id'])
    if not invites:
        await callback.answer("📨 Нет приглашений!", show_alert=True)
        return
    text = "📨 *Приглашения:*\n\n"
    builder = InlineKeyboardBuilder()
    for inv in invites:
        text += f"🏴 {inv['gang_name']} [{inv['gang_tag']}]\n"
        builder.button(text=f"Принять {inv['gang_name']}", callback_data=f"gang_accept_{inv['id']}")
    builder.button(text="🔙 Назад", callback_data="gang_my")
    builder.adjust(1)
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("gang_accept_"))
async def gang_accept(callback: CallbackQuery):
    invite_id = int(callback.data.replace("gang_accept_", ""))
    if db.accept_invite(invite_id, callback.from_user.id):
        await callback.answer("✅ Ты в банде!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка!", show_alert=True)

@router.callback_query(lambda c: c.data == "gang_leave")
async def gang_leave(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Да", callback_data="gang_leave_confirm")
    builder.button(text="❌ Нет", callback_data="gang_my")
    await callback.message.edit_text("⚠ Покинуть банду?", reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "gang_leave_confirm")
async def gang_leave_confirm(callback: CallbackQuery):
    if db.leave_gang(callback.from_user.id):
        await callback.answer("🚪 Покинул!", show_alert=True)
    else:
        await callback.answer("❌ Ошибка!", show_alert=True)

# ==================== КРИМИНАЛ ====================
@router.message(F.text == "🕵️ КРИМИНАЛ")
@check_user
async def crime_button(message: Message):
    user = db.get_user(message.from_user.id)
    text = f"🕵️ *Криминал*\n🗡 {user['weapon']}\n📊 Преступлений: {user['crimes_committed']}\n💰 Краденого: ${user['stolen_total']}"
    await message.answer(text, reply_markup=Keyboards.crime_menu(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data == "crime_robplayer")
async def crime_rob_player(callback: CallbackQuery):
    await callback.message.edit_text("🔫 Используй: /rob [ID]", parse_mode="Markdown")

@router.message(Command("rob"))
@check_user
async def rob_player(message: Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ /rob [ID]")
        return
    try:
        victim_id = int(args[1])
    except:
        await message.answer("❌ Неверный ID!")
        return
    
    if victim_id == message.from_user.id:
        await message.answer("❌ Нельзя себя!")
        return
    
    victim = db.get_user(victim_id)
    if not victim:
        await message.answer("❌ Игрок не найден!")
        return
    if victim['money'] < 50:
        await message.answer("❌ У жертвы < $50!")
        return
    
    user = db.get_user(message.from_user.id)
    weapon_dmg = WEAPONS.get(user['weapon'], {"damage": 5})['damage']
    v_weapon_dmg = WEAPONS.get(victim['weapon'], {"damage": 5})['damage']
    success_chance = 0.3 + (weapon_dmg * 0.01) - (v_weapon_dmg * 0.005)
    success_chance = max(0.1, min(0.9, success_chance))
    
    if random.random() < success_chance:
        stolen = int(victim['money'] * random.uniform(0.1, 0.3))
        db.add_money(victim_id, -stolen)
        db.add_money(message.from_user.id, stolen)
        db.update_user(message.from_user.id, crimes_committed=user['crimes_committed'] + 1, stolen_total=user['stolen_total'] + stolen)
        await message.answer(f"✅ Ограблен! +${stolen}")
    else:
        fine = random.randint(50, 200)
        db.add_money(message.from_user.id, -fine)
        await message.answer(f"🚔 Провал! Штраф: ${fine}")

@router.callback_query(lambda c: c.data == "crime_robstore")
async def crime_rob_store(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user['energy'] < 30:
        await callback.answer("❌ Мало энергии!", show_alert=True)
        return
    
    db.update_user(callback.from_user.id, energy=user['energy'] - 30)
    weapon_dmg = WEAPONS.get(user['weapon'], {"damage": 5})['damage']
    success = random.random() < (0.3 + weapon_dmg * 0.02)
    
    if success:
        loot = random.randint(100, 500)
        db.add_money(user['user_id'], loot)
        db.update_user(user['user_id'], crimes_committed=user['crimes_committed'] + 1, stolen_total=user['stolen_total'] + loot)
        await callback.answer(f"✅ +${loot}!", show_alert=True)
    else:
        fine = random.randint(50, 200)
        db.add_money(user['user_id'], -fine)
        await callback.answer(f"🚔 Штраф: ${fine}", show_alert=True)

@router.callback_query(lambda c: c.data in ["crime_carjack", "crime_burglary"])
async def crime_other(callback: CallbackQuery):
    crime_type = callback.data
    user = db.get_user(callback.from_user.id)
    
    energy_cost = {"crime_carjack": 25, "crime_burglary": 40}.get(crime_type, 30)
    if user['energy'] < energy_cost:
        await callback.answer("❌ Мало энергии!", show_alert=True)
        return
    
    db.update_user(callback.from_user.id, energy=user['energy'] - energy_cost)
    success = random.random() < 0.35
    
    if success:
        loot = random.randint(200, 800) if crime_type == "crime_carjack" else random.randint(500, 2000)
        db.add_money(user['user_id'], loot)
        db.update_user(user['user_id'], crimes_committed=user['crimes_committed'] + 1, stolen_total=user['stolen_total'] + loot)
        await callback.answer(f"✅ +${loot}!", show_alert=True)
    else:
        fine = random.randint(100, 500)
        db.add_money(user['user_id'], -fine)
        await callback.answer(f"🚔 Штраф: ${fine}", show_alert=True)

@router.callback_query(lambda c: c.data == "crime_sellstolen")
async def crime_sell_stolen(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    if user['stolen_total'] < 100:
        await callback.answer("❌ Мало краденого!", show_alert=True)
        return
    sell = int(user['stolen_total'] * 0.7)
    db.add_money(user['user_id'], sell)
    db.update_user(user['user_id'], stolen_total=0)
    await callback.answer(f"💰 Продано за ${sell}!", show_alert=True)

# ==================== ОСТАЛЬНОЕ ====================
@router.message(F.text == "📊 СТАТУС")
@check_user
async def status_button(message: Message):
    user = db.get_user(message.from_user.id)
    city = CITIES.get(user['current_city'], CITIES['newark'])
    def bar(v):
        filled = int(v / 10)
        return "█" * filled + "░" * (10 - filled)
    
    await message.answer(
        f"📊 *Статус*\n\n"
        f"👤 {user['first_name']} | Ур.{user['level']}\n"
        f"📍 {city.emoji} {city.name}\n\n"
        f"🍞 [{bar(user['hunger'])}] {user['hunger']}%\n"
        f"💧 [{bar(user['thirst'])}] {user['thirst']}%\n"
        f"❤️ [{bar(user['health'])}] {user['health']}%\n"
        f"😴 [{bar(user['sleep'])}] {user['sleep']}%\n"
        f"😊 [{bar(user['mood'])}] {user['mood']}%\n\n"
        f"💰 ${user['money']} | ⚡ {user['energy']}\n"
        f"🗡 {user['weapon']} | 🏠 {user['house_id'] or 'Нет'}",
        parse_mode="Markdown"
    )

@router.message(F.text == "🗺 КАРТА")
@check_user
async def map_button(message: Message):
    user = db.get_user(message.from_user.id)
    current = CITIES.get(user['current_city'], CITIES['newark'])
    builder = InlineKeyboardBuilder()
    text = f"🗺 *Карта*\n📍 {current.emoji} {current.name}\n\n"
    
    for city_id, city in CITIES.items():
        if city_id != user['current_city']:
            if user['level'] >= city.min_level:
                text += f"🟢 {city.emoji} {city.name} — 🚕 ${city.taxi_price}\n"
                builder.button(text=f"{city.emoji} {city.name}", callback_data=f"travel_{city_id}")
            else:
                text += f"🔒 {city.emoji} {city.name} — ур.{city.min_level}\n"
    
    builder.button(text="🔙 В меню", callback_data="back_to_main")
    builder.adjust(1)
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.callback_query(lambda c: c.data.startswith("travel_"))
async def travel(callback: CallbackQuery):
    city_id = callback.data.replace("travel_", "")
    user = db.get_user(callback.from_user.id)
    city = CITIES.get(city_id)
    
    if not city or user['level'] < city.min_level:
        await callback.answer("❌ Недоступно!", show_alert=True)
        return
    if user['money'] < city.taxi_price:
        await callback.answer(f"❌ Нужно ${city.taxi_price}!", show_alert=True)
        return
    
    db.add_money(user['user_id'], -city.taxi_price)
    db.update_user(user['user_id'], current_city=city_id)
    
    npcs = npc_manager.get_npcs_in_city(city_id)
    await callback.message.edit_text(
        f"🚕 *{city.emoji} {city.name}!*\n{city.description}\n👥 Жителей: {len(npcs)}\n💰 -${city.taxi_price}",
        parse_mode="Markdown"
    )

@router.message(F.text == "🏆 ТОП")
@check_user
async def top_button(message: Message):
    db.cursor.execute("SELECT first_name, money, level, current_city FROM users ORDER BY money DESC LIMIT 10")
    top = db.cursor.fetchall()
    text = "🏆 *Топ-10*\n\n"
    for i, p in enumerate(top, 1):
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        medal = medals.get(i, f"{i}.")
        city = CITIES.get(p['current_city'], CITIES['newark'])
        text += f"{medal} {p['first_name']} [{city.emoji}] — ${p['money']}\n"
    
    db.cursor.execute("SELECT COUNT(*) + 1 FROM users WHERE money > (SELECT money FROM users WHERE user_id = ?)", (message.from_user.id,))
    rank = db.cursor.fetchone()[0]
    text += f"\n📊 Ты: #{rank}"
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("ref"))
@check_user
async def ref_cmd(message: Message):
    user = db.get_user(message.from_user.id)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user['referral_code']}"
    await message.answer(f"👥 *Рефералы*\n🔗 `{ref_link}`\n📊 {user['total_referrals']} чел.", parse_mode="Markdown")

@router.message(Command("profile"))
@check_user
async def profile_cmd(message: Message):
    user = db.get_user(message.from_user.id)
    city = CITIES.get(user['current_city'], CITIES['newark'])
    gang = db.get_gang(user['gang_id']) if user['gang_id'] else None
    
    await message.answer(
        f"👤 *{user['first_name']}*\n"
        f"📍 {city.emoji} {city.name}\n"
        f"💰 ${user['money']} | ⭐ Ур.{user['level']}\n"
        f"🏴 {gang['gang_name'] if gang else 'Нет'}\n"
        f"🗡 {user['weapon']} | 🕵️ {user['crimes_committed']} прест.",
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data == "back_to_main")
async def back_to_main(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    city = CITIES.get(user['current_city'], CITIES['newark'])
    gang = db.get_gang(user['gang_id']) if user['gang_id'] else None
    
    await callback.message.edit_text(
        f"📋 *Меню*\n📍 {city.emoji} {city.name}\n💰 ${user['money']} | ⭐ Ур.{user['level']}\n"
        f"{'🏴 ' + gang['gang_name'] if gang else ''}",
        parse_mode="Markdown"
    )

# ==================== NPC ОБНОВЛЕНИЕ ====================
async def update_npcs():
    """Обновление активностей NPC каждые 5 минут"""
    npc_manager.update_npc_activities()

# ==================== ЗАПУСК ====================
async def set_commands():
    commands = [
        BotCommand(command="start", description="Начать игру"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="gang_create", description="Создать банду"),
        BotCommand(command="rob", description="Ограбить игрока"),
        BotCommand(command="ref", description="Рефералы"),
    ]
    await bot.set_my_commands(commands)

async def main():
    logging.basicConfig(level=logging.INFO)
    await set_commands()
    
    scheduler.add_job(update_npcs, 'interval', minutes=5)
    scheduler.start()
    
    print("✅ Бот с NPC запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⏹ Бот остановлен")
