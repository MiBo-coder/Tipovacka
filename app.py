import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import time
import math
import os
import hashlib
import pytz

# --- KONFIGURACE A KONSTANTY ---
st.set_page_config(page_title="Tipovačka hokej - Olympiáda 2026", layout="wide")

# Limit hráčů pro registraci přes formulář
MAX_PLAYERS = 40

# Indexy sloupců v Google Sheetu "Tipy" (gspread je 1-based)
COL_TIP_DOMACI = 3
COL_TIP_HOSTE = 4

st.markdown("""
<style>
    /* Zvětšení písma */
    html, body, [class*="css"] {
        font-size: 18px !important;
    }
    /* Zvýraznění přesných tipů */
    .exact-match {
        background-color: #ffd700;
        color: black;
        font-weight: bold;
        padding: 4px;
        border-radius: 4px;
    }
    /* Zúžení formuláře pro tipování */
    .stNumberInput {
        max-width: 150px;
    }
    /* Vycentrování tabulek - vynucení */
    .dataframe { text-align: center !important; }
    th { text-align: center !important; }
    td { text-align: center !important; }
    .stDataFrame { text-align: center !important; }
    
    /* Decentní box pro nejbližší zápas */
    .next-match-box {
        background-color: #e8f4f8;
        padding: 15px;
        border-radius: 8px;
        border-left: 5px solid #00aaff;
        margin-bottom: 20px;
        color: #0f5132;
    }
    
    /* Patička s upozorněním */
    .footer-warning {
        margin-top: 50px;
        padding: 10px;
        background-color: #fff3cd;
        border: 1px solid #ffeeba;
        color: #856404;
        border-radius: 5px;
        text-align: center;
        font-size: 0.8em;
    }
</style>
""", unsafe_allow_html=True)

# --- VLAJKY JAKO OBRÁZKY (ISO KÓDY) ---
FLAGS_ISO = {
    "Česko": "cz", "Kanada": "ca", "USA": "us", "Švédsko": "se", 
    "Finsko": "fi", "Slovensko": "sk", "Německo": "de", "Švýcarsko": "ch",
    "Dánsko": "dk", "Lotyšsko": "lv", "Rusko": "ru", "Itálie": "it",
    "Francie": "fr", "Kazachstán": "kz", "Norsko": "no", "Rakousko": "at"
}
def get_flag(t):
    iso = FLAGS_ISO.get(t)
    if iso:
        return f'<img src="https://flagcdn.com/24x18/{iso}.png" style="vertical-align: middle; height: 16px;">'
    return ""

def get_team_label(team_name):
    flag_html = get_flag(team_name)
    return f"{flag_html} {team_name}"

# --- BEZPEČNOST (HASHING) ---
def make_hash(password):
    """Vytvoří SHA-256 hash z hesla."""
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def check_password(input_pass, stored_pass):
    """
    Ověří heslo. Podporuje:
    1. Nová hashovaná hesla.
    2. Stará plain-text hesla (pro zpětnou kompatibilitu).
    """
    input_hashed = make_hash(input_pass)
    if str(stored_pass) == input_hashed:
        return True
    if str(stored_pass) == str(input_pass):
        return True
    return False

# --- PŘIPOJENÍ (CACHED RESOURCES) ---
@st.cache_resource
def get_gspread_client():
    """Vytvoří a drží spojení na API."""
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
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
    Toto se provede jen JEDNOU při startu, ne při každém kliknutí -> ŠETŘÍ API.
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
        
    return ws_zapasy, ws_tipy, ws_users, ws_nastaveni

# --- POMOCNÉ FUNKCE (LOGIKA) ---
def parse_date(date_str):
    if not date_str: return None
    # Pokud už je to datetime (díky optimalizaci), vrátíme ho
    if isinstance(date_str, datetime): return date_str
    
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%d.%m.%Y"):
        try: return datetime.strptime(str(date_str), fmt)
        except ValueError: continue
    return None

def is_past_deadline(deadline_str):
    if not deadline_str: return False
    d = parse_date(deadline_str)
    return d and datetime.now() > d

def get_all_teams(zapasy):
    teams = set()
    ignored = ["čtvrtfinále", "semifinále", "finále", "o 3. místo", "o bronz", "vítěz"]
    for z in zapasy:
        d, h = str(z['Domaci']), str(z['Hoste'])
        if not any(x in d.lower() for x in ignored): teams.add(d)
        if not any(x in h.lower() for x in ignored): teams.add(h)
    return sorted(list(teams))

# --- BATCH UPDATE ---
def save_tips_batch(ws_tipy, user_email, tips_to_save, existing_tips):
    updates = []
    new_rows = []
    existing_map = {}
    
    # Mapování existujících tipů
    for i, row in enumerate(existing_tips):
        # i + 2, protože gspread je 1-based a 1. řádek je hlavička
        existing_map[(str(row['Email']), str(row['Zapas_ID']))] = i + 2
        
    for zid, (d, h) in tips_to_save.items():
        key = (user_email, str(zid))
        if key in existing_map:
            row_idx = existing_map[key]
            updates.append(gspread.Cell(row_idx, COL_TIP_DOMACI, d))
            updates.append(gspread.Cell(row_idx, COL_TIP_HOSTE, h))
        else:
            new_rows.append([user_email, zid, d, h])
            
    if updates: ws_tipy.update_cells(updates)
    if new_rows: ws_tipy.append_rows(new_rows)
    st.cache_data.clear() # Invalidace cache dat

# --- LOGIKA BODŮ ---
def spocitej_body_zapas(tip_d, tip_h, real_d, real_h, team_d, team_h, faze):
    if str(real_d) == "" or str(real_h) == "": return 0, False, False
    try:
        tip_d, tip_h = int(tip_d), int(tip_h)
        real_d, real_h = int(real_d), int(real_h)
    except: return 0, False, False

    base_points = 0
    is_exact = False
    winner_real = 1 if real_d > real_h else 2
    winner_tip = 1 if tip_d > tip_h else (2 if tip_h > tip_d else 0)
    if winner_real != winner_tip: return 0, False, False

    diff = abs(real_d - tip_d) + abs(real_h - tip_h)
    base_points += max(2, 7 - diff)

    if tip_d == real_d and tip_h == real_h:
        base_points += 2
        is_exact = True

    if "playoff" in str(faze).lower():
        base_points = math.ceil(base_points * 1.5)

    match_teams = (str(team_d) + " " + str(team_h)).lower()
    if "česko" in match_teams or "czech" in match_teams:
        base_points += 2

    return base_points, is_exact, (base_points > 0)

def spocitej_dlouhodobe_body(user_row, official_results):
    body = 0
    if official_results.get('winner') and str(user_row.get('Tip_Vitez')) == official_results['winner']: body += 15
    real_medals = [m for m in official_results.get('medals', []) if m]
    user_medals = [str(user_row.get('Tip_Med1')), str(user_row.get('Tip_Med2')), str(user_row.get('Tip_Med3'))]
    unique_tips = set([t for t in user_medals if t])
    for tip in unique_tips:
        if tip in real_medals: body += 4
    return body

# --- DATA LOADING (CACHED VALUES) ---
@st.cache_data(ttl=60) 
def load_data_values():
    ws_zapasy, ws_tipy, ws_users, ws_nastaveni = get_worksheets_resources()
    zapasy_raw = ws_zapasy.get_all_records()
    for z in zapasy_raw:
        z['Datum_Obj'] = parse_date(z['Datum'])
    tipy = ws_tipy.get_all_records()
    users = ws_users.get_all_records()
    nastaveni = ws_nastaveni.get_all_records() if ws_nastaveni else []
    return zapasy_raw, tipy, users, nastaveni

# --- CALC RANKING (PRO TRENDY) ---
def get_user_points_at_date(users, tipy, zapasy, date_limit=None):
    points = {str(u['Email']): 0 for u in users}
    tips_map = {(str(t['Email']), t['Zapas_ID']): t for t in tipy}
    for z in zapasy:
        match_date = z.get('Datum_Obj')
        if date_limit and match_date and match_date > date_limit: continue
        if str(z['Skore_Domaci']) != "":
            for u in users:
                email = str(u['Email'])
                t = tips_map.get((email, z['ID']))
                if t:
                    p, _, _ = spocitej_body_zapas(t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], z.get('Faze',''))
                    points[email] += p
    return points

# --- MAIN APP ---
def main():
    col1, col2 = st.columns([1, 4])
    col2.title("🏒 Tipovačka hokej - Olympiáda 2026")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    try:
        zapasy, tipy, users, nastaveni_data = load_data_values()
        ws_zapasy, ws_tipy, ws_users, ws_nastaveni = get_worksheets_resources()
    except Exception as e:
        st.error(f"Chyba databáze (zkus chvíli počkat a refresh): {e}"); st.stop()

    config = {row['Klic']: row['Hodnota'] for row in nastaveni_data}
    DEADLINE = config.get('deadline', '2026-02-06 12:00')
    OFFICIAL_RESULTS = {
        'winner': config.get('vitez_turnaje', ''),
        'medals': [config.get('med_1', ''), config.get('med_2', ''), config.get('med_3', '')]
    }

    # --- LOGIN & REGISTRACE ---
    if not st.session_state['logged_in']:
        tab_login, tab_reg = st.tabs(["🔑 Přihlášení", "📝 Registrace"])
        contact_info = "🆘 Zapomněl jsi heslo? Napiš na: **tipovacka.mibo@gmail.com**"

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email"); password = st.text_input("Heslo", type="password")
                if st.form_submit_button("Vstoupit"):
                    clean_email = email.strip().lower()
                    df_u = pd.DataFrame(users)
                    if not df_u.empty:
                        df_u['Email_L'] = df_u['Email'].astype(str).str.strip().str.lower()
                        u = df_u[df_u['Email_L'] == clean_email]
                        
                        if not u.empty and check_password(password, u.iloc[0]['Heslo']):
                            st.session_state['logged_in'] = True; st.session_state['user_email'] = str(u.iloc[0]['Email']); st.session_state['user_name'] = u.iloc[0]['Jmeno']; st.session_state['user_team'] = u.iloc[0].get('Tym', ''); st.session_state['user_role'] = u.iloc[0]['Role']; st.rerun()
                        else: st.error("Chyba přihlášení.")
            st.markdown(contact_info)

        with tab_reg:
            # Kontrola kapacity
            if len(users) >= MAX_PLAYERS:
                st.warning(f"⚠️ **Kapacita tipovačky ({MAX_PLAYERS} hráčů) je naplněna.**")
                st.info("Bohužel už není možné se automaticky zaregistrovat. Pokud máš pocit, že se jedná o chybu, nebo máš protekci, napiš na **tipovacka.mibo@gmail.com**.")
            else:
                with st.form("reg_form"):
                    r_email = st.text_input("Email"); r_name = st.text_input("Jméno"); r_pass = st.text_input("Heslo", type="password")
                    if st.form_submit_button("Vytvořit účet"):
                        email_clean = r_email.strip().lower(); name_clean = r_name.strip().lower()
                        email_exists = any(str(u.get('Email')).strip().lower() == email_clean for u in users)
                        name_exists = any(str(u.get('Jmeno')).strip().lower() == name_clean for u in users)
                        if email_exists: st.error("Tento email už existuje!")
                        elif name_exists: st.error(f"Jméno '{r_name}' už někdo používá.")
                        elif not r_email or not r_name or not r_pass: st.error("Vyplň všechna pole.")
                        else:
                            hashed_pw = make_hash(r_pass)
                            # Default role 'user'
                            ws_users.append_row([r_email, r_name, hashed_pw, 0, 'user', '', '', '', '', '', 'NE', ''])
                            st.cache_data.clear()
                            st.success("Registrace úspěšná! Přihlašuji...")
                            
                            # AUTO LOGIN LOGIKA
                            st.session_state['logged_in'] = True
                            st.session_state['user_email'] = r_email
                            st.session_state['user_name'] = r_name
                            st.session_state['user_team'] = ''
                            st.session_state['user_role'] = 'user'
                            time.sleep(1)
                            st.rerun()
            st.markdown(contact_info)

    # --- APP (PŘIHLÁŠEN) ---
    else:
        c1, c2, c3 = st.columns([3, 4, 1])
        c1.write(f"👤 **{st.session_state['user_name']}**")
        c1.caption(f"Tým: {st.session_state.get('user_team') or '-'}")
        if c3.button("Odhlásit"): st.session_state['logged_in'] = False; st.rerun()
        st.divider()

        # --- NOVINKA: NEJBLIŽŠÍ ZÁPAS (S OPRAVOU ČASOVÝCH PÁSEM) ---
        prague_tz = pytz.timezone('Europe/Prague')
        now_prague = datetime.now(prague_tz)
        match_dt_aware = None
        upcoming_match = None

        for z in zapasy:
            if str(z['Skore_Domaci']) == "":
                match_dt_naive = z.get('Datum_Obj')
                if match_dt_naive:
                    try: match_dt_aware_temp = prague_tz.localize(match_dt_naive)
                    except ValueError: match_dt_aware_temp = match_dt_naive.replace(tzinfo=prague_tz)
                    if match_dt_aware_temp > now_prague:
                        upcoming_match = z
                        match_dt_aware = match_dt_aware_temp
                        break
        
        if upcoming_match and match_dt_aware:
            delta = match_dt_aware - now_prague
            hours, remainder = divmod(delta.seconds, 3600); minutes, _ = divmod(remainder, 60)
            
            tips_d, tips_h = 0, 0
            for t in tipy:
                if t['Zapas_ID'] == upcoming_match['ID']:
                    if t['Tip_Domaci'] > t['Tip_Hoste']: tips_d += 1
                    elif t['Tip_Hoste'] > t['Tip_Domaci']: tips_h += 1
            total_tips = tips_d + tips_h
            perc_d = int(tips_d/total_tips*100) if total_tips else 0
            perc_h = int(tips_h/total_tips*100) if total_tips else 0
            
            f_d = get_flag(upcoming_match['Domaci']); f_h = get_flag(upcoming_match['Hoste'])
            
            st.markdown(f"""
            <div class="next-match-box">
                <b>⏱️ Nejbližší zápas:</b> {f_d} {upcoming_match['Domaci']} vs {f_h} {upcoming_match['Hoste']} (za {delta.days}d {hours}h {minutes}m)<br>
                <small>Jak tipují hráči: {perc_d}% domácí / {perc_h}% hosté</small>
            </div>
            """, unsafe_allow_html=True)

        # VÝPOČTY BODŮ
        match_points = {}; exact_matches = {}; matches_scored = {}; stats_basic = {}; stats_playoff = {}
        zapas_map = {z['ID']: z for z in zapasy}
        finished_matches = [z for z in zapasy if str(z['Skore_Domaci']) != ""]
        is_tournament_over = (len(finished_matches) == len(zapasy) and len(zapasy) > 0)
        
        for u in users: 
            email = str(u['Email'])
            match_points[email] = 0; exact_matches[email] = 0; matches_scored[email] = 0; stats_basic[email] = 0; stats_playoff[email] = 0
            
        tips_map = {}
        for t in tipy:
            tips_map[(str(t['Email']), t['Zapas_ID'])] = t
            zid = t['Zapas_ID']; email = str(t['Email'])
            
            if zid in zapas_map and str(zapas_map[zid]['Skore_Domaci']) != "":
                z = zapas_map[zid]
                faze = str(z.get('Faze', '')).lower()
                p, ie, sa = spocitej_body_zapas(t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], faze)
                match_points[email] += p
                if ie: exact_matches[email] += 1
                if sa: matches_scored[email] += 1
                if "playoff" in faze or "finále" in faze or "o 3. místo" in faze: stats_playoff[email] += p
                else: stats_basic[email] += p

        # Bonus ostrostřelci
        max_exact = 0; bonus_ostrostrelci = {}
        if exact_matches: max_exact = max(exact_matches.values())
        for email, count in exact_matches.items():
            bonus_ostrostrelci[email] = 6 if (is_tournament_over and count == max_exact and max_exact > 0) else 0

        long_term_points = {}
        for u in users:
            email = str(u['Email'])
            long_term_points[email] = spocitej_dlouhodobe_body(u, OFFICIAL_RESULTS) + bonus_ostrostrelci.get(email, 0)
        
        total_points = {e: match_points.get(e, 0) + long_term_points.get(e, 0) for e in match_points}

        # PŘÍPRAVA DAT PRO ŽEBŘÍČEK & TRENDY
        rd = []
        for u in users:
            e = str(u['Email'])
            rd.append({
                "Email": e, 
                "Hráč": u['Jmeno'], 
                "Tým": u.get('Tym', '-'), 
                "Zaplaceno": str(u.get('Zaplaceno', 'NE')).upper(), # Pro filtrování vítězů
                "Body Zápasy": match_points.get(e,0), 
                "Body Bonusy": long_term_points.get(e,0), 
                "Celkem": total_points.get(e,0)
            })
        df_rank = pd.DataFrame(rd).sort_values("Celkem", ascending=False).reset_index(drop=True)
        df_rank.index += 1
        df_rank['Poradi'] = df_rank.index

        # Trendy
        yesterday_limit = datetime.now() - timedelta(days=1)
        pts_yesterday = get_user_points_at_date(users, tipy, zapasy, date_limit=yesterday_limit)
        rd_prev = []
        for u in users:
            e = str(u['Email'])
            b_prev = pts_yesterday.get(e, 0)
            rd_prev.append({"Email": e, "Total": b_prev})
        df_prev = pd.DataFrame(rd_prev).sort_values("Total", ascending=False).reset_index(drop=True)
        df_prev.index += 1
        df_prev['Poradi'] = df_prev.index
        prev_ranks = df_prev.set_index('Email')['Poradi'].to_dict()

        df_rank['Vývoj pořadí'] = ""
        for idx, row in df_rank.iterrows():
            email = row['Email']
            if email in prev_ranks:
                diff = prev_ranks[email] - row['Poradi'] 
                if diff > 0: df_rank.at[idx, 'Vývoj pořadí'] = f"🟢 ▲{diff}"
                elif diff < 0: df_rank.at[idx, 'Vývoj pořadí'] = f"🔴 ▼{abs(diff)}"
                else: df_rank.at[idx, 'Vývoj pořadí'] = "➖"
            else:
                df_rank.at[idx, 'Vývoj pořadí'] = "🆕"

        # ZÁLOŽKY
        tabs = st.tabs(["🏒 Tipování", "🕵️ Přehled", "🏆 Medaile", "🥇 Žebříček", "🎯 Statistiky", "⚙️ Profil", "📜 Pravidla", "🏛️ Historické výsledky", "💰 Startovné a výhry"])
        t_matches, t_overview, t_long, t_rank, t_stats, t_prof, t_rules, t_history, t_bank = tabs

        # 1. TIPOVÁNÍ
        with t_matches:
            st.header("Tvoje tipy na jednotlivé zápasy")
            moje_tipy_dict = {t['Zapas_ID']: {'d': t['Tip_Domaci'], 'h': t['Tip_Hoste']} for t in tipy if str(t['Email']) == st.session_state['user_email']}
            with st.form("tips_form"):
                tips_to_save = {} 
                for z in zapasy:
                    zid = z['ID']
                    d_obj = z.get('Datum_Obj')
                    d_str = d_obj.strftime("%d.%m. %H:%M") if d_obj else z['Datum']
                    label = f"{get_team_label(z['Domaci'])} - {get_team_label(z['Hoste'])}"
                    st.markdown(f"**{label}** <small>({d_str})</small>", unsafe_allow_html=True)
                    if str(z['Skore_Domaci']) != "":
                        mt = moje_tipy_dict.get(zid, {})
                        p, ie, _ = spocitej_body_zapas(mt.get('d'), mt.get('h'), z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], z.get('Faze',''))
                        st.info(f"Výsledek: {z['Skore_Domaci']}:{z['Skore_Hoste']} | Tvůj tip: {mt.get('d','-')}:{mt.get('h','-')} | **{p}b** {'⭐' if ie else ''}")
                    else:
                        c1, c2, _ = st.columns([1,1,3])
                        mt = moje_tipy_dict.get(zid, {'d': 0, 'h': 0})
                        v_d = c1.number_input("D", value=int(mt['d']), key=f"d_{zid}", label_visibility="collapsed")
                        v_h = c2.number_input("H", value=int(mt['h']), key=f"h_{zid}", label_visibility="collapsed")
                        tips_to_save[zid] = (v_d, v_h)
                    st.write("---")
                if st.form_submit_button("💾 Uložit tipy"):
                    with st.spinner("Ukládám..."): save_tips_batch(ws_tipy, st.session_state['user_email'], tips_to_save, tipy); st.success("Uloženo!"); time.sleep(1); st.rerun()

        # 2. PŘEHLED
        with t_overview:
            st.header("Globální přehled tipů")
            if not finished_matches: st.info("Zatím žádné odehrané zápasy.")
            else:
                data = []; tips_map = {(str(t['Email']), t['Zapas_ID']): t for t in tipy}
                for z in finished_matches:
                    faze = z.get('Faze', '')
                    row = {
                        "Zápas": f"{z['Domaci']} - {z['Hoste']}", 
                        "Fáze": faze, 
                        "Výsledek": f"{z['Skore_Domaci']}:{z['Skore_Hoste']}"
                    }
                    for u in users:
                        t = tips_map.get((str(u['Email']), z['ID']))
                        if t:
                            p, ie, _ = spocitej_body_zapas(t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], z.get('Faze',''))
                            txt = f"{t['Tip_Domaci']}:{t['Tip_Hoste']} ({p}b)"
                            if ie: txt = f"⭐ {txt}"
                        else: txt = "-"
                        row[u['Jmeno']] = txt
                    data.append(row)
                st.dataframe(pd.DataFrame(data).style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)

        # 3. DLOUHODOBÉ
        with t_long:
            st.header("Tvoje tipy na vítěze a medailisty")
            me_idx = next((i for i, u in enumerate(users) if str(u['Email']) == st.session_state['user_email']), None)
            mr = users[me_idx] if me_idx is not None else {}
            has_complete_tips = (str(mr.get('Tip_Vitez','')).strip() and str(mr.get('Tip_Med1','')).strip() and str(mr.get('Tip_Med2','')).strip() and str(mr.get('Tip_Med3','')).strip())
            if has_complete_tips: st.success("✅ **Máte natipováno.**")
            else: st.warning("⚠️ **Pozor:** Chybí vám natipovat vítěze a medailisty!")
            st.info("Uzávěrka před začátkem turnaje!")
            lck = is_past_deadline(DEADLINE)
            if lck: st.warning(f"Sázky uzavřeny ({DEADLINE})")
            ht = get_all_teams(zapasy)
            with st.form("lb"):
                sw = st.selectbox("Celkový Vítěz", ht, index=ht.index(mr.get('Tip_Vitez')) if mr.get('Tip_Vitez') in ht else 0, disabled=lck)
                c1,c2,c3 = st.columns(3)
                m1 = c1.selectbox("Medaile 1", ht, index=ht.index(mr.get('Tip_Med1')) if mr.get('Tip_Med1') in ht else 0, key="m1", disabled=lck)
                m2 = c2.selectbox("Medaile 2", ht, index=ht.index(mr.get('Tip_Med2')) if mr.get('Tip_Med2') in ht else 1, key="m2", disabled=lck)
                m3 = c3.selectbox("Medaile 3", ht, index=ht.index(mr.get('Tip_Med3')) if mr.get('Tip_Med3') in ht else 2, key="m3", disabled=lck)
                if not lck and st.form_submit_button("💾 Uložit medaile"):
                    row_idx = me_idx + 2
                    updates = [
                        gspread.Cell(row_idx, 7, sw),
                        gspread.Cell(row_idx, 8, m1),
                        gspread.Cell(row_idx, 9, m2),
                        gspread.Cell(row_idx, 10, m3)
                    ]
                    try:
                        ws_users.update_cells(updates); st.cache_data.clear(); st.success("Uloženo!"); st.rerun()
                    except Exception as e: st.error(f"Chyba při ukládání: {e}")

        # 4. ŽEBŘÍČEK
        with t_rank:
            if OFFICIAL_RESULTS.get('winner'):
                # FILTR: Gratulujeme jen těm, co zaplatili
                df_winners = df_rank[df_rank['Zaplaceno'] == 'ANO'].sort_values("Celkem", ascending=False)
                
                if len(df_winners) >= 3:
                    st.success("🎉 **TURNAJ UKONČEN! GRATULACE VÍTĚZŮM!** 🎉")
                    n1 = df_winners.iloc[0]['Hráč']; n2 = df_winners.iloc[1]['Hráč']; n3 = df_winners.iloc[2]['Hráč']
                    st.markdown(f"### 🥇 {n1} | 🥈 {n2} | 🥉 {n3}")
                    st.markdown("Pro předání výhry se ozvěte na **tipovacka.mibo@gmail.com**.")
            
            st.header("Celkové pořadí")
            
            if len(df_rank) > 0:
                s1 = df_rank.iloc[0]['Celkem']; s2 = df_rank.iloc[1]['Celkem'] if len(df_rank) > 1 else 0; s3 = df_rank.iloc[2]['Celkem'] if len(df_rank) > 2 else 0
                
                df_rank['Ztráta na 1.'] = df_rank['Celkem'].apply(lambda x: s1 - x if s1 > x else "")
                df_rank['Ztráta na 2.'] = df_rank['Celkem'].apply(lambda x: s2 - x if s2 > x else "")
                df_rank['Ztráta na 3.'] = df_rank['Celkem'].apply(lambda x: s3 - x if s3 > x else "")

                cols_to_fix = ['Body Zápasy', 'Body Bonusy', 'Celkem']
                for col in cols_to_fix:
                    df_rank[col] = df_rank[col].astype(str) + " b."
                for col in ['Ztráta na 1.', 'Ztráta na 2.', 'Ztráta na 3.']:
                    df_rank[col] = df_rank[col].apply(lambda x: f"-{x} b." if x != "" else "")

            at = sorted(list(set(df_rank['Tým'].replace('', '-'))))
            vybrany_tym = st.selectbox("Filtr týmu", ["Všechny"] + at)
            if vybrany_tym != "Všechny": df_rank = df_rank[df_rank['Tým'] == vybrany_tym]
            
            cols = ['Vývoj pořadí', 'Hráč', 'Tým', 'Body Zápasy', 'Body Bonusy', 'Celkem', 'Ztráta na 1.', 'Ztráta na 2.', 'Ztráta na 3.']
            
            def highlight_top3(s):
                if s.name == 1: return ['background-color: #FFD700; color: black'] * len(s)
                elif s.name == 2: return ['background-color: #C0C0C0; color: black'] * len(s)
                elif s.name == 3: return ['background-color: #CD7F32; color: black'] * len(s)
                else: return [''] * len(s)

            styled_rank = df_rank[cols].style.apply(highlight_top3, axis=1)
            st.dataframe(styled_rank, use_container_width=True, hide_index=True)
            
        # 5. STATISTIKY
        with t_stats:
            st.header("Statistika nuda je, má však cenné údaje")
            st.subheader("🍀 Šťastná ruka & 💀 Zabiják tiketů")
            st.caption("Zápasy s nejvyšším a nejnižším průměrem bodů na hráče.")

            if finished_matches:
                tips_by_match = {}
                for t in tipy: tips_by_match.setdefault(t['Zapas_ID'], []).append(t)

                match_stats = []
                for z in finished_matches:
                    tips_for_z = tips_by_match.get(z['ID'], [])
                    if not tips_for_z: continue
                    total_pts = 0; count = 0
                    faze_lower = str(z.get('Faze', '')).lower()
                    is_playoff = any(x in faze_lower for x in ["playoff", "finále", "o 3. místo", "čtvrtfinále", "semifinále"])

                    for t in tips_for_z:
                        p, _, _ = spocitej_body_zapas(t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], z.get('Faze',''))
                        total_pts += p; count += 1
                    
                    if count > 0:
                        match_stats.append({
                            'Zápas': f"{z['Domaci']} - {z['Hoste']}",
                            'Skóre': f"{z['Skore_Domaci']}:{z['Skore_Hoste']}",
                            'Průměr': total_pts / count,
                            'Fáze': 'Playoff' if is_playoff else 'Základní část'
                        })

                if match_stats:
                    df_stats = pd.DataFrame(match_stats)
                    summary_rows = []

                    def add_extremes(subset, label_prefix):
                        if subset.empty: return
                        best = subset.loc[subset['Průměr'].idxmax()]
                        worst = subset.loc[subset['Průměr'].idxmin()]
                        
                        summary_rows.append({"Fáze": label_prefix, "Kategorie": "Nejvyšší bodový průměr", "Zápas": best['Zápas'], "Výsledek": best['Skóre'], "Průměr bodů": f"{best['Průměr']:.2f}"})
                        summary_rows.append({"Fáze": label_prefix, "Kategorie": "Nejnižší bodový průměr", "Zápas": worst['Zápas'], "Výsledek": worst['Skóre'], "Průměr bodů": f"{worst['Průměr']:.2f}"})

                    add_extremes(df_stats[df_stats['Fáze'] == 'Základní část'], "Základní část")
                    add_extremes(df_stats[df_stats['Fáze'] == 'Playoff'], "Playoff (x1.5)")

                    if summary_rows:
                        df_summary = pd.DataFrame(summary_rows)
                        st.dataframe(df_summary.style.set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])]), use_container_width=True, hide_index=True)
            else:
                st.info("Zatím nejsou k dispozici data z odehraných zápasů.")

            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("🎯 Nejvíc přesných tipů")
                df_ex = pd.DataFrame([{"Jméno": u['Jmeno'], "Trefy": exact_matches.get(str(u['Email']), 0)} for u in users]).sort_values("Trefy", ascending=False)
                st.dataframe(df_ex.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
            with c2:
                st.subheader("📊 Úspěšnost tipů")
                sd = []
                for u in users:
                    sc = matches_scored.get(str(u['Email']), 0)
                    perc = (sc/len(finished_matches)*100) if finished_matches else 0
                    sd.append({"Jméno": u['Jmeno'], "Úspěšnost": f"{perc:.1f}%", "_s": perc})
                st.dataframe(pd.DataFrame(sd).sort_values("_s", ascending=False).drop(columns=["_s"]).style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)

            st.divider()
            c3, c4 = st.columns(2)
            with c3:
                st.subheader("👑 Král Základní části")
                sb = pd.DataFrame([{"Jméno": u['Jmeno'], "Body": stats_basic.get(str(u['Email']), 0)} for u in users]).sort_values("Body", ascending=False)
                st.dataframe(sb.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
            with c4:
                st.subheader("🔥 Král Playoff")
                sp = pd.DataFrame([{"Jméno": u['Jmeno'], "Body": stats_playoff.get(str(u['Email']), 0)} for u in users]).sort_values("Body", ascending=False)
                st.dataframe(sp.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🌐 Koho tipujem na medaile?")
            all_winners = [u.get('Tip_Vitez') for u in users if u.get('Tip_Vitez')]
            all_medals = [m for u in users for m in [u.get('Tip_Med1'), u.get('Tip_Med2'), u.get('Tip_Med3')] if m]
            
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                if all_winners:
                    st.write("**Favorité na ZLATO**")
                    win_counts = pd.Series(all_winners).value_counts().reset_index()
                    win_counts.columns = ['Tým', 'Počet hlasů']
                    win_counts.index += 1
                    st.dataframe(win_counts.style.set_properties(**{'text-align': 'center'}), use_container_width=True)
            with col_g2:
                if all_medals:
                    st.write("**Favorité na MEDAILE**")
                    med_counts = pd.Series(all_medals).value_counts().reset_index()
                    med_counts.columns = ['Tým', 'Počet hlasů']
                    med_counts.index += 1
                    st.dataframe(med_counts.style.set_properties(**{'text-align': 'center'}), use_container_width=True)

        # 6. PROFIL
        with t_prof:
            st.header("Můj profil")
            current_u_idx = next((i for i, u in enumerate(users) if str(u['Email']) == st.session_state['user_email']), None)
            if current_u_idx is not None:
                current_data = users[current_u_idx]
                curr_team = current_data.get('Tym', '')
                all_existing_teams = sorted(list(set([u.get('Tym', '') for u in users if u.get('Tym', '') != ''])))
                with st.form("prof"):
                    new_name = st.text_input("Změnit jméno", value=current_data['Jmeno'])
                    st.write(f"Aktuální tým: **{curr_team if curr_team else 'Žádný'}**")
                    c1, c2 = st.columns(2)
                    with c1:
                        sel = st.selectbox("Přidat se k týmu", ["- Vyber -"] + all_existing_teams)
                        final_team = sel if sel != "- Vyber -" else curr_team
                    with c2:
                        new_t = st.text_input("Nebo založit nový")
                        if new_t: final_team = new_t
                    if st.form_submit_button("💾 Uložit profil"):
                        row_idx = current_u_idx + 2
                        updates = [gspread.Cell(row_idx, 2, new_name), gspread.Cell(row_idx, 6, final_team)]
                        try:
                            ws_users.update_cells(updates)
                            st.session_state['user_name'] = new_name
                            st.session_state['user_team'] = final_team
                            st.cache_data.clear(); st.success("Profil aktualizován!"); time.sleep(1); st.rerun()
                        except Exception as e: st.error(f"Chyba při ukládání: {e}")

        # 7. PRAVIDLA
        with t_rules:
            st.header("Pravidla hry")
            st.markdown("""
            * **Zápasy do rozhodnutí:** Tipujeme výsledek po konci zápasu (včetně prodloužení/nájezdů), takže nejsou možné remízy.
            * **Bodování:**
                * Základ je **7 bodů**.
                * Za každý rozdíl v gólech domácích a hostů se odečítá **1 bod**.
                * Minimální počet bodů při správném určení vítěze jsou **2 body**.
                * **+2 body** bonus za trefení přesného výsledku.
                * **+2 body** bonus, pokud hraje Česko.
            * **Playoff:** Všechny body za zápas se násobí **1.5x** (kromě českého bonusu).
            * **Tipy na medailisty:**
                * **+15 bodů** za vítěze turnaje.
                * **+4 body** za každého trefeného medailistu.
            * **Bonusy:**
                * **+6 bodů** pro "Ostrostřelce" (hráč s nejvíce přesnými tipy na konci turnaje).
            """)
            st.caption("Made by MiBo | Kontakt: tipovacka.mibo@gmail.com")

        # 8. HISTORIE (ROZDĚLENÁ)
        with t_history:
            st.header("Síň slávy - Historické výsledky")
            st.markdown("Přehled vítězů a medailistů z minulých turnajů.")

            col_hist_h, col_hist_f = st.columns(2)
            
            with col_hist_h:
                st.subheader("🏒 Hokej")
                history_hockey = [
                    {"Rok": 2025, "Turnaj": "MS - Švédsko/Dánsko", "🥇 1. Místo": "Brácha Tyrdy", "🥈 2. Místo": "Lukáš", "🥉 3. Místo": "Antonín"},
                    {"Rok": 2024, "Turnaj": "MS - Česko", "🥇 1. Místo": "Luděk / Příbor", "🥈 2. Místo": "-", "🥉 3. Místo": "Tony"},
                    {"Rok": 2023, "Turnaj": "MS - Finsko/Lotyšsko", "🥇 1. Místo": "Tyrda", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Honza K."},
                    {"Rok": 2022, "Turnaj": "MS - Finsko", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "Tonda", "🥉 3. Místo": "MiBo"},
                    {"Rok": 2022, "Turnaj": "ZOH - Čína", "🥇 1. Místo": "Kedárek", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Kedar"},
                    {"Rok": 2021, "Turnaj": "MS - Lotyšsko", "🥇 1. Místo": "Honza Geryk", "🥈 2. Místo": "Peťa údržbář", "🥉 3. Místo": "Janča"},
                    {"Rok": 2019, "Turnaj": "MS - Slovensko", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Honza K."},
                    {"Rok": 2018, "Turnaj": "MS - Dánsko", "🥇 1. Místo": "Dominik", "🥈 2. Místo": "Lukáš", "🥉 3. Místo": "Tonda"},
                    {"Rok": 2017, "Turnaj": "MS - Němesko/Francie", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "Tonda", "🥉 3. Místo": "MiBo"},
                    {"Rok": 2016, "Turnaj": "MS - Rusko", "🥇 1. Místo": "Vlasta", "🥈 2. Místo": "Kuba H.", "🥉 3. Místo": "MiBo"},
                ]
                df_hist_h = pd.DataFrame(history_hockey)
                st.dataframe(df_hist_h.style.set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])]), use_container_width=True, hide_index=True)

            with col_hist_f:
                st.subheader("⚽ Fotbal")
                history_football = [
                    {"Rok": 2024, "Turnaj": "EURO - Německo", "🥇 1. Místo": "Brácha Tyrdy", "🥈 2. Místo": "Antonín", "🥉 3. Místo": "Tyrda"},
                    {"Rok": 2022, "Turnaj": "MS - Katar", "🥇 1. Místo": "Tony", "🥈 2. Místo": "Lukáč", "🥉 3. Místo": "MiBo"},
                    {"Rok": 2021, "Turnaj": "EURO", "🥇 1. Místo": "Dominik", "🥈 2. Místo": "Kedar", "🥉 3. Místo": "Tony B."},
                    {"Rok": 2016, "Turnaj": "EURO - Francie", "🥇 1. Místo": "Vojta H.", "🥈 2. Místo": "Ondra T.", "🥉 3. Místo": "Luděk"},
                ]
                df_hist_f = pd.DataFrame(history_football)
                st.dataframe(df_hist_f.style.set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])]), use_container_width=True, hide_index=True)
            
            me_email = st.session_state.get('user_email', '')
            if "mibo" in me_email.lower():
                 st.info("💡 **Zajímavost:** Hráč **MiBo** má na kontě neuvěřitelných 7 medailí z obou sportů (4x🥈, 3x🥉). To už je skoro prokletí! 😅")    

        # 9. STARTOVNÉ
        with t_bank:
            st.header("Startovné, Bank a Výhry")
            me = next((u for u in users if str(u['Email']) == st.session_state['user_email']), None)
            zaplaceno = str(me.get('Zaplaceno', 'NE')).upper() if me else 'NE'
            ENTRY_FEE = 150
            total_paid = sum(1 for u in users if str(u.get('Zaplaceno','')).upper() == 'ANO')
            bank_total = total_paid * ENTRY_FEE
            
            if zaplaceno == 'ANO': st.success("✅ Tvé startovné je ZAPLACENO.")
            else: st.warning("❌ Startovné zatím NENÍ uhrazeno.")
            
            st.divider()
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Platební údaje")
                st.write("**Číslo účtu:** 1596874001/2700"); st.write(f"**Částka:** {ENTRY_FEE} Kč"); st.write("**Poznámka:** Tvoje jméno/přezdívka")
                if os.path.exists("qr_platba.jpeg"):
                    st.image("qr_platba.jpeg", caption="QR Platba", width=250)
                else:
                    st.info("QR kód není nahrán.")
            with c2:
                st.subheader("Aktuální výše výher")
                st.write(f"🥇 **1. Místo:** {int(bank_total * 0.6)} Kč")
                st.write(f"🥈 **2. Místo:** {int(bank_total * 0.2)} Kč")
                st.write(f"🥉 **3. Místo:** {int(bank_total * 0.1)} Kč")

        # --- ADMIN & MODERATOR PANEL ---
        user_role = st.session_state.get('user_role')
        if user_role in ['admin', 'moderator']:
            with st.sidebar:
                st.header(f"Panel: {user_role.capitalize()}")
                
                # 1. ZADÁVÁNÍ VÝSLEDKŮ (Vidí Admin i Moderator)
                with st.expander("Výsledky zápasů", expanded=True):
                    z_names = [f"{z['ID']}: {z['Domaci']} vs {z['Hoste']}" for z in zapasy]
                    sel_z = st.selectbox("Vyber zápas", z_names)
                    sid = int(sel_z.split(":")[0])
                    with st.form("admin_score"):
                        c1, c2 = st.columns(2)
                        d = c1.text_input("Góly D"); h = c2.text_input("Góly H")
                        if st.form_submit_button("Uložit"):
                            cell = ws_zapasy.find(str(sid))
                            ws_zapasy.update_cell(cell.row, 5, d); ws_zapasy.update_cell(cell.row, 6, h)
                            st.cache_data.clear(); st.success("OK"); st.rerun()

                # 2. SPRÁVA TURNAJE (Vidí POUZE Admin)
                if user_role == 'admin':
                    with st.expander("Konec turnaje"):
                        with st.form("af"):
                            ht = get_all_teams(zapasy)
                            def get_idx(val): return ht.index(val) if val in ht else 0
                            w = st.selectbox("Vítěz", ht, index=get_idx(config.get('vitez_turnaje', '')))
                            m1 = st.selectbox("Medaile 1", ht, index=get_idx(config.get('med_1', '')))
                            m2 = st.selectbox("Medaile 2", ht, index=get_idx(config.get('med_2', '')))
                            m3 = st.selectbox("Medaile 3", ht, index=get_idx(config.get('med_3', '')))
                            if st.form_submit_button("Uzavřít turnaj"):
                                def upd(k, v):
                                    c = ws_nastaveni.find(k)
                                    if c: ws_nastaveni.update_cell(c.row, 2, v)
                                    else: ws_nastaveni.append_row([k, v])
                                upd('vitez_turnaje', w); upd('med_1', m1); upd('med_2', m2); upd('med_3', m3)
                                st.cache_data.clear(); st.success("Turnaj uzavřen!"); st.rerun()
                    
                    with st.expander("Platby"):
                        users_list = [f"{u['Jmeno']} ({u['Email']})" for u in users]
                        sel_user_pay = st.selectbox("Vyber uživatele", users_list)
                        sel_email = sel_user_pay.split(" (")[-1].replace(")", "")
                        u_idx = next((i for i, u in enumerate(users) if str(u['Email']) == sel_email), 0)
                        curr = str(users[u_idx].get('Zaplaceno', 'NE'))
                        new_s = st.radio("Stav", ["ANO", "NE"], index=0 if curr=="ANO" else 1)
                        if st.button("Změnit stav"):
                            ws_users.update_cell(u_idx+2, 12, new_s); st.cache_data.clear(); st.success("Změněno"); st.rerun()

    # PATIČKA
    st.markdown('<div class="footer-warning">⚠️ <b>Tip:</b> Pro pohyb v aplikaci používej záložky. Tlačítko Zpět nebo Refresh (F5) tě může odhlásit.</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()