import asyncio
import logging
import os
import random
import sqlite3
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import (
    CallbackQuery, Message, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, BotCommand
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import pytz

# ==================== ЗАГРУЗКА КОНФИГУРАЦИИ ====================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

moscow_tz = pytz.timezone('Europe/Moscow')

# ==================== СИСТЕМА ВЫЖИВАНИЯ ====================
class SurvivalStats:
    """Базовые параметры выживания"""
    MAX_HUNGER = 100      # 100 = сыт, 0 = голоден
    MAX_THIRST = 100      # 100 = не хочет пить, 0 = обезвожен
    MAX_HEALTH = 100      # 100 = здоров, 0 = мёртв
    MAX_SLEEP = 100       # 100 = бодр, 0 = истощён
    MAX_MOOD = 100        # 100 = счастлив, 0 = депрессия
    MAX_TEMPERATURE = 40  # Максимальная комфортная температура
    
    # Скорость истощения (в час)
    HUNGER_DECAY = 5      # -5 голода в час
    THIRST_DECAY = 7      # -7 жажды в час
    SLEEP_DECAY = 4       # -4 сна в час
    HEALTH_DECAY = 2      # -2 здоровья в час (если голоден/обезвожен)
    MOOD_DECAY = 1        # -1 настроения в час
    
    # Болезни
    DISEASES = {
        "flu": {
            "name": "🤒 Грипп",
            "health_decay": 5,
            "energy_penalty": 20,
            "cure_cost": 200,
            "duration_hours": 24,
            "contagion_chance": 0.3
        },
        "poisoning": {
            "name": "🤢 Отравление",
            "health_decay": 8,
            "energy_penalty": 30,
            "cure_cost": 300,
            "duration_hours": 12,
            "contagion_chance": 0
        },
        "broken_bone": {
            "name": "🦴 Перелом",
            "health_decay": 3,
            "energy_penalty": 50,
            "cure_cost": 1000,
            "duration_hours": 72,
            "contagion_chance": 0
        },
        "depression": {
            "name": "😔 Депрессия",
            "health_decay": 2,
            "energy_penalty": 40,
            "cure_cost": 500,
            "duration_hours": 48,
            "contagion_chance": 0.1
        },
        "covid": {
            "name": "🦠 Ковид",
            "health_decay": 6,
            "energy_penalty": 60,
            "cure_cost": 800,
            "duration_hours": 168,  # 7 дней
            "contagion_chance": 0.5
        }
    }
    
    # Еда и напитки
    FOOD_ITEMS = {
        "bread": {"name": "🍞 Хлеб", "hunger": 15, "price": 20, "type": "food", "expiry_hours": 48},
        "shaurma": {"name": "🌯 Шаурма", "hunger": 40, "price": 150, "type": "food", "expiry_hours": 12, "risk": 0.2},
        "doshirak": {"name": "🍜 Доширак", "hunger": 25, "price": 35, "type": "food", "expiry_hours": 8760},  # вечный
        "steak": {"name": "🥩 Стейк", "hunger": 60, "price": 500, "type": "food", "expiry_hours": 24, "mood": 10},
        "sushi": {"name": "🍣 Суши", "hunger": 35, "price": 300, "type": "food", "expiry_hours": 6, "risk": 0.15},
        "borsch": {"name": "🍲 Борщ", "hunger": 45, "price": 200, "type": "food", "expiry_hours": 72, "health": 5},
        "pizza": {"name": "🍕 Пицца", "hunger": 50, "price": 400, "type": "food", "expiry_hours": 24, "mood": 15},
        "shawarma_king": {"name": "👑 Царь-Шаурма", "hunger": 100, "price": 800, "type": "food", "expiry_hours": 6, "mood": 25, "risk": 0.3}
    }
    
    DRINK_ITEMS = {
        "water": {"name": "💧 Вода", "thirst": 30, "price": 15, "type": "drink", "expiry_hours": 8760},
        "coffee": {"name": "☕ Кофе", "thirst": 15, "price": 50, "type": "drink", "energy": 20, "mood": 5},
        "energy_drink": {"name": "⚡ Энергетик", "thirst": 10, "price": 60, "type": "drink", "energy": 40, "health": -3},
        "juice": {"name": "🧃 Сок", "thirst": 40, "price": 30, "type": "drink", "health": 5},
        "vodka": {"name": "🍸 Водка", "thirst": 5, "price": 200, "type": "drink", "mood": 20, "health": -10, "addiction_chance": 0.1},
        "kvas": {"name": "🍺 Квас", "thirst": 50, "price": 25, "type": "drink", "mood": 5},
        "champagne": {"name": "🍾 Шампанское", "thirst": 10, "price": 500, "type": "drink", "mood": 30, "health": -5},
        "mineral_water": {"name": "💎 Мин.Вода Премиум", "thirst": 40, "price": 150, "type": "drink", "health": 15, "mood": 10}
    }
    
    # Медикаменты
    MEDICAL_ITEMS = {
        "bandage": {"name": "🩹 Бинт", "health": 15, "price": 100, "type": "medical"},
        "painkiller": {"name": "💊 Обезбол", "health": 25, "price": 200, "type": "medical", "mood": 5},
        "antibiotic": {"name": "💉 Антибиотик", "health": 50, "price": 500, "type": "medical", "cures_disease": True},
        "vitamins": {"name": "🌿 Витамины", "health": 10, "price": 150, "type": "medical", "immunity_boost": 0.3},
        "first_aid_kit": {"name": "🏥 Аптечка", "health": 40, "price": 350, "type": "medical", "cures_disease": False},
        "morphine": {"name": "💉 Морфин", "health": 60, "price": 800, "type": "medical", "mood": 15, "addiction_chance": 0.3},
        "bandage_gold": {"name": "✨ Золотой бинт", "health": 100, "price": 2000, "type": "medical", "mood": 20, "cures_disease": True}
    }
    
    # Оружие и защита
    WEAPONS = {
        "fists": {"name": "👊 Кулаки", "damage": 5, "defense": 0, "price": 0, "type": "weapon"},
        "knife": {"name": "🔪 Нож", "damage": 15, "defense": 5, "price": 300, "type": "weapon"},
        "baseball_bat": {"name": "🏏 Бита", "damage": 20, "defense": 10, "price": 500, "type": "weapon"},
        "pistol": {"name": "🔫 Пистолет", "damage": 35, "defense": 15, "price": 1500, "type": "weapon", "illegal": True},
        "shotgun": {"name": "💥 Дробовик", "damage": 50, "defense": 20, "price": 3000, "type": "weapon", "illegal": True},
        "ak47": {"name": "🔫 АК-47", "damage": 70, "defense": 25, "price": 5000, "type": "weapon", "illegal": True},
        "rpg": {"name": "🚀 РПГ", "damage": 95, "defense": 5, "price": 15000, "type": "weapon", "illegal": True}
    }

# ==================== ГОРОДА (БЕЗ ИЗМЕНЕНИЙ) ====================
class City:
    def __init__(self, id: str, name: str, emoji: str, country: str,
                 min_level: int, living_cost: int, taxi_price: int,
                 description: str, speciality: str, crime_rate: float = 0.1,
                 disease_risk: float = 0.05, temperature: int = 20):
        self.id = id
        self.name = name
        self.emoji = emoji
        self.country = country
        self.min_level = min_level
        self.living_cost = living_cost
        self.taxi_price = taxi_price
        self.description = description
        self.speciality = speciality
        self.crime_rate = crime_rate
        self.disease_risk = disease_risk
        self.temperature = temperature

CITIES = {
    "newark": City("newark", "Нью-Арк", "🌆", "🇺🇸 США", 1, 10, 25,
                   "Суровый промышленный город. Высокий уровень преступности.",
                   "Промышленность, сталь", crime_rate=0.3, disease_risk=0.08, temperature=15),
    "losangeles": City("losangeles", "Лос-Анжела", "🌴", "🇺🇸 США", 5, 50, 100,
                       "Город ангелов и голливудской мечты.",
                       "Киноиндустрия, туризм", crime_rate=0.15, disease_risk=0.04, temperature=25),
    "moscow": City("moscow", "Москоу", "❄️", "🇷🇺 Россия", 3, 35, 75,
                   "Величественная столица. Медведи на улицах — миф (но не точно).",
                   "Нефть, газ, IT", crime_rate=0.2, disease_risk=0.06, temperature=5),
    "tokyo": City("tokyo", "Токио", "🗾", "🇯🇵 Япония", 4, 45, 90,
                  "Город будущего и древних традиций.",
                  "Технологии, робототехника", crime_rate=0.05, disease_risk=0.03, temperature=18),
    "london": City("london", "Лондон", "☔", "🇬🇧 Великобритания", 6, 60, 120,
                   "Финансовое сердце Европы. Постоянные дожди.",
                   "Финансы, банки", crime_rate=0.12, disease_risk=0.05, temperature=12),
    "dubai": City("dubai", "Дубай", "🏜️", "🇦🇪 ОАЭ", 8, 100, 200,
                  "Город роскоши и небоскребов.",
                  "Нефть, роскошь", crime_rate=0.02, disease_risk=0.01, temperature=35),
    "yerevan": City("yerevan", "Ереван", "⛰️", "🇦🇲 Армения", 2, 20, 50,
                    "Древний город с богатой историей и вкуснейшим кофе.",
                    "Туризм, коньяк", crime_rate=0.08, disease_risk=0.04, temperature=20),
    "shanghai": City("shanghai", "Шанхай", "🏮", "🇨🇳 Китай", 7, 80, 150,
                     "Экономический гигант Азии. +100 к социальному рейтингу.",
                     "Производство, технологии", crime_rate=0.03, disease_risk=0.07, temperature=22)
}

# ==================== БАЗА ДАННЫХ (ОБНОВЛЕННАЯ) ====================
class Database:
    def __init__(self, db_path: str = "game.db"):
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
                bank INTEGER DEFAULT 0,
                crypto INTEGER DEFAULT 0,
                energy INTEGER DEFAULT 100,
                max_energy INTEGER DEFAULT 100,
                level INTEGER DEFAULT 1,
                xp INTEGER DEFAULT 0,
                reputation INTEGER DEFAULT 0,
                current_city TEXT DEFAULT 'newark',
                house_id TEXT,
                work_level INTEGER DEFAULT 1,
                last_work TIMESTAMP,
                last_energy TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                referral_code TEXT UNIQUE,
                referred_by INTEGER,
                total_referrals INTEGER DEFAULT 0,
                vip INTEGER DEFAULT 0,
                
                -- Параметры выживания
                hunger INTEGER DEFAULT 100,
                thirst INTEGER DEFAULT 100,
                health INTEGER DEFAULT 100,
                sleep INTEGER DEFAULT 100,
                mood INTEGER DEFAULT 100,
                temperature REAL DEFAULT 20.0,
                immunity REAL DEFAULT 0.5,
                
                -- Болезни
                disease TEXT,
                disease_start TIMESTAMP,
                disease_end TIMESTAMP,
                
                -- Зависимости
                alcohol_addiction REAL DEFAULT 0,
                drug_addiction REAL DEFAULT 0,
                
                -- Оружие
                weapon TEXT DEFAULT 'fists',
                armor TEXT,
                
                -- Статистика
                total_kills INTEGER DEFAULT 0,
                total_deaths INTEGER DEFAULT 0,
                crimes_committed INTEGER DEFAULT 0,
                jail_time INTEGER DEFAULT 0,
                
                -- Временные метки
                last_hunger_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_thirst_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_sleep_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_health_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_mood_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_temperature_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_disease_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS inventory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                item_id TEXT,
                item_type TEXT,
                quantity INTEGER DEFAULT 1,
                expiry_date TIMESTAMP,
                active_until TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            );
            
            CREATE TABLE IF NOT EXISTS crimes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                crime_type TEXT,
                victim_id INTEGER,
                loot INTEGER DEFAULT 0,
                success BOOLEAN,
                jail_time INTEGER DEFAULT 0,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            );
            
            CREATE TABLE IF NOT EXISTS taxi_drivers (
                driver_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                driver_name TEXT,
                car_model TEXT,
                price_mult REAL DEFAULT 1.0,
                rating REAL DEFAULT 5.0,
                total_rides INTEGER DEFAULT 0,
                earnings INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            );
            
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                type TEXT,
                amount INTEGER,
                description TEXT,
                city TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS hospital_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                treatment_type TEXT,
                cost INTEGER,
                cured_disease TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            );
        """)
        self.conn.commit()
    
    def get_user(self, user_id: int) -> Optional[Dict]:
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = self.cursor.fetchone()
        return dict(row) if row else None
    
    def create_user(self, user_id: int, username: str, first_name: str, referral_code: str = None):
        own_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        
        referrer_id = None
        if referral_code:
            self.cursor.execute("SELECT user_id FROM users WHERE referral_code = ?", (referral_code,))
            referrer = self.cursor.fetchone()
            if referrer and referrer[0] != user_id:
                referrer_id = referrer[0]
        
        self.cursor.execute("""
            INSERT INTO users (user_id, username, first_name, referral_code, referred_by)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username, first_name, own_code, referrer_id))
        
        if referrer_id:
            self.cursor.execute("""
                UPDATE users SET money = money + 50, total_referrals = total_referrals + 1
                WHERE user_id = ?
            """, (referrer_id,))
            self.cursor.execute("UPDATE users SET money = money + 25 WHERE user_id = ?", (user_id,))
        
        self.conn.commit()
    
    def update_user(self, user_id: int, **kwargs):
        set_clause = ", ".join([f"{k} = ?" for k in kwargs.keys()])
        values = list(kwargs.values()) + [user_id]
        self.cursor.execute(f"UPDATE users SET {set_clause} WHERE user_id = ?", values)
        self.conn.commit()
    
    def add_money(self, user_id: int, amount: int, type_: str = "income", description: str = "", city: str = None):
        self.cursor.execute("UPDATE users SET money = money + ? WHERE user_id = ?", (amount, user_id))
        self.cursor.execute("""
            INSERT INTO transactions (user_id, type, amount, description, city)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, type_, amount, description, city))
        self.conn.commit()
    
    def get_inventory(self, user_id: int) -> List[Dict]:
        self.cursor.execute("SELECT * FROM inventory WHERE user_id = ?", (user_id,))
        return [dict(row) for row in self.cursor.fetchall()]
    
    def add_item(self, user_id: int, item_id: str, item_type: str, quantity: int = 1, expiry_hours: int = 24):
        expiry = (datetime.now() + timedelta(hours=expiry_hours)).isoformat()
        self.cursor.execute("""
            INSERT INTO inventory (user_id, item_id, item_type, quantity, expiry_date)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, item_id, item_type, quantity, expiry))
        self.conn.commit()
    
    def consume_item(self, user_id: int, item_id: str) -> bool:
        self.cursor.execute("""
            SELECT id, quantity FROM inventory 
            WHERE user_id = ? AND item_id = ? AND quantity > 0
            ORDER BY expiry_date ASC LIMIT 1
        """, (user_id, item_id))
        item = self.cursor.fetchone()
        
        if not item:
            return False
        
        if item['quantity'] > 1:
            self.cursor.execute("UPDATE inventory SET quantity = quantity - 1 WHERE id = ?", (item['id'],))
        else:
            self.cursor.execute("DELETE FROM inventory WHERE id = ?", (item['id'],))
        
        self.conn.commit()
        return True
    
    def heal_disease(self, user_id: int) -> bool:
        self.cursor.execute("""
            UPDATE users SET disease = NULL, disease_start = NULL, disease_end = NULL
            WHERE user_id = ?
        """, (user_id,))
        self.conn.commit()
        return True

# Инициализация базы данных
db = Database()

# ==================== ТЕКСТУРЫ ДЛЯ КАРТЫ ГОРОДА ====================
class CityLocation:
    """Локации внутри города"""
    def __init__(self, id: str, name: str, emoji: str, description: str, actions: List[str]):
        self.id = id
        self.name = name
        self.emoji = emoji
        self.description = description
        self.actions = actions

CITY_LOCATIONS = {
    "hospital": CityLocation("hospital", "Больница", "🏥",
                            "Здесь можно вылечить болезни и купить медикаменты.",
                            ["heal", "buy_medicine", "checkup"]),
    "pharmacy": CityLocation("pharmacy", "Аптека", "💊",
                             "Легальные и не очень препараты.",
                             ["buy_medicine", "buy_drugs"]),
    "supermarket": CityLocation("supermarket", "Супермаркет", "🏪",
                                "Еда, вода и предметы первой необходимости.",
                                ["buy_food", "buy_drinks", "buy_misc"]),
    "restaurant": CityLocation("restaurant", "Ресторан", "🍽",
                               "Дорогая еда для повышения настроения.",
                               ["eat", "drink", "socialize"]),
    "police_station": CityLocation("police_station", "Полицейский участок", "🚔",
                                   "Здесь регистрируют преступления... или совершают их.",
                                   ["report_crime", "pay_fine", "bribe"]),
    "black_market": CityLocation("black_market", "Чёрный рынок", "🌑",
                                 "Оружие, наркотики и другие незаконные товары.",
                                 ["buy_weapon", "buy_drugs", "sell_stolen"]),
    "gym": CityLocation("gym", "Спортзал", "🏋️",
                        "Тренируйся, чтобы стать сильнее!",
                        ["train", "sparring"]),
    "park": CityLocation("park", "Парк", "🌳",
                         "Отдыхай и восстанавливай настроение.",
                         ["rest", "jogging", "meet_people"]),
    "bar": CityLocation("bar", "Бар", "🍻",
                        "Выпей с друзьями... или с незнакомцами.",
                        ["drink", "socialize", "fight"]),
    "home": CityLocation("home", "Дом", "🏠",
                         "Твоё убежище. Здесь можно поспать и восстановиться.",
                         ["sleep", "rest", "store_items"])
}

# ==================== КЛАВИАТУРЫ (ОБНОВЛЕННЫЕ) ====================
class Keyboards:
    @staticmethod
    def main_navigation() -> ReplyKeyboardMarkup:
        builder = ReplyKeyboardBuilder()
        builder.row(KeyboardButton(text="💼 РАБОТА"), KeyboardButton(text="🎰 КАЗИНО"))
        builder.row(KeyboardButton(text="🛒 МАГАЗИН"), KeyboardButton(text="🏠 ДОМ"))
        builder.row(KeyboardButton(text="🗺 ГОРОД"), KeyboardButton(text="🎒 ИНВЕНТАРЬ"))
        builder.row(KeyboardButton(text="📊 СТАТУС"), KeyboardButton(text="🗺 КАРТА"))
        builder.row(KeyboardButton(text="🏆 ТОП"), KeyboardButton(text="❓ ПОМОЩЬ"))
        return builder.as_markup(resize_keyboard=True)
    
    @staticmethod
    def city_locations() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for loc_id, loc in CITY_LOCATIONS.items():
            builder.button(text=f"{loc.emoji} {loc.name}", callback_data=f"location_{loc_id}")
        builder.button(text="🔙 На карту", callback_data="back_to_map")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def survival_actions() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🍞 Есть", callback_data="survival_eat")
        builder.button(text="💧 Пить", callback_data="survival_drink")
        builder.button(text="😴 Спать", callback_data="survival_sleep")
        builder.button(text="💊 Лечиться", callback_data="survival_heal")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def crime_actions() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔫 Ограбить прохожего", callback_data="crime_mug")
        builder.button(text="🏪 Ограбить магазин", callback_data="crime_robbery")
        builder.button(text="🚗 Угнать машину", callback_data="crime_carjack")
        builder.button(text="💰 Кража со взломом", callback_data="crime_burglary")
        builder.button(text="🔙 Назад", callback_data="back_to_city")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def supermarket_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for item_id, item in list(SurvivalStats.FOOD_ITEMS.items())[:5]:
            builder.button(text=f"{item['name']} (${item['price']})", callback_data=f"buyfood_{item_id}")
        for item_id, item in list(SurvivalStats.DRINK_ITEMS.items())[:4]:
            builder.button(text=f"{item['name']} (${item['price']})", callback_data=f"buydrink_{item_id}")
        builder.button(text="🔙 Назад", callback_data="back_to_city")
        builder.adjust(2)
        return builder.as_markup()
    
    @staticmethod
    def hospital_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        builder.button(text="🏥 Вылечить болезнь ($500)", callback_data="hospital_cure_disease")
        builder.button(text="💊 Купить лекарства", callback_data="hospital_buy_meds")
        builder.button(text="🩺 Проверить здоровье (бесплатно)", callback_data="hospital_checkup")
        builder.button(text="🔙 Назад", callback_data="back_to_city")
        builder.adjust(1)
        return builder.as_markup()
    
    @staticmethod
    def black_market_menu() -> InlineKeyboardMarkup:
        builder = InlineKeyboardBuilder()
        for weapon_id, weapon in SurvivalStats.WEAPONS.items():
            if weapon_id != "fists":
                builder.button(
                    text=f"{weapon['name']} (${weapon['price']})",
                    callback_data=f"buyweapon_{weapon_id}"
                )
        builder.button(text="🔙 Назад", callback_data="back_to_city")
        builder.adjust(1)
        return builder.as_markup()

# ==================== СИСТЕМА ВЫЖИВАНИЯ (ЛОГИКА) ====================
class SurvivalSystem:
    @staticmethod
    def update_hunger(user: Dict, hours_passed: float):
        """Обновление голода"""
        decay = int(SurvivalStats.HUNGER_DECAY * hours_passed)
        new_hunger = max(0, user['hunger'] - decay)
        
        # Если голод на нуле - урон здоровью
        if new_hunger <= 0 and user['hunger'] > 0:
            db.update_user(user['user_id'], health=max(0, user['health'] - 10))
        
        db.update_user(user['user_id'], hunger=new_hunger, last_hunger_update=datetime.now().isoformat())
    
    @staticmethod
    def update_thirst(user: Dict, hours_passed: float):
        """Обновление жажды"""
        decay = int(SurvivalStats.THIRST_DECAY * hours_passed)
        new_thirst = max(0, user['thirst'] - decay)
        
        if new_thirst <= 0 and user['thirst'] > 0:
            db.update_user(user['user_id'], health=max(0, user['health'] - 15))
        
        db.update_user(user['user_id'], thirst=new_thirst, last_thirst_update=datetime.now().isoformat())
    
    @staticmethod
    def update_sleep(user: Dict, hours_passed: float):
        """Обновление сна"""
        decay = int(SurvivalStats.SLEEP_DECAY * hours_passed)
        new_sleep = max(0, user['sleep'] - decay)
        
        if new_sleep <= 20:
            penalty = 30 if new_sleep <= 0 else 10
            db.update_user(user['user_id'], max_energy=100 - penalty)
        
        db.update_user(user['user_id'], sleep=new_sleep, last_sleep_update=datetime.now().isoformat())
    
    @staticmethod
    def update_health(user: Dict, hours_passed: float):
        """Обновление здоровья с учётом болезней и состояний"""
        decay = 0
        
        # Базовый decay
        if user['hunger'] < 20:
            decay += SurvivalStats.HEALTH_DECAY
        if user['thirst'] < 20:
            decay += SurvivalStats.HEALTH_DECAY
        if user['sleep'] < 20:
            decay += SurvivalStats.HEALTH_DECAY
        if user['temperature'] < 0 or user['temperature'] > 35:
            decay += 1
        
        # Болезни усиливают decay
        if user['disease'] and user['disease'] in SurvivalStats.DISEASES:
            disease = SurvivalStats.DISEASES[user['disease']]
            decay += disease['health_decay']
            
            # Проверка окончания болезни
            if user['disease_end']:
                end_time = datetime.fromisoformat(user['disease_end'])
                if datetime.now() > end_time:
                    # Шанс самоизлечения
                    if random.random() < user['immunity']:
                        db.heal_disease(user['user_id'])
        
        # Зависимости
        if user['alcohol_addiction'] > 0.5:
            decay += 2
        if user['drug_addiction'] > 0.3:
            decay += 3
        
        new_health = max(0, min(100, user['health'] - int(decay * hours_passed)))
        
        # Смерть
        if new_health <= 0:
            SurvivalSystem.handle_death(user)
        else:
            db.update_user(user['user_id'], health=new_health, last_health_update=datetime.now().isoformat())
    
    @staticmethod
    def update_mood(user: Dict, hours_passed: float):
        """Обновление настроения"""
        decay = SurvivalStats.MOOD_DECAY
        
        # Факторы влияющие на настроение
        if user['hunger'] < 30:
            decay += 2
        if user['thirst'] < 30:
            decay += 2
        if user['sleep'] < 30:
            decay += 3
        if user['disease']:
            decay += 3
        if user['money'] > 10000:
            decay -= 1
        
        new_mood = max(0, min(100, user['mood'] - int(decay * hours_passed)))
        db.update_user(user['user_id'], mood=new_mood, last_mood_update=datetime.now().isoformat())
    
    @staticmethod
    def update_temperature(user: Dict):
        """Обновление температуры в зависимости от города и сезона"""
        city = CITIES.get(user['current_city'], CITIES['newark'])
        base_temp = city.temperature
        
        # Сезонная корректировка
        season = get_current_season()
        season_mod = {"winter": -15, "spring": 0, "summer": 15, "autumn": -5}
        base_temp += season_mod.get(season, 0)
        
        # Время суток
        time = get_time_of_day()
        time_mod = {"morning": -2, "afternoon": 5, "evening": 0, "night": -5}
        base_temp += time_mod.get(time, 0)
        
        # Эффекты температуры
        if base_temp < 0:
            # Шанс заболеть
            if random.random() < 0.1 and not user['disease']:
                SurvivalSystem.infect_disease(user, "flu")
        elif base_temp > 30:
            # Обезвоживание быстрее
            db.update_user(user['user_id'], thirst=max(0, user['thirst'] - 5))
        
        db.update_user(user['user_id'], temperature=base_temp, last_temperature_update=datetime.now().isoformat())
    
    @staticmethod
    def infect_disease(user: Dict, disease_id: str):
        """Заразить игрока болезнью"""
        disease = SurvivalStats.DISEASES.get(disease_id)
        if not disease or user['disease']:
            return False
        
        now = datetime.now()
        end_time = now + timedelta(hours=disease['duration_hours'])
        
        # Иммунитет может предотвратить
        if random.random() < user['immunity']:
            return False
        
        db.update_user(user['user_id'],
                       disease=disease_id,
                       disease_start=now.isoformat(),
                       disease_end=end_time.isoformat())
        return True
    
    @staticmethod
    def handle_death(user: Dict):
        """Обработка смерти игрока"""
        penalty = int(user['money'] * 0.2)  # Потеря 20% денег
        
        db.update_user(user['user_id'],
                       money=max(0, user['money'] - penalty),
                       health=50,  # Воскрешение с 50 HP
                       hunger=50,
                       thirst=50,
                       sleep=50,
                       mood=30,
                       total_deaths=user['total_deaths'] + 1)
        
        # Лечим все болезни (смерть лечит всё... или нет)
        db.heal_disease(user['user_id'])
    
    @staticmethod
    def eat_food(user: Dict, food_id: str) -> Tuple[bool, str]:
        """Съесть еду"""
        food = SurvivalStats.FOOD_ITEMS.get(food_id)
        if not food:
            return False, "❌ Еда не найдена!"
        
        # Проверка на испорченность
        inventory = db.get_inventory(user['user_id'])
        food_items = [i for i in inventory if i['item_id'] == food_id]
        
        if not food_items:
            return False, "❌ У тебя нет этой еды!"
        
        # Риск отравления
        if 'risk' in food and random.random() < food['risk']:
            SurvivalSystem.infect_disease(user, "poisoning")
            db.consume_item(user['user_id'], food_id)
            return True, "🤢 Еда была испорчена! Ты отравился!"
        
        # Применяем эффекты
        new_hunger = min(100, user['hunger'] + food['hunger'])
        updates = {'hunger': new_hunger}
        
        if 'mood' in food:
            updates['mood'] = min(100, user['mood'] + food['mood'])
        if 'health' in food:
            updates['health'] = min(100, user['health'] + food['health'])
        
        db.update_user(user['user_id'], **updates)
        db.consume_item(user['user_id'], food_id)
        
        return True, f"{food['name']} съеден! Голод: {new_hunger}/100"
    
    @staticmethod
    def drink(drink_id: str, user: Dict) -> Tuple[bool, str]:
        """Питьё"""
        drink = SurvivalStats.DRINK_ITEMS.get(drink_id)
        if not drink:
            return False, "❌ Напиток не найден!"
        
        if not db.consume_item(user['user_id'], drink_id):
            return False, "❌ У тебя нет этого напитка!"
        
        # Эффекты
        updates = {}
        if 'thirst' in drink:
            updates['thirst'] = min(100, user['thirst'] + drink['thirst'])
        if 'energy' in drink:
            updates['energy'] = min(100, user['energy'] + drink['energy'])
        if 'mood' in drink:
            updates['mood'] = min(100, user['mood'] + drink['mood'])
        if 'health' in drink:
            updates['health'] = max(0, min(100, user['health'] + drink['health']))
        
        # Зависимость от алкоголя
        if 'addiction_chance' in drink and random.random() < drink['addiction_chance']:
            updates['alcohol_addiction'] = min(1.0, user['alcohol_addiction'] + 0.05)
        
        db.update_user(user['user_id'], **updates)
        
        return True, f"{drink['name']} выпит! Жажда: {updates.get('thirst', user['thirst'])}/100"
    
    @staticmethod
    def sleep_action(user: Dict) -> str:
        """Сон восстанавливает силы"""
        if user['sleep'] >= 90:
            return "😴 Ты не хочешь спать!"
        
        # Спим 6 часов
        new_sleep = min(100, user['sleep'] + 60)
        new_energy = min(100, user['energy'] + 50)
        
        db.update_user(user['user_id'],
                       sleep=new_sleep,
                       energy=new_energy,
                       last_sleep_update=datetime.now().isoformat())
        
        return f"😴 Ты поспал! Сон: {new_sleep}/100, Энергия: {new_energy}/100"

