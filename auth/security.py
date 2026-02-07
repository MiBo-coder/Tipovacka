"""
Bezpečnostní modul
Bcrypt + kompatibilita se starými SHA-256 hesly
"""

import streamlit as st
import bcrypt
import hashlib
import time
from datetime import datetime, timedelta
from typing import Tuple, Optional
from utils.config import MAX_LOGIN_ATTEMPTS, LOCKOUT_DURATION, TIMEZONE


def hash_password(password: str) -> str:
    """
    Vytvoří bcrypt hash hesla.
    
    Args:
        password: Heslo v plain textu
        
    Returns:
        Bcrypt hash jako string
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_password(password: str, stored_hash: str) -> bool:
    """
    Ověří heslo proti hashe.
    Podporuje STARÉ SHA-256 hashe (64 znaků) pro zpětnou kompatibilitu.
    
    Args:
        password: Heslo k ověření
        stored_hash: Uložený hash
        
    Returns:
        True pokud heslo odpovídá
    """
    if not stored_hash:
        return False
    
    # Detekce starého SHA-256 hashe (64 znaků, nezačíná $)
    if len(stored_hash) == 64 and not stored_hash.startswith('$'):
        # Starý formát - SHA-256
        sha_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return sha_hash == stored_hash
    
    # Nový bcrypt formát
    try:
        return bcrypt.checkpw(password.encode('utf-8'), stored_hash.encode('utf-8'))
    except (ValueError, AttributeError):
        return False


def check_login_attempts() -> Tuple[bool, Optional[str]]:
    """
    Kontroluje počet neúspěšných pokusů o přihlášení.
    
    Returns:
        (allowed, error_message) - True pokud je přihlášení povoleno
    """
    if 'login_attempts' not in st.session_state:
        st.session_state.login_attempts = 0
        st.session_state.last_attempt_time = None
        st.session_state.lockout_until = None
    
    now = datetime.now(TIMEZONE)
    
    # Kontrola lockoutu
    if st.session_state.get('lockout_until'):
        lockout_end = st.session_state.lockout_until
        if now < lockout_end:
            remaining = (lockout_end - now).seconds // 60
            return False, f"Příliš mnoho pokusů. Zkuste to za {remaining} min."
        else:
            # Lockout vypršel, reset
            st.session_state.login_attempts = 0
            st.session_state.lockout_until = None
    
    # Reset pokusů pokud uplynulo časové okno (5 minut)
    if st.session_state.last_attempt_time:
        time_since_last = (now - st.session_state.last_attempt_time).seconds
        if time_since_last > 300:  # 5 minut
            st.session_state.login_attempts = 0
    
    return True, None


def record_failed_login():
    """Zaznamenává neúspěšný pokus o přihlášení."""
    now = datetime.now(TIMEZONE)
    st.session_state.login_attempts += 1
    st.session_state.last_attempt_time = now
    
    # Exponenciální zpoždění (2s, 4s, 8s, 16s, 32s)
    delay = min(2 ** st.session_state.login_attempts, 32)
    time.sleep(delay)
    
    # Lockout po překročení limitu
    if st.session_state.login_attempts >= MAX_LOGIN_ATTEMPTS:
        st.session_state.lockout_until = now + timedelta(seconds=LOCKOUT_DURATION)


def record_successful_login():
    """Resetuje počítadlo po úspěšném přihlášení."""
    st.session_state.login_attempts = 0
    st.session_state.last_attempt_time = None
    st.session_state.lockout_until = None


def validate_password_strength(password: str) -> Tuple[bool, Optional[str]]:
    """
    Validuje sílu hesla.
    
    Args:
        password: Heslo k ověření
        
    Returns:
        (is_valid, error_message)
    """
    if len(password) < 6:
        return False, "Heslo musí mít alespoň 6 znaků."
    
    if len(password) > 128:
        return False, "Heslo je příliš dlouhé (max 128 znaků)."
    
    return True, None
