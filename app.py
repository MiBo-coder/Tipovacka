"""
NATIPUJ.CZ - Hokejová Tipovačka Olympiáda 2026
Hlavní aplikační soubor
ZACHOVÁNO: Kompletní UI a funkčnost z tipovacka_12.py
"""

import streamlit as st
import os

# Vlastní moduly
from auth.login import render_login_page
from ui.pages import render_main_application
from ui.components import add_bg_from_local, apply_custom_css

# --- KONFIGURACE STRÁNKY ---
st.set_page_config(
    page_title="Tipovačka - Olympiáda 2026",
    layout="wide",
    page_icon="🏆"
)

# --- APLIKACE CSS STYLŮ ---
apply_custom_css()


def main():
    """Hlavní aplikační funkce"""
    
    # Přidání pozadí (pokud existuje)
    if os.path.exists("ice_bg.jpg"):
        add_bg_from_local("ice_bg.jpg")
    
    # Hlavička aplikace
    col_h1, col_h2 = st.columns([1, 4])
    with col_h2:
        st.title("NATIPUJ.CZ - hokej - Olympiáda 2026")
    
    # Inicializace session state
    if 'logged_in' not in st.session_state:
        st.session_state.update({
            'logged_in': False,
            'user_email': None,
            'user_name': None,
            'user_team': None,
            'user_role': None,
            'chat_limit': 30  # Pro postupné načítání chatu
        })
    
    # --- NEPŘIHLÁŠENÝ UŽIVATEL ---
    if not st.session_state['logged_in']:
        render_login_page()
        return
    
    # --- PŘIHLÁŠENÝ UŽIVATEL ---
    render_main_application()
    
    # PATIČKA (z originálu)
    st.markdown(
        '<div class="footer-warning">⚠️ <b>Tip:</b> Pro pohyb v aplikaci používej záložky. '
        'Tlačítko Zpět nebo Refresh (F5) tě může odhlásit.</div>',
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