# ==================== КРИМИНАЛЬНАЯ СИСТЕМА ====================
class CrimeSystem:
    CRIME_TYPES = {
        "mug": {
            "name": "🔫 Ограбление прохожего",
            "min_reward": 50,
            "max_reward": 500,
            "risk": 0.4,
            "jail_time": 2,  # часа
            "min_weapon_damage": 5,
            "xp_reward": 20
        },
        "robbery": {
            "name": "🏪 Ограбление магазина",
            "min_reward": 200,
            "max_reward": 2000,
            "risk": 0.6,
            "jail_time": 6,
            "min_weapon_damage": 15,
            "xp_reward": 50
        },
        "carjack": {
            "name": "🚗 Угон машины",
            "min_reward": 500,
            "max_reward": 5000,
            "risk": 0.5,
            "jail_time": 4,
            "min_weapon_damage": 10,
            "xp_reward": 35
        },
        "burglary": {
            "name": "💰 Кража со взломом",
            "min_reward": 1000,
            "max_reward": 10000,
            "risk": 0.7,
            "jail_time": 8,
            "min_weapon_damage": 20,
            "xp_reward": 80
        }
    }
    
    @staticmethod
    def commit_crime(user: Dict, crime_type: str) -> Tuple[bool, str, int, int]:
        """Совершить преступление"""
        crime = CrimeSystem.CRIME_TYPES.get(crime_type)
        if not crime:
            return False, "❌ Неизвестное преступление!", 0, 0
        
        # Проверка оружия
        weapon_data = SurvivalStats.WEAPONS.get(user['weapon'], SurvivalStats.WEAPONS['fists'])
        if weapon_data['damage'] < crime['min_weapon_damage']:
            return False, f"❌ Нужно оружие мощнее! Минимальный урон: {crime['min_weapon_damage']}", 0, 0
        
        # Проверка энергии
        if user['energy'] < 20:
            return False, "❌ Недостаточно энергии!", 0, 0
        
        # Расчёт успеха с учётом города
        city = CITIES.get(user['current_city'], CITIES['newark'])
        success_chance = 1 - crime['risk'] - city.crime_rate + (user['level'] * 0.02)
        success_chance = max(0.1, min(0.9, success_chance))
        
        # Трата энергии
        db.update_user(user['user_id'], energy=user['energy'] - 20)
        
        if random.random() < success_chance:
            # Успех
            reward = random.randint(crime['min_reward'], crime['max_reward'])
            db.add_money(user['user_id'], reward, "crime", crime['name'], user['current_city'])
            db.update_user(user['user_id'],
                           xp=user['xp'] + crime['xp_reward'],
                           crimes_committed=user['crimes_committed'] + 1,
                           reputation=user['reputation'] - 5)  # Теряем репутацию
            
            return True, f"✅ {crime['name']} успешно! +${reward}", reward, 0
        else:
            # Провал - тюрьма
            jail_hours = crime['jail_time']
            fine = int(reward_guess := random.randint(crime['min_reward'], crime['max_reward']) * 0.5)
            
            db.update_user(user['user_id'],
                           money=max(0, user['money'] - fine),
                           jail_time=jail_hours,
                           reputation=user['reputation'] - 10)
            
            return False, f"🚔 Ты пойман! Штраф: ${fine}. Тюрьма: {jail_hours}ч.", 0, jail_hours

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_current_season() -> str:
    month = datetime.now(moscow_tz).month
    if month in [12, 1, 2]: return "winter"
    if month in [3, 4, 5]: return "spring"
    if month in [6, 7, 8]: return "summer"
    return "autumn"

