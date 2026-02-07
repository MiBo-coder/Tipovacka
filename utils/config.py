"""
Konfigurace aplikace
ZACHOVÁNO: Všechny konstanty z tipovacka_12.py
"""

import pytz

# --- ZÁKLADNÍ NASTAVENÍ ---
MAX_PLAYERS = 40
MAX_SCORE_VALUE = 20
TIMEZONE = pytz.timezone('Europe/Prague')

# --- GOOGLE SHEETS SLOUPCE ---
# Indexy sloupců v Google Sheetu "Tipy" (gspread je 1-based)
COL_TIP_DOMACI = 3
COL_TIP_HOSTE = 4
COL_TIP_PRODLOUZENI = 5

# --- VLAJKY TÝMŮ (ISO KÓDY) ---
FLAGS_ISO = {
    "Česko": "cz", 
    "Kanada": "ca", 
    "USA": "us", 
    "Švédsko": "se", 
    "Finsko": "fi", 
    "Slovensko": "sk", 
    "Německo": "de", 
    "Švýcarsko": "ch",
    "Dánsko": "dk", 
    "Lotyšsko": "lv", 
    "Rusko": "ru", 
    "Itálie": "it",
    "Francie": "fr", 
    "Kazachstán": "kz", 
    "Norsko": "no", 
    "Rakousko": "at"
}

# --- BANK A PLATBY ---
ENTRY_FEE = 150  # Startovné v Kč
BANK_ACCOUNT = "1596874001/2700"

# --- BEZPEČNOST ---
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_DURATION = 900  # 15 minut v sekundách

# --- BODOVÁNÍ (z originálu) ---
POINTS_CONFIG = {
    'max_base_points': 7,
    'min_winner_points': 2,
    'exact_match_bonus': 2,
    'playoff_multiplier': 1.5,
    'czech_team_bonus': 2,
    'overtime_correct': 1,
    'overtime_wrong': -1,
    'winner_points': 15,
    'medal_points': 4,
    'sharpshooter_bonus': 6,
    'tiper_dne_per_match': 0.5,
    'underdog_threshold': 0.20,
    'underdog_bonus': 1
}

# --- HISTORICKÉ VÝSLEDKY (z originálu) ---
HISTORY_HOCKEY = [
    {"Rok": 2025, "Turnaj": "MS - Švédsko/Dánsko", "🥇 1. Místo": "Brácha Tyrdy", "🥈 2. Místo": "Lukáš", "🥉 3. Místo": "Antonín"},
    {"Rok": 2024, "Turnaj": "MS - Česko", "🥇 1. Místo": "Luděk / Příbor", "🥈 2. Místo": "-", "🥉 3. Místo": "Tony B."},
    {"Rok": 2023, "Turnaj": "MS - Finsko/Lotyšsko", "🥇 1. Místo": "Tyrda", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Honza K."},
    {"Rok": 2022, "Turnaj": "MS - Finsko", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "Tonda V.", "🥉 3. Místo": "MiBo"},
    {"Rok": 2022, "Turnaj": "ZOH - Čína", "🥇 1. Místo": "Kedárek", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Kedar"},
    {"Rok": 2021, "Turnaj": "MS - Lotyšsko", "🥇 1. Místo": "Honza Geryk", "🥈 2. Místo": "Peťa údržbář", "🥉 3. Místo": "Janča"},
    {"Rok": 2019, "Turnaj": "MS - Slovensko", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Honza K."},
    {"Rok": 2018, "Turnaj": "MS - Dánsko", "🥇 1. Místo": "Dominik", "🥈 2. Místo": "Lukáš", "🥉 3. Místo": "Tonda V."},
    {"Rok": 2017, "Turnaj": "MS - Německo/Francie", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "Tonda V.", "🥉 3. Místo": "MiBo"},
    {"Rok": 2016, "Turnaj": "MS - Rusko", "🥇 1. Místo": "Vlasta", "🥈 2. Místo": "Kuba H.", "🥉 3. Místo": "MiBo"},
]

HISTORY_FOOTBALL = [
    {"Rok": 2024, "Turnaj": "EURO - Německo", "🥇 1. Místo": "Brácha Tyrdy", "🥈 2. Místo": "Antonín", "🥉 3. Místo": "Tyrda"},
    {"Rok": 2022, "Turnaj": "MS - Katar", "🥇 1. Místo": "Tony B.", "🥈 2. Místo": "Lukáš", "🥉 3. Místo": "MiBo"},
    {"Rok": 2021, "Turnaj": "EURO - 11 zemí", "🥇 1. Místo": "Dominik", "🥈 2. Místo": "Kedar", "🥉 3. Místo": "Tony B."},
    {"Rok": 2016, "Turnaj": "EURO - Francie", "🥇 1. Místo": "Vojta H.", "🥈 2. Místo": "Ondra T.", "🥉 3. Místo": "Luděk"},
]

# Uzávěrka pro tipování dlouhodobých sázek (nastavte podle potřeby)
DEADLINE = "2026-02-12 12:00" 

# Oficiální výsledky (zatím prázdné, doplní se až po skončení turnaje)
# Příklad po skončení: {'winner': 'Česko', 'medals': ['Česko', 'Kanada', 'USA']}
OFFICIAL_RESULTS = {
    'winner': '',   
    'medals': []     
}