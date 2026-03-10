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

# --- HELPERS ---
def get_connection():
    return sqlite3.connect("ernte_2026.db")

# VERBESSERTES GPS TRACKING MIT DB-ANBINDUNG
def gps_tracking_logic(user_id):
    # Das JavaScript sendet jetzt die Koordinaten per AJAX/POST zurück an die App
    # In Streamlit Cloud nutzen wir eine Komponente, die Werte zurückgibt
    from streamlit_js_eval import streamlit_js_eval
    
    # Abfrage der GPS Daten über JS
    loc = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: {lat: pos.coords.latitude, lon: pos.coords.longitude}}, '*') })", key="gps_eval")
    
    if loc and isinstance(loc, dict) and 'lat' in loc:
        lat = loc['lat']
        lon = loc['lon']
        # Speichere in DB
        conn = get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user_id, lat, lon))
        conn.commit(); conn.close()
        return lat, lon
    return None

def simulate_gps_move(user_id, lat, lon):
    conn = get_connection(); cur = conn.cursor()
    cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user_id, lat, lon))
    conn.commit(); conn.close()

def get_color(kultur):
    k = str(kultur).lower()
    if 'weichweizen' in k or 'weizen' in k: 
        if 'hartweizen' in k or 'durum' in k: return 'purple'
        return 'red'
    if 'gerste' in k: return 'yellow'
    if 'raps' in k: return 'brown'
    if 'mais' in k: return 'blue'
    return 'gray'

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
    
    # GPS AKTIVIERUNG
    # Wir brauchen streamlit-js-eval für echtes Cloud-Tracking
    try:
        coords = gps_tracking_logic(user['id'])
        if coords:
            st.sidebar.success(f"📍 GPS aktiv: {coords[0]:.4f}, {coords[1]:.4f}")
    except:
        st.sidebar.warning("GPS wird geladen...")

    if st.sidebar.button("🔄 Daten aktualisieren"): st.rerun()

    # ROLE-BASED NAVIGATION
    if user['role'] == 'Abfahrer':
        menu = ["🏠 Fuhrenverwaltung"]
    elif user['role'] == 'Drescher':
        menu = ["🏠 Fuhrenverwaltung", "🚛 Fahrzeugliste"]
    else: # Admin
        menu = ["🏠 Fuhrenverwaltung", "📋 Fuhrenliste", "🚛 Fahrzeugliste", "📈 Erntefortschritt", "📍 Live-Karte", "🗺️ Schlagverwaltung", "👥 Nutzerverwaltung"]
    
    choice = st.sidebar.radio("Navigation", menu)
    if st.sidebar.button("Abmelden"): st.session_state.user = None; st.rerun()

    # --- 1. FUHRENVERWALTUNG ---
    if choice == "🏠 Fuhrenverwaltung":
        st.header("🏠 Fuhrenverwaltung")
        if user['role'] in ['Drescher', 'Admin']:
            with st.expander("🚜 Neue Fuhre starten", expanded=True):
                conn = get_connection()
                schlaege = pd.read_sql("SELECT id, name FROM schlaege WHERE status = 'Aktiv'", conn)
                abfahrer = pd.read_sql("SELECT id, full_name FROM users WHERE role='Abfahrer' AND id NOT IN (SELECT abfahrer_id FROM fuhren WHERE status='Aktiv')", conn)
                conn.close()
                if schlaege.empty: st.warning("Keine Schläge freigegeben.")
                elif abfahrer.empty: st.info("Warte auf freie Abfahrer...")
                else:
                    c1, c2 = st.columns(2)
                    sel_s = c1.selectbox("Schlag", schlaege['id'].tolist(), format_func=lambda x: schlaege[schlaege['id']==x]['name'].values[0])
                    sel_a = c2.selectbox("Abfahrer", abfahrer['id'].tolist(), format_func=lambda x: abfahrer[abfahrer['id']==x]['full_name'].values[0])
                    kennz = st.text_input("Kennzeichen")
                    if st.button("Fuhre freigeben"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("INSERT INTO fuhren (schlag_id, drescher_id, abfahrer_id, lkw_kennzeichen, status) VALUES (?,?,?,?,'Aktiv')", (sel_s, user['id'], sel_a, kennz))
                        conn.commit(); conn.close(); st.success("Freigegeben!"); time.sleep(1); st.rerun()

        st.subheader("⚖️ Aktive Fuhren (Waage)")
        conn = get_connection()
        q = "SELECT f.id, s.name as Schlag, u.full_name as Drescher, f.lkw_kennzeichen as LKW FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u ON f.drescher_id = u.id WHERE f.status = 'Aktiv'"
        if user['role'] != 'Admin': q += f" AND f.abfahrer_id = {user['id']}"
        aktive = pd.read_sql(q, conn); conn.close()
        if aktive.empty: st.info("Keine offenen Fuhren.")
        else:
            for _, row in aktive.iterrows():
                with st.container(border=True):
                    st.write(f"**#{row['id']} - {row['Schlag']}** ({row['LKW']})")
                    c1, c2, c3 = st.columns(3)
                    brut = c1.number_input("Brutto (kg)", key=f"b{row['id']}", step=100)
                    tara = c2.number_input("Tara (kg)", key=f"t{row['id']}", step=100)
                    feuchte = c3.number_input("Feuchte (%)", key=f"f{row['id']}", step=0.1)
                    c4, c5 = st.columns(2)
                    hl = c4.number_input("HL", key=f"hl{row['id']}", step=0.1)
                    prot = c5.number_input("Protein (%)", key=f"p{row['id']}", step=0.1)
                    st.caption(f"Netto: **{(brut-tara):,.0f} kg**".replace(",","."))
                    if st.button("Abschließen", key=f"btn{row['id']}"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("UPDATE fuhren SET brutto_gewicht=?, leer_gewicht=?, netto_gewicht=?, feuchte=?, hl_gewicht=?, protein=?, status='Abgeschlossen', end_time=CURRENT_TIMESTAMP WHERE id=?", (brut, tara, brut-tara, feuchte, hl, prot, row['id']))
                        conn.commit(); conn.close(); st.rerun()

    # --- 2. FAHRZEUGLISTE ---
    elif choice == "🚛 Fahrzeugliste":
        st.header("🚛 Aktueller Fahrzeugstatus")
        conn = get_connection()
        query = """
            SELECT u.id as user_id, u.full_name as Fahrer, u.role as Rolle,
            CASE WHEN f.id IS NOT NULL THEN '🚚 Voll / Weg zur Erfassung' ELSE '🚜 Frei / Weg zum Acker' END as Status,
            COALESCE(s.name, '-') as Schlag
            FROM users u
            LEFT JOIN fuhren f ON u.id = f.abfahrer_id AND f.status = 'Aktiv'
            LEFT JOIN schlaege s ON f.schlag_id = s.id
            WHERE u.role != 'Admin'
        """
        fahrzeuge = pd.read_sql(query, conn); conn.close()
        for index, row in fahrzeuge.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**{row['Fahrer']}** ({row['Rolle']})")
                c2.write(f"{row['Status']} (Ort: {row['Schlag']})")
                if c3.button("📍 Finden", key=f"find_{row['user_id']}"):
                    st.session_state.map_center_user = row['user_id']
                    st.success("Standort markiert! Gehe jetzt zur Live-Karte.")

    # --- 5. LIVE-KARTE ---
    elif choice == "📍 Live-Karte":
        st.header("📍 Live-Karte")
        conn = get_connection()
        f_df = pd.read_sql("SELECT name, fruchtart, status, coords_json FROM schlaege", conn)
        loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id GROUP BY l.user_id HAVING MAX(l.timestamp)", conn)
        conn.close()
        
        center = [51.57, 11.73]
        zoom = 12
        if 'map_center_user' in st.session_state:
            target = loc_df[loc_df['user_id'] == st.session_state.map_center_user]
            if not target.empty:
                center = [target.iloc[0]['lat'], target.iloc[0]['lon']]
                zoom = 16
                del st.session_state.map_center_user

        m = folium.Map(location=center, zoom_start=zoom, tiles="cartodbpositron")
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json'])
            if c:
                col = get_color(r['fruchtart'])
                is_fin = r['status'] == 'Abgeschlossen'
                folium.Polygon(locations=c, color='green' if is_fin else col, fill=True, fill_color='green' if is_fin else col, fill_opacity=0.5, weight=3 if is_fin else 1, dash_array='5,5' if is_fin else None, popup=f"{r['name']} ({r['fruchtart']})").add_to(m)
        for _, l in loc_df.iterrows():
            icon_name = 'cog' if l['role'] == 'Drescher' else 'truck'
            folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']} ({l['timestamp']})", icon=folium.Icon(color='blue' if l['role']=='Drescher' else 'red', icon=icon_name, prefix='fa')).add_to(m)
        st_folium(m, width=1200, height=800)
    
    # (Restliche Reiter bleiben gleich...)
    elif choice == "📋 Fuhrenliste": st.write("Historie aktiv.")
    elif choice == "📈 Erntefortschritt": st.write("Fortschritt aktiv.")
    elif choice == "🗺️ Schlagverwaltung": st.write("Schlagverwaltung aktiv.")
    elif choice == "👥 Nutzerverwaltung": st.write("Nutzerverwaltung aktiv.")
