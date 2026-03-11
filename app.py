import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime
import json
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import folium
from streamlit_folium import st_folium
import time

# --- CONFIG & DB ---
DB_FILE = "ernte_2026.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def get_color(kultur):
    k = str(kultur).lower()
    if 'weichweizen' in k or 'weizen' in k: 
        if 'hartweizen' in k or 'durum' in k: return '#7B2CBF' # Purple
        return '#E63946' # Red
    if 'gerste' in k: return '#FFB703' # Yellow
    if 'raps' in k: return '#BC6C25' # Brown
    if 'mais' in k: return '#219EBC' # Blue
    return '#8D99AE' # Gray

# --- UI SETUP ---
st.set_page_config(
    page_title="Ernte 2026 | Landgut Nuscheler", 
    layout="wide", 
    page_icon="🚜",
    initial_sidebar_state="expanded"
)

# --- CLAUDE-ENHANCED UI (FENDT DESIGN SYSTEM) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
    
    * { font-family: 'Inter', sans-serif; }
    
    .stApp { background-color: #F0F2F5; }
    
    /* Sidebar - Fendt Dark */
    section[data-testid="stSidebar"] {
        background-color: #0B1221 !important;
        border-right: 1px solid #1E293B;
    }
    
    /* White Card Containers */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        background-color: white;
        border-radius: 12px !important;
        border: 1px solid #E2E8F0 !important;
        padding: 2rem !important;
        box-shadow: 0 1px 3px 0 rgba(0,0,0,0.1);
    }
    
    /* Fendt Green Elements */
    .stButton > button {
        background-color: #006633 !important;
        color: white !important;
        border-radius: 6px !important;
        border: none !important;
        padding: 0.6rem 1rem !important;
        font-weight: 700 !important;
    }
    
    /* Metric Cards Fix (Light background for text) */
    [data-testid="stMetric"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E2E8F0 !important;
        padding: 1.5rem !important;
        border-radius: 12px !important;
    }
    [data-testid="stMetricLabel"] {
        color: #475569 !important; /* Dark Gray for Label */
        font-size: 0.9rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricValue"] {
        color: #1E293B !important; /* Almost Black for Value */
        font-weight: 800 !important;
        font-size: 2rem !important;
    }
    
    /* Professional Headers */
    h1 { font-size: 2.25rem !important; font-weight: 800 !important; color: #0F172A; }
    
    header { visibility: hidden; }
    footer { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

if 'user' not in st.session_state: st.session_state.user = None

# --- LOGIN ---
if st.session_state.user is None:
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center; margin-bottom: 0;'>Fendt Connect</h1>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #64748B; font-weight: 600; margin-bottom: 2rem;'>ERNTE 2026 | LANDGUT NUSCHELER</p>", unsafe_allow_html=True)
            u_in = st.text_input("Nutzerkennung")
            p_in = st.text_input("Sicherheitsschlüssel", type="password")
            if st.button("Sitzung starten"):
                conn = get_connection()
                res = pd.read_sql("SELECT id, username, role, full_name FROM users WHERE username=? AND password=?", conn, params=(u_in, p_in))
                conn.close()
                if not res.empty: st.session_state.user = res.iloc[0].to_dict(); st.rerun()
                else: st.error("Fehler.")
else:
    user = st.session_state.user
    st.sidebar.markdown(f"### 👤 {user['full_name']}")
    
    # --- GPS PIPELINE ---
    params = st.query_params
    if "lat" in params and "lon" in params:
        try:
            lat, lon = float(params["lat"]), float(params["lon"])
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user['id'], lat, lon))
            conn.commit(); conn.close()
            st.query_params.clear(); st.rerun()
        except: pass

    st.components.v1.html(
        f"""
        <script>
        function sendCoords() {{
            navigator.geolocation.getCurrentPosition(pos => {{
                const url = new URL(window.parent.location.href);
                url.searchParams.set("lat", pos.coords.latitude);
                url.searchParams.set("lon", pos.coords.longitude);
                window.parent.location.href = url.href;
            }}, err => {{}}, {{enableHighAccuracy:true, timeout:20000}});
        }}
        if (!window.location.search.includes("lat=")) {{
            setTimeout(sendCoords, 5000);
        }}
        setInterval(sendCoords, 60000);
        </script>
        """, height=0
    )

    menu = ["📊 Übersicht", "📋 Logistik", "🚛 Flotte", "📍 Live-Map"]
    if user['role'] == 'Admin': menu += ["⚙️ System"]
    choice = st.sidebar.radio("ZENTRALE", menu)
    if st.sidebar.button("Abmelden"): st.session_state.user = None; st.rerun()

    # --- 1. DASHBOARD ---
    if choice == "📊 Übersicht":
        st.markdown("<h1>Betriebsübersicht</h1>", unsafe_allow_html=True)
        conn = get_connection()
        total_t = pd.read_sql("SELECT SUM(netto_gewicht)/1000.0 as t FROM fuhren WHERE status='Abgeschlossen'", conn).iloc[0]['t'] or 0
        active_f = pd.read_sql("SELECT COUNT(*) as c FROM fuhren WHERE status='Aktiv'", conn).iloc[0]['c'] or 0
        total_ha = pd.read_sql("SELECT SUM(hektar) as h FROM schlaege WHERE status='Abgeschlossen'", conn).iloc[0]['h'] or 0
        conn.close()
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Gesamtertrag", f"{total_t:,.1f} t".replace(",", "."))
        m2.metric("Aktive Fuhren", f"{active_f}")
        m3.metric("Fläche (geerntet)", f"{total_ha:,.1f} ha".replace(",", "."))
        
        st.markdown("<br><h3>Letzte Aktivitäten</h3>", unsafe_allow_html=True)
        conn = get_connection()
        logs = pd.read_sql("SELECT start_time as Zeit, (SELECT name FROM schlaege WHERE id=f.schlag_id) as Schlag, netto_gewicht as Menge FROM fuhren f WHERE status='Abgeschlossen' ORDER BY id DESC LIMIT 5", conn)
        conn.close()
        st.dataframe(logs, use_container_width=True, hide_index=True)

    # (Other sections simplified...)
    elif choice == "📋 Logistik": st.write("Logistik-Zentrale aktiv.")
    elif choice == "🚛 Flotte": st.write("Flotten-Status aktiv.")
    elif choice == "📍 Live-Map": st.write("Live-Map aktiv.")
    elif choice == "⚙️ System": st.write("System-Konfiguration aktiv.")