def get_time_of_day() -> str:
    hour = datetime.now(moscow_tz).hour
    if 6 <= hour < 12: return "morning"
    if 12 <= hour < 17: return "afternoon"
    if 17 <= hour < 22: return "evening"
    return "night"

def get_city_multiplier(city_id: str) -> float:
    multipliers = {"newark": 1.0, "yerevan": 1.2, "moscow": 1.5, "tokyo": 1.8,
                   "losangeles": 2.0, "london": 2.5, "shanghai": 3.0, "dubai": 4.0}
    return multipliers.get(city_id, 1.0)

# ==================== ИНИЦИАЛИЗАЦИЯ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)
scheduler = AsyncIOScheduler()

# ==================== ОБРАБОТЧИКИ КОМАНД ====================
@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject = None):
    user_id = message.from_user.id
    username = message.from_user.username or "Player"
    first_name = message.from_user.first_name or "Игрок"
    
    user = db.get_user(user_id)
    
    if not user:
        referral_code = command.args if command.args else None
        db.create_user(user_id, username, first_name, referral_code)
        
        await message.answer(
            f"🌆 *Добро пожаловать в Нью-Арк, {first_name}!*\n\n"
            f"🎯 Это мир выживания и криминала!\n\n"
            f"📊 *Твои показатели:*\n"
            f"🍞 Голод: 100/100\n"
            f"💧 Жажда: 100/100\n"
            f"❤️ Здоровье: 100/100\n"
            f"😴 Сон: 100/100\n"
            f"😊 Настроение: 100/100\n"
            f"💰 Деньги: $500\n\n"
            f"⚠ *Следи за выживанием!* Если голод/жажда на нуле — теряешь здоровье.\n"
            f"💀 При смерти теряешь 20% денег!\n\n"
            f"💡 Используй кнопки меню:\n"
            f"🗺 ГОРОД — посетить локации\n"
            f"📊 СТАТУС — проверить показатели",
            reply_markup=Keyboards.main_navigation(),
            parse_mode="Markdown"
        )
    else:
        await message.answer(
            f"👋 *С возвращением, {first_name}!*",
            reply_markup=Keyboards.main_navigation(),
            parse_mode="Markdown"
        )

@router.message(F.text == "📊 СТАТУС")
@router.message(Command("status"))
async def show_status(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала /start")
        return
    
    city = CITIES.get(user['current_city'], CITIES['newark'])
    
    # Определяем статусы
    hunger_status = "🔴" if user['hunger'] < 20 else "🟡" if user['hunger'] < 50 else "🟢"
    thirst_status = "🔴" if user['thirst'] < 20 else "🟡" if user['thirst'] < 50 else "🟢"
    health_status = "🔴" if user['health'] < 20 else "🟡" if user['health'] < 50 else "🟢"
    sleep_status = "🔴" if user['sleep'] < 20 else "🟡" if user['sleep'] < 50 else "🟢"
    mood_status = "🔴" if user['mood'] < 20 else "🟡" if user['mood'] < 50 else "🟢"
    
    weapon_data = SurvivalStats.WEAPONS.get(user['weapon'], SurvivalStats.WEAPONS['fists'])
    
    status_text = (
        f"📊 *Статус выживания*\n\n"
        f"👤 {user['first_name']} | Ур.{user['level']}\n"
        f"📍 {city.emoji} {city.name}\n\n"
        f"{hunger_status} 🍞 Голод: {user['hunger']}/100\n"
        f"{thirst_status} 💧 Жажда: {user['thirst']}/100\n"
        f"{health_status} ❤️ Здоровье: {user['health']}/100\n"
        f"{sleep_status} 😴 Сон: {user['sleep']}/100\n"
        f"{mood_status} 😊 Настроение: {user['mood']}/100\n\n"
        f"🌡 Температура: {user['temperature']:.1f}°C\n"
        f"🛡 Иммунитет: {user['immunity']:.0%}\n"
        f"🗡 Оружие: {weapon_data['name']} (Урон: {weapon_data['damage']})\n\n"
        f"{'🤒 Болезнь: ' + SurvivalStats.DISEASES[user['disease']]['name'] if user['disease'] else '✅ Здоров'}\n"
        f"{'🔒 В тюрьме! ' + str(user['jail_time']) + 'ч' if user['jail_time'] > 0 else '✅ Свободен'}\n\n"
        f"💰 Деньги: ${user['money']} | ⚡ Энергия: {user['energy']}"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🍞 Есть", callback_data="survival_eat")
    builder.button(text="💧 Пить", callback_data="survival_drink")
    builder.button(text="😴 Спать", callback_data="survival_sleep")
    builder.button(text="💊 Лечиться", callback_data="survival_heal")
    builder.adjust(2)
    
    await message.answer(status_text, reply_markup=builder.as_markup(), parse_mode="Markdown")

@router.message(F.text == "🗺 ГОРОД")
async def city_menu(message: Message):
    user = db.get_user(message.from_user.id)
    if not user:
        await message.answer("❌ Сначала /start")
        return
    
    if user['jail_time'] > 0:
        await message.answer(f"🔒 Ты в тюрьме! Осталось: {user['jail_time']}ч")
        return
    
    city = CITIES.get(user['current_city'], CITIES['newark'])
    
    await message.answer(
        f"🏙 *{city.emoji} {city.name}*\n\n"
        f"Выбери локацию для посещения:\n"
        f"⚠ Уровень преступности: {city.crime_rate:.0%}\n"
        f"🦠 Риск болезней: {city.disease_risk:.0%}",
        reply_markup=Keyboards.city_locations(),
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data.startswith("location_"))
async def location_handler(callback: CallbackQuery):
    location_id = callback.data.replace("location_", "")
    location = CITY_LOCATIONS.get(location_id)
    
    if not location:
        await callback.answer("❌ Локация не найдена!")
        return
    
    if location_id == "supermarket":
        await callback.message.edit_text(
            f"🏪 *Супермаркет*\n💰 Купи еду и напитки:",
            reply_markup=Keyboards.supermarket_menu(),
            parse_mode="Markdown"
        )
    elif location_id == "hospital":
        await callback.message.edit_text(
            f"🏥 *Больница*\n💊 Лечение и медикаменты:",
            reply_markup=Keyboards.hospital_menu(),
            parse_mode="Markdown"
        )
    elif location_id == "black_market":
        user = db.get_user(callback.from_user.id)
        if user['reputation'] < -10:
            await callback.message.edit_text(
                f"🌑 *Чёрный рынок*\n🔫 Покупка оружия:",
                reply_markup=Keyboards.black_market_menu(),
                parse_mode="Markdown"
            )
        else:
            await callback.answer("❌ Нужна репутация ниже -10!", show_alert=True)
    elif location_id == "bar":
        await callback.message.edit_text(
            f"🍻 *Бар*\nХочешь выпить или устроить драку?",
            reply_markup=Keyboards.crime_actions(),
            parse_mode="Markdown"
        )
    elif location_id == "police_station":
        await callback.message.edit_text(
            f"🚔 *Полицейский участок*\nТы что-то натворил?",
            reply_markup=Keyboards.crime_actions(),
            parse_mode="Markdown"
        )
    else:
        await callback.answer(f"🚧 {location.name} в разработке!", show_alert=True)

@router.callback_query(lambda c: c.data.startswith("buyfood_"))
async def buy_food(callback: CallbackQuery):
    food_id = callback.data.replace("buyfood_", "")
    user = db.get_user(callback.from_user.id)
    food = SurvivalStats.FOOD_ITEMS.get(food_id)
    
    if not food:
        await callback.answer("❌ Еда не найдена!")
        return
    
    if user['money'] < food['price']:
        await callback.answer(f"❌ Нужно ${food['price']}!")
        return
    
    db.add_money(user['user_id'], -food['price'], "purchase", f"Куплено: {food['name']}")
    db.add_item(user['user_id'], food_id, "food", 1, food.get('expiry_hours', 24))
    
    await callback.answer(f"✅ Куплено: {food['name']}!")

@router.callback_query(lambda c: c.data.startswith("buydrink_"))
async def buy_drink(callback: CallbackQuery):
    drink_id = callback.data.replace("buydrink_", "")
    user = db.get_user(callback.from_user.id)
    drink = SurvivalStats.DRINK_ITEMS.get(drink_id)
    
    if not drink:
        await callback.answer("❌ Напиток не найден!")
        return
    
    if user['money'] < drink['price']:
        await callback.answer(f"❌ Нужно ${drink['price']}!")
        return
    
    db.add_money(user['user_id'], -drink['price'], "purchase", f"Куплено: {drink['name']}")
    db.add_item(user['user_id'], drink_id, "drink", 1, 8760)  # Напитки не портятся долго
    
    await callback.answer(f"✅ Куплено: {drink['name']}!")

@router.callback_query(lambda c: c.data == "survival_eat")
async def survival_eat(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    inventory = db.get_inventory(user['user_id'])
    food_items = [i for i in inventory if i['item_type'] == 'food']
    
    if not food_items:
        await callback.answer("❌ У тебя нет еды! Купи в супермаркете.")
        return
    
    # Авто-выбор первой еды
    food_id = food_items[0]['item_id']
    success, message = SurvivalSystem.eat_food(user, food_id)
    
    await callback.answer(message, show_alert=True)
    
    # Обновляем статус
    user = db.get_user(callback.from_user.id)
    await show_status(callback.message)
    await callback.message.edit_text(
        callback.message.text + f"\n\n{message}",
        reply_markup=callback.message.reply_markup,
        parse_mode="Markdown"
    )

@router.callback_query(lambda c: c.data == "survival_drink")
async def survival_drink(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    inventory = db.get_inventory(user['user_id'])
    drink_items = [i for i in inventory if i['item_type'] == 'drink']
    
    if not drink_items:
        await callback.answer("❌ У тебя нет напитков! Купи в супермаркете.")
        return
    
    drink_id = drink_items[0]['item_id']
    success, message = SurvivalSystem.drink(drink_id, user)
    
    await callback.answer(message, show_alert=True)

@router.callback_query(lambda c: c.data == "survival_sleep")
async def survival_sleep(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    message = SurvivalSystem.sleep_action(user)
    await callback.answer(message, show_alert=True)

@router.callback_query(lambda c: c.data == "survival_heal")
async def survival_heal(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    
    if user['health'] >= 80 and not user['disease']:
        await callback.answer("✅ Ты здоров!")
        return
    
    # Авто-лечение через аптечку если есть
    inventory = db.get_inventory(user['user_id'])
    meds = [i for i in inventory if i['item_type'] == 'medical']
    
    if meds:
        med_id = meds[0]['item_id']
        med_data = SurvivalStats.MEDICAL_ITEMS.get(med_id)
        if med_data:
            db.consume_item(user['user_id'], med_id)
            db.update_user(user['user_id'], health=min(100, user['health'] + med_data.get('health', 0)))
            await callback.answer(f"💊 Использовано: {med_data['name']}!")
            return
    
    await callback.answer("❌ Нет медикаментов! Купи в аптеке или больнице.")

@router.callback_query(lambda c: c.data == "hospital_cure_disease")
async def hospital_cure(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)
    
    if not user['disease']:
        await callback.answer("✅ У тебя нет болезней!")
        return
    
    if user['money'] < 500:
        await callback.answer("❌ Нужно $500!")
        return
    
    db.add_money(user['user_id'], -500, "medical", "Лечение болезни")
    db.heal_disease(user['user_id'])
    
    await callback.answer("✅ Болезнь вылечена!")

@router.callback_query(lambda c: c.data.startswith("buyweapon_"))
async def buy_weapon(callback: CallbackQuery):
    weapon_id = callback.data.replace("buyweapon_", "")
    user = db.get_user(callback.from_user.id)
    weapon = SurvivalStats.WEAPONS.get(weapon_id)
    
    if not weapon:
        await callback.answer("❌ Оружие не найдено!")
        return
    
    if user['money'] < weapon['price']:
        await callback.answer(f"❌ Нужно ${weapon['price']}!")
        return
    
    db.add_money(user['user_id'], -weapon['price'], "purchase", f"Куплено: {weapon['name']}")
    db.update_user(user['user_id'], weapon=weapon_id)
    
    await callback.answer(f"✅ Куплено: {weapon['name']}!")

@router.callback_query(lambda c: c.data == "back_to_city")
async def back_to_city(callback: CallbackQuery):
    await city_menu(callback.message)

@router.message(Command("help"))
@router.message(F.text == "❓ ПОМОЩЬ")
async def help_cmd(message: Message):
    help_text = (
        "📚 *Помощь по выживанию*\n\n"
        "🎯 *Основное:*\n"
        "• Следи за голодом, жаждой, сном и здоровьем!\n"
        "• Покупай еду в супермаркете\n"
        "• Лечи болезни в больнице\n"
        "• Спи дома для восстановления\n\n"
        "⚔ *Оружие и преступления:*\n"
        "• Покупай оружие на чёрном рынке\n"
        "• Совершай преступления для быстрого заработка\n"
        "• Риск: тюрьма или смерть!\n\n"
        "🗺 *Команды:*\n"
        "/status — статус выживания\n"
        "/city — локации города\n"
        "/inventory — инвентарь\n"
        "/help — помощь\n\n"
        "💀 *Смерть:* При смерти теряешь 20% денег!"
    )
    await message.answer(help_text, parse_mode="Markdown")

# ==================== ФОНОВЫЕ ОБНОВЛЕНИЯ ====================
async def update_survival():
    """Обновление параметров выживания для всех игроков"""
    db.cursor.execute("SELECT * FROM users")
    users = db.cursor.fetchall()
    
    for user_row in users:
        user = dict(user_row)
        
        # Сколько часов прошло с последнего обновления
        last_update = datetime.fromisoformat(user['last_hunger_update'])
        hours_passed = (datetime.now() - last_update).total_seconds() / 3600
        
        if hours_passed < 0.01:  # Меньше 36 секунд — пропускаем
            continue
        
        # Обновляем все параметры
        SurvivalSystem.update_hunger(user, hours_passed)
        SurvivalSystem.update_thirst(user, hours_passed)
        SurvivalSystem.update_sleep(user, hours_passed)
        SurvivalSystem.update_health(user, hours_passed)
        SurvivalSystem.update_mood(user, hours_passed)
        
        # Температура обновляется каждый час
        if (datetime.now() - datetime.fromisoformat(user['last_temperature_update'])).total_seconds() > 3600:
            SurvivalSystem.update_temperature(user)
        
        # Случайная болезнь
        if random.random() < 0.001:  # 0.1% шанс каждый тик
            city = CITIES.get(user['current_city'], CITIES['newark'])
            if random.random() < city.disease_risk:
                disease = random.choice(list(SurvivalStats.DISEASES.keys()))
                SurvivalSystem.infect_disease(user, disease)

# ==================== ЗАПУСК ====================
async def set_commands():
    commands = [
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="status", description="Статус выживания"),
        BotCommand(command="city", description="Город"),
        BotCommand(command="inventory", description="Инвентарь"),
        BotCommand(command="map", description="Карта городов"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="work", description="Работа"),
        BotCommand(command="shop", description="Магазин"),
        BotCommand(command="ref", description="Рефералы"),
        BotCommand(command="top", description="Рейтинг"),
    ]
    await bot.set_my_commands(commands)

async def on_startup():
    logging.basicConfig(level=logging.INFO)
    await set_commands()
    scheduler.add_job(update_survival, 'interval', seconds=36)
    scheduler.start()
    print("✅ Бот с системой выживания запущен!")

async def main():
    await on_startup()
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("⏹ Бот остановлен")
