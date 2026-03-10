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
from streamlit_js_eval import streamlit_js_eval

DB_FILE = "ernte_2026.db"

# --- AUTO-INITIALIZE DB IF MISSING ---
def init_db_if_missing():
    # If the file is gone because we deleted it from GitHub, we MUST recreate it
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS schlaege (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, fruchtart TEXT, hektar REAL, status TEXT DEFAULT "Inaktiv", coords_json TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, lat REAL, lon REAL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
    cursor.execute('CREATE TABLE IF NOT EXISTS fuhren (id INTEGER PRIMARY KEY AUTOINCREMENT, start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, end_time TIMESTAMP, schlag_id INTEGER, drescher_id INTEGER, abfahrer_id INTEGER, lkw_kennzeichen TEXT, netto_gewicht REAL, feuchte REAL, status TEXT DEFAULT "Aktiv", brutto_gewicht REAL, leer_gewicht REAL)')
    
    # Check for Admin
    cursor.execute("SELECT id FROM users WHERE username='Lukas'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password, role, full_name) VALUES ('Lukas', 'Ernte2026', 'Admin', 'Lukas Nuscheler')")
        cursor.execute("INSERT INTO users (username, password, role, full_name) VALUES ('Benno', 'Ernte2026', 'Abfahrer', 'Benno')")
    
    # Import master data if schlaege table is empty
    cursor.execute("SELECT COUNT(*) FROM schlaege")
    if cursor.fetchone()[0] == 0 and os.path.exists("schlag_geometrien_v2.json"):
        with open("schlag_geometrien_v2.json", "r") as f:
            geos = json.load(f)
            for g in geos:
                cursor.execute("INSERT INTO schlaege (name, fruchtart, hektar, status, coords_json) VALUES (?, ?, ?, 'Aktiv', ?)", (g['name'], g.get('fruchtart','-'), g.get('hektar',0), json.dumps(g.get('coords',[]))))
    conn.commit()
    conn.close()

init_db_if_missing()

def get_connection():
    return sqlite3.connect(DB_FILE)

# --- UI SETUP ---
st.set_page_config(page_title="Ernte 2026 - Landgut Nuscheler", layout="wide")
if 'user' not in st.session_state: st.session_state.user = None

# --- LOGIN ---
if st.session_state.user is None:
    st.title("🌾 Ernte 2026 - Login")
    u_in = st.text_input("Nutzername"); p_in = st.text_input("Passwort", type="password")
    if st.button("Einloggen"):
        conn = get_connection()
        res = pd.read_sql("SELECT id, username, role, full_name FROM users WHERE username=? AND password=?", conn, params=(u_in, p_in))
        conn.close()
        if not res.empty: st.session_state.user = res.iloc[0].to_dict(); st.rerun()
        else: st.error("Nutzername oder Passwort falsch.")
else:
    user = st.session_state.user
    st.sidebar.title(f"Hallo, {user['full_name']}")
    
    # --- GPS SERVICE ---
    loc_res = streamlit_js_eval(
        js_expressions="navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: pos.coords.latitude + ':' + pos.coords.longitude}, '*') }, err => {}, {enableHighAccuracy:true})", 
        key="gps_v14"
    )
    if loc_res and ":" in str(loc_res):
        try:
            lat, lon = str(loc_res).split(":")
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user['id'], float(lat), float(lon)))
            conn.commit(); conn.close()
        except: pass

    if st.sidebar.button("🚨 STANDORT JETZT SENDEN", type="primary", use_container_width=True): st.rerun()
    
    menu = ["🏠 Fuhrenverwaltung", "📋 Fuhrenliste", "🚛 Fahrzeugliste", "📈 Erntefortschritt", "📍 Live-Karte"]
    if user['role'] == 'Admin': menu += ["🗺️ Schlagverwaltung", "👥 Nutzerverwaltung"]
    choice = st.sidebar.radio("Navigation", menu)
    if st.sidebar.button("Abmelden"): st.session_state.user = None; st.rerun()

    # --- 3. FAHRZEUGLISTE ---
    if choice == "🚛 Fahrzeugliste":
        st.header("🚛 Fahrzeugstatus")
        conn = get_connection()
        query = "SELECT u.full_name as Fahrer, (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Letzter_Kontakt FROM users u WHERE u.role != 'Admin'"
        df = pd.read_sql(query, conn); conn.close()
        st.dataframe(df, use_container_width=True)

    # --- 5. LIVE-KARTE ---
    elif choice == "📍 Live-Karte":
        st.header("📍 Live-Karte")
        conn = get_connection()
        f_df = pd.read_sql("SELECT name, fruchtart, status, coords_json FROM schlaege", conn)
        loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id WHERE l.id IN (SELECT MAX(id) FROM locations GROUP BY user_id)", conn)
        conn.close()
        m = folium.Map(location=[51.57, 11.73], zoom_start=12, tiles="cartodbpositron")
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json'])
            if c:
                folium.Polygon(locations=c, color='gray', fill=True, fill_opacity=0.4, popup=r['name']).add_to(m)
        for _, l in loc_df.iterrows():
            folium.Marker([l['lat'], l['lon']], popup=l['full_name']).add_to(m)
        st_folium(m, width=1200, height=800)

    # (Fuhrenverwaltung & Rest logic logic...)
    elif choice == "🏠 Fuhrenverwaltung": st.write("Fuhrenverwaltung aktiv.")
    elif choice == "📋 Fuhrenliste": st.write("Fuhrenliste aktiv.")
