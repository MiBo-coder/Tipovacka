"""
Datová vrstva - Google Sheets
ZACHOVÁNO: Přesná logika z tipovacka_12.py s oauth2client
"""

import streamlit as st
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import os
from utils.config import TIMEZONE, COL_TIP_DOMACI, COL_TIP_HOSTE, COL_TIP_PRODLOUZENI


@st.cache_resource
def get_gspread_client():
    """
    Vytvoří a drží spojení na API.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    
    if os.path.exists('credentials.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    else:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    return gspread.authorize(creds)


@st.cache_resource
def get_worksheets_resources():
    """
    Otevře Spreadsheet a vrátí objekty Worksheetů.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    client = get_gspread_client()
    sh = client.open("Tipovacka_Data")
    
    ws_zapasy = sh.worksheet("Zapasy")
    ws_tipy = sh.worksheet("Tipy")
    ws_users = sh.worksheet("Uzivatele")
    
    # Bezpečné načtení Nastavení
    try:
        ws_nastaveni = sh.worksheet("Nastaveni")
    except gspread.WorksheetNotFound:
        ws_nastaveni = None
    
    # Načtení chatu
    try:
        ws_chat = sh.worksheet("Chat")
    except gspread.WorksheetNotFound:
        ws_chat = sh.add_worksheet(title="Chat", rows=1000, cols=4)
    
    return ws_zapasy, ws_tipy, ws_users, ws_nastaveni, ws_chat


def parse_date(date_str):
    """
    Parse datum z Google Sheets.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        return date_str
    
    dt = None
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            dt = datetime.strptime(str(date_str), fmt)
            break
        except ValueError:
            continue
    
    # Přiřadíme timezone Praha
    if dt and dt.tzinfo is None:
        return TIMEZONE.localize(dt)
    return dt


@st.cache_data(ttl=60)
def load_all_data():
    """
    Načte všechna data s cachingem (60s TTL).
    PŮVODNÍ LOGIKA z tipovacka_12.py
    
    Returns:
        (zapasy, tipy, users, config, chat_data)
    """
    ws_zapasy, ws_tipy, ws_users, ws_nastaveni, ws_chat = get_worksheets_resources()
    
    # Načtení dat
    zapasy_raw = ws_zapasy.get_all_records()
    tipy_raw = ws_tipy.get_all_records()
    users_raw = ws_users.get_all_records()
    chat_raw = ws_chat.get_all_records()
    
    # Zpracování zápasů
    zapasy = []
    for z in zapasy_raw:
        z_obj = z.copy()
        z_obj['Datum_Obj'] = parse_date(z.get('Datum'))
        z_obj['ID'] = str(z['ID'])
        zapasy.append(z_obj)
    
    # Zpracování tipů
    tipy = []
    for t in tipy_raw:
        t_obj = t.copy()
        t_obj['Zapas_ID'] = str(t['Zapas_ID'])
        t_obj['Email'] = str(t['Email'])
        tipy.append(t_obj)
    
    # Zpracování users
    users = users_raw
    
    # Konfigurace
    config = {}
    if ws_nastaveni:
        nastaveni_raw = ws_nastaveni.get_all_records()
        config = {row['Klic']: row['Hodnota'] for row in nastaveni_raw}
    
    # Chat
    chat_data = chat_raw
    
    return zapasy, tipy, users, config, chat_data


def save_tips_batch(ws_tipy, user_email: str, tips_dict: dict, existing_tips: list):
    """
    Uloží tipy v dávce (batch).
    PŮVODNÍ FUNKCE z tipovacka_12.py s optimalizací
    
    Args:
        ws_tipy: Worksheet objekt
        user_email: Email uživatele
        tips_dict: {match_id: (home, away, ot)}
        existing_tips: Existující tipy
    """
    all_data = ws_tipy.get_all_records()
    
    # Mapování: (Email, Zapas_ID) -> Číslo řádku (gspread index = i + 2)
    existing_map = {}
    for i, row in enumerate(all_data):
        key = (str(row['Email']), str(row['Zapas_ID']))
        existing_map[key] = i + 2
    
    updates = []
    new_rows = []
    
    for zid, (d, h, ot) in tips_dict.items():
        # Validace prodloužení
        final_ot = ot if abs(int(d) - int(h)) == 1 else ""
        
        key = (str(user_email), str(zid))
        
        if key in existing_map:
            # UPDATE existujícího řádku
            row_idx = existing_map[key]
            updates.append(gspread.Cell(row_idx, COL_TIP_DOMACI, d))
            updates.append(gspread.Cell(row_idx, COL_TIP_HOSTE, h))
            updates.append(gspread.Cell(row_idx, COL_TIP_PRODLOUZENI, final_ot))
        else:
            # INSERT nového řádku
            new_rows.append([user_email, zid, d, h, final_ot])
    
    # Provedeme batch operace
    if updates:
        ws_tipy.update_cells(updates)
    if new_rows:
        ws_tipy.append_rows(new_rows)
    
    # Invalidace cache
    st.cache_data.clear()


def update_user_password(ws_users, user_idx: int, new_hash: str):
    """
    Aktualizuje heslo uživatele (pro automatickou migraci na bcrypt).
    """
    ws_users.update_cell(user_idx + 2, 3, new_hash)
    st.cache_data.clear()


def create_reset_request(email: str):
    """
    Vytvoří požadavek na reset hesla v listu 'Reset'.
    PŮVODNÍ LOGIKA pro obnovu hesla.
    """
    client = get_gspread_client()
    sh = client.open("Tipovacka_Data")
    
    try:
        ws_reset = sh.worksheet("Reset")
    except gspread.WorksheetNotFound:
        # Pokud list neexistuje, vytvoříme ho (bezpečnostní pojistka)
        ws_reset = sh.add_worksheet(title="Reset", rows=1000, cols=3)
        ws_reset.append_row(["Email", "Datum", "Status"]) # Hlavička
    
    # Zápis požadavku
    ws_reset.append_row([email, str(datetime.now()), "PENDING"])