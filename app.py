import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math
import os

# --- KONFIGURACE A CSS ---
st.set_page_config(page_title="Tipovačka hokej - Olympiáda 2026", layout="wide")

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
</style>
""", unsafe_allow_html=True)

# --- PŘIPOJENÍ (Resource - drží se v paměti stále) ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    if os.path.exists('credentials.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    else:
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    
    client = gspread.authorize(creds)
    return client.open("Tipovacka_Data")

# --- POMOCNÉ FUNKCE ---
def parse_date(date_str):
    if not date_str: return None
    for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(date_str), fmt)
        except ValueError:
            continue
    return None

def is_past_deadline(deadline_str):
    if not deadline_str: return False
    deadline = parse_date(deadline_str)
    if deadline and datetime.now() > deadline:
        return True
    return False

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
    for i, row in enumerate(existing_tips):
        existing_map[(str(row['Email']), str(row['Zapas_ID']))] = i + 2
        
    for zid, (d, h) in tips_to_save.items():
        key = (user_email, str(zid))
        if key in existing_map:
            row_idx = existing_map[key]
            updates.append(gspread.Cell(row_idx, 3, d))
            updates.append(gspread.Cell(row_idx, 4, h))
        else:
            new_rows.append([user_email, zid, d, h])
            
    if updates:
        ws_tipy.update_cells(updates)
    if new_rows:
        ws_tipy.append_rows(new_rows)
    
    # DŮLEŽITÉ: Po uložení vymažeme cache, aby se načetla čerstvá data
    st.cache_data.clear()

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
    
    if winner_real != winner_tip:
        return 0, False, False

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
    if official_results.get('winner') and str(user_row.get('Tip_Vitez')) == official_results['winner']:
        body += 15
    
    real_medals = [m for m in official_results.get('medals', []) if m]
    user_medals = [str(user_row.get('Tip_Med1')), str(user_row.get('Tip_Med2')), str(user_row.get('Tip_Med3'))]
    unique_tips = set([t for t in user_medals if t])
    for tip in unique_tips:
        if tip in real_medals:
            body += 4
    return body

# --- DATA LOADING (CACHED) ---
# TTL=30 znamená, že data se načtou z Googlu max jednou za 30 vteřin.
# Jinak se berou z paměti serveru. To šetří API limity.
@st.cache_data(ttl=30)
def load_data_values():
    sh = get_connection()
    # Načteme hodnoty (data)
    zapasy = sh.worksheet("Zapasy").get_all_records()
    tipy = sh.worksheet("Tipy").get_all_records()
    users = sh.worksheet("Uzivatele").get_all_records()
    try: nastaveni = sh.worksheet("Nastaveni").get_all_records()
    except: nastaveni = []
    return zapasy, tipy, users, nastaveni

# Pomocná funkce pro získání objektů worksheetů (pro zápis)
def get_worksheets():
    sh = get_connection()
    return sh.worksheet("Zapasy"), sh.worksheet("Tipy"), sh.worksheet("Uzivatele"), sh.worksheet("Nastaveni")

# --- MAIN APP ---
def main():
    col1, col2 = st.columns([1, 4])
    col2.title("🏒 Tipovačka hokej - Olympiáda 2026")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    try:
        # Načtení dat (cachované)
        zapasy, tipy, users, nastaveni_data = load_data_values()
        
        # Objekty pro zápis (necachované, volají se jen při zápisu)
        ws_zapasy, ws_tipy, ws_users, ws_nastaveni = get_worksheets()
        
    except Exception as e:
        st.error(f"Chyba databáze (zkus chvíli počkat a refresh): {e}")
        st.stop()

    config = {row['Klic']: row['Hodnota'] for row in nastaveni_data}
    DEADLINE = config.get('deadline', '2026-02-06 12:00')
    OFFICIAL_RESULTS = {
        'winner': config.get('vitez_turnaje', ''),
        'medals': [config.get('med_1', ''), config.get('med_2', ''), config.get('med_3', '')]
    }

    # --- LOGIN & REGISTRACE ---
    if not st.session_state['logged_in']:
        tab_login, tab_reg = st.tabs(["🔑 Přihlášení", "📝 Registrace"])
        contact_info = "🆘 Zapomněl jsi heslo nebo máš problém? Napiš na: **tipovacka.mibo@gmail.com**"

        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Heslo", type="password")
                if st.form_submit_button("Vstoupit"):
                    email_clean = email.strip().lower()
                    df_users = pd.DataFrame(users)
                    if not df_users.empty:
                        df_users['Email_Lower'] = df_users['Email'].astype(str).str.strip().str.lower()
                        df_users['Heslo'] = df_users['Heslo'].astype(str)
                        user = df_users[df_users['Email_Lower'] == email_clean]
                        if not user.empty and str(user.iloc[0]['Heslo']) == password:
                            st.session_state['logged_in'] = True
                            st.session_state['user_email'] = str(user.iloc[0]['Email'])
                            st.session_state['user_name'] = user.iloc[0]['Jmeno']
                            st.session_state['user_role'] = user.iloc[0]['Role']
                            st.session_state['user_team'] = user.iloc[0].get('Tym', '')
                            st.rerun()
                        else:
                            st.error("Chybné jméno nebo heslo.")
                    else:
                        st.error("Databáze uživatelů je prázdná.")
            st.markdown(contact_info)

        with tab_reg:
            st.info("Zadej svůj email a zvol si heslo. Jméno musí být unikátní.")
            with st.form("reg_form"):
                r_email = st.text_input("Tvůj Email")
                r_name = st.text_input("Jméno / Přezdívka (bude vidět v žebříčku)")
                r_pass = st.text_input("Heslo", type="password")
                
                if st.form_submit_button("Vytvořit účet"):
                    email_clean = r_email.strip().lower()
                    name_clean = r_name.strip().lower()
                    email_exists = False
                    name_exists = False
                    
                    for u in users:
                        if str(u.get('Email')).strip().lower() == email_clean: email_exists = True
                        if str(u.get('Jmeno')).strip().lower() == name_clean: name_exists = True
                    
                    if email_exists: st.error("Tento email už existuje!")
                    elif name_exists: st.error(f"Jméno '{r_name}' už někdo používá.")
                    elif not r_email or not r_name or not r_pass: st.error("Vyplň všechna pole.")
                    else:
                        ws_users.append_row([r_email, r_name, r_pass, 0, 'user', '', '', '', '', '', 'NE', ''])
                        st.cache_data.clear() # Vyčistit cache po registraci
                        st.session_state['logged_in'] = True
                        st.session_state['user_email'] = r_email
                        st.session_state['user_name'] = r_name
                        st.session_state['user_role'] = 'user'
                        st.session_state['user_team'] = ''
                        st.success("Účet vytvořen! Vítej."); time.sleep(1); st.rerun()
            st.markdown(contact_info)

    # --- APLIKACE (PŘIHLÁŠEN) ---
    else:
        c1, c2, c3 = st.columns([3, 4, 1])
        c1.write(f"👤 **{st.session_state['user_name']}**")
        c1.caption(f"Tým: {st.session_state.get('user_team') or '❌ (Bez týmu)'}")
        if c3.button("Odhlásit"):
            st.session_state['logged_in'] = False; st.rerun()
        st.divider()

        # VÝPOČTY
        match_points = {}
        exact_matches = {}
        matches_scored = {}
        stats_basic = {}
        stats_playoff = {}
        
        zapas_map = {z['ID']: z for z in zapasy}
        finished_matches = [z for z in zapasy if str(z['Skore_Domaci']) != ""]
        is_tournament_over = (len(finished_matches) == len(zapasy) and len(zapasy) > 0)
        
        for u in users: 
            email = str(u['Email'])
            match_points[email] = 0; exact_matches[email] = 0; matches_scored[email] = 0
            stats_basic[email] = 0; stats_playoff[email] = 0
            
        tips_map = {}
        for t in tipy:
            tips_map[(str(t['Email']), t['Zapas_ID'])] = t
            zid = t['Zapas_ID']
            email = str(t['Email'])
            
            if zid in zapas_map and str(zapas_map[zid]['Skore_Domaci']) != "":
                z = zapas_map[zid]
                faze = str(z.get('Faze', '')).lower()
                p, ie, sa = spocitej_body_zapas(
                    t['Tip_Domaci'], t['Tip_Hoste'], 
                    z['Skore_Domaci'], z['Skore_Hoste'], 
                    z['Domaci'], z['Hoste'], faze
                )
                match_points[email] = match_points.get(email, 0) + p
                if ie: exact_matches[email] = exact_matches.get(email, 0) + 1
                if sa: matches_scored[email] = matches_scored.get(email, 0) + 1
                
                if "playoff" in faze or "finále" in faze or "o 3. místo" in faze:
                    stats_playoff[email] += p
                else:
                    stats_basic[email] += p

        # Bonus ostrostřelci (+6b)
        max_exact = 0
        if exact_matches: max_exact = max(exact_matches.values())
        
        bonus_ostrostrelci = {}
        for email, count in exact_matches.items():
            if is_tournament_over and count == max_exact and max_exact > 0:
                bonus_ostrostrelci[email] = 6
            else:
                bonus_ostrostrelci[email] = 0

        long_term_points = {}
        for u in users:
            email = str(u['Email'])
            b_medals = spocitej_dlouhodobe_body(u, OFFICIAL_RESULTS)
            b_sharp = bonus_ostrostrelci.get(email, 0)
            long_term_points[email] = b_medals + b_sharp
        
        total_points = {e: match_points.get(e, 0) + long_term_points.get(e, 0) for e in match_points}

        # --- ZÁLOŽKY ---
        tabs = st.tabs([
            "🏒 Tipování", "🕵️ Přehled tipů", "🏆 Tipy na vítěze", "🥇 Žebříček", "🎯 Statistiky", "⚙️ Profil", "📜 Pravidla", "💰 Startovné, Bank a Výhry"
        ])
        
        tab_matches, tab_all_tips, tab_long, tab_leaderboard, tab_stats, tab_profile, tab_rules, tab_bank = tabs

        # 1. TIPOVÁNÍ
        with tab_matches:
            st.header("Tvoje tipy na zápasy")
            st.caption("Tipni si přesný výsledek.")
            moje_tipy_dict = {t['Zapas_ID']: {'d': t['Tip_Domaci'], 'h': t['Tip_Hoste']} for t in tipy if str(t['Email']) == st.session_state['user_email']}
            
            with st.form("matches_form"):
                st.form_submit_button("💾 Uložit všechny tipy (Nahoře)")
                tips_to_save = {} 
                
                for z in zapasy:
                    zid = z['ID']
                    faze = z.get('Faze', 'Skupina')
                    d_str = z['Datum']
                    try: d_str = parse_date(z['Datum']).strftime("%d.%m. %H:%M")
                    except: pass
                    
                    st.markdown(f"**{z['Domaci']} - {z['Hoste']}** <span style='color:gray; font-size:0.8em'>({d_str} | {faze})</span>", unsafe_allow_html=True)
                    if "playoff" in str(faze).lower(): st.caption("🔥 Playoff násobič 1.5x")

                    if str(z['Skore_Domaci']) != "":
                        mt = moje_tipy_dict.get(zid, {})
                        p, is_exact, _ = spocitej_body_zapas(mt.get('d'), mt.get('h'), z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], faze)
                        msg = f"Výsledek: {z['Skore_Domaci']}:{z['Skore_Hoste']} | Tvůj tip: {mt.get('d','-')}:{mt.get('h','-')} | **{p} bodů**"
                        if is_exact: msg += " ⭐"
                        if p > 0: st.success(msg)
                        else: st.error(msg)
                    else:
                        c1, c2, _ = st.columns([1, 1, 4])
                        mt = moje_tipy_dict.get(zid, {})
                        val_d = c1.number_input("D", value=int(mt.get('d', 0)), min_value=0, key=f"md_{zid}", label_visibility="collapsed")
                        val_h = c2.number_input("H", value=int(mt.get('h', 0)), min_value=0, key=f"mh_{zid}", label_visibility="collapsed")
                        tips_to_save[zid] = (val_d, val_h)
                    st.divider()

                if st.form_submit_button("💾 Uložit všechny tipy (Dole)"):
                    with st.spinner("Ukládám tipy..."):
                        save_tips_batch(ws_tipy, st.session_state['user_email'], tips_to_save, tipy)
                    st.success("Tipy byly úspěšně uloženy!"); time.sleep(1); st.rerun()

        # 2. PŘEHLED
        with tab_all_tips:
            st.header("Globální přehled tipů všech hráčů")
            if not finished_matches:
                st.info("Zatím nejsou žádné odehrané zápasy.")
            else:
                table_data = []
                for z in finished_matches:
                    row = {"Zápas": f"{z['Domaci']} - {z['Hoste']}", "Výsledek": f"{z['Skore_Domaci']}:{z['Skore_Hoste']}"}
                    for u in users:
                        email = str(u['Email'])
                        t = tips_map.get((email, z['ID']))
                        if t:
                            p, is_exact, _ = spocitej_body_zapas(t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], z.get('Faze',''))
                            txt = f"{t['Tip_Domaci']}:{t['Tip_Hoste']} ({p}b)"
                            if is_exact: txt = f"⭐ {txt}"
                        else: txt = "-"
                        row[u['Jmeno']] = txt
                    table_data.append(row)
                st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

        # 3. DLOUHODOBÉ
        with tab_long:
            st.header("Tipy na vítěze a medailisty")
            
            me_idx = next((i for i, u in enumerate(users) if str(u['Email']) == st.session_state['user_email']), None)
            mr = users[me_idx] if me_idx is not None else {}
            has_complete_tips = (
                str(mr.get('Tip_Vitez', '')).strip() != '' and
                str(mr.get('Tip_Med1', '')).strip() != '' and
                str(mr.get('Tip_Med2', '')).strip() != '' and
                str(mr.get('Tip_Med3', '')).strip() != ''
            )
            if has_complete_tips: st.success("✅ **Máte natipováno.** Svůj tip můžete do začátku turnaje změnit.")
            else: st.warning("⚠️ **Pozor:** Chybí vám natipovat vítěze a medailisty!")

            st.info("Tipni si vítěze a medailisty. Uzávěrka před začátkem turnaje!")
            lck = is_past_deadline(DEADLINE)
            if lck: st.warning(f"Sázky uzavřeny ({DEADLINE})")
            else: st.success(f"Otevřeno do {DEADLINE}")
            
            ht = get_all_teams(zapasy)
            
            with st.form("lb"):
                sw = st.selectbox("Celkový Vítěz", ht, index=ht.index(mr.get('Tip_Vitez')) if mr.get('Tip_Vitez') in ht else 0, disabled=lck)
                c1,c2,c3 = st.columns(3)
                m1 = c1.selectbox("Medaile 1", ht, index=ht.index(mr.get('Tip_Med1')) if mr.get('Tip_Med1') in ht else 0, key="m1", disabled=lck)
                m2 = c2.selectbox("Medaile 2", ht, index=ht.index(mr.get('Tip_Med2')) if mr.get('Tip_Med2') in ht else 1, key="m2", disabled=lck)
                m3 = c3.selectbox("Medaile 3", ht, index=ht.index(mr.get('Tip_Med3')) if mr.get('Tip_Med3') in ht else 2, key="m3", disabled=lck)
                
                if not lck and st.form_submit_button("💾 Uložit medaile"):
                    ws_users.update_cell(me_idx+2, 7, sw)
                    ws_users.update_cell(me_idx+2, 8, m1)
                    ws_users.update_cell(me_idx+2, 9, m2)
                    ws_users.update_cell(me_idx+2, 10, m3)
                    st.cache_data.clear() # Smazat cache
                    st.success("Uloženo!"); st.rerun()

        # 4. ŽEBŘÍČEK
        with tab_leaderboard:
            if OFFICIAL_RESULTS.get('winner'):
                st.balloons()
                st.success("🎉 **GRATULACE VÍTĚZŮM!** 🎉")
                st.markdown("### 🏆 Sláva vítězům, čest poraženým! Ozvěte se na tipovacka.mibo@gmail.com pro výhru.")
            
            st.header("Celkové pořadí")
            rd = []
            for u in users:
                e = str(u['Email'])
                rd.append({
                    "Hráč": u['Jmeno'], "Tým": u.get('Tym', '-'),
                    "Body Zápasy": match_points.get(e,0), "Body Bonusy": long_term_points.get(e,0),
                    "Celkem": total_points.get(e,0)
                })
            
            df = pd.DataFrame(rd).sort_values("Celkem", ascending=False).reset_index(drop=True)
            df.index += 1
            df.index.name = "Pořadí"
            
            if len(df) > 0:
                s1 = df.iloc[0]['Celkem']; s2 = df.iloc[1]['Celkem'] if len(df) > 1 else 0; s3 = df.iloc[2]['Celkem'] if len(df) > 2 else 0
                df['Ztráta na 1. místo'] = df['Celkem'].apply(lambda x: s1 - x if s1 > x else "")
                df['Ztráta na 2. místo'] = df['Celkem'].apply(lambda x: s2 - x if s2 > x else "")
                df['Ztráta na 3. místo'] = df['Celkem'].apply(lambda x: s3 - x if s3 > x else "")

            at = sorted(list(set(df['Tým'].replace('', '-'))))
            vybrany_tym = st.selectbox("Filtr týmu", ["Všechny"] + at)
            if vybrany_tym != "Všechny": df = df[df['Tým'] == vybrany_tym]
            
            def highlight_top3(s):
                if s.name == 1: return ['background-color: #FFD700; color: black'] * len(s)
                elif s.name == 2: return ['background-color: #C0C0C0; color: black'] * len(s)
                elif s.name == 3: return ['background-color: #CD7F32; color: black'] * len(s)
                else: return [''] * len(s)

            st.dataframe(df.style.apply(highlight_top3, axis=1), use_container_width=True)

        # 5. STATISTIKY
        with tab_stats:
            st.header("Statistiky")
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("🎯 Nejvíc přesných tipů")
                df_ex = pd.DataFrame([{"Jméno": u['Jmeno'], "Trefy": exact_matches.get(str(u['Email']), 0)} for u in users]).sort_values("Trefy", ascending=False)
                st.dataframe(df_ex, use_container_width=True, hide_index=True)
            with c2:
                st.subheader("📊 Úspěšnost")
                sd = []
                for u in users:
                    sc = matches_scored.get(str(u['Email']), 0)
                    perc = (sc/len(finished_matches)*100) if finished_matches else 0
                    sd.append({"Jméno": u['Jmeno'], "Úspěšnost": f"{perc:.1f}%", "_s": perc})
                st.dataframe(pd.DataFrame(sd).sort_values("_s", ascending=False).drop(columns=["_s"]), use_container_width=True, hide_index=True)

            st.divider()
            c3, c4 = st.columns(2)
            with c3:
                st.subheader("👑 Král Základní části")
                sb = pd.DataFrame([{"Jméno": u['Jmeno'], "Body": stats_basic.get(str(u['Email']), 0)} for u in users]).sort_values("Body", ascending=False)
                st.dataframe(sb, use_container_width=True, hide_index=True)
            with c4:
                st.subheader("🔥 Král Playoff")
                sp = pd.DataFrame([{"Jméno": u['Jmeno'], "Body": stats_playoff.get(str(u['Email']), 0)} for u in users]).sort_values("Body", ascending=False)
                st.dataframe(sp, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🌐 Jak tipuje dav?")
            all_winners = [u.get('Tip_Vitez') for u in users if u.get('Tip_Vitez')]
            all_medals = [m for u in users for m in [u.get('Tip_Med1'), u.get('Tip_Med2'), u.get('Tip_Med3')] if m]
            
            col_g1, col_g2 = st.columns(2)
            with col_g1:
                if all_winners:
                    st.write("**Favorité na ZLATO**")
                    win_counts = pd.Series(all_winners).value_counts().reset_index()
                    win_counts.columns = ['Tým', 'Počet hlasů']
                    win_counts.index += 1
                    st.dataframe(win_counts, use_container_width=True)
            with col_g2:
                if all_medals:
                    st.write("**Favorité na MEDAILE**")
                    med_counts = pd.Series(all_medals).value_counts().reset_index()
                    med_counts.columns = ['Tým', 'Počet hlasů']
                    med_counts.index += 1
                    st.dataframe(med_counts, use_container_width=True)

        # 6. PROFIL
        with tab_profile:
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
                        ws_users.update_cell(current_u_idx+2, 2, new_name)
                        ws_users.update_cell(current_u_idx+2, 6, final_team)
                        st.session_state['user_name'] = new_name
                        st.session_state['user_team'] = final_team
                        st.cache_data.clear()
                        st.success("Uloženo!"); time.sleep(1); st.rerun()

        # 7. PRAVIDLA
        with tab_rules:
            st.header("Pravidla hry")
            st.markdown("""
            * **Zápasy do rozhodnutí:** Tipujeme výsledek po konci zápasu (včetně prodloužení/nájezdů), takže nejsou možné remízy.
            * **Bodování:**
                * Základ je **7 bodů**.
                * Za každý rozdíl v gólech domácích a hostů se odečítá **1 bod**.
                * Minimální počet bodů při správném určení vítěze jsou **2 body**.
                * **+2 body** bonus za trefení přesného výsledku.
                * **+2 body** bonus, pokud hraje Česko.
            * **Playoff:** Všechny body se násobí **1.5x** (kromě českého bonusu).
            * **Dlouhodobé sázky:**
                * **15 bodů** za vítěze turnaje.
                * **4 body** za každého trefeného medailistu.
            * **Bonusy:**
                * **+6 bodů** pro "Ostrostřelce" (hráč s nejvíce přesnými tipy na konci turnaje).
            """)
            st.caption("Made by MiBo | Kontakt: tipovacka.mibo@gmail.com")

        # 8. STARTOVNÉ (QR KÓD)
        with tab_bank:
            st.header("💰 Startovné, Bank a Výhry")
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
                st.write("**Číslo účtu:** 1596874001/2700")
                st.write(f"**Částka:** {ENTRY_FEE} Kč")
                st.write("**Poznámka pro příjemce:** Tvoje jméno/přezdívka v soutěži")
                # QR KÓD - Musí být nahrán na GitHubu jako 'qr_platba.jpeg'
                st.image("qr_platba.jpeg", caption="QR Platba", width=250)
                
            with c2:
                st.subheader("Aktuální výše výher")
                st.write(f"🥇 **1. Místo:** {int(bank_total * 0.6)} Kč")
                st.write(f"🥈 **2. Místo:** {int(bank_total * 0.2)} Kč")
                st.write(f"🥉 **3. Místo:** {int(bank_total * 0.1)} Kč")

        # --- ADMIN ---
        if st.session_state.get('user_role') == 'admin':
            with st.sidebar:
                st.header("Admin Panel")
                with st.expander("Výsledky zápasů"):
                    z_names = [f"{z['ID']}: {z['Domaci']} vs {z['Hoste']}" for z in zapasy]
                    sel_z = st.selectbox("Vyber zápas", z_names)
                    sid = int(sel_z.split(":")[0])
                    with st.form("admin_score"):
                        c1, c2 = st.columns(2)
                        d = c1.text_input("Góly D"); h = c2.text_input("Góly H")
                        if st.form_submit_button("Uložit"):
                            cell = ws_zapasy.find(str(sid))
                            ws_zapasy.update_cell(cell.row, 5, d); ws_zapasy.update_cell(cell.row, 6, h)
                            st.cache_data.clear()
                            st.success("OK"); st.rerun()

                with st.expander("Konec turnaje (Medailisté)"):
                    with st.form("af"):
                        # Selectboxy pro admina
                        ht = get_all_teams(zapasy)
                        # Pokud už je něco v configu, najdeme index, jinak 0
                        def get_idx(val): 
                            return ht.index(val) if val in ht else 0

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
                            st.cache_data.clear()
                            st.success("Turnaj uzavřen!"); st.rerun()
                
                with st.expander("Platby"):
                    users_list = [f"{u['Jmeno']} ({u['Email']})" for u in users]
                    sel_user_pay = st.selectbox("Vyber uživatele", users_list)
                    sel_email = sel_user_pay.split(" (")[-1].replace(")", "")
                    u_idx = next((i for i, u in enumerate(users) if str(u['Email']) == sel_email), 0)
                    curr = str(users[u_idx].get('Zaplaceno', 'NE'))
                    new_s = st.radio("Stav", ["ANO", "NE"], index=0 if curr=="ANO" else 1)
                    if st.button("Změnit stav"):
                        ws_users.update_cell(u_idx+2, 12, new_s)
                        st.cache_data.clear()
                        st.success("Změněno"); st.rerun()

if __name__ == "__main__":
    main()