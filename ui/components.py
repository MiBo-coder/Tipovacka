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
    """
    st.markdown("""
<style>
    /* Zvětšení písma */
    html, body, [class*="css"] {
        font-size: 18px !important;
    }
    
    /* MODRÉ INPUTY - AGRESIVNÍ STYL (Oprava pro tvůj požadavek) */
    /* Samotné políčko pro zadávání čísel */
    div[data-testid="stNumberInput"] input {
        background-color: #e8f4f8 !important; 
        color: black !important; 
        font-weight: bold !important;
        border: 1px solid #89cff0 !important;
    }
    /* Celý kontejner inputu */
    div[data-baseweb="input"] {
        background-color: #e8f4f8 !important;
        border: 1px solid #89cff0 !important;
        border-radius: 5px !important;
    }
    /* Selectboxy (rozbalovátka) */
    div[data-baseweb="select"] > div, div[data-testid="stSelectbox"] > div > div {
        background-color: #e8f4f8 !important; 
        border: 1px solid #89cff0 !important; 
        color: black !important;
        border-radius: 5px !important;
    }
    /* Tlačítka +/- u čísel */
    button[data-testid="stNumberInputStepDown"], button[data-testid="stNumberInputStepUp"] {
        background-color: #d1ecf1 !important; 
        color: black !important;
        border: 1px solid #89cff0 !important;
    }

    /* Ostatní styly */
    .exact-match {
        background-color: #ffd700;
        color: black;
        font-weight: bold;
        padding: 4px;
        border-radius: 4px;
    }
    
    .stNumberInput {
        max-width: 150px;
    }
    
    /* Zarovnání tabulek na střed */
    .dataframe { text-align: center !important; }
    th { text-align: center !important; }
    td { text-align: center !important; }
    .stDataFrame { text-align: center !important; }
    
    /* Box pro nejbližší zápas */
    .next-match-box {
        background-color: rgba(232, 244, 248, 0.95) !important;
        border-left: 8px solid #007bff !important;
        border: 1px solid #007bff !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3) !important;
        color: #000 !important; padding: 20px !important;
        margin-bottom: 20px;
    }
    
    /* Patička */
    .footer-warning {
        margin-top: 50px;
        padding: 10px;
        background-color: rgba(255, 243, 205, 0.9);
        border: 1px solid #ffeeba;
        color: #856404;
        border-radius: 5px;
        text-align: center;
        font-size: 0.8em;
    }

    /* Úprava nadpisů */
    .stApp h1 { text-align: center !important; }
    
    /* Checkboxy */
    div[data-testid="stCheckbox"] label p {
        color: black !important;
        font-weight: 600 !important;
    }
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
        color: #000 !important; padding: 20px !important;
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
