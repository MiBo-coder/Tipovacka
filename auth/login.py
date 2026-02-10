"""
Přihlašovací stránka
ZACHOVÁNO: Přesné UI z tipovacka_12.py + bcrypt security + Obnova hesla
"""

import streamlit as st
import time
from auth.security import (
    hash_password, verify_password,
    check_login_attempts, record_failed_login, record_successful_login,
    validate_password_strength
)
# IMPORTOVÁNO create_reset_request z database.py
from data.database import load_all_data, get_worksheets_resources, update_user_password, create_reset_request
from utils.config import MAX_PLAYERS


def render_login_page():
    """
    Renderuje přihlašovací stránku.
    DESIGN UPDATE: Centrovaný úzký layout (Card UI).
    """
    # Načtení dat
    _, _, users, _, _ = load_all_data()
    ws_zapasy, ws_tipy, ws_users, ws_nastaveni, ws_chat = get_worksheets_resources()

    pocet_hracu = len(users)
    st.markdown(f"<div style='text-align: center; color: #64748b; margin-bottom: 20px;'>Do hry je zapojeno již <b>{pocet_hracu}</b> hráčů!</div>", unsafe_allow_html=True)
    
    # 1. HLAVNÍ SLOUPEC PRO CENTROVÁNÍ (Responsivní)
    # Na mobilu to zabere víc místa, na desktopu jen střed.
    # Použijeme prázdné sloupce po stranách.
    col_left, col_center, col_right = st.columns([1, 4, 1]) 
    
    # Pokud je obrazovka široká (desktop), zúžíme prostřední sloupec ještě víc
    # (Streamlit neumí detekovat zařízení, ale poměr 1:2:1 je na desktop fajn, na mobilu se to "slepí" pod sebe)
    # Pro lepší kontrolu použijeme vnořené sloupce uvnitř col_center, pokud by to bylo moc široké.
    # Ale pro začátek zkusíme poměr [1, 2, 1] na celý layout.
    
    # UPDATE: Aby to bylo opravdu úzké "jako karta", dáme poměr [1, 1.5, 1] nebo i [2, 3, 2]
    # Zkusíme raději čistší přístup - vložíme obsah přímo do st.tabs a ty omezíme.
    
    st.write("") # Odsazení shora
    
    # Layout: Prázdno | Taby | Prázdno
    c1, c2, c3 = st.columns([1, 2, 1])
    
    with c2:
        # Taby pro přihlášení a registraci
        tab_login, tab_reg = st.tabs(["🔑 Přihlášení", "📝 Registrace"])
        
        # --- TAB 1: PŘIHLÁŠENÍ ---
        with tab_login:
            st.write("") # Malá mezera
            with st.form("login_form"):
                email = st.text_input("Email")
                password = st.text_input("Heslo", type="password")
                
                st.write("") # Mezera před tlačítkem
                # use_container_width=True roztáhne tlačítko na šířku sloupce (formuláře)
                submit = st.form_submit_button("Vstoupit", use_container_width=True)
                
                if submit:
                    # Rate limiting
                    allowed, error_msg = check_login_attempts()
                    if not allowed:
                        st.error(error_msg); return
                    
                    if not email or not password:
                        st.error("Vyplňte všechna pole."); record_failed_login(); return
                    
                    clean_email = email.strip().lower()
                    user_match = None; user_idx = None
                    
                    for idx, u in enumerate(users):
                        if str(u['Email']).strip().lower() == clean_email:
                            user_match = u; user_idx = idx; break
                    
                    if user_match and verify_password(password, user_match.get('Heslo', '')):
                        if str(user_match.get('Povoleno', 'ANO')).upper() != 'ANO':
                            st.error("Účet deaktivován."); return
                        
                        # Migrace hesla
                        old_hash = user_match.get('Heslo', '')
                        if len(old_hash) == 64 and not old_hash.startswith('$'):
                            new_hash = hash_password(password)
                            update_user_password(ws_users, user_idx, new_hash)
                        
                        record_successful_login()
                        st.session_state.update({
                            'logged_in': True, 'user_email': str(user_match['Email']),
                            'user_name': user_match.get('Jmeno', 'Hráč'),
                            'user_team': user_match.get('Tym', ''), 'user_role': user_match.get('Role', 'user')
                        })
                        st.success("Přihlášení úspěšné!"); time.sleep(0.5); st.rerun()
                    else:
                        record_failed_login(); st.error("Chyba přihlášení.")
            
            # --- OBNOVA HESLA (Mimo formulář, menší a decentní) ---
            st.write("")
            with st.expander("Zapomněl jsi heslo?", expanded=False):
                st.caption("Pošleme ti nové dočasné heslo.")
                st.info("💡 Pokud ti email nedorazí do 2 hodin, napiš mi prosím na: **tipovacka.mibo@gmail.com**")
                reset_email = st.text_input("Tvůj registrační mail", key="reset_mail_input")
                if st.button("Obnovit heslo", use_container_width=True):
                    # ... (logika obnovy hesla zůstává stejná) ...
                    clean_reset = reset_email.strip().lower()
                    if any(str(u.get('Email')).strip().lower() == clean_reset for u in users):
                        try:
                            create_reset_request(clean_reset)
                            st.success("Požadavek odeslán!")
                        except Exception as e: st.error(f"Chyba: {e}")
                    else:
                        st.error("Email nenalezen.")

        # --- TAB 2: REGISTRACE ---
        with tab_reg:
            st.write("")
            with st.form("register_form", clear_on_submit=True):
                # Stejný styl jako login
                reg_email = st.text_input("Email", key="reg_email")
                reg_name = st.text_input("Jméno/Přezdívka (zobrazované ve hře)", key="reg_name")
                reg_pass1 = st.text_input("Heslo", type="password", key="reg_pass1")
                reg_pass2 = st.text_input("Potvrzení hesla", type="password", key="reg_pass2")
                
                st.write("")
                submit_reg = st.form_submit_button("Registrovat se", use_container_width=True)
            
            if submit_reg:
                # Validace prázdných polí
                if not all([reg_email, reg_name, reg_pass1, reg_pass2]):
                    st.error("Vyplňte všechna pole.")
                    return
                
                # Validace emailu (základní)
                if '@' not in reg_email or '.' not in reg_email:
                    st.error("Neplatný formát emailu.")
                    return
                
                # Validace jména
                if len(reg_name.strip()) < 2:
                    st.error("Jméno musí mít alespoň 2 znaky.")
                    return
                
                # Kontrola shody hesel
                if reg_pass1 != reg_pass2:
                    st.error("Hesla se neshodují.")
                    return
                
                # Validace síly hesla
                pass_valid, pass_error = validate_password_strength(reg_pass1)
                if not pass_valid:
                    st.error(pass_error)
                    return
                
                # Kontrola existence emailu
                email_exists = any(
                    str(u['Email']).strip().lower() == reg_email.strip().lower()
                    for u in users
                )
                
                if email_exists:
                    st.error("Tento email je již registrován.")
                    return
                
                # Vytvoření uživatele s bcrypt heslem
                try:
                    password_hash = hash_password(reg_pass1)
                    
                    # Nové ID
                    new_id = int(max([u.get('ID', 0) for u in users])) + 1 if users else 1
                    
                    # Nový řádek (struktura z tipovacka_12.py)
                    row = [
                        reg_email,
                        reg_name,
                        password_hash,
                        0,           # Body
                        'user',      # Role
                        '',          # Tým
                        '',          # Vítěz
                        '',          # Med1
                        '',          # Med2
                        '',          # Med3
                        'NE',        # Zaplaceno
                        '',          # Placeholder
                        '',          # Placeholder
                        'ANO',       # Povoleno
                        new_id       # ID
                    ]
                    
                    ws_users.append_row(row)
                    st.cache_data.clear()
                    
                    st.success("Registrace úspěšná! Nyní se můžete přihlásit.")
                    st.balloons()
                    time.sleep(2)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"Chyba při registraci: {e}")
                    st.info("Zkuste to později nebo kontaktujte správce.")