"""
Business logika - výpočet bodů
ZACHOVÁNO: Přesná logika z tipovacka_12.py
"""

import math
from datetime import datetime
from utils.config import TIMEZONE


def spocitej_body_zapas(tip_d, tip_h, real_d, real_h, team_d, team_h, faze, tip_ot='', real_ot=''):
    """
    Spočítá body za jeden zápas.
    
    Returns:
        (points, is_exact, scored, ot_points)
    """
    # Validace vstupu
    try:
        if str(real_d) == "" or str(real_h) == "":
            return 0, False, False, 0
        
        td = int(tip_d)
        th = int(tip_h)
        rd = int(real_d)
        rh = int(real_h)
    except (ValueError, TypeError):
        return 0, False, False, 0
    
    # 1. URČENÍ VÍTĚZE (1 = domácí, 2 = hosté)
    winner_real = 1 if rd > rh else 2
    winner_tip = 1 if td > th else (2 if th > td else 0)
    
    # --- GATEKEEPER: KONTROLA VÍTĚZE ---
    # Pokud se vítěz neshoduje, okamžitě končíme. Žádné body, žádné bonusy.
    if winner_real != winner_tip:
        return 0, False, False, 0

    # Pokud jsme tady, vítěz je SPRÁVNĚ. Jdeme počítat body.
    base_points = 0
    ot_points = 0
    is_exact = False
    
    # 2. VÝPOČET ZÁKLADNÍCH BODŮ (Rozdíl skóre)
    # Spočítáme rozdíl v gólech
    diff = abs(rd - td) + abs(rh - th)
    
    # Body podle přesnosti (max 7, min 2)
    base_points = max(2, 7 - diff)
    
    # Bonus za přesný tip
    if td == rd and th == rh:
        base_points += 2
        is_exact = True
    
    # 3. PLAYOFF MULTIPLIKÁTOR
    faze_lower = str(faze).lower()
    is_playoff = any(x in faze_lower for x in ["playoff", "finále", "o 3.", "čtvrt", "semi"])
    
    if is_playoff:
        base_points = math.ceil(base_points * 1.5)
    
    # 4. BONUS ZA ČESKÉ TÝMY
    match_teams = (str(team_d) + " " + str(team_h)).lower()
    if ("česko" in match_teams or "czech" in match_teams) and base_points > 0:
        base_points += 2
    
    # 5. BONUS/PENALIZACE ZA PRODLOUŽENÍ
    # Počítáme jen pokud byl tipnut rozdíl o 1 gól (podmínka pro možnost OT)
    if abs(td - th) == 1:
        tip_ot_bool = str(tip_ot).strip().upper() == "ANO"
        real_ot_bool = str(real_ot).strip().upper() == "ANO"
        
        if tip_ot_bool:
            if real_ot_bool:
                ot_points = 1  # Trefil jsi, že bude OT
            else:
                ot_points = -1 # Myslel sis OT, ale nebylo
    
    # Celkem (nemůže být záporné)
    total_points = max(0, base_points + ot_points)
    scored = (total_points > 0 or ot_points != 0)
    
    return total_points, is_exact, scored, ot_points


def get_all_teams(zapasy):
    """
    Vrátí seznam všech týmů ze zápasů.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    teams = set()
    ignored = ["čtvrtfinále", "semifinále", "finále", "o 3. místo", "o bronz", "vítěz"]
    
    for z in zapasy:
        d, h = str(z['Domaci']), str(z['Hoste'])
        
        if not any(x in d.lower() for x in ignored):
            teams.add(d)
        if not any(x in h.lower() for x in ignored):
            teams.add(h)
    
    return sorted(list(teams))


def is_past_deadline(deadline_str):
    """
    Kontroluje, zda už uplynula uzávěrka.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    if not deadline_str:
        return False
    
    try:
        for fmt in ("%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M"):
            try:
                d = datetime.strptime(str(deadline_str), fmt)
                d = TIMEZONE.localize(d)
                return datetime.now(TIMEZONE) > d
            except ValueError:
                continue
    except:
        pass
    
    return False


def spocitej_dlouhodobe_body(user_row, official_results):
    """
    Spočítá body z dlouhodobých sázek (vítěz + medaile).
    PŮVODNÍ FUNKCE z tipovacka_12.py
    
    Args:
        user_row: Řádek uživatele z users
        official_results: {'winner': str, 'medals': [str, str, str]}
        
    Returns:
        int: Celkové body za dlouhodobé tipy
    """
    points = 0
    
    # Vítěz turnaje (+15 bodů)
    if official_results.get('winner') and str(user_row.get('Tip_Vitez')) == official_results['winner']:
        points += 15
    
    # Medaile (+4 body za každou)
    real_medals = [m for m in official_results.get('medals', []) if m]
    user_medals = [
        str(user_row.get('Tip_Med1')),
        str(user_row.get('Tip_Med2')),
        str(user_row.get('Tip_Med3'))
    ]
    
    # Unikátní zásahy (pokud tip uživatele je v reálných medailích)
    unique_hits = set([t for t in user_medals if t and t in real_medals])
    points += len(unique_hits) * 4
    
    return points
