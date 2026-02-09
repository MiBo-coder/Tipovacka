"""
NATIPUJ.CZ - Hokejová Tipovačka Olympiáda 2026
Hlavní aplikační soubor
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
    # UPDATE: Logo místo textu
    
    # 1. Řádek pro LOGO (Centrování pomocí sloupců)
    # Poměr [1, 2, 1] zajistí, že logo bude uprostřed. 
    # Pokud by bylo moc velké, změň poměr na [1, 1, 1] nebo [2, 1, 2].
    col_l, col_logo, col_r = st.columns([1.2, 1, 1.2])
    
    with col_logo:
        # Zobrazíme logo. use_container_width=True ho roztáhne na šířku prostředního sloupce.
        # Pokud soubor neexistuje, zobrazí se textová záloha.
        if os.path.exists("logo natipuj.png"):
            st.image("logo natipuj.png", use_container_width=True)
        else:
            # Záloha kdyby se obrázek nenačetl
            st.markdown("<h1 style='text-align: center;'>NATIPUJ.CZ</h1>", unsafe_allow_html=True)

    # 2. Řádek pro PODNADPIS (Hokej - Olympiáda)
    st.markdown("""
        <div style="
            display: flex; 
            justify-content: center; 
            align-items: center; 
            gap: 10px;
            color: #64748b;
            font-size: 1.4rem;
            font-weight: 500;
            margin-top: -10px; /* Přisuneme to blíž k logu */
            margin-bottom: 20px;
        ">
            <span>Hokej - Olympiáda 2026</span>
        </div>
    """, unsafe_allow_html=True)
    
    # Inicializace session state
    if 'logged_in' not in st.session_state:
        st.session_state.update({
            'logged_in': False,
            'user_email': None,
            'user_name': None,
            'user_team': None,
            'user_role': None,
            'chat_limit': 30
        })
    
    # --- NEPŘIHLÁŠENÝ UŽIVATEL ---
    if not st.session_state['logged_in']:
        render_login_page()
        return
    
    # --- PŘIHLÁŠENÝ UŽIVATEL ---
    render_main_application()
    
    # PATIČKA
    st.markdown(
        '<div class="footer-warning">⚠️ <b>Tip:</b> Pro pohyb v aplikaci používej záložky. '
        'Tlačítko Zpět nebo Refresh (F5) tě může odhlásit.</div>',
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()