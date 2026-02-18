"""
UI Stránky - všechny záložky aplikace  
KOMPLETNÍ verze - adaptováno z tipovačka_12.py
"""

import streamlit as st
import pandas as pd
import gspread
import time
import os
from datetime import datetime, timedelta
import pytz

# Vlastní moduly
from data.database import load_all_data, get_worksheets_resources, save_tips_batch
from business.scoring import spocitej_body_zapas, get_all_teams, is_past_deadline, spocitej_dlouhodobe_body
from ui.components import get_team_label, get_flag
from utils.config import (
    TIMEZONE, ENTRY_FEE, BANK_ACCOUNT, HISTORY_HOCKEY, HISTORY_FOOTBALL,
    OFFICIAL_RESULTS, DEADLINE
)


def get_user_points_at_date(users, tipy, zapasy, date_limit):
    """Pomocná funkce pro výpočet bodů k určitému datu"""
    match_points = {}
    for u in users:
        match_points[str(u['Email'])] = 0
    
    finished_before = [z for z in zapasy if str(z.get('Skore_Domaci', '')) != "" and z.get('Datum_Obj') and z['Datum_Obj'] < date_limit]
    
    for z in finished_before:
        zid = z['ID']
        for t in tipy:
            if t['Zapas_ID'] == zid:
                email = str(t['Email'])
                p, _, _, _ = spocitej_body_zapas(
                    t['Tip_Domaci'], t['Tip_Hoste'],
                    z['Skore_Domaci'], z['Skore_Hoste'],
                    z['Domaci'], z['Hoste'], z.get('Faze', ''),
                    t.get('Tip_Prodlouzeni', ''), z.get('Prodlouzeni', '')
                )
                match_points[email] += p
    
    return match_points

def get_daily_message():
    """Vrátí kontextovou hlášku podle aktuálního data."""
    now = datetime.now(TIMEZONE)
    day = now.day
    month = now.month
    
    # Pokud není únor 2026, vrátíme obecnou hlášku (pro testování nebo jiný rok)
    if month != 2 or now.year != 2026:
        return "Vítejte u olympijské tipovačky!"

    if day < 11:
        return f"Do startu turnaje zbývá {11 - day} dní! Už aby to tu bylo!"
    elif day == 11:
        return "Dnes to vypukne! Začíná základní část."
    elif 11 < day <= 15:
        return "Základní skupiny jsou v plném proudu. Každý bod se počítá!"
    elif day == 16:
        return "Základní část skončila. Zítra začíná play-off!"
    elif day == 17:
        return "Osmifinále! Kdo dnes vypadne a pojede domů?"
    elif day == 18:
        return "Čtvrtfinále. Teď už jde do tuhého."
    elif day == 19:
        return "Den volna před bouří. Zkontroluj si své tipy na medaile!"
    elif day == 20:
        return "Semifinále! Kdo si zahraje o zlato?"
    elif day == 21:
        return "Boj o bronz. Utěcha nebo zklamání?"
    elif day == 22:
        return "VELKÉ FINÁLE! Kdo se stane olympijským šampionem?"
    else:
        return "Turnaj je za námi. Sláva vítězům, čest poraženým!"

def render_main_application():
    """Hlavní aplikace pro přihlášeného uživatele"""
    
    # === NAČTENÍ DAT ===
    zapasy, tipy, users, config, chat_data = load_all_data()
    ws_zapasy, ws_tipy, ws_users, ws_nastaveni, ws_chat = get_worksheets_resources()
    
    # --- PŘÍPRAVA STATISTIK ZÁPASŮ (CACHE) ---
    match_stats_cache = {}
    tips_by_match_id = {}
    for t in tipy:
        zid = t['Zapas_ID']
        tips_by_match_id.setdefault(zid, []).append(t)
    
    for z in zapasy:
        zid = z['ID']
        mts = tips_by_match_id.get(zid, [])
        valid_tips = [x for x in mts if not (int(x['Tip_Domaci']) == 0 and int(x['Tip_Hoste']) == 0)]
        total = len(valid_tips)
        
        if total > 0:
            d = sum(1 for x in valid_tips if int(x['Tip_Domaci']) > int(x['Tip_Hoste']))
            h = sum(1 for x in valid_tips if int(x['Tip_Hoste']) > int(x['Tip_Domaci']))
            perc_d = int(d / total * 100)
            perc_h = 100 - perc_d
            match_stats_cache[zid] = (perc_d, perc_h, total)
        else:
            match_stats_cache[zid] = (0, 0, 0)

    # ==========================================
    # 1. HLAVIČKA (PROFIL + ODHLÁSIT)
    # ==========================================
    curr_id = next((u.get('ID', '?') for u in users if str(u['Email']) == st.session_state['user_email']), '?')
    
    # Použijeme sloupce, aby to bylo v jedné rovině
    c_head1, c_head2 = st.columns([5, 1])
    with c_head1:
        st.markdown(f"👤 **{st.session_state['user_name']}** <span style='color:grey; font-size:0.8em'>(ID: {curr_id})</span>", unsafe_allow_html=True)
    with c_head2:
        if st.button("Odhlásit", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()
    
    # ==========================================
    # 2. INFO BOX (HLÁŠKA DNE / POŘADÍ)
    # ==========================================
    # Tady si připravíme data pro box, ale vykreslíme ho hezky čistě
    
    # Musíme si narychlo spočítat body pro zobrazení pořadí (zjednodušená verze pro UI)
    # Kompletní výpočet běží níže, tady jen pro InfoBox vytáhneme data z "df_rank" pokud existuje, 
    # ale protože df_rank se počítá až dole, použijeme Placeholder a naplníme ho až na konci funkce!
    
    info_box_placeholder = st.container()
    
    # ==========================================
    # 3. DASHBOARD (VÝSLEDKY | NEJBLIŽŠÍ ZÁPAS | CHAT)
    # ==========================================
    
    # A) Příprava dat pro NEJBLIŽŠÍ ZÁPAS
    prague_tz = pytz.timezone('Europe/Prague')
    now_prague = datetime.now(prague_tz)
    upcoming_match = None
    
    # Najdeme nejbližší budoucí zápas
    sorted_matches = sorted([z for z in zapasy if str(z['Skore_Domaci']) == ""], key=lambda x: x.get('Datum_Obj') or datetime.max)
    
    for z in sorted_matches:
        match_dt = z.get('Datum_Obj')
        if match_dt:
            if match_dt.tzinfo is None: match_dt = prague_tz.localize(match_dt)
            if match_dt > now_prague:
                upcoming_match = z
                match_dt_aware = match_dt
                break
    
    # B) Příprava dat pro VÝSLEDKY a CHAT
    finished_matches = [z for z in zapasy if str(z['Skore_Domaci']) != ""]
    
    # C) VYKRESLENÍ TŘÍ SLOUPCŮ
    # Poměr [1, 1.2, 1] dá prostřednímu bloku trochu víc místa, aby karta dýchala
    col_results, col_next, col_chat = st.columns([1, 1.2, 1])
    
    # --- 1. SLOUPEC: POSLEDNÍ VÝSLEDKY ---
    with col_results:
        st.markdown("<div style='font-size: 0.8em; color: #64748b; font-weight: bold; margin-bottom: 5px; text-align: center;'>POSLEDNÍ VÝSLEDKY</div>", unsafe_allow_html=True)
        if finished_matches:
            # Vezmeme poslední 2 a otočíme je
            last_matches = finished_matches[-2:]
            for m in reversed(last_matches):
                f_d = get_flag(m['Domaci']); f_h = get_flag(m['Hoste'])
                st.markdown(f"""
                <div style="border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; background-color: white; margin-bottom: 8px;">
                    <div style="font-weight: bold; font-size: 0.9em; text-align: center;">
                        {f_d} {m['Domaci']} <span style="color:#ef4444">{m['Skore_Domaci']}:{m['Skore_Hoste']}</span> {m['Hoste']} {f_h}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("Čekání na první zápas")

    # --- 2. SLOUPEC: NEJBLIŽŠÍ ZÁPAS (UPROSTŘED) ---
    with col_next:
        if upcoming_match:
            delta = match_dt_aware - now_prague
            hours, remainder = divmod(delta.seconds, 3600); minutes, _ = divmod(remainder, 60)
            
            pd_next, ph_next, _ = match_stats_cache.get(upcoming_match['ID'], (0,0,0))
            f_d = get_flag(upcoming_match['Domaci']); f_h = get_flag(upcoming_match['Hoste'])

            # Upravil jsem margin-top na 0, aby to lícovalo s nadpisy okolních sloupců
            st.markdown(f"""
            <div class="next-match-box" style="margin-top: 0px; margin-bottom: 20px;">
                <div style="font-size: 0.75em; text-transform: uppercase; letter-spacing: 1px; color: #64748b; margin-bottom: 5px;">⏱️ Nejbližší zápas (za {delta.days}d {hours}h {minutes}m)</div>
                <div style="font-size: 1.3em; font-weight: bold;">
                    {f_d} {upcoming_match['Domaci']} <span style="color:#000000">:</span> {upcoming_match['Hoste']} {f_h}
                </div>
                <div style="font-size: 0.75em; color: #475569; margin-top: 5px;">
                    Tipujeme: Domácí <b>{pd_next}%</b> : <b>{ph_next}%</b> Hosté
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
             st.info("Žádný nadcházející zápas.")

    # --- 3. SLOUPEC: DISKUZE ---
    with col_chat:
        st.markdown("<div style='font-size: 0.8em; color: #64748b; font-weight: bold; margin-bottom: 5px; text-align: center;'>💬 DISKUZE</div>", unsafe_allow_html=True)
        if chat_data:
            last_msgs = chat_data[-2:]
            for msg in reversed(last_msgs):
                # Zkrácení zprávy
                msg_txt = (msg['Zprava'][:35] + '..') if len(msg['Zprava']) > 35 else msg['Zprava']
                st.markdown(f"""
                <div style="border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; background-color: white; margin-bottom: 8px;">
                    <div style="font-size: 0.85em;">
                        <b>{msg['Hrac']}:</b> {msg_txt}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.caption("V diskuzi je ticho.")

    st.write("") # Malá mezera před medailemi

    # UPOZORNĚNÍ NA MEDAILE (Pokud chybí)
    me_stats = next((u for u in users if str(u['Email']) == st.session_state['user_email']), {})
    has_medals = (
        str(me_stats.get('Tip_Vitez','')).strip() and 
        str(me_stats.get('Tip_Med1','')).strip() and 
        str(me_stats.get('Tip_Med2','')).strip() and 
        str(me_stats.get('Tip_Med3','')).strip()
    )
    
    if not has_medals and not is_past_deadline(DEADLINE):
        st.warning("⚠️ **POZOR:** Nemáš natipované medaile a vítěze! Jdi do záložky **Medaile**.")

    # Tady kód pokračuje VÝPOČTY BODŮ...
    # VÝPOČTY BODŮ
    match_points = {}; exact_matches = {}; matches_scored = {}; stats_basic = {}; stats_playoff = {}
    # Nové bonusové kontejnery
    bonus_odvaha = {str(u['Email']): 0 for u in users}
    bonus_tiper_dne = {str(u['Email']): 0 for u in users}

    zapas_map = {z['ID']: z for z in zapasy}
    finished_matches = [z for z in zapasy if str(z['Skore_Domaci']) != ""]
    is_tournament_over = (len(finished_matches) == len(zapasy) and len(zapasy) > 0)

    for u in users: 
        email = str(u['Email'])
        match_points[email] = 0; exact_matches[email] = 0; matches_scored[email] = 0; stats_basic[email] = 0; stats_playoff[email] = 0

    tips_map = {}
    tips_by_match = {} # Pro výpočet procent (Odvaha)

    for t in tipy:
        tips_map[(str(t['Email']), t['Zapas_ID'])] = t
        tips_by_match.setdefault(t['Zapas_ID'], []).append(t)

    # 1. ZÁKLADNÍ PRŮCHOD (Body za zápasy + Prodloužení)
    unique_tips_map = {}
    for t in tipy:
        # Tímto se přepíší starší/duplicitní záznamy, zůstane jen jeden unikátní pro User+Zápas
        unique_tips_map[(str(t['Email']), t['Zapas_ID'])] = t

    # Nyní iterujeme jen přes unikátní tipy
    for (email, zid), t in unique_tips_map.items():
        if zid in zapas_map and str(zapas_map[zid]['Skore_Domaci']) != "":
            z = zapas_map[zid]
            faze = str(z.get('Faze', '')).lower()
            # Voláme novou verzi funkce s prodloužením
            p, ie, sa, _ = spocitej_body_zapas(
                t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], 
                z['Domaci'], z['Hoste'], faze,
                t.get('Tip_Prodlouzeni', ''), z.get('Prodlouzeni', '')
            )
            match_points[email] += p
            if ie: exact_matches[email] += 1
            if sa: matches_scored[email] += 1
            if "playoff" in faze or "finále" in faze or "o 3. místo" in faze: stats_playoff[email] += p
            else: stats_basic[email] += p

    # 2. VÝPOČET: BONUS ZA ODVAHU (Underdog)
    for z in finished_matches:
        zid = z['ID']
        match_tips = tips_by_match.get(zid, [])
        if not match_tips: continue

        # Kolik % věří komu
        cnt_d = sum(1 for mt in match_tips if mt['Tip_Domaci'] > mt['Tip_Hoste'])
        cnt_h = sum(1 for mt in match_tips if mt['Tip_Hoste'] > mt['Tip_Domaci'])
        total = len(match_tips)
        if total == 0: continue

        perc_d = cnt_d / total; perc_h = cnt_h / total

        # Kdo vyhrál?
        rd, rh = int(z['Skore_Domaci']), int(z['Skore_Hoste'])
        winner = 'd' if rd > rh else ('h' if rh > rd else 'draw')

        # Podmínka < 20%
        is_underdog_win = (winner == 'd' and perc_d < 0.20) or (winner == 'h' and perc_h < 0.20)

        if is_underdog_win:
            for mt in match_tips:
                u_win = 'd' if mt['Tip_Domaci'] > mt['Tip_Hoste'] else ('h' if mt['Tip_Hoste'] > mt['Tip_Domaci'] else 'draw')
                if u_win == winner:
                    bonus_odvaha[str(mt['Email'])] += 1

    # 3. VÝPOČET: TIPER DNE (Zpětně podle dnů, ale jen když je den KOMPLETNÍ)
    tiper_dne_log = [] 
    # Unikátní dny ze všech zápasů (i neodehraných, abychom věděli, co patří k jakému dni)
    all_dates = sorted(list(set([z['Datum_Obj'].date() for z in zapasy if z.get('Datum_Obj')])))

    last_finished_day_stats = None # Pro info box (včerejší vítěz)

    for d_date in all_dates:
        # Všechny zápasy toho dne
        matches_that_day = [z for z in zapasy if z.get('Datum_Obj') and z['Datum_Obj'].date() == d_date]
        if not matches_that_day: continue

        # Podmínka: Všechny zápasy toho dne musí mít výsledek
        day_finished = all(str(z['Skore_Domaci']) != "" for z in matches_that_day)

        if day_finished:
            daily_pts = {str(u['Email']): 0 for u in users}
            for z in matches_that_day:
                # Použijeme unikátní mapu tipů z předchozího kroku (nutno mít aplikovaný fix z minula!)
                # Pokud fix nemáš, použij: t = next((x for x in tipy if x['Zapas_ID'] == z['ID'] and str(x['Email']) == email), None)
                for u in users:
                    email = str(u['Email'])
                    t = tips_map.get((email, z['ID']))
                    if t:
                        p, _, _, _ = spocitej_body_zapas(
                            t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], 
                            z['Domaci'], z['Hoste'], z.get('Faze',''),
                            t.get('Tip_Prodlouzeni', ''), z.get('Prodlouzeni', '')
                        )
                        daily_pts[email] += p
            
            # Kdo vyhrál den?
            if daily_pts:
                max_val = max(daily_pts.values())
                if max_val > 0:
                    winners = [e for e, s in daily_pts.items() if s == max_val]
                    bonus_val = 0.5 * len(matches_that_day) # 0.5 bodu za zápas
                    
                    winner_names = []
                    for w in winners:
                        bonus_tiper_dne[w] += bonus_val
                        w_name = next((u['Jmeno'] for u in users if str(u['Email']) == w), w)
                        winner_names.append(w_name)
                    
                    # Log pro statistiky
                    tiper_dne_log.append({
                        "Datum": d_date, 
                        "Jméno": ", ".join(winner_names), 
                        "Body ten den": max_val, 
                        "Bonus": bonus_val
                    })
                    
                    # Uložíme si poslední vyhodnocený den pro Info Box
                    last_finished_day_stats = tiper_dne_log[-1]

    # Kompletace celkových bodů a rozdělení bonusů pro tabulku
    # Bonus ostrostřelci (Původní logika)
    max_exact = 0; bonus_ostrostrelci = {}
    if exact_matches: max_exact = max(exact_matches.values())
    for email, count in exact_matches.items():
        bonus_ostrostrelci[email] = 6 if (is_tournament_over and count == max_exact and max_exact > 0) else 0

    long_term_points = {}     # Pouze body za medaile/vítěze
    
    for u in users:
        email = str(u['Email'])
        lt_pts = spocitej_dlouhodobe_body(u, OFFICIAL_RESULTS)
        long_term_points[email] = lt_pts
        
    # Celkový součet pro řazení
    total_points = {}
    for u in users:
        e = str(u['Email'])
        total_bonus = (
            long_term_points.get(e, 0) + 
            bonus_ostrostrelci.get(e, 0) + 
            bonus_odvaha.get(e, 0) + 
            bonus_tiper_dne.get(e, 0)
        )
        total_points[e] = match_points.get(e, 0) + total_bonus

    # PŘÍPRAVA DAT PRO ŽEBŘÍČEK - S novými sloupci
    rd = []
    for u in users:
        e = str(u['Email'])
        rd.append({
            "Email": e, 
            "Hráč": u['Jmeno'], 
            "Tým": u.get('Tym', '-'), 
            "Zaplaceno": str(u.get('Zaplaceno', 'NE')).upper(), 
            "Body Zápasy": match_points.get(e,0), 
            "Tiper Dne": bonus_tiper_dne.get(e, 0),    # Nový sloupec
            "Odvaha": bonus_odvaha.get(e, 0),          # Nový sloupec
            "Medaile/Vítěz": long_term_points.get(e, 0) + bonus_ostrostrelci.get(e, 0), # Sloučené dlouhodobé
            "Celkem": total_points.get(e,0)
        })
    df_rank = pd.DataFrame(rd).sort_values("Celkem", ascending=False).reset_index(drop=True)
    df_rank['Pořadí'] = df_rank['Celkem'].rank(method='min', ascending=False).astype(int)

    # --- NAPLNĚNÍ INFO BOXU (Placeholder nahoře) ---
    with info_box_placeholder:
        daily_msg = get_daily_message()
        my_row = df_rank[df_rank['Email'] == st.session_state['user_email']]
        
        # Info o posledním tiperovi dne
        tiper_msg_html = ""
        if last_finished_day_stats:
            d_str = last_finished_day_stats['Datum'].strftime('%d.%m.')
            names = last_finished_day_stats['Jméno']
            pts = last_finished_day_stats['Body ten den']
            tiper_msg_html = f"<div style='margin-top: 8px; font-size: 0.9em; color: #059669; background-color: #ecfdf5; padding: 4px 8px; border-radius: 4px; display: inline-block;'>🏅 <b>Tiper dne ({d_str}):</b> {names} ({pts} b.)</div>"

        if not my_row.empty:
            my_points = float(my_row.iloc[0]['Celkem'])
            my_rank = my_row.iloc[0]['Pořadí']
            
            # --- NOVÉ: ROZPAD BODŮ (Sjednoceno na .1f) ---
            p_match = float(my_row.iloc[0]['Body Zápasy'])
            p_tiper = float(my_row.iloc[0]['Tiper Dne'])
            p_odvaha = float(my_row.iloc[0]['Odvaha'])
            
            # FIX: Zde musíme volat původní název sloupce 'Medaile/Vítěz'
            p_end = float(my_row.iloc[0]['Medaile/Vítěz']) 

            # HTML string bez odsazení
            breakdown_html = f"""<div style="font-size: 0.85em; color: #475569; margin-top: 4px; margin-bottom: 8px;">Zápasy: <b>{p_match:.1f}</b> | Tiper dne: <b>{p_tiper:.1f}</b> | Odvaha: <b>{p_odvaha:.1f}</b> | Koncový bonus: <b>{p_end:.1f}</b></div>"""

            # Sousedé v žebříčku
            ahead_txt = ""
            behind_txt = ""
            shared_txt = ""

            # 1. KDO JE PŘEDE MNOU? 
            better_players = df_rank[df_rank['Celkem'].apply(lambda x: round(x, 1) > round(my_points, 1))]
            if not better_players.empty:
                closest_ahead = better_players.iloc[-1]
                diff = round(float(closest_ahead['Celkem']) - my_points, 1)
                ahead_txt = f"Ztráta na <b>{closest_ahead['Hráč']}</b>: <b>{diff:.1f} b.</b>"
            else:
                ahead_txt = "👑 Jsi ve vedení!"

            # 2. S KÝM SDÍLÍM POZICI?
            same_points = df_rank[
                (df_rank['Celkem'].apply(lambda x: round(x, 1) == round(my_points, 1))) & 
                (df_rank['Email'] != st.session_state['user_email'])
            ]
            if not same_points.empty:
                names = same_points['Hráč'].tolist()
                if len(names) > 3: shared_txt = f" | Sdílíš pozici s <b>{len(names)}</b> hráči"
                else: shared_txt = f" | Sdílíš s: <b>{', '.join(names)}</b>"

            # 3. KDO JE ZA MNOU?
            worse_players = df_rank[df_rank['Celkem'].apply(lambda x: round(x, 1) < round(my_points, 1))]
            if not worse_players.empty:
                closest_behind = worse_players.iloc[0]
                diff = round(my_points - float(closest_behind['Celkem']), 1)
                behind_txt = f" | Náskok na <b>{closest_behind['Hráč']}</b>: <b>{diff:.1f} b.</b>"
            else:
                behind_txt = " | Jsi poslední."

            content_html = f"""
<div style="text-align: center; color: #1e293b; padding: 15px; background-color: #f8fafc; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 20px;">
<div style="font-weight: bold; font-size: 1.1em; margin-bottom: 5px; color: #334155;">{daily_msg}</div>
<div style="font-size: 1.3em; margin-bottom: 2px;">Jsi na <b>{int(my_rank)}. místě</b> ({my_points:.1f} b)</div>
{breakdown_html}
<div style="font-size: 0.9em; color: #64748b;">
{ahead_txt}{shared_txt}{behind_txt}
</div>
{tiper_msg_html}
</div>
"""
            st.markdown(content_html, unsafe_allow_html=True)
            
        else:
            st.warning("Zatím nejsi v žebříčku.")

    # Trendy
    prague_tz = pytz.timezone('Europe/Prague')  # 1. Musíme znát zónu
    yesterday_limit = datetime.now(prague_tz) - timedelta(days=1) # 2. Teď je 'yesterday_limit' aware (má zónu)
    pts_yesterday = get_user_points_at_date(users, tipy, zapasy, date_limit=yesterday_limit)
    rd_prev = []
    for u in users:
        e = str(u['Email'])
        b_prev = pts_yesterday.get(e, 0)
        rd_prev.append({"Email": e, "Total": b_prev})
    df_prev = pd.DataFrame(rd_prev).sort_values("Total", ascending=False).reset_index(drop=True)
    df_prev.index += 1
    df_prev['Pořadí'] = df_prev.index
    prev_ranks = df_prev.set_index('Email')['Pořadí'].to_dict()

    df_rank['Vývoj pořadí'] = ""
    leader_score = df_rank.iloc[0]['Celkem'] if not df_rank.empty else 0

    for idx, row in df_rank.iterrows():
        if leader_score == 0:
            df_rank.at[idx, 'Vývoj pořadí'] = "➖"
        else:
            email = row['Email']
            if email in prev_ranks:
                diff = prev_ranks[email] - row['Pořadí'] 
                if diff > 0: df_rank.at[idx, 'Vývoj pořadí'] = f"🟢 ▲{diff}"
                elif diff < 0: df_rank.at[idx, 'Vývoj pořadí'] = f"🔴 ▼{abs(diff)}"
                else: df_rank.at[idx, 'Vývoj pořadí'] = "➖"
            else:
                df_rank.at[idx, 'Vývoj pořadí'] = "🆕"

    # --- POČÍTADLO ZPRÁV (CELKOVÉ) ---
    count_msg = len(chat_data)
    label_chat = f"🗣️ Diskuze ({count_msg})"

    # ZÁLOŽKY
    tab_names = [
        "🕵️ Přehled", "🏒 Tipování", "🥇 Žebříček", "🏆 Medaile", 
        "🎯 Statistiky", "⚙️ Profil", "📜 Pravidla",
        "🏛️ Historické výsledky", "💰 Startovné a výhry", label_chat
    ]

    # 2. Zjištění role a přidání Admin záložky
    user_role = st.session_state.get('user_role')
    is_admin = user_role in ['admin', 'moderator']

    if is_admin:
        tab_names.append("🛠️ Admin")

    # 3. Vytvoření záložek
    all_tabs = st.tabs(tab_names)

    # 4. Rozbalení standardních záložek (prvních 10)
    # POZOR: Tady musíme prohodit i proměnné t_overview a t_matches, 
    # aby odpovídaly pořadí v seznamu tab_names!
    t_overview, t_matches, t_rank, t_long, t_stats, t_prof, t_rules, t_history, t_bank, t_chat = all_tabs[:10]

    # 5. Admin záložka (pokud existuje, je poslední)
    t_admin = all_tabs[10] if is_admin else None

    # 1. TIPOVÁNÍ
    # 1. TIPOVÁNÍ
    with t_matches:
        # Zrušíme st.header, protože už máme velký nadpis v app.py, ať to není přeplácané
        # st.header("Tvoje tipy na jednotlivé zápasy")
        
        with st.expander("💡 Info k zadávání tipů"):
            st.markdown("""
            * Tipy se ukládají hromadně **tlačítkem dole**.
            * **Není nutné** najednou natipovat všechny zápasy. K tipování se můžeš kdykoliv vrátit. Svoje tipy můžeš kdykoliv před začátkem zápasu změnit.
            * **Hokej se hraje do rozhodnutí:** Musíš vybrat vítěze (např. 3:2).
            * **Remíza po 60 min:** Nastav rozdíl o 1 gól (např. 2:3) a zaškrtni "Prodloužení".
            * Stav **0:0** se ignoruje (bere se jako nenatipováno).
            """)

        moje_tipy_dict = {str(t['Zapas_ID']): t for t in tipy if str(t['Email']) == st.session_state['user_email']}
        
        with st.form("tips_form"):
            tips_to_save = {} 
            match_names_map = {}

            # Řazení zápasů podle data (volitelné, jinak bere pořadí z DB)
            # zapasy.sort(key=lambda x: x['Datum_Obj'] or datetime.max)

            for z in zapasy:
                zid = z['ID']
                match_names_map[str(zid)] = f"{z['Domaci']} vs {z['Hoste']}"

                # Příprava dat
                d_obj = z.get('Datum_Obj')
                d_str = d_obj.strftime("%d.%m. %H:%M") if d_obj else z['Datum']
                
                # --- KLÍČOVÁ OPRAVA: DEFINICE PROMĚNNÝCH PŘED PODMÍNKOU ---
                mt = moje_tipy_dict.get(str(zid), {})
                # Bezpečné načtení hodnot (pokud neexistují, dáme 0 nebo prázdný string)
                old_d = mt.get('Tip_Domaci', 0)
                old_h = mt.get('Tip_Hoste', 0)
                old_ot = mt.get('Tip_Prodlouzeni', '') 
                # -----------------------------------------------------------

                # Kontrola zamčení
                prague_tz = pytz.timezone('Europe/Prague')
                now_prague = datetime.now(prague_tz)
                match_dt = z.get('Datum_Obj')
                if match_dt and match_dt.tzinfo is None:
                    match_dt = prague_tz.localize(match_dt)

                is_locked = (match_dt and now_prague > match_dt)
                is_played = (str(z['Skore_Domaci']) != "")
                
                # Label pro Expander
                f_d = get_flag(z['Domaci'])
                f_h = get_flag(z['Hoste'])
                clock = "🔒" if (is_locked or is_played) else "⏱️"
                
                # Vytvoříme hezký label s vlajkami
                card_label = f"{clock} {z['Domaci']} vs {z['Hoste']} ({d_str})"

                # Načtení statistik z cache
                perc_d, perc_h, count_tips = match_stats_cache.get(zid, (0, 0, 0))
                
                # UPDATE TEXTU: "tento zápas již natipovalo..."
                stats_label = f" | {count_tips} hráčů již natipovalo" if count_tips > 0 else ""
                card_label = f"{clock} {z['Domaci']} vs {z['Hoste']} ({d_str}){stats_label}"

                # --- KARTA ZÁPASU ---
                with st.expander(card_label, expanded=not (is_locked or is_played)):
                    
                    # === NOVÉ: GRAFICKÝ PRUH (MODRÁ vs ČERVENÁ) ===
                    if count_tips > 0:
                        # Modrá (Domácí) zleva, Červená (Hosté) zprava
                        # Uděláme to jako flexbox dvou divů
                        st.markdown(f"""
                        <div style="display: flex; justify-content: space-between; font-size: 0.8em; color: #334155; margin-bottom: 5px;">
                            <span> {z['Domaci']}: <b>{perc_d}%</b></span>
                            <span> {z['Hoste']}: <b>{perc_h}%</b></span>
                        </div>
                        
                        <div style="width: 100%; height: 8px; background-color: #ef4444; border-radius: 4px; overflow: hidden; margin-bottom: 15px; display: flex;">
                            <div style="width: {perc_d}%; height: 100%; background-color: #3b82f6;"></div>
                            </div>
                        """, unsafe_allow_html=True)
                    
                    # Hlavička uvnitř karty (Vlajky velké)
                    st.markdown(
                        f"<div style='text-align: center; font-size: 1.2rem; margin-bottom: 15px; color: #334155;'>"
                        f"<b>{z['Domaci']}</b> {f_d} <span style='color:#cbd5e1; margin:0 15px'>|</span> {f_h} <b>{z['Hoste']}</b>"
                        f"</div>", 
                        unsafe_allow_html=True
                    )

                    if is_played or is_locked:
                        # ZOBRAZENÍ VÝSLEDKU (READ-ONLY)
                        p, ie, _, ot_p = spocitej_body_zapas(
                            old_d, old_h, z['Skore_Domaci'], z['Skore_Hoste'], 
                            z['Domaci'], z['Hoste'], z.get('Faze',''),
                            old_ot, z.get('Prodlouzeni', '')
                        )
                        ot_txt = f" (OT: {ot_p}b)" if ot_p != 0 else ""
                        
                        # Barvičky
                        bg = "#dcfce7" if p > 0 else "#fee2e2"
                        border = "#22c55e" if p > 0 else "#ef4444"
                        
                        st.markdown(
                            f"<div style='background-color: {bg}; padding: 10px; border-radius: 8px; text-align: center; border: 1px solid {border};'>"
                            f"<strong style='color: #000; font-size: 1.2rem;'>Zisk: {p} b.</strong> {ot_txt}<br>"
                            f"<small>Realita: {z['Skore_Domaci']}:{z['Skore_Hoste']} | Tvůj tip: {old_d}:{old_h}</small>"
                            f"</div>", unsafe_allow_html=True
                        )
                            
                    else:
                        # FORMULÁŘ PRO TIPOVÁNÍ - FINAL FIX
                        
                        # Inputy
                        _, c_d, c_vs, c_h, _ = st.columns([2, 2.5, 0.6, 2.5, 2])
                        
                        with c_d:
                            st.markdown(f"<div style='text-align: center; font-size:0.85rem; font-weight:bold; margin-bottom:4px; color: #475569;'>DOMÁCÍ</div>", unsafe_allow_html=True)
                            v_d = st.number_input("D", value=int(old_d) if old_d != "" else 0, key=f"d_{zid}", min_value=0, label_visibility="collapsed")
                        
                        with c_vs:
                            # ČERNÁ DVOJTEČKA
                            st.markdown(
                                "<div style='display: flex; align-items: center; justify-content: center; height: 84px; font-weight: 900; font-size: 2rem; color: #000000; padding-top: 15px;'>:</div>", 
                                unsafe_allow_html=True
                            )
                        
                        with c_h:
                            st.markdown(f"<div style='text-align: center; font-size:0.85rem; font-weight:bold; margin-bottom:4px; color: #475569;'>HOSTÉ</div>", unsafe_allow_html=True)
                            v_h = st.number_input("H", value=int(old_h) if old_h != "" else 0, key=f"h_{zid}", min_value=0, label_visibility="collapsed")
                        
                        # PRODLOUŽENÍ (OT) - Centrování
                        st.write("") 
                        is_checked = (str(old_ot).upper() == "ANO")
                        
                        # TRIK PRO CENTROVÁNÍ:
                        # Prostřední sloupec uděláme jen tak široký, aby se tam vešel text.
                        # Tím, že krajní sloupce zaberou zbytek, se to "vystředí" tlakem.
                        _, c_ot_center, _ = st.columns([1, 0.8, 1]) 
                        
                        with c_ot_center:
                            v_ot = st.checkbox(
                                "Bude prodloužení / nájezdy?", 
                                value=is_checked, 
                                key=f"ot_{zid}",
                                help="Zaškrtni, pokud věříš, že se NEROZHODNE v základní hrací době."
                            )
                            
                            # Validace hned pod tím
                            if v_ot:
                                if abs(v_d - v_h) == 1:
                                    # UPDATE: Odstraněno pozadí (background-color) a rámeček. Jen čistý text.
                                    st.markdown("<div style='text-align: center; color: #16a34a; font-weight:bold; font-size: 0.9rem; margin-top: 5px;'>✅ Tip na prodloužení aktivní</div>", unsafe_allow_html=True)
                                else:
                                    # Chybovou hlášku necháme podbarvenou, ta musí křičet
                                    st.markdown("<div style='text-align: center; background-color: #fee2e2; color: #991b1b; padding: 4px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; margin-top: 5px; border: 1px solid #fecaca;'>⚠️ Rozdíl musí být 1 gól!</div>", unsafe_allow_html=True)

                        tips_to_save[zid] = (v_d, v_h, "ANO" if v_ot else "")

            # --- TLAČÍTKO ULOŽIT ---
            st.write("---")
            zpravy_placeholder = st.empty()

            # OPRAVA TLAČÍTKA: Odstraněn parametr type="primary" (už nebude červené/plné)
            # Necháme use_container_width=True, aby bylo hezky přes šířku, ale bude mít neutrální barvu.
            if st.form_submit_button("💾 Uložit tipy", use_container_width=True):
                draw_errors = []
                for zid, (d, h, ot) in tips_to_save.items():
                    if d == 0 and h == 0: continue
                    if d == h:
                        match_name = match_names_map.get(str(zid), f"Zápas {zid}")
                        draw_errors.append(match_name)
                
                if draw_errors:
                    msg = "**❌ CHYBA: Remíza není povolena!**\n\nUprav tyto zápasy:\n" + "\n".join([f"- {e}" for e in draw_errors])
                    zpravy_placeholder.error(msg)
                else:
                    with st.spinner("Ukládám tipy..."): 
                        save_tips_batch(ws_tipy, st.session_state['user_email'], tips_to_save, tipy)
                        zpravy_placeholder.success("✅ Tipy úspěšně uloženy!")
                        time.sleep(1)
                        st.rerun()

    # 2. PŘEHLED
    with t_overview:
        st.header("Globální přehled tipů")
        st.caption("Velká tabule se všemi zápasy a tipy. Tady si můžeš zkontolovat, jestli už si na danej zápas poslal tip a máš ho uloženej. Pokud ano, svítí ti u zápsu TIP.")

        # Příprava dat
        rank_map = df_rank.set_index('Email')['Pořadí'].to_dict()
        my_email = st.session_state.get('user_email', '')
        my_name = st.session_state.get('user_name', '') # Potřebujeme pro styling

        # 1. SEŘAZENÍ HRÁČŮ (JÁ PRVNÍ, PAK OSTATNÍ)
        sorted_users = sorted(users, key=lambda u: -1 if str(u['Email']) == my_email else rank_map.get(str(u['Email']), 999))

        # 2. PŘÍPRAVA DAT
        all_matches_sorted = sorted(zapasy, key=lambda x: int(x['ID']))
        
        data = []
        tips_map = {(str(t['Email']), t['Zapas_ID']): t for t in tipy}

        # Počítadlo řádků pro sloupec "#"
        row_idx = 1

        for z in all_matches_sorted:
            # Zjištění stavu zápasu
            is_finished = (str(z['Skore_Domaci']) != "")
            
            # Kontrola času (LOCK)
            prague_tz = pytz.timezone('Europe/Prague')
            now_prague = datetime.now(prague_tz)
            match_dt = z.get('Datum_Obj')
            if match_dt and match_dt.tzinfo is None: match_dt = prague_tz.localize(match_dt)
            
            # Zápas je "viditelný" (revealed), pokud je odehrán NEBO už uplynul čas začátku (zamčeno)
            is_revealed = is_finished or (match_dt and now_prague > match_dt)

            faze = z.get('Faze', '')
            vis_result = f"{z['Skore_Domaci']}:{z['Skore_Hoste']}" if is_finished else (f"{z['Datum_Obj'].strftime('%d.%m. %H:%M')}" if match_dt else "-")
            if is_finished and str(z.get('Prodlouzeni','')) == 'ANO': 
                vis_result += " (OT)"

            row = {
                "#": row_idx,
                "Zápas": f"{z['Domaci']} - {z['Hoste']}", 
                "Fáze": faze, 
                "Výsledek": vis_result
            }
            row_idx += 1

            for u in sorted_users:
                email = str(u['Email'])
                t = tips_map.get((email, z['ID']))
                
                txt = "-" # Default
                
                if is_revealed:
                    # Ukazujeme tipy, protože je zamčeno nebo dohráno
                    if t:
                        d = int(t.get('Tip_Domaci', 0))
                        h = int(t.get('Tip_Hoste', 0))
                        
                        if d == 0 and h == 0:
                            txt = "-"
                        else:
                            ot_mark = " (OT)" if str(t.get('Tip_Prodlouzeni','')) == 'ANO' else ""
                            txt = f"{d}:{h}{ot_mark}"
                            
                            # Body počítáme a zobrazujeme JEN pokud je zápas dohrán (is_finished)
                            if is_finished:
                                p, ie, _, _ = spocitej_body_zapas(
                                    t['Tip_Domaci'], t['Tip_Hoste'], 
                                    z['Skore_Domaci'], z['Skore_Hoste'], 
                                    z['Domaci'], z['Hoste'], z.get('Faze',''),
                                    t.get('Tip_Prodlouzeni', ''), z.get('Prodlouzeni', '')
                                )
                                txt += f" ({p} b.)"
                                if ie: txt = f"⭐ {txt}"
                    else:
                        txt = "❌" # Nenatipováno a zamčeno
                else:
                    # Zápas je v budoucnu -> jen info, zda má natipováno
                    if t:
                        try:
                            d, h = int(t.get('Tip_Domaci', 0)), int(t.get('Tip_Hoste', 0))
                        except: d, h = 0, 0
                        txt = "TIP" if (d != 0 or h != 0) else "" # Změněno na ikonku pro lepší přehlednost
                    else:
                        txt = "" 

                row[email] = txt
            
            data.append(row)

        if data:
            # Sloupce: Indexové + Hráči
            cols_info = ['#', 'Zápas', 'Fáze', 'Výsledek']
            cols_users = [str(u['Email']) for u in sorted_users]
            
            df_ov = pd.DataFrame(data, columns=cols_info + cols_users)

            # --- A. NASTAVENÍ INDEXU (Tím se sloupce "přilepí" vlevo) ---
            df_ov.set_index(['#', 'Zápas', 'Fáze', 'Výsledek'], inplace=True)

            # --- B. VYTVOŘENÍ PATROVÉ HLAVIČKY PRO HRÁČE ---
            header_tuples = []
            for u in sorted_users:
                email = str(u['Email'])
                u_rank = rank_map.get(email, '-')
                u_points = total_points.get(email, 0)
                
                # Hlavička: (Jméno, Info o bodech)
                header_tuples.append((u['Jmeno'], f"{u_rank}. místo ({u_points} b.)"))

            df_ov.columns = pd.MultiIndex.from_tuples(header_tuples)

            # --- C. STYLING (Podbarvení mého sloupce) ---
            def highlight_me_col(s):
                # s.name je tuple ('Jmeno', 'Info')
                # Porovnáváme první část (Jméno) s mým jménem
                col_name = s.name[0]
                if col_name == my_name:
                    return ['background-color: #e8f4f8; border-left: 2px solid #007bff; border-right: 2px solid #007bff; color: black; font-weight: bold'] * len(s)
                return [''] * len(s)

            # Aplikace stylu
            styled_df = df_ov.style.apply(highlight_me_col, axis=0).set_properties(**{
                'text-align': 'center', 
                'white-space': 'nowrap'
            })

            st.dataframe(
                styled_df, 
                use_container_width=True, 
                height=600
            )
        else:
            st.info("Zatím nejsou k dispozici žádná data o zápasech.")

        # B) TABULKA DLOUHODOBÝCH SÁZEK
        if OFFICIAL_RESULTS.get('winner'):
            st.divider()
            st.subheader("🏆 Vyhodnocení dlouhodobých sázek")
            st.caption("Detailní rozpis bodů za tipy na vítěze a medailisty.")

            long_term_data = []
            real_winner = str(OFFICIAL_RESULTS['winner'])
            real_medals = [str(m) for m in OFFICIAL_RESULTS['medals'] if m]

            # Zde řadíme podle bodů (vítěz nahoře), ale můžeme použít sorted_users, pokud chcete sebe nahoře i tady.
            # Necháme standardní řazení podle úspěchu v LT.

            for u in users:
                t_w = str(u.get('Tip_Vitez', '-'))
                t_m1 = str(u.get('Tip_Med1', '-'))
                t_m2 = str(u.get('Tip_Med2', '-'))
                t_m3 = str(u.get('Tip_Med3', '-'))

                pts_w = 15 if t_w == real_winner and real_winner else 0

                def get_medal_display(tip_val):
                    if tip_val in real_medals: return f"{tip_val} (4 b.)"
                    return f"{tip_val} (0 b.)"

                # Statistiky
                u_rank = rank_map.get(str(u['Email']), '-')
                u_points = total_points.get(str(u['Email']), 0)

                # Tady jsme v buňce (data), takže \n funguje, pokud zapneme 'white-space: pre-wrap'
                player_label = f"{u['Jmeno']}\n{u_rank}. místo ({u_points} b.)"

                lt_row = {
                    "Hráč": player_label,
                    "Tip Vítěz": f"{t_w} ({pts_w} b.)" if t_w != '-' else "-",
                    "Medaile 1": get_medal_display(t_m1),
                    "Medaile 2": get_medal_display(t_m2),
                    "Medaile 3": get_medal_display(t_m3),
                    "Celkem LT": spocitej_dlouhodobe_body(u, OFFICIAL_RESULTS)
                }
                long_term_data.append(lt_row)

            if long_term_data:
                df_lt = pd.DataFrame(long_term_data)
                df_lt = df_lt.sort_values("Celkem LT", ascending=False)

                # Zde musíme povolit zalamování řádků (pre-wrap) pro sloupec "Hráč"
                st.dataframe(
                    df_lt.style.set_properties(**{'text-align': 'center', 'white-space': 'pre-wrap'}), 
                    use_container_width=True, 
                    hide_index=True
                )

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
            submit_medals = st.form_submit_button("💾 Uložit medaile", disabled=lck)

            # Ukládáme jen když se klikne A NENÍ zamčeno (pojistka)
            if submit_medals and not lck:
                with st.spinner("Ukládám medaile..."):
                    row_idx = me_idx + 2
                    updates = [
                        gspread.Cell(row_idx, 7, sw),
                        gspread.Cell(row_idx, 8, m1),
                        gspread.Cell(row_idx, 9, m2),
                        gspread.Cell(row_idx, 10, m3)
                    ]
                    try:
                        ws_users.update_cells(updates)
                        st.cache_data.clear()
                        st.success("✅ Tipy na medaile byly úspěšně uloženy!")
                        time.sleep(1) 
                        st.rerun()
                    except Exception as e: st.error(f"Chyba při ukládání: {e}")

    # 4. ŽEBŘÍČEK
    with t_rank:
        if OFFICIAL_RESULTS.get('winner'):
            # FILTR: Gratulujeme jen těm, co zaplatili
            df_winners = df_rank[df_rank['Zaplaceno'] == 'ANO'].sort_values("Celkem", ascending=False)

            if len(df_winners) >= 1:
                st.success("🎉 **TURNAJ UKONČEN! GRATULACE VÍTĚZŮM!** 🎉")

                # Získání jmen pro jednotlivá místa (může jich být víc)
                firsts = df_winners[df_winners['Pořadí'] == 1]['Hráč'].tolist()
                seconds = df_winners[df_winners['Pořadí'] == 2]['Hráč'].tolist()
                thirds = df_winners[df_winners['Pořadí'] == 3]['Hráč'].tolist()

                def fmt_names(names): return ", ".join(names) if names else "-"

                st.markdown(f"### 🥇 {fmt_names(firsts)}")
                if seconds: st.markdown(f"### 🥈 {fmt_names(seconds)}")
                if thirds: st.markdown(f"### 🥉 {fmt_names(thirds)}")

                st.markdown("Pro předání výhry se ozvěte na **tipovacka.mibo@gmail.com**. Pro zobrazení výše výhry se podívejte so záložky Startovné a výhry.")

        st.header("Celkové pořadí")

        if len(df_rank) > 0:
            # 1. Výpočet referenčních bodů (s1, s2, s3)
            # Bereme data z df_rank, která jsou stále čísla (float/int)
            s1 = df_rank.iloc[0]['Celkem']
            s2 = df_rank.iloc[1]['Celkem'] if len(df_rank) > 1 else 0
            s3 = df_rank.iloc[2]['Celkem'] if len(df_rank) > 2 else 0

            # 2. Výpočet ztrát (zatím jako ČÍSLA nebo None, ne stringy!)
            # Důležité: Necháváme df_rank čisté s čísly, formátování děláme až pro zobrazení
            df_rank['Ztráta na 1. místo'] = df_rank['Celkem'].apply(lambda x: s1 - x if s1 > x else None)
            df_rank['Ztráta na 2. místo'] = df_rank['Celkem'].apply(lambda x: s2 - x if s2 > x else None)
            df_rank['Ztráta na 3. místo'] = df_rank['Celkem'].apply(lambda x: s3 - x if s3 > x else None)

        # 3. Filtr týmu
        at = sorted(list(set(df_rank['Tým'].replace('', '-'))))
        vybrany_tym = st.selectbox("Filtr týmu", ["Všechny"] + at)
        
        # Lokální proměnná pro filtrovaná data (nepřepisujeme globální df_rank, abychom ho nerozbili)
        df_show = df_rank.copy()
        if vybrany_tym != "Všechny": 
            df_show = df_show[df_show['Tým'] == vybrany_tym]

        # --- NOVÁ TABULKA ŽEBŘÍČKU (V2 - Zvýrazněná & Opravená) ---
        
        # 4. Definice sloupců a názvů
        cols_map = {
            'Pořadí': 'Pořadí',
            'Vývoj pořadí': 'Trend',
            'Hráč': 'Hráč',
            'Tým': 'Tým',
            'Celkem': 'CELKEM',         
            'Body Zápasy': 'Zápasy',
            'Tiper Dne': 'Tiper\nDne',
            'Odvaha': 'Bonus\nOdvaha',
            'Medaile/Vítěz': 'Koncový\nbonus',
            'Ztráta na 1. místo': 'Ztráta\nna 1.',
            'Ztráta na 2. místo': 'Ztráta\nna 2.',
            'Ztráta na 3. místo': 'Ztráta\nna 3.'
        }
        
        source_cols = [
            'Pořadí', 'Vývoj pořadí', 'Hráč', 'Tým', 
            'Celkem', 
            'Body Zápasy', 'Tiper Dne', 'Odvaha', 'Medaile/Vítěz', 
            'Ztráta na 1. místo', 'Ztráta na 2. místo', 'Ztráta na 3. místo'
        ]
        
        # 5. Vytvoření display dataframe
        df_display = df_show[source_cols].copy().rename(columns=cols_map)
        
        # 6. Formátování BODOVÝCH sloupců (na 1 desetinné místo + " b.")
        format_cols_points = ['CELKEM', 'Zápasy', 'Tiper\nDne', 'Bonus\nOdvaha', 'Koncový\nbonus']
        for col in format_cols_points:
            if col in df_display.columns:
                # x může být float nebo int. F-string :.1f zvládne obojí.
                df_display[col] = df_display[col].apply(lambda x: f"{float(x):.1f} b." if pd.notnull(x) and x != "" else "")

        # 7. Formátování ZTRÁTOVÝCH sloupců (na 1 desetinné místo + " b.")
        format_cols_loss = ['Ztráta\nna 1.', 'Ztráta\nna 2.', 'Ztráta\nna 3.']
        for col in format_cols_loss:
            if col in df_display.columns:
                # Zde máme None pro prázdné hodnoty (viz krok 2)
                df_display[col] = df_display[col].apply(lambda x: f"-{float(x):.1f} b." if pd.notnull(x) and x != "" else "")

        # 8. Funkce pro barvení
        def highlight_rows_v2(s):
            is_me = (s['Hráč'] == st.session_state['user_name'])
            try:
                rank = s['Pořadí']
                # Body už jsou string, ale pro barvení řádků nám stačí vědět rank
                # (Předpokládáme, že kdo má rank 1, má body > 0, pokud ne, nevadí)
                # Pro jistotu zkontrolujeme, zda 'CELKEM' není prázdné
                p_str = str(s['CELKEM'])
                has_points = " b." in p_str and p_str != "0.0 b."
            except:
                rank = 999; has_points = False

            css = ''
            # Barvíme medaile
            if has_points:
                if rank == 1: css = 'background-color: #FFD700; color: black;'
                elif rank == 2: css = 'background-color: #C0C0C0; color: black;'
                elif rank == 3: css = 'background-color: #CD7F32; color: black;'

            # Můj řádek
            if is_me:
                if not css: css = 'background-color: #e8f4f8; color: black;'
                css += ' font-weight: bold; border-top: 2px solid #007bff; border-bottom: 2px solid #007bff;'
            return [css] * len(s)

        styled = df_display.style.apply(highlight_rows_v2, axis=1)
        
        # ZVÝRAZNĚNÍ SLOUPCE CELKEM (Bez barvy pozadí, jen rámeček a font)
        # Tím pádem bude prosvítat barva řádku (zlatá/stříbrná)
        styled = styled.set_properties(subset=['CELKEM'], **{
            'font-weight': '900',                # Extra tučné
            'border-left': '3px solid #000000',  # Silný levý okraj
            'border-right': '3px solid #000000', # Silný pravý okraj
            'font-size': '1.1em'
        })

        st.dataframe(
            styled, 
            use_container_width=True, 
            hide_index=True,
            height=600
        )
    # 5. STATISTIKY
    with t_stats:
        st.header("Statistika nuda je, má však cenné údaje")

        # --- NOVÉ STATISTIKY (Tiper Dne & Odvaha) ---
        col_spec1, col_spec2 = st.columns(2)

        with col_spec1:
            st.markdown("#### 📅 Tiper Dne")
            st.caption("Kdo získal bonus za **včerejší** den? (Nejvíce bodů za den)")

            # Zjištění včerejška pro zobrazení "aktuálního" vítěze
            yesterday = datetime.now().date() - timedelta(days=1)
            yesterday_winners = [x for x in tiper_dne_log if x['Datum'] == yesterday]

            if yesterday_winners:
                st.write(f"**Vítězové ze dne {yesterday.strftime('%d.%m.')}:**")
                st.dataframe(pd.DataFrame(yesterday_winners)[['Jméno', 'Body ten den', 'Bonus']], use_container_width=True, hide_index=True)
            else:
                st.info(f"Za včerejšek ({yesterday.strftime('%d.%m.')}) nebyl udělen žádný bonus.")

            with st.expander("🏆 Celkový žebříček: Tiper Dne"):
                td_data = [{"Jméno": u['Jmeno'], "Celkem Bonus": bonus_tiper_dne.get(str(u['Email']), 0)} for u in users if bonus_tiper_dne.get(str(u['Email']), 0) > 0]
                if td_data:
                    st.dataframe(pd.DataFrame(td_data).sort_values("Celkem Bonus", ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.write("Zatím nikdo.")

        with col_spec2:
            st.markdown("#### 🦁 Bonus za Odvahu")
            st.caption("Hráči, kteří trefili vítěze, na kterého sázelo **méně než 20 %** lidí (+1 bod).")

            odvaha_data = [{"Jméno": u['Jmeno'], "Body za Odvahu": bonus_odvaha.get(str(u['Email']), 0)} for u in users if bonus_odvaha.get(str(u['Email']), 0) > 0]

            if odvaha_data:
                st.dataframe(pd.DataFrame(odvaha_data).sort_values("Body za Odvahu", ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info("Zatím se nenašel žádný odvážlivec, který by trefil překvapení.")

        st.divider()
        
        st.subheader("🔮 Čitelnost týmů")
        st.caption("Průměrný počet čistých bodů (Základ + Přesný tip + OT + Odvaha), který tým přináší.")

        if finished_matches:
            # {tym: [seznam_čistých_bodů_z_každého_tipu]}
            team_stats_map = {}

            for z in finished_matches:
                zid = z['ID']
                match_tips = tips_by_match.get(zid, [])
                if not match_tips: continue

                # --- 1. PŘÍPRAVA PRO BONUS ZA ODVAHU ---
                # Musíme vědět, jak na tom tým byl v % sázek
                cnt_d = sum(1 for mt in match_tips if mt['Tip_Domaci'] > mt['Tip_Hoste'])
                cnt_h = sum(1 for mt in match_tips if mt['Tip_Hoste'] > mt['Tip_Domaci'])
                total_tips = len(match_tips)
                
                perc_d = cnt_d / total_tips if total_tips > 0 else 0
                perc_h = cnt_h / total_tips if total_tips > 0 else 0
                
                rd, rh = int(z['Skore_Domaci']), int(z['Skore_Hoste'])
                real_winner = 'd' if rd > rh else ('h' if rh > rd else 'draw')
                
                # Byl vítěz outsider? (< 20%)
                is_underdog_win = False
                if real_winner == 'd' and perc_d < 0.20: is_underdog_win = True
                if real_winner == 'h' and perc_h < 0.20: is_underdog_win = True

                # --- 2. VÝPOČET BODŮ PRO KAŽDÝ TIP ---
                match_sum_points = 0
                valid_tips_count = 0

                for t in match_tips:
                    td, th = int(t['Tip_Domaci']), int(t['Tip_Hoste'])
                    
                    # A) ZÁKLADNÍ BODY + PŘESNÝ TIP (Rekonstrukce logiky)
                    pure_points = 0
                    
                    tip_winner = 'd' if td > th else ('h' if th > td else 'draw')
                    
                    # Pokud trefil vítěze
                    if tip_winner == real_winner and real_winner != 'draw':
                        diff = abs(rd - td) + abs(rh - th)
                        base = max(2, 7 - diff)
                        pure_points += base
                        
                        # Bonus za přesný tip
                        if td == rd and th == rh:
                            pure_points += 2
                    
                    # B) OT BONUS / PENALIZACE
                    # Logika: Pokud je rozdíl v tipu 1 gól, řešíme OT
                    if abs(td - th) == 1:
                        tip_ot_bool = str(t.get('Tip_Prodlouzeni', '')).upper() == 'ANO'
                        real_ot_bool = str(z.get('Prodlouzeni', '')).upper() == 'ANO'
                        
                        if tip_ot_bool:
                            if real_ot_bool: pure_points += 1 # Trefil remízu po 60min
                            else: pure_points -= 1            # Netrefil (skončilo v základu)
                    
                    # C) BONUS ZA ODVAHU
                    # Pokud trefil vítěze a ten vítěz byl underdog
                    if is_underdog_win and tip_winner == real_winner:
                        pure_points += 1

                    # Ošetření záporných bodů (jen pro jistotu, aby průměr nebyl divoký, i když -1 je teoreticky možná)
                    match_sum_points += max(0, pure_points)
                    valid_tips_count += 1
                
                # --- 3. ULOŽENÍ PRŮMĚRU ZÁPASU ---
                if valid_tips_count > 0:
                    avg_match_pts = match_sum_points / valid_tips_count
                    
                    # Přičtení do statistik obou týmů
                    team_stats_map.setdefault(z['Domaci'], []).append(avg_match_pts)
                    team_stats_map.setdefault(z['Hoste'], []).append(avg_match_pts)

            # --- 4. VYKRESLENÍ TABULEK ---
            final_data = []
            for team, avgs in team_stats_map.items():
                if avgs:
                    grand_avg = sum(avgs) / len(avgs)
                    final_data.append({"Tým": team, "Průměr bodů": grand_avg})
            
            if final_data:
                df_teams = pd.DataFrame(final_data).sort_values("Průměr bodů", ascending=False)
                
                col_read1, col_read2 = st.columns(2)
                
                with col_read1:
                    st.markdown("**Nejčitelnější týmy (Top 3)**")
                    top_3 = df_teams.head(3).copy()
                    top_3['Průměr bodů'] = top_3['Průměr bodů'].apply(lambda x: f"{x:.2f}")
                    st.dataframe(top_3.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)
                    
                with col_read2:
                    st.markdown("**Nejhůř čitelné týmy (Bottom 3)**")
                    bot_3 = df_teams.tail(3).sort_values("Průměr bodů", ascending=True).copy()
                    bot_3['Průměr bodů'] = bot_3['Průměr bodů'].apply(lambda x: f"{x:.2f}")
                    st.dataframe(bot_3.style.set_properties(**{'text-align': 'center'}), use_container_width=True, hide_index=True)

                st.info("ℹ️ *Data zahrnují: Základní body, přesný tip, OT bonus/penalizaci a bonus za odvahu. Nezahrnují: Playoff násobič, Český bonus, Tiper dne.*")
        
        else:
            st.info("Čekáme na první odehrané zápasy.")

        st.divider()

        # --- PŮVODNÍ STATISTIKY ---
        st.subheader("🍀 Šťastná ruka & 💀 Zabiják tiketů")
        st.caption("Zápasy s nejvyšším a nejnižším průměrem bodů na hráče.")

        if finished_matches:
            # Přepočet statistik pro zápasy
            match_stats = []
            for z in finished_matches:
                tips_for_z = tips_by_match.get(z['ID'], [])
                if not tips_for_z: continue

                total_pts = 0; count = 0
                faze_lower = str(z.get('Faze', '')).lower()
                is_playoff = any(x in faze_lower for x in ["playoff", "finále", "o 3. místo", "čtvrtfinále", "semifinále"])

                for t in tips_for_z:
                    # Zde musíme použít správnou funkci pro výpočet bodů, kterou jsme definovali dříve (včetně OT)
                    p, _, _, _ = spocitej_body_zapas(
                        t['Tip_Domaci'], t['Tip_Hoste'], z['Skore_Domaci'], z['Skore_Hoste'], 
                        z['Domaci'], z['Hoste'], z.get('Faze',''),
                        t.get('Tip_Prodlouzeni', ''), z.get('Prodlouzeni', '')
                    )
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

            # A. ZMĚNA ÚDAJŮ
            with st.form("prof"):
                st.subheader("Osobní údaje")
                # Zobrazení ID a Jména
                st.write(f"🆔 Tvoje hráčské ID: **{current_data.get('ID', 'N/A')}**")
                st.caption("Toto ID uváděj do poznámky při platbě startovného.")
                st.write(f"Jméno hráče: **{current_data['Jmeno']}**")

                st.divider()
                st.subheader("Týmová příslušnost")
                st.write(f"Aktuální tým: **{curr_team if curr_team else 'Žádný'}**")

                c1, c2 = st.columns(2)
                with c1:
                    sel = st.selectbox("Přidat se k týmu", ["- Vyber -"] + all_existing_teams)
                    final_team = sel if sel != "- Vyber -" else curr_team
                with c2:
                    new_t = st.text_input("Nebo založit nový")
                    if new_t: final_team = new_t

                if st.form_submit_button("💾 Uložit změnu týmu"):
                    row_idx = current_u_idx + 2
                    # Aktualizujeme POUZE sloupec 6 (Tým), sloupec 2 (Jméno) necháváme být
                    updates = [gspread.Cell(row_idx, 6, final_team)]
                    try:
                        ws_users.update_cells(updates)
                        # st.session_state['user_name'] už neměníme
                        st.session_state['user_team'] = final_team
                        st.cache_data.clear()
                        st.success("✅ Tým byl úspěšně aktualizován!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e: st.error(f"Chyba při ukládání: {e}")

            st.divider()

            # B. ZMĚNA HESLA (NOVÉ)
            with st.form("pass_change"):
                st.subheader("Změna hesla")
                p_old = st.text_input("Staré heslo", type="password")
                p_new = st.text_input("Nové heslo", type="password")
                p_new2 = st.text_input("Kontrola nového hesla", type="password")

                if st.form_submit_button("🔐 Změnit heslo"):
                    # Ověření starého hesla
                    if check_password(p_old, current_data['Heslo']):
                        if p_new == p_new2:
                            if len(p_new) > 0:
                                new_hash = make_hash(p_new)
                                ws_users.update_cell(current_u_idx + 2, 3, new_hash) # Sloupec 3 je Heslo
                                st.cache_data.clear()
                                st.success("Heslo úspěšně změněno!")
                            else:
                                st.error("Heslo nesmí být prázdné.")
                        else:
                            st.error("Nová hesla se neshodují.")
                    else:
                        st.error("Staré heslo není správné.")

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
        * **Playoff:** Všechny body za zápas se násobí **1.5x** (kromě bonusů, včetně českého).
        * **Tipy na medailisty:**
            * **+15 bodů** za vítěze turnaje.
            * **+4 body** za každého trefeného medailistu.
        * **Tiper dne**
            * Ten kdo za daný hrací den získal nejvíce bodů, získává navíc bonus **0,5 bodu** za každý odehraný zápas v tomto dnu. Bonus může získat více hráčů.
        * **Bonus za odvahu**
            * Pokud zvolíte za vítěze zápasu tým, který tipuje méně než 20 % tipujcích, tak při výhře tohoto týmu získáváte navíc bonus **+1 bod**.
        * **Další bonusy:**
            * **+6 bodů** pro "Ostrostřelce" (hráč s nejvíce přesnými tipy na konci turnaje).
            * Pokud si tipneš, že zápas půjde do prodloužení/nájezdů a budeš mít pravdu, získáš **+1 bod**. V opačném případě **1 bod** ztrácíš.
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
                {"Rok": 2024, "Turnaj": "MS - Česko", "🥇 1. Místo": "Luděk / Příbor", "🥈 2. Místo": "-", "🥉 3. Místo": "Tony B."},
                {"Rok": 2023, "Turnaj": "MS - Finsko/Lotyšsko", "🥇 1. Místo": "Tyrda", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Honza K."},
                {"Rok": 2022, "Turnaj": "MS - Finsko", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "Tonda V.", "🥉 3. Místo": "MiBo"},
                {"Rok": 2022, "Turnaj": "ZOH - Čína", "🥇 1. Místo": "Kedárek", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Kedar"},
                {"Rok": 2021, "Turnaj": "MS - Lotyšsko", "🥇 1. Místo": "Honza Geryk", "🥈 2. Místo": "Peťa údržbář", "🥉 3. Místo": "Janča"},
                {"Rok": 2019, "Turnaj": "MS - Slovensko", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "MiBo", "🥉 3. Místo": "Honza K."},
                {"Rok": 2018, "Turnaj": "MS - Dánsko", "🥇 1. Místo": "Dominik", "🥈 2. Místo": "Lukáš", "🥉 3. Místo": "Tonda V."},
                {"Rok": 2017, "Turnaj": "MS - Němesko/Francie", "🥇 1. Místo": "Lukáš", "🥈 2. Místo": "Tonda V.", "🥉 3. Místo": "MiBo"},
                {"Rok": 2016, "Turnaj": "MS - Rusko", "🥇 1. Místo": "Vlasta", "🥈 2. Místo": "Kuba H.", "🥉 3. Místo": "MiBo"},
            ]
            df_hist_h = pd.DataFrame(history_hockey)
            st.dataframe(df_hist_h.style.set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])]), use_container_width=True, hide_index=True)

        with col_hist_f:
            st.subheader("⚽ Fotbal")
            history_football = [
                {"Rok": 2024, "Turnaj": "EURO - Německo", "🥇 1. Místo": "Brácha Tyrdy", "🥈 2. Místo": "Antonín", "🥉 3. Místo": "Tyrda"},
                {"Rok": 2022, "Turnaj": "MS - Katar", "🥇 1. Místo": "Tony B.", "🥈 2. Místo": "Lukáš", "🥉 3. Místo": "MiBo"},
                {"Rok": 2021, "Turnaj": "EURO - 11 zemí", "🥇 1. Místo": "Dominik", "🥈 2. Místo": "Kedar", "🥉 3. Místo": "Tony B."},
                {"Rok": 2016, "Turnaj": "EURO - Francie", "🥇 1. Místo": "Vojta H.", "🥈 2. Místo": "Ondra T.", "🥉 3. Místo": "Luděk"},
            ]
            df_hist_f = pd.DataFrame(history_football)
            st.dataframe(df_hist_f.style.set_properties(**{'text-align': 'center'}).set_table_styles([dict(selector='th', props=[('text-align', 'center')])]), use_container_width=True, hide_index=True)
        st.subheader("Pořadí hráčů")
        st.markdown("Historická úspěšnost hráčů napříč všemi turnaji (seřazeno dle medailí: 🥇 > 🥈 > 🥉).")

        # 1. Agregace dat
        # Sloučíme oba seznamy do jednoho
        all_history = history_hockey + history_football
        medal_stats = {}

        def add_medal(name_raw, type_medal):
            # Ošetření pro dělená místa (např. "Luděk / Příbor")
            names = [n.strip() for n in str(name_raw).split('/')]
            for name in names:
                if name in ["-", "", None]: continue

                # Normalizace jmen (volitelné - sjednotí např. "Tony" a "Tony B." pokud chceš, zatím nechávám raw)
                key = name

                if key not in medal_stats:
                    medal_stats[key] = {'🥇 Zlato': 0, '🥈 Stříbro': 0, '🥉 Bronz': 0, 'Celkem': 0}

                medal_stats[key][type_medal] += 1
                medal_stats[key]['Celkem'] += 1

        for row in all_history:
            add_medal(row.get('🥇 1. Místo'), '🥇 Zlato')
            add_medal(row.get('🥈 2. Místo'), '🥈 Stříbro')
            add_medal(row.get('🥉 3. Místo'), '🥉 Bronz')

        # 2. Převod na DataFrame
        if medal_stats:
            df_hall = pd.DataFrame.from_dict(medal_stats, orient='index').reset_index()
            df_hall.columns = ['Hráč', '🥇 Zlato', '🥈 Stříbro', '🥉 Bronz', 'Celkem medailí']

            # 3. Třídění (Olympijský systém: G > S > B)
            df_hall = df_hall.sort_values(by=['🥇 Zlato', '🥈 Stříbro', '🥉 Bronz'], ascending=False).reset_index(drop=True)
            df_hall.index += 1 # Pořadí od 1.

            # Zobrazení
            st.dataframe(df_hall.style.set_properties(**{'text-align': 'center'}), use_container_width=True)
        else:
            st.info("Zatím nejsou data pro výpočet síně slávy.")

        me_email = st.session_state.get('user_email', '')
        if "mibo" in me_email.lower():
                st.info("💡 **Zajímavost:** Hráč **MiBo** má na kontě neuvěřitelných 7 medailí z obou sportů (4x🥈, 3x🥉). To už je skoro prokletí! 😅")    
    # 10. DISKUZE
    with t_chat:
        # Jakmile uživatel otevře tuto záložku, uložíme si, že viděl všechny aktuální zprávy
        st.session_state['chat_seen_count'] = len(chat_data)

        st.header("🗣️ Diskuze")

        # --- LOGIKA NAČÍTÁNÍ VÍCE ZPRÁV ---
        # Inicializace počítadla v session state, pokud tam není
        if 'chat_limit' not in st.session_state:
            st.session_state['chat_limit'] = 30

        # Kolik zpráv máme celkem v DB?
        total_msgs = len(chat_data)
        # Kolik jich teď chceme zobrazit?
        current_limit = st.session_state['chat_limit']

        st.caption(f"Místo pro hecování, analýzy, drby a všechno ostatní s čím se chcete podělit s ostatními. Zobrazuji posledních **{min(current_limit, total_msgs)}** zpráv.")

        # A) VSTUPNÍ POLE
        with st.form("chat_input_form", clear_on_submit=True):
            col_ch1, col_ch2 = st.columns([5, 1], vertical_alignment="bottom")
            new_msg = col_ch1.text_input("Napiš zprávu...", key="chat_msg_input", placeholder="Kdo neskáče není Čech...")
            sent = col_ch2.form_submit_button("Odeslat")

            if sent and new_msg:
                prague_tz = pytz.timezone('Europe/Prague')
                now_str = datetime.now(prague_tz).strftime("%d.%m. %H:%M")
                user_nm = st.session_state['user_name']
                try:
                    ws_chat.append_row([now_str, user_nm, new_msg])
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e: st.error(f"Chyba: {e}")

        st.divider()

        # B) VÝPIS ZPRÁV
        chat_container = st.container()
        with chat_container:
            if not chat_data:
                st.info("Zatím tu je ticho... Buď první!")
            else:
                # Vezmeme posledních X zpráv podle limitu (např. posledních 30, 60...)
                msgs_to_show = chat_data[-current_limit:]

                # Otočíme je, aby nejnovější byly nahoře
                for msg in reversed(msgs_to_show): 
                    is_me = (msg['Hrac'] == st.session_state['user_name'])
                    avatar = "😎" if is_me else "👤"
                    with st.chat_message(name=msg['Hrac'], avatar=avatar):
                        st.write(f"**{msg['Hrac']}** <small style='color:grey'>({msg['Datum']})</small>", unsafe_allow_html=True)
                        st.write(msg['Zprava'])

        # C) TLAČÍTKO "NAČÍST DALŠÍ"
        # Zobrazíme ho jen, pokud máme v záloze víc zpráv, než kolik zrovna ukazujeme
        if total_msgs > current_limit:
            st.write("---")
            if st.button(f"Načíst dalších 30 starších zpráv 📜 ({total_msgs - current_limit} zbývá)"):
                st.session_state['chat_limit'] += 30
                st.rerun()
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
            my_id = me.get('ID', '?') if me else '?'
            st.write("**Číslo účtu:** 1596874001/2700"); st.write(f"**Částka:** {ENTRY_FEE} Kč")
            st.markdown(f"**Poznámka pro příjemce:** `{st.session_state['user_name']} (ID: {my_id})`")
            st.caption("Prosím uveď ID, ať platbu snadno spárujeme.")
            if os.path.exists("qr_platba.jpeg"):
                st.image("qr_platba.jpeg", caption="QR Platba", width=250)
            else:
                st.info("QR kód není nahrán.")
        with c2:
            st.subheader("Aktuální rozdělení výher")

            # Definice banků (60% / 20% / 10% - zbývá 10% rezerva/poplatky)
            pot_1 = int(bank_total * 0.6)
            pot_2 = int(bank_total * 0.2)
            pot_3 = int(bank_total * 0.1)

            # Logika dělení (Split Pot)
            # Spočítáme, kolik lidí je na 1., 2. a 3. místě
            c1 = len(df_rank[df_rank['Pořadí'] == 1])
            c2 = len(df_rank[df_rank['Pořadí'] == 2])
            c3 = len(df_rank[df_rank['Pořadí'] == 3])

            # --- VÝPOČET PRO 1. MÍSTO ---
            prize_1 = 0
            desc_1 = ""
            if c1 == 1:
                prize_1 = pot_1
            elif c1 > 1:
                # Dělí se o 1. místo a další místa pod tím
                pool = pot_1
                if c1 >= 2: pool += pot_2 # Pokud jsou 2 a víc, berou i stříbro
                if c1 >= 3: pool += pot_3 # Pokud jsou 3 a víc, berou i bronz
                prize_1 = int(pool / c1)
                desc_1 = f"(Dělená výhra: {c1} hráči)"

            # --- VÝPOČET PRO 2. MÍSTO ---
            # Existuje jen pokud je na 1. místě sám
            prize_2 = 0
            desc_2 = ""
            if c1 == 1:
                if c2 == 1:
                    prize_2 = pot_2
                elif c2 > 1:
                    # Dělí se o 2. a 3. místo
                    pool = pot_2
                    if c2 >= 2: pool += pot_3
                    prize_2 = int(pool / c2)
                    desc_2 = f"(Dělená výhra: {c2} hráči)"

            # --- VÝPOČET PRO 3. MÍSTO ---
            # Existuje jen pokud 1. a 2. místo obsadili max 2 lidé dohromady
            prize_3 = 0
            desc_3 = ""
            slots_taken = c1 + (c2 if c1 == 1 else 0) # Kolik pozic je zabráno před bronzem

            if slots_taken < 3: 
                # Bronz se rozděluje mezi všechny na 3. místě
                if c3 > 0:
                    prize_3 = int(pot_3 / c3)

            # VÝPIS
            st.write(f"🥇 **1. Místo:** {prize_1} Kč {desc_1}")
            if prize_2 > 0:
                st.write(f"🥈 **2. Místo:** {prize_2} Kč {desc_2}")
            else:
                st.caption("🥈 2. Místo: - (bráno vítězi)")

            if prize_3 > 0:
                st.write(f"🥉 **3. Místo:** {prize_3} Kč {desc_3}")
            else:
                st.caption("🥉 3. Místo: - (bráno vyššími pozicemi)")

    # --- ADMIN & MODERATOR PANEL ---
    if is_admin and t_admin:
        with t_admin:
            st.header(f"Panel: {user_role.capitalize()}")

            # 1. ZADÁVÁNÍ VÝSLEDKŮ
            with st.expander("Výsledky zápasů", expanded=True):
                z_names = [f"{z['ID']}: {z['Domaci']} vs {z['Hoste']}" for z in zapasy]
                sel_z = st.selectbox("Vyber zápas", z_names)
                sid = int(sel_z.split(":")[0])
                with st.form("admin_score"):
                    curr_z = next((x for x in zapasy if x['ID'] == sid), {})

                    # Tady máme plnou šířku, takže 3 sloupce budou vypadat skvěle
                    c1, c2, c3 = st.columns(3)
                    d = c1.text_input("Góly Domácí", value=curr_z.get('Skore_Domaci', ''))
                    h = c2.text_input("Góly Hosté", value=curr_z.get('Skore_Hoste', ''))

                    curr_ot = str(curr_z.get('Prodlouzeni', 'NE')).upper()
                    ot_val = c3.selectbox("Prodloužení?", ["NE", "ANO"], index=1 if curr_ot == "ANO" else 0, key=f"admin_ot_{sid}")

                    if st.form_submit_button("💾 Uložit výsledek"):
                        try:
                            all_ids = ws_zapasy.col_values(1) 
                            search_id = str(sid)
                            if search_id in all_ids:
                                row_idx = all_ids.index(search_id) + 1
                                ws_zapasy.update_cell(row_idx, 5, d)
                                ws_zapasy.update_cell(row_idx, 6, h)
                                ws_zapasy.update_cell(row_idx, 8, ot_val)
                                st.cache_data.clear(); st.success(f"✅ Výsledek zápasu {sid} uložen!"); time.sleep(1); st.rerun()
                            else:
                                st.error(f"❌ Chyba: ID zápasu '{sid}' nenalezeno.")
                        except Exception as e: st.error(f"Chyba: {e}")

            # 2. POUZE PRO HLAVNÍHO ADMINA
            if user_role == 'admin':
                col_ad1, col_ad2 = st.columns(2)

                with col_ad1:
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

                with col_ad2:
                    with st.expander("Správa plateb"):
                        users_list = [f"[ID: {u.get('ID','?')}] {u['Jmeno']} ({u['Email']})" for u in users]
                        sel_user_pay = st.selectbox("Vyber uživatele", users_list)
                        sel_email = sel_user_pay.split(" (")[-1].replace(")", "")
                        u_idx = next((i for i, u in enumerate(users) if str(u['Email']) == sel_email), 0)

                        st.write(f"Stav: **{str(users[u_idx].get('Zaplaceno', 'NE'))}**")
                        c_p1, c_p2 = st.columns(2)
                        if c_p1.button("✅ Zaplaceno"):
                            ws_users.update_cell(u_idx+2, 11, "ANO"); st.cache_data.clear(); st.success("OK"); time.sleep(0.5); st.rerun()
                        if c_p2.button("❌ Nezaplaceno"):
                            ws_users.update_cell(u_idx+2, 11, "NE"); st.cache_data.clear(); st.success("OK"); time.sleep(0.5); st.rerun()


# PATIČKA
st.markdown('<div class="footer-warning">⚠️ <b>Tip:</b> Pro pohyb v aplikaci používej záložky. Tlačítko Zpět nebo Refresh (F5) tě může odhlásit.</div>', unsafe_allow_html=True)

