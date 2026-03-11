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
    
    # --- v15 GPS MEDIC & DIAGNOSE ---
    params = st.query_params
    if "lat" in params and "lon" in params:
        try:
            lat, lon = float(params["lat"]), float(params["lon"])
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user['id'], lat, lon))
            conn.commit(); conn.close()
            st.query_params.clear(); st.rerun()
        except: pass

    # Hidden JS Medic Component
    st.components.v1.html(
        f"""
        <div style="color: gray; font-size: 10px; font-family: sans-serif;" id="status">Suche Satelliten...</div>
        <script>
        function sendCoords() {{
            const status = document.getElementById('status');
            navigator.geolocation.getCurrentPosition(pos => {{
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                status.innerText = "OK: " + lat.toFixed(3) + ", " + lon.toFixed(3);
                const url = new URL(window.parent.location.href);
                url.searchParams.set("lat", lat);
                url.searchParams.set("lon", lon);
                url.searchParams.set("diag", "success");
                window.parent.location.href = url.href;
            }}, err => {{
                status.innerText = "FEHLER: " + err.message + " (Code " + err.code + ")";
                const url = new URL(window.parent.location.href);
                url.searchParams.set("diag_err", err.code);
                window.parent.location.href = url.href;
            }}, {{enableHighAccuracy:true, timeout:10000}});
        }}
        // Initial force trigger on page load
        if (!window.location.search.includes("lat=")) {{
            setTimeout(sendCoords, 3000);
        }}
        </script>
        """, height=30
    )

    if st.sidebar.button("🚨 STANDORT JETZT SENDEN", type="primary", use_container_width=True):
        st.rerun()

    menu = ["🏠 Fuhrenverwaltung", "📋 Fuhrenliste", "🚛 Fahrzeugliste", "📈 Erntefortschritt", "📍 Live-Karte"]
    if user['role'] == 'Admin': menu += ["🗺️ Schlagverwaltung", "👥 Nutzerverwaltung"]
    choice = st.sidebar.radio("Navigation", menu)
    if st.sidebar.button("Abmelden"): st.session_state.user = None; st.rerun()

    # --- 3. FAHRZEUGLISTE (DIAGNOSE MODE) ---
    if choice == "🚛 Fahrzeugliste":
        st.header("🚛 Fahrzeugstatus & Diagnose")
        
        # Test Button for Database Write
        if st.button("🛠️ DB-TEST-PING SENDEN (Simuliert Standort 0,0)"):
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, 0.0, 0.0)", (user['id'],))
            conn.commit(); conn.close()
            st.success("Test-Ping in Datenbank geschrieben! Liste aktualisiert..."); time.sleep(1); st.rerun()

        conn = get_connection()
        query = """
            SELECT u.id, u.full_name as Fahrer, 
            (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Letzter_Kontakt
            FROM users u WHERE u.role != 'Admin'
        """
        df = pd.read_sql(query, conn); conn.close()
        st.dataframe(df, use_container_width=True)
        
        if "diag_err" in params:
            st.error(f"⚠️ DIAGNOSE: Handy meldet Fehler-Code {params['diag_err']}")
            if params['diag_err'] == "1": st.info("Bedeutung: Berechtigung verweigert. Bitte GPS im Browser aktivieren.")
            if params['diag_err'] == "3": st.info("Bedeutung: Zeitüberschreitung. Kein GPS-Empfang oder Handy zu langsam.")

    # --- 5. LIVE-KARTE ---
    elif choice == "📍 Live-Karte":
        st.header("📍 Live-Karte")
        conn = get_connection()
        f_df = pd.read_sql("SELECT name, fruchtart, status, coords_json FROM schlaege", conn)
        loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id WHERE l.id IN (SELECT MAX(id) FROM locations GROUP BY user_id)", conn)
        conn.close()
        m = folium.Map(location=[51.57, 11.73], zoom_start=12, tiles="cartodbpositron")
        # Polygons
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json'])
            if c:
                folium.Polygon(locations=c, color='gray', fill=True, fill_opacity=0.4, popup=r['name']).add_to(m)
        # Latest Positions (Skip 0,0 test pings on map)
        for _, l in loc_df.iterrows():
            if l['lat'] != 0.0:
                folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']} ({l['timestamp']})").add_to(m)
        st_folium(m, width=1200, height=800)

    # (Other sections simplified for now to save space...)
    elif choice == "🏠 Fuhrenverwaltung": st.write("Fuhrenverwaltung aktiv.")
    elif choice == "📋 Fuhrenliste": st.write("Fuhrenliste aktiv.")
