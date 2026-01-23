import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import time
import math

# --- KONFIGURACE ---
st.set_page_config(page_title="Tipovačka hokej - Olympiáda 2026", layout="wide")

# --- PŘIPOJENÍ (Obojživelné: Local vs Cloud) ---
@st.cache_resource
def get_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # 1. Zkusíme najít lokální soubor (pro tvůj počítač)
    import os
    if os.path.exists('credentials.json'):
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
    else:
        # 2. Pokud soubor není, jsme na Cloudu -> použijeme Secrets
        # Vytvoříme dict z Streamlit secrets objektu
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
    for z in zapasy:
        if z['Domaci']: teams.add(z['Domaci'])
        if z['Hoste']: teams.add(z['Hoste'])
    return sorted(list(teams))

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

# --- DATA LOADING ---
def load_data(sh):
    ws_zapasy = sh.worksheet("Zapasy")
    ws_tipy = sh.worksheet("Tipy")
    ws_users = sh.worksheet("Uzivatele")
    try: ws_nastaveni = sh.worksheet("Nastaveni")
    except: ws_nastaveni = None
    
    zapasy = ws_zapasy.get_all_records()
    tipy = ws_tipy.get_all_records()
    users = ws_users.get_all_records()
    nastaveni = ws_nastaveni.get_all_records() if ws_nastaveni else []
    
    return zapasy, tipy, users, nastaveni, ws_users, ws_tipy, ws_zapasy, ws_nastaveni

# --- MAIN APP ---
def main():
    st.title("🏒 Tipovačka hokej - Olympiáda 2026")

    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False

    try:
        sh = get_connection()
        zapasy, tipy, users, nastaveni_data, ws_users, ws_tipy, ws_zapasy, ws_nastaveni = load_data(sh)
    except Exception as e:
        st.error(f"Chyba databáze: {e}")
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
        
        with tab_login:
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Heslo", type="password")
                if st.form_submit_button("Vstoupit"):
                    df_users = pd.DataFrame(users)
                    if not df_users.empty:
                        df_users['Email'] = df_users['Email'].astype(str)
                        df_users['Heslo'] = df_users['Heslo'].astype(str)
                        user = df_users[df_users['Email'] == email]
                        
                        if not user.empty and str(user.iloc[0]['Heslo']) == password:
                            st.session_state['logged_in'] = True
                            st.session_state['user_email'] = email
                            st.session_state['user_name'] = user.iloc[0]['Jmeno']
                            st.session_state['user_role'] = user.iloc[0]['Role']
                            st.session_state['user_team'] = user.iloc[0].get('Tym', '')
                            st.rerun()
                        else:
                            st.error("Chybné jméno nebo heslo.")
                    else:
                        st.error("Databáze uživatelů je prázdná.")

        with tab_reg:
            st.info("Zde si vytvoř účet.")
            with st.form("reg_form"):
                r_email = st.text_input("Tvůj Email")
                r_name = st.text_input("Jméno / Přezdívka")
                r_pass = st.text_input("Heslo", type="password")
                
                if st.form_submit_button("Vytvořit účet"):
                    exists = False
                    for u in users:
                        if str(u.get('Email')) == r_email:
                            exists = True
                            break
                    
                    if exists:
                        st.error("Tento email už existuje!")
                    elif not r_email or not r_name or not r_pass:
                        st.error("Vyplň všechna pole.")
                    else:
                        # Ukládáme s prázdným týmem
                        ws_users.append_row([r_email, r_name, r_pass, 0, 'user', ''])
                        st.success("Účet vytvořen! Můžeš se přihlásit.")
                        time.sleep(1)
                        st.rerun()

    # --- APLIKACE (PŘIHLÁŠEN) ---
    else:
        c1, c2, c3 = st.columns([2, 4, 1])
        c1.write(f"👤 **{st.session_state['user_name']}**")
        c1.caption(f"Tým: {st.session_state.get('user_team') or '❌ (Zatím bez týmu)'}")
        
        if c3.button("Odhlásit"):
            st.session_state['logged_in'] = False
            st.rerun()
        
        st.divider()

        # --- STATISTIKY ---
        match_points = {}
        exact_matches = {}
        matches_scored = {}
        zapas_map = {z['ID']: z for z in zapasy}
        finished_matches_count = sum(1 for z in zapasy if str(z['Skore_Domaci']) != "")
        
        for u in users: 
            email = str(u['Email'])
            match_points[email] = 0
            exact_matches[email] = 0
            matches_scored[email] = 0
            
        for t in tipy:
            zid = t['Zapas_ID']
            if zid in zapas_map:
                z = zapas_map[zid]
                faze = z.get('Faze', 'Skupina') 
                p, ie, sa = spocitej_body_zapas(
                    t['Tip_Domaci'], t['Tip_Hoste'], 
                    z['Skore_Domaci'], z['Skore_Hoste'], 
                    z['Domaci'], z['Hoste'], faze
                )
                email = str(t['Email'])
                match_points[email] += p
                if ie: exact_matches[email] += 1
                if sa: matches_scored[email] += 1

        long_term_points = {}
        for u in users:
            b = spocitej_dlouhodobe_body(u, OFFICIAL_RESULTS)
            long_term_points[str(u['Email'])] = b
        
        max_exact_count = max(exact_matches.values()) if exact_matches else 0
        exact_match_bonus = {e: (6 if c == max_exact_count and max_exact_count > 0 else 0) for e, c in exact_matches.items()}

        total_points = {e: match_points.get(e, 0) + long_term_points.get(e, 0) for e in match_points}

        # --- ZÁLOŽKY ---
        tabs = st.tabs([
            "📜 Pravidla", "🏒 Zápasy", "🕵️ Přehled", "🏆 Medaile", "🥇 Žebříček", "🎯 Statistiky", "⚙️ Profil"
        ])
        
        tab_rules, tab_matches, tab_all_tips, tab_long, tab_leaderboard, tab_stats, tab_profile = tabs

        with tab_rules:
            st.header("Pravidla")
            st.markdown("""
            * **Základ:** 7 bodů. Mínus rozdíl skóre. Min 2 body za vítěze.
            * **Bonusy:** +2 za přesný výsledek, +2 za Česko.
            * **Playoff:** Násobič 1.5x.
            * **Dlouhodobé:** Vítěz 15b, Medaile 4b, Ostrostřelec +6b (na konci).
            """)

        with tab_matches:
            st.header("Tipování zápasů")
            moje_tipy_dict = {t['Zapas_ID']: {'d': t['Tip_Domaci'], 'h': t['Tip_Hoste']} for t in tipy if str(t['Email']) == st.session_state['user_email']}
            
            with st.form("matches_form"):
                for z in zapasy:
                    zid = z['ID']
                    faze = z.get('Faze', 'Skupina')
                    d_str = z['Datum']
                    try: d_str = parse_date(z['Datum']).strftime("%d.%m. %H:%M")
                    except: pass
                    
                    if "playoff" in str(faze).lower(): st.markdown(f"🔥 **{z['Domaci']} - {z['Hoste']}** (PLAYOFF 1.5x)")
                    else: st.write(f"**{z['Domaci']} - {z['Hoste']}**")
                    st.caption(f"{d_str} | {faze}")
                    
                    if str(z['Skore_Domaci']) != "":
                        mt = moje_tipy_dict.get(zid, {})
                        p, _, _ = spocitej_body_zapas(mt.get('d'), mt.get('h'), z['Skore_Domaci'], z['Skore_Hoste'], z['Domaci'], z['Hoste'], faze)
                        st.success(f"Výsledek: {z['Skore_Domaci']}:{z['Skore_Hoste']}")
                        st.info(f"Tvůj tip: {mt.get('d','-')}:{mt.get('h','-')} ({p} b.)")
                    else:
                        c1, c2 = st.columns(2)
                        mt = moje_tipy_dict.get(zid, {})
                        c1.number_input(z['Domaci'], value=mt.get('d', 0), min_value=0, key=f"md_{zid}")
                        c2.number_input(z['Hoste'], value=mt.get('h', 0), min_value=0, key=f"mh_{zid}")
                    st.divider()
                
                if st.form_submit_button("💾 Uložit tipy"):
                    for z in zapasy:
                        zid = z['ID']
                        if str(z['Skore_Domaci']) == "":
                            nd, nh = st.session_state[f"md_{zid}"], st.session_state[f"mh_{zid}"]
                            found = False
                            for i, row in enumerate(tipy):
                                if str(row['Email']) == st.session_state['user_email'] and str(row['Zapas_ID']) == str(zid):
                                    ws_tipy.update_cell(i + 2, 3, nd)
                                    ws_tipy.update_cell(i + 2, 4, nh)
                                    found = True; break
                            if not found: ws_tipy.append_row([st.session_state['user_email'], zid, nd, nh])
                    st.success("Uloženo!"); time.sleep(1); st.rerun()

        with tab_all_tips:
            st.header("Přehled tipů")
            fin = [z for z in zapasy if str(z['Skore_Domaci']) != ""]
            if not fin: st.info("Žádné odehrané zápasy.")
            else:
                tl = {(str(t['Email']), t['Zapas_ID']): f"{t['Tip_Domaci']}:{t['Tip_Hoste']}" for t in tipy}
                od = []
                for u in users:
                    rd = {"Jméno": u['Jmeno']}
                    for z in fin: rd[f"{z['Domaci']} vs {z['Hoste']}"] = tl.get((str(u['Email']), z['ID']), "-")
                    od.append(rd)
                st.dataframe(pd.DataFrame(od), use_container_width=True)

        with tab_long:
            st.header("Dlouhodobé sázky")
            lck = is_past_deadline(DEADLINE)
            if lck: st.warning(f"Uzavřeno ({DEADLINE})")
            else: st.success(f"Otevřeno do {DEADLINE}")
            
            ht = get_all_teams(zapasy) or ["Česko", "Kanada"]
            me_idx = next((i for i, u in enumerate(users) if str(u['Email']) == st.session_state['user_email']), None)
            mr = users[me_idx] if me_idx is not None else {}
            
            with st.form("lb"):
                sw = st.selectbox("Vítěz", ht, index=ht.index(mr.get('Tip_Vitez')) if mr.get('Tip_Vitez') in ht else 0, disabled=lck)
                c1,c2,c3 = st.columns(3)
                m1 = c1.selectbox("M1", ht, index=ht.index(mr.get('Tip_Med1')) if mr.get('Tip_Med1') in ht else 0, key="m1", disabled=lck)
                m2 = c2.selectbox("M2", ht, index=ht.index(mr.get('Tip_Med2')) if mr.get('Tip_Med2') in ht else 1, key="m2", disabled=lck)
                m3 = c3.selectbox("M3", ht, index=ht.index(mr.get('Tip_Med3')) if mr.get('Tip_Med3') in ht else 2, key="m3", disabled=lck)
                if not lck and st.form_submit_button("💾 Uložit"):
                    ws_users.update_cell(me_idx+2, 7, sw)
                    ws_users.update_cell(me_idx+2, 8, m1)
                    ws_users.update_cell(me_idx+2, 9, m2)
                    ws_users.update_cell(me_idx+2, 10, m3)
                    st.success("OK"); st.rerun()

        with tab_leaderboard:
            st.header("Žebříček")
            rd = []
            for u in users:
                e = str(u['Email'])
                rd.append({
                    "Jméno": u['Jmeno'], "Tým": u.get('Tym', '-'),
                    "Zápasy": match_points.get(e,0), "Medaile": long_term_points.get(e,0),
                    "Celkem": total_points.get(e,0)
                })
            df = pd.DataFrame(rd)
            at = sorted(list(set(df['Tým'].replace('', '-'))))
            
            # --- TADY JE TA OPRAVENÁ PROMĚNNÁ ---
            vybrany_tym = st.selectbox("Filtr týmu", ["Všechny"] + at)
            if vybrany_tym != "Všechny": df = df[df['Tým'] == vybrany_tym]
            # ------------------------------------
            
            st.dataframe(df.sort_values("Celkem", ascending=False).reset_index(drop=True).set_index("Jméno"), use_container_width=True)

        with tab_stats:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Ostrostřelci")
                st.dataframe(pd.DataFrame([{"Jméno": u['Jmeno'], "Trefy": exact_matches.get(str(u['Email']), 0)} for u in users]).sort_values("Trefy", ascending=False), use_container_width=True)
            with c2:
                st.subheader("Úspěšnost")
                sd = []
                for u in users:
                    sc = matches_scored.get(str(u['Email']), 0)
                    perc = (sc/finished_matches_count*100) if finished_matches_count else 0
                    sd.append({"Jméno": u['Jmeno'], "Úspěšnost": f"{perc:.0f}%", "_s": perc})
                st.dataframe(pd.DataFrame(sd).sort_values("_s", ascending=False).drop(columns=["_s"]), use_container_width=True)

        with tab_profile:
            st.header("Nastavení profilu a týmu")
            current_u_idx = next((i for i, u in enumerate(users) if str(u['Email']) == st.session_state['user_email']), None)
            
            if current_u_idx is not None:
                current_data = users[current_u_idx]
                curr_team = current_data.get('Tym', '')
                
                # Získání seznamu všech existujících týmů (unikátní, neprázdné, seřazené)
                all_existing_teams = sorted(list(set([u.get('Tym', '') for u in users if u.get('Tym', '') != ''])))
                
                with st.form("prof"):
                    new_name = st.text_input("Tvé jméno", value=current_data['Jmeno'])
                    st.divider()
                    st.write("### 👥 Tvůj Tým")
                    st.info(f"Aktuální tým: **{curr_team if curr_team else 'Žádný'}**")
                    
                    team_mode = st.radio("Co chceš udělat?", ["Zůstat beze změny", "Přidat se k existujícímu týmu", "Založit nový tým"])
                    
                    final_team_name = curr_team 
                    
                    if team_mode == "Přidat se k existujícímu týmu":
                        if not all_existing_teams:
                            st.warning("Zatím nejsou žádné týmy.")
                            final_team_name = curr_team
                        else:
                            try: def_idx = all_existing_teams.index(curr_team)
                            except: def_idx = 0
                            selected_existing = st.selectbox("Vyber tým ze seznamu", all_existing_teams, index=def_idx)
                            final_team_name = selected_existing
                            
                    elif team_mode == "Založit nový tým":
                        new_created_team = st.text_input("Název nového týmu (např. Irimon)")
                        if new_created_team:
                            final_team_name = new_created_team
                    
                    if st.form_submit_button("💾 Uložit změny"):
                        ws_users.update_cell(current_u_idx+2, 2, new_name)
                        ws_users.update_cell(current_u_idx+2, 6, final_team_name)
                        st.session_state['user_name'] = new_name
                        st.session_state['user_team'] = final_team_name
                        st.success("Profil aktualizován!")
                        time.sleep(1)
                        st.rerun()

        # --- ADMIN PANEL (UVNITŘ ELSE) ---
        if st.session_state.get('user_role') == 'admin':
            with st.sidebar:
                st.header("Admin")
                with st.expander("Výsledky zápasů"):
                    # Změna: V seznamu ukazujeme ID i Týmy
                    z_names = [f"{z['ID']}: {z['Domaci']} vs {z['Hoste']}" for z in zapasy]
                    sel_z = st.selectbox("Vyber zápas", z_names)
                    
                    # Z textu "1: Česko vs Kanada" si vytáhneme jen to ID před dvojtečkou
                    sid = int(sel_z.split(":")[0])
                    
                    with st.form("as"):
                        st.write(f"Zadáváš výsledek pro: **{sel_z}**")
                        c1, c2 = st.columns(2)
                        d = c1.text_input("Góly Domácí")
                        h = c2.text_input("Góly Hosté")
                        
                        if st.form_submit_button("Uložit výsledek"):
                            try:
                                cell = ws_zapasy.find(str(sid))
                                ws_zapasy.update_cell(cell.row, 5, d)
                                ws_zapasy.update_cell(cell.row, 6, h)
                                st.success(f"Uloženo: {d}:{h}")
                            except Exception as e:
                                st.error(f"Chyba při ukládání: {e}")

                with st.expander("Konec turnaje (Admin)"):
                    with st.form("af"):
                        st.info("Vyplň přesné názvy týmů (např. 'Česko').")
                        w = st.text_input("Celkový Vítěz", value=config.get('vitez_turnaje', ''))
                        m1 = st.text_input("Medaile 1", value=config.get('med_1', ''))
                        m2 = st.text_input("Medaile 2", value=config.get('med_2', ''))
                        m3 = st.text_input("Medaile 3", value=config.get('med_3', ''))
                        
                        if st.form_submit_button("Uzavřít turnaj"):
                            def upd(k, v):
                                cell = ws_nastaveni.find(k)
                                if cell: ws_nastaveni.update_cell(cell.row, 2, v)
                                else: ws_nastaveni.append_row([k, v])
                            upd('vitez_turnaje', w)
                            upd('med_1', m1)
                            upd('med_2', m2)
                            upd('med_3', m3)
                            st.success("Turnaj uzavřen, body přičteny!")

if __name__ == "__main__":
    main()