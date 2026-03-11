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
        if 'hartweizen' in k or 'durum' in k: return '#7B2CBF'
        return '#E63946'
    if 'gerste' in k: return '#FFB703'
    if 'raps' in k: return '#BC6C25'
    if 'mais' in k: return '#219EBC'
    return '#8D99AE'

# --- UI SETUP (DARK GRAY THEME) ---
st.set_page_config(page_title="Ernte 2026 | Landgut Nuscheler", layout="wide")

# Custom CSS for Dark Gray Professional Theme
st.markdown("""
    <style>
    /* Main Background Dark Gray */
    .stApp {
        background-color: #0E1117 !important;
        color: #FAFAFA !important;
    }
    
    /* Sidebar Dark */
    section[data-testid="stSidebar"] {
        background-color: #161B22 !important;
    }
    
    /* Text Colors for visibility */
    h1, h2, h3, label, .stMarkdown, p {
        color: #FAFAFA !important;
    }
    
    /* Expander and Containers */
    .stExpander, div[data-testid="stVerticalBlock"] > div[style*="border"] {
        background-color: #1C2128 !important;
        border: 1px solid #30363D !important;
        border-radius: 8px !important;
    }
    
    /* Input Fields */
    .stTextInput input, .stNumberInput input, .stSelectbox div {
        background-color: #0D1117 !important;
        color: white !important;
        border: 1px solid #30363D !important;
    }
    
    /* Tables/Dataframes */
    .stDataFrame {
        background-color: #0D1117 !important;
        border: 1px solid #30363D !important;
    }
    
    /* Buttons */
    .stButton > button {
        background-color: #E63946 !important; /* Action Red like the Screenshot */
        color: white !important;
        border-radius: 6px !important;
    }
    
    /* Sidebar Radio */
    [data-testid="stSidebar"] .stWidget label {
        color: #8B949E !important;
    }
    
    /* Map scaling */
    iframe { border-radius: 12px !important; }
    </style>
    """, unsafe_allow_html=True)

if 'user' not in st.session_state: st.session_state.user = None

# --- LOGIN ---
if st.session_state.user is None:
    st.markdown("<h1 style='text-align: center; margin-top: 5rem;'>🌾 Ernte 2026 - Login</h1>", unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1, 1])
    with col:
        with st.container(border=True):
            u_in = st.text_input("Nutzername")
            p_in = st.text_input("Passwort", type="password")
            if st.button("Einloggen"):
                conn = get_connection()
                res = pd.read_sql("SELECT id, username, role, full_name FROM users WHERE username=? AND password=?", conn, params=(u_in, p_in))
                conn.close()
                if not res.empty: st.session_state.user = res.iloc[0].to_dict(); st.rerun()
                else: st.error("Fehler.")
else:
    user = st.session_state.user
    st.sidebar.title(f"👤 {user['full_name']}")
    
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

    if st.sidebar.button("🚨 STANDORT JETZT SENDEN", type="primary", use_container_width=True): st.rerun()

    menu = ["🏠 Fuhrenverwaltung", "📋 Fuhrenliste", "🚛 Fahrzeugliste", "📈 Erntefortschritt", "📍 Live-Karte", "🗺️ Schlagverwaltung", "👥 Nutzerverwaltung"]
    choice = st.sidebar.radio("Navigation", menu)
    st.sidebar.markdown("---")
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
                if not schlaege.empty and not abfahrer.empty:
                    c1, c2 = st.columns(2)
                    sel_s = c1.selectbox("Schlag", schlaege['id'].tolist(), format_func=lambda x: schlaege[schlaege['id']==x]['name'].values[0])
                    sel_a = c2.selectbox("Abfahrer", abfahrer['id'].tolist(), format_func=lambda x: abfahrer[abfahrer['id']==x]['full_name'].values[0])
                    kennz = st.text_input("LKW Kennzeichen")
                    if st.button("Fuhre freigeben"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("INSERT INTO fuhren (schlag_id, drescher_id, abfahrer_id, lkw_kennzeichen, status) VALUES (?,?,?,?,'Aktiv')", (sel_s, user['id'], sel_a, kennz))
                        conn.commit(); conn.close(); st.success("Freigegeben!"); time.sleep(1); st.rerun()

        st.subheader("⚖️ Aktive Fuhren (Waage)")
        conn = get_connection()
        q = "SELECT f.id, s.name as Schlag, u.full_name as Drescher, f.lkw_kennzeichen as LKW FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u ON f.drescher_id = u.id WHERE f.status = 'Aktiv'"
        if user['role'] != 'Admin': q += f" AND f.abfahrer_id = {user['id']}"
        aktive = pd.read_sql(q, conn); conn.close()
        for _, row in aktive.iterrows():
            with st.container(border=True):
                st.write(f"**#{row['id']} - {row['Schlag']}** | LKW: {row['LKW']}")
                c1, c2, c3 = st.columns(3)
                brut = c1.number_input("Brutto (kg)", key=f"b{row['id']}", step=100); tara = c2.number_input("Tara (kg)", key=f"t{row['id']}", step=100); feuchte = c3.number_input("Feuchte (%)", key=f"f{row['id']}", step=0.1)
                if st.button("Fuhre abschließen", key=f"btn{row['id']}"):
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute("UPDATE fuhren SET brutto_gewicht=?, leer_gewicht=?, netto_gewicht=?, feuchte=?, status='Abgeschlossen', end_time=CURRENT_TIMESTAMP WHERE id=?", (brut, tara, brut-tara, feuchte, row['id']))
                    conn.commit(); conn.close(); st.rerun()

    # --- 2. FUHRENLISTE ---
    elif choice == "📋 Fuhrenliste":
        st.header("📋 Fuhrenhistorie")
        conn = get_connection()
        df = pd.read_sql("SELECT f.id, f.start_time as Datum, s.name as Schlag, s.fruchtart as Kultur, u1.full_name as Drescher, u2.full_name as Abfahrer, f.netto_gewicht as 'Netto (kg)' FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u1 ON f.drescher_id = u1.id JOIN users u2 ON f.abfahrer_id = u2.id WHERE f.status = 'Abgeschlossen' ORDER BY f.start_time DESC", conn)
        st.dataframe(df, use_container_width=True); conn.close()

    # --- 3. FAHRZEUGLISTE ---
    elif choice == "🚛 Fahrzeugliste":
        st.header("🚛 Fahrzeugstatus")
        conn = get_connection()
        query = "SELECT u.full_name as Fahrer, (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Letzter_Kontakt FROM users u WHERE u.role != 'Admin'"
        df = pd.read_sql(query, conn); conn.close()
        st.dataframe(df, use_container_width=True)

    # --- 4. ERNTEFORTSCHRITT ---
    elif choice == "📈 Erntefortschritt":
        st.header("📈 Live Erntefortschritt")
        conn = get_connection()
        t_df = pd.read_sql("SELECT s.fruchtart as Kultur, SUM(f.netto_gewicht)/1000.0 as t FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id WHERE f.status = 'Abgeschlossen' GROUP BY s.fruchtart", conn)
        a_df = pd.read_sql("SELECT fruchtart as Kultur, SUM(hektar) as Gesamt_ha, SUM(CASE WHEN status='Abgeschlossen' THEN hektar ELSE 0 END) as Geerntet_ha FROM schlaege GROUP BY fruchtart", conn)
        m_df = pd.merge(a_df, t_df, on='Kultur', how='left').fillna(0); m_df['Offen_ha'] = m_df['Gesamt_ha'] - m_df['Geerntet_ha']
        st.dataframe(m_df, use_container_width=True); conn.close()

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
                col = get_color(r['fruchtart']); is_fin = r['status'] == 'Abgeschlossen'
                folium.Polygon(locations=c, color='#006633' if is_fin else col, fill=True, fill_color='#006633' if is_fin else col, fill_opacity=0.4, weight=1, popup=r['name']).add_to(m)
        for _, l in loc_df.iterrows():
            if l['lat'] != 0.0:
                folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']} ({l['timestamp']})", icon=folium.Icon(color='red' if l['role']=='Abfahrer' else 'blue', icon='truck' if l['role']=='Abfahrer' else 'cog', prefix='fa')).add_to(m)
        st_folium(m, width=1500, height=800)

    # --- 6. SCHLAGVERWALTUNG ---
    elif choice == "🗺️ Schlagverwaltung":
        st.header("🗺️ Schlagverwaltung")
        conn = get_connection(); df_s = pd.read_sql("SELECT id, name, fruchtart, hektar, status FROM schlaege", conn)
        edited = st.data_editor(df_s, hide_index=True, use_container_width=True)
        if st.button("💾 Speichern"):
            cur = conn.cursor()
            for _, r in edited.iterrows():
                cur.execute("UPDATE schlaege SET status=? WHERE id=?", (r['status'], r['id']))
            conn.commit(); conn.close(); st.success("Gespeichert!"); st.rerun()
        conn.close()

    # --- 7. NUTZERVERWALTUNG ---
    elif choice == "👥 Nutzerverwaltung":
        st.header("👥 Nutzerverwaltung")
        conn = get_connection(); st.table(pd.read_sql("SELECT id, username, full_name, role FROM users", conn)); conn.close()
