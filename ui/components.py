"""
UI Komponenty a helper funkce
ZACHOVÁNO: Kompletní CSS a funkce z tipovacka_12.py
"""

import streamlit as st
import base64
from utils.config import FLAGS_ISO


def apply_custom_css():
    """
    Aplikuje KOMPLETNÍ CSS styl pro aplikaci.
    UPDATE: Oprava zmizelých popisků (Login) + Černý text pro všechny inputy.
    """
    st.markdown('<style>@import url("https://fonts.googleapis.com/css2?family=Montserrat:wght@800&family=Roboto:wght@400;500;700&display=swap");</style>', unsafe_allow_html=True)
    
    st.markdown("""
<style>
    /* 0. FIXY */
    .stApp a[href^="#"] { display: none !important; }
    
    /* 1. GLOBÁL */
    html, body, [class*="css"] {
        font-family: 'Roboto', sans-serif;
        color: #1a1a1a !important; 
    }
    .stApp { background-color: #ffffff; }

    /* 2. INPUTY (CHLÍVKY) - OBECNÝ KONTEJNER */
    div[data-baseweb="input"] {
        background-color: #e0f2fe !important; /* SVĚTLE MODRÁ */
        border: 2px solid #475569 !important;
        border-radius: 8px !important;
    }

    /* 2a. ČÍSELNÉ INPUTY (Karta zápasu) */
    input[type="number"] {
        background-color: transparent !important;
        color: #000000 !important;
        font-weight: 900 !important;
        font-size: 1.4rem !important;
        text-align: center !important;
        padding-right: 0 !important;
        -webkit-text-fill-color: #000000 !important;
    }

    /* 2b. TEXTOVÉ INPUTY (Login, Registrace) */
    input[type="text"], input[type="password"] {
        background-color: transparent !important;
        color: #000000 !important;       /* Černý text */
        font-weight: 500 !important;
        font-size: 1rem !important;
        -webkit-text-fill-color: #000000 !important;
        caret-color: #000000 !important; /* Černý kurzor */
    }

    /* Focus stavy */
    div[data-baseweb="input"]:focus-within {
        background-color: #ffffff !important;
        border-color: #2563eb !important;
    }

    /* 3. CHECKBOX */
    div[data-testid="stCheckbox"] {
        display: flex;
        justify-content: center;
        align-items: center;
        width: 100%;
    }
    div[data-baseweb="checkbox"] {
        justify-content: center;
    }
    div[data-baseweb="checkbox"] label {
        font-size: 1rem !important;
        font-weight: 600 !important;
        color: #1e293b !important;
        margin-left: 10px;
    }

    /* 4. OSTATNÍ */
    div[data-baseweb="tab-list"] { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
    div[data-baseweb="tab"] { flex: 0 1 auto !important; font-size: 1rem !important; font-weight: 600 !important; }
    div.block-container { background-color: rgba(255, 255, 255, 0.95); padding: 3rem 1rem; border-radius: 16px; max-width: 1200px; }
    .footer-warning { margin-top: 40px; padding: 15px; background-color: #fffbeb; border: 1px solid #fcd34d; color: #92400e; border-radius: 8px; font-size: 0.9em; text-align: center; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

def add_bg_from_local(image_file):
    """
    Přidá obrázek pozadí s průhledným boxem.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    with open(image_file, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
    
    st.markdown(
    f"""
    <style>
    /* 1. HLAVNÍ POZADÍ */
    .stApp {{
        background-image: url(data:image/{"jpg"};base64,{encoded_string.decode()});
        background-size: cover;
        background-position: center;
        background-repeat: no-repeat;
        background-attachment: fixed;
    }}

    /* 2. PRŮHLEDNOST BLOKU */
    div.block-container {{
        background-color: rgba(255, 255, 255, 0.72); 
        padding: 3rem;
        border-radius: 15px;
        border: 1px solid rgba(255, 255, 255, 0.5);
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }}
    header[data-testid="stHeader"] {{ background-color: transparent; }}
    .footer-warning {{ background-color: rgba(255, 243, 205, 0.9); color: #856404 !important; border: 1px solid #ffeeba; }}

    /* 3. VSTUPNÍ POLE (MODRÁ) */
    div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-testid="stSelectbox"] > div > div {{
        background-color: #e8f4f8 !important; border: 1px solid #89cff0 !important; color: black !important; border-radius: 5px !important;
    }}
    button[data-testid="stNumberInputStepDown"], button[data-testid="stNumberInputStepUp"] {{
        background-color: #e8f4f8 !important; border: 1px solid #89cff0 !important; color: black !important;
    }}

    /* 4. CHECKBOXY */
    div[data-baseweb="checkbox"] div {{ background-color: #e8f4f8 !important; border-color: #007bff !important; }}
    div[data-baseweb="checkbox"] div[aria-checked="true"] {{ background-color: #007bff !important; border-color: #007bff !important; }}
    div[data-baseweb="checkbox"] div[aria-checked="true"] svg path {{ stroke: white !important; stroke-width: 3px !important; }}
    div[data-testid="stCheckbox"] label p {{ color: black !important; font-weight: 700 !important; }}

    /* 5. OTAZNÍK (Tooltip) */
    div[data-testid="stTooltipIcon"] {{ color: #004085 !important; }}
    div[data-testid="stTooltipIcon"] svg {{ stroke: #004085 !important; }}

    /* 6. DROPDOWN MENU */
    ul[data-baseweb="menu"] {{ background-color: #ffffff !important; border: 1px solid #89cff0 !important; }}
    li[data-baseweb="option"] {{ color: black !important; background-color: #ffffff !important; }}
    li[data-baseweb="option"]:hover, li[data-baseweb="option"][aria-selected="true"] {{ background-color: #e8f4f8 !important; color: black !important; font-weight: bold; }}
    
    /* 7. TEXTY V INPUTECH */
    input[type="text"], input[type="number"], input[type="password"] {{ color: black !important; font-weight: 500; }}

    /* 8. BOX NEJBLIŽŠÍHO ZÁPASU */
    .next-match-box {{
        background-color: rgba(232, 244, 248, 0.95) !important;
        border-left: 8px solid #007bff !important;
        border: 1px solid #007bff !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
        color: #000 !important; 
        padding: 20px !important;
        text-align: center !important;
    }}

    /* --- NOVÉ ÚPRAVY PRO STATISTIKY --- */

    /* E) CAPTIONS (Popisky pod nadpisy) - Bílá záře místo obdélníku */
    div[data-testid="stCaptionContainer"] {{
        color: #000000 !important;       /* Čistá černá */
        font-weight: 600 !important;     /* Tučnější písmo */
        font-size: 1rem !important;      /* O něco větší */
        /* Trik: Bílý stín kolem písmen zajistí čitelnost bez pozadí */
        text-shadow: 0px 0px 4px rgba(255, 255, 255, 1), 0px 0px 4px rgba(255, 255, 255, 1);
    }}

    /* H) ALERT BOXY (st.info, st.success, atd.) ve statistikách */
    /* Uděláme je více bílé (neprůhledné), aby byl text uvnitř čitelný */
    div[data-testid="stAlert"] {{
        background-color: rgba(255, 255, 255, 0.9) !important;
        border: 1px solid #ccc !important;
        color: #000 !important;
    }}
    /* Vynucení černé barvy pro text a ikony uvnitř alert boxů */
    div[data-testid="stAlert"] p, div[data-testid="stAlert"] svg {{
        color: #000 !important;
        fill: #000 !important;
    }}

    .stApp h1 {{
        text-align: center !important;
    }}
    .stApp h2, .stApp h3 {{
        text-align: left !important;
    }}
    </style>
    """,
    unsafe_allow_html=True
    )


def get_flag(team_name):
    """
    Vrátí HTML pro vlajku týmu.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    iso = FLAGS_ISO.get(team_name)
    if iso:
        return f'<img src="https://flagcdn.com/24x18/{iso}.png" style="vertical-align: middle; height: 16px;">'
    return ""


def get_team_label(team_name):
    """
    Vrátí formátovaný label týmu s vlajkou.
    PŮVODNÍ FUNKCE z tipovacka_12.py
    """
    flag_html = get_flag(team_name)
    return f"{flag_html} {team_name}"
