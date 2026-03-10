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

# --- DATABASE PROTECTION ---
# If we are in the cloud, we want to keep the data even if app.py is updated
DB_FILE = "ernte_2026.db"

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
        else: st.error("Fehler.")
else:
    user = st.session_state.user
    st.sidebar.title(f"Hallo, {user['full_name']}")
    
    # --- v13 MANUAL & AUTO GPS COMBO ---
    st.sidebar.markdown("### 📍 Standort-Service")
    
    # Big Red Button for Manual Force
    if st.sidebar.button("🚨 STANDORT JETZT SENDEN", type="primary", use_container_width=True):
        st.session_state.trigger_gps = True

    # JS Component for GPS
    loc_res = streamlit_js_eval(
        js_expressions="navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: pos.coords.latitude + ':' + pos.coords.longitude + ':' + Date.now()}, '*') }, err => {}, {enableHighAccuracy:true})", 
        key="gps_v13"
    )

    if loc_res and ":" in str(loc_res):
        try:
            lat, lon, ts = str(loc_res).split(":")
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user['id'], float(lat), float(lon)))
            conn.commit(); conn.close()
        except: pass

    if st.sidebar.button("🔄 Ansicht aktualisieren"): st.rerun()

    menu = ["🏠 Fuhrenverwaltung", "📋 Fuhrenliste", "🚛 Fahrzeugliste", "📈 Erntefortschritt", "📍 Live-Karte"]
    if user['role'] == 'Admin': menu += ["🗺️ Schlagverwaltung", "👥 Nutzerverwaltung"]
    choice = st.sidebar.radio("Navigation", menu)
    if st.sidebar.button("Abmelden"): st.session_state.user = None; st.rerun()

    # --- 3. FAHRZEUGLISTE (WITH DEBUG) ---
    if choice == "🚛 Fahrzeugliste":
        st.header("🚛 Fahrzeugstatus")
        conn = get_connection()
        query = """
            SELECT u.id, u.full_name as Fahrer, 
            (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Letzter_Kontakt,
            CASE WHEN f.id IS NOT NULL THEN '🚚 Voll' ELSE '🚜 Frei' END as Status
            FROM users u
            LEFT JOIN fuhren f ON u.id = f.abfahrer_id AND f.status = 'Aktiv'
            WHERE u.role != 'Admin'
        """
        df = pd.read_sql(query, conn); conn.close()
        st.dataframe(df, use_container_width=True)
        
        st.subheader("🛠️ Debug: Letzte 5 Datenbank-Einträge")
        conn = get_connection()
        debug_df = pd.read_sql("SELECT * FROM locations ORDER BY id DESC LIMIT 5", conn)
        st.table(debug_df); conn.close()

    # --- 5. LIVE-KARTE ---
    elif choice == "📍 Live-Karte":
        st.header("📍 Live-Karte")
        conn = get_connection()
        f_df = pd.read_sql("SELECT name, fruchtart, status, coords_json FROM schlaege", conn)
        loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id WHERE l.id IN (SELECT MAX(id) FROM locations GROUP BY user_id)", conn)
        conn.close()
        
        m = folium.Map(location=[51.57, 11.73], zoom_start=12, tiles="cartodbpositron")
        # (Polygons and Markers remain same...)
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json'])
            if c:
                is_fin = r['status'] == 'Abgeschlossen'
                folium.Polygon(locations=c, color='green' if is_fin else 'gray', fill=True, fill_opacity=0.4).add_to(m)
        for _, l in loc_df.iterrows():
            folium.Marker([l['lat'], l['lon']], popup=l['full_name']).add_to(m)
        st_folium(m, width=1200, height=800)

    # Rest of logic...
