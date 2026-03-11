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
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #F8FAFC !important;
        letter-spacing: -0.02em;
    }
    
    /* Navigation Radio */
    div[data-testid="stSidebarUserContent"] .stWidget label {
        color: #94A3B8 !important;
        font-weight: 600;
        text-transform: uppercase;
        font-size: 0.75rem;
        letter-spacing: 0.05em;
    }
    
    /* Fendt Green Elements */
    .stButton > button {
        background-color: #006633 !important;
        color: white !important;
        border-radius: 6px !important;
        border: none !important;
        padding: 0.6rem 1rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em;
        box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .stButton > button:hover {
        background-color: #004D26 !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1), 0 2px 4px -1px rgba(0,0,0,0.06);
    }
    
    /* Metric Cards - Modern Look */
    [data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #E2E8F0;
        padding: 1.25rem !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 3px 0 rgba(0,0,0,0.1), 0 1px 2px 0 rgba(0,0,0,0.06);
    }
    [data-testid="stMetricValue"] {
        color: #0F172A !important;
        font-weight: 800 !important;
        font-size: 1.875rem !important;
    }
    [data-testid="stMetricLabel"] {
        color: #64748B !important;
        font-weight: 600 !important;
        font-size: 0.875rem !important;
    }
    
    /* White Card Containers */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        background-color: white;
        border-radius: 12px !important;
        border: 1px solid #E2E8F0 !important;
        padding: 2rem !important;
        box-shadow: 0 1px 3px 0 rgba(0,0,0,0.1);
    }
    
    /* Dataframes */
    .stDataFrame {
        border: 1px solid #E2E8F0;
        border-radius: 8px;
    }
    
    /* Professional Headers */
    h1 { font-size: 2.25rem !important; font-weight: 800 !important; color: #0F172A; letter-spacing: -0.025em; }
    h2 { font-size: 1.5rem !important; font-weight: 700 !important; color: #1E293B; }
    h3 { font-size: 1.125rem !important; font-weight: 700 !important; color: #334155; }
    
    /* Hide Header Decorations */
    header { visibility: hidden; }
    footer { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)

if 'user' not in st.session_state: st.session_state.user = None

# --- LOGIN (Fendt Modern Style) ---
if st.session_state.user is None:
    _, col, _ = st.columns([1, 1.5, 1])
    with col:
        st.markdown("<br><br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center; margin-bottom: 0;'>Fendt Connect</h1>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: #64748B; font-weight: 600; margin-bottom: 2rem;'>ERNTE 2026 | LANDGUT NUSCHELER</p>", unsafe_allow_html=True)
            u_in = st.text_input("Nutzerkennung")
            p_in = st.text_input("Sicherheitsschlüssel", type="password")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("Sitzung starten"):
                conn = get_connection()
                res = pd.read_sql("SELECT id, username, role, full_name FROM users WHERE username=? AND password=?", conn, params=(u_in, p_in))
                conn.close()
                if not res.empty: st.session_state.user = res.iloc[0].to_dict(); st.rerun()
                else: st.error("Authentifizierung fehlgeschlagen.")
else:
    user = st.session_state.user
    st.sidebar.markdown(f"### 👤 {user['full_name']}")
    st.sidebar.markdown(f"<span style='color: #94A3B8; font-weight: 600; font-size: 0.75rem;'>RANG: {user['role'].upper()}</span>", unsafe_allow_html=True)
    
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
    st.sidebar.markdown("<br><br><br>", unsafe_allow_html=True)
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
        logs = pd.read_sql("SELECT start_time as Zeit, (SELECT name FROM schlaege WHERE id=f.schlag_id) as Schlag, netto_gewicht as Menge FROM fuhren f WHERE status='Abgeschlossen' ORDER BY id DESC LIMIT 10", conn)
        conn.close()
        st.dataframe(logs, use_container_width=True, hide_index=True)

    # --- 2. LOGISTIK ---
    elif choice == "📋 Logistik":
        st.markdown("<h1>Logistik-Zentrale</h1>", unsafe_allow_html=True)
        if user['role'] in ['Drescher', 'Admin']:
            with st.container(border=True):
                st.subheader("Fuhren-Disposition")
                conn = get_connection()
                schlaege = pd.read_sql("SELECT id, name FROM schlaege WHERE status = 'Aktiv'", conn)
                abfahrer = pd.read_sql("SELECT id, full_name FROM users WHERE role='Abfahrer' AND id NOT IN (SELECT abfahrer_id FROM fuhren WHERE status='Aktiv')", conn)
                conn.close()
                if not schlaege.empty and not abfahrer.empty:
                    c1, c2, c3 = st.columns(3)
                    sel_s = c1.selectbox("Schlag", schlaege['id'].tolist(), format_func=lambda x: schlaege[schlaege['id']==x]['name'].values[0])
                    sel_a = c2.selectbox("Fahrer", abfahrer['id'].tolist(), format_func=lambda x: abfahrer[abfahrer['id']==x]['full_name'].values[0])
                    kennz = c3.text_input("Kennzeichen")
                    if st.button("Fuhre starten"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("INSERT INTO fuhren (schlag_id, drescher_id, abfahrer_id, lkw_kennzeichen, status) VALUES (?,?,?,?,'Aktiv')", (sel_s, user['id'], sel_a, kennz))
                        conn.commit(); conn.close(); st.success("Bestätigt."); time.sleep(1); st.rerun()

        st.markdown("<br><h3>Offene Erfassung</h3>", unsafe_allow_html=True)
        conn = get_connection()
        q = "SELECT f.id, s.name as Schlag, f.lkw_kennzeichen as LKW FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id WHERE f.status = 'Aktiv'"
        if user['role'] != 'Admin': q += f" AND f.abfahrer_id = {user['id']}"
        aktive = pd.read_sql(q, conn); conn.close()
        
        for _, row in aktive.iterrows():
            with st.container(border=True):
                st.markdown(f"**ID {row['id']}** | {row['Schlag']} | {row['LKW']}")
                c1, c2, c3 = st.columns(3)
                brut = c1.number_input("Brutto (kg)", key=f"b{row['id']}", step=100)
                tara = c2.number_input("Tara (kg)", key=f"t{row['id']}", step=100)
                feuchte = c3.number_input("Feuchte (%)", key=f"f{row['id']}", step=0.1)
                if st.button("Abschließen", key=f"btn{row['id']}"):
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute("UPDATE fuhren SET brutto_gewicht=?, leer_gewicht=?, netto_gewicht=?, feuchte=?, status='Abgeschlossen', end_time=CURRENT_TIMESTAMP WHERE id=?", (brut, tara, brut-tara, feuchte, row['id']))
                    conn.commit(); conn.close(); st.rerun()

    # --- 3. FLOTTE ---
    elif choice == "🚛 Flotte":
        st.markdown("<h1>Flotten-Status</h1>", unsafe_allow_html=True)
        conn = get_connection()
        query = """
            SELECT u.full_name as Einheit, 
            (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Letzter_Kontakt,
            CASE WHEN f.id IS NOT NULL THEN 'BELADEN' ELSE 'BEREITSCHAFT' END as Status
            FROM users u
            LEFT JOIN fuhren f ON u.id = f.abfahrer_id AND f.status = 'Aktiv'
            WHERE u.role != 'Admin'
        """
        df = pd.read_sql(query, conn); conn.close()
        st.dataframe(df, use_container_width=True, hide_index=True)

    # --- 4. MAP ---
    elif choice == "📍 Live-Map":
        st.markdown("<h1>Feld- & Positionsdaten</h1>", unsafe_allow_html=True)
        conn = get_connection()
        f_df = pd.read_sql("SELECT name, fruchtart, status, coords_json FROM schlaege", conn)
        loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id WHERE l.id IN (SELECT MAX(id) FROM locations GROUP BY user_id)", conn)
        conn.close()
        m = folium.Map(location=[51.57, 11.73], zoom_start=12, tiles="cartodbpositron")
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json'])
            if c:
                col = get_color(r['fruchtart']); is_fin = r['status'] == 'Abgeschlossen'
                folium.Polygon(locations=c, color='#006633' if is_fin else col, fill=True, fill_color='#006633' if is_fin else col, fill_opacity=0.35, weight=1, popup=r['name']).add_to(m)
        for _, l in loc_df.iterrows():
            if l['lat'] != 0.0:
                folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']}", icon=folium.Icon(color='red' if l['role']=='Abfahrer' else 'blue', icon='truck' if l['role']=='Abfahrer' else 'cog', prefix='fa')).add_to(m)
        st_folium(m, width=1500, height=700)

    # --- 5. SYSTEM ---
    elif choice == "⚙️ System":
        st.markdown("<h1>System-Konfiguration</h1>", unsafe_allow_html=True)
        conn = get_connection(); df_s = pd.read_sql("SELECT id, name, fruchtart, hektar, status FROM schlaege", conn)
        edited = st.data_editor(df_s, hide_index=True, use_container_width=True)
        if st.button("Speichern"):
            cur = conn.cursor()
            for _, r in edited.iterrows():
                cur.execute("UPDATE schlaege SET status=? WHERE id=?", (r['status'], r['id']))
            conn.commit(); conn.close(); st.success("Konfiguration gesichert."); st.rerun()
        conn.close()
