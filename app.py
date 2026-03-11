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

DB_FILE = "ernte_2026.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

def get_color(kultur):
    k = str(kultur).lower()
    if 'weichweizen' in k or 'weizen' in k: return '#E63946' # Red
    if 'gerste' in k: return '#FFB703' # Yellow
    if 'raps' in k: return '#BC6C25' # Brown
    if 'mais' in k: return '#219EBC' # Blue
    if 'durum' in k or 'hartweizen' in k: return '#6A4C93' # Purple
    return '#8D99AE' # Gray

# --- UI SETUP & PROFESSIONAL STYLING ---
st.set_page_config(page_title="Ernte 2026 | Landgut Nuscheler", layout="wide", page_icon="🌾")

# Custom CSS for Fendt-Inspired Look
st.markdown("""
    <style>
    /* Main Background */
    .stApp {
        background-color: #F8F9FA;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background-color: #1B263B !important;
        color: white !important;
    }
    section[data-testid="stSidebar"] .stMarkdown, section[data-testid="stSidebar"] label {
        color: #E0E1DD !important;
    }
    
    /* Headers */
    h1, h2, h3 {
        color: #1B263B;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        font-weight: 700 !important;
    }
    
    /* Cards / Containers */
    div[data-testid="stVerticalBlock"] > div[style*="border"] {
        background-color: white;
        border-radius: 12px !important;
        border: 1px solid #E9ECEF !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        padding: 1.5rem !important;
        margin-bottom: 1rem;
    }
    
    /* Buttons */
    .stButton > button {
        border-radius: 8px !important;
        background-color: #006633 !important; /* Fendt Green */
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        transition: all 0.3s ease;
        width: 100%;
    }
    .stButton > button:hover {
        background-color: #004d26 !important;
        box-shadow: 0 4px 12px rgba(0,102,51,0.2);
    }
    
    /* Metric Cards */
    div[data-testid="stMetricValue"] {
        color: #006633 !important;
        font-weight: 800 !important;
    }
    
    /* Dataframe Styling */
    .stDataFrame {
        border-radius: 10px;
        overflow: hidden;
    }
    
    /* Hide Streamlit elements for cleaner look */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

if 'user' not in st.session_state: st.session_state.user = None

# --- LOGIN ---
if st.session_state.user is None:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<h1 style='text-align: center;'>🚜 Ernte 2026</h1>", unsafe_allow_html=True)
            st.markdown("<p style='text-align: center; color: gray;'>Landgut Nuscheler | Logistik & Tracking</p>", unsafe_allow_html=True)
            u_in = st.text_input("Nutzername")
            p_in = st.text_input("Passwort", type="password")
            if st.button("System Login"):
                conn = get_connection()
                res = pd.read_sql("SELECT id, username, role, full_name FROM users WHERE username=? AND password=?", conn, params=(u_in, p_in))
                conn.close()
                if not res.empty: st.session_state.user = res.iloc[0].to_dict(); st.rerun()
                else: st.error("Zugriff verweigert.")
else:
    user = st.session_state.user
    st.sidebar.markdown(f"### 👤 {user['full_name']}")
    st.sidebar.markdown(f"**Rolle:** {user['role']}")
    
    # --- GPS LOGIC (Silent in Sidebar) ---
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

    menu = ["🏠 Dashboard", "📋 Fuhrenverwaltung", "🚛 Flottenübersicht", "📊 Erntefortschritt", "📍 Live-Karte"]
    if user['role'] == 'Admin': menu += ["👥 System-Verwaltung"]
    choice = st.sidebar.radio("Navigation", menu)
    
    st.sidebar.markdown("---")
    if st.sidebar.button("System Abmelden"): st.session_state.user = None; st.rerun()

    # --- 1. DASHBOARD (NEW) ---
    if choice == "🏠 Dashboard":
        st.title("🏠 Betriebs-Dashboard")
        
        conn = get_connection()
        # Stats
        total_tonnage = pd.read_sql("SELECT SUM(netto_gewicht)/1000.0 as t FROM fuhren WHERE status='Abgeschlossen'", conn).iloc[0]['t'] or 0
        active_fuhren = pd.read_sql("SELECT COUNT(*) as c FROM fuhren WHERE status='Aktiv'", conn).iloc[0]['c'] or 0
        harvested_ha = pd.read_sql("SELECT SUM(hektar) as h FROM schlaege WHERE status='Abgeschlossen'", conn).iloc[0]['h'] or 0
        conn.close()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Gesamtmenge (t)", f"{total_tonnage:,.1f}".replace(",", "."))
        c2.metric("Aktive Fuhren", f"{active_fuhren}")
        c3.metric("Fläche Geerntet (ha)", f"{harvested_ha:,.1f}".replace(",", "."))
        
        st.markdown("### 📋 Letzte Aktivitäten")
        conn = get_connection()
        logs = pd.read_sql("SELECT start_time as Zeit, (SELECT name FROM schlaege WHERE id=f.schlag_id) as Schlag, (SELECT full_name FROM users WHERE id=f.abfahrer_id) as Fahrer, netto_gewicht as Menge FROM fuhren f WHERE status='Abgeschlossen' ORDER BY id DESC LIMIT 5", conn)
        conn.close()
        st.dataframe(logs, use_container_width=True)

    # --- 2. FUHRENVERWALTUNG ---
    elif choice == "📋 Fuhrenverwaltung":
        st.title("📋 Fuhrenverwaltung")
        
        if user['role'] in ['Drescher', 'Admin']:
            with st.container(border=True):
                st.subheader("🚜 Neue Fuhre anlegen")
                conn = get_connection()
                schlaege = pd.read_sql("SELECT id, name FROM schlaege WHERE status = 'Aktiv'", conn)
                abfahrer = pd.read_sql("SELECT id, full_name FROM users WHERE role='Abfahrer' AND id NOT IN (SELECT abfahrer_id FROM fuhren WHERE status='Aktiv')", conn)
                conn.close()
                if not schlaege.empty and not abfahrer.empty:
                    c1, c2, c3 = st.columns(3)
                    sel_s = c1.selectbox("Schlag wählen", schlaege['id'].tolist(), format_func=lambda x: schlaege[schlaege['id']==x]['name'].values[0])
                    sel_a = c2.selectbox("Abfahrer zuweisen", abfahrer['id'].tolist(), format_func=lambda x: abfahrer[abfahrer['id']==x]['full_name'].values[0])
                    kennz = c3.text_input("LKW Kennzeichen")
                    if st.button("Fuhre starten"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("INSERT INTO fuhren (schlag_id, drescher_id, abfahrer_id, lkw_kennzeichen, status) VALUES (?,?,?,?,'Aktiv')", (sel_s, user['id'], sel_a, kennz))
                        conn.commit(); conn.close(); st.success("Fuhre erfolgreich gestartet!"); time.sleep(1); st.rerun()

        st.markdown("### ⚖️ Aktive Wiegevorgänge")
        conn = get_connection()
        q = "SELECT f.id, s.name as Schlag, u.full_name as Drescher, f.lkw_kennzeichen as LKW FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u ON f.drescher_id = u.id WHERE f.status = 'Aktiv'"
        if user['role'] != 'Admin': q += f" AND f.abfahrer_id = {user['id']}"
        aktive = pd.read_sql(q, conn); conn.close()
        
        if aktive.empty: st.info("Momentan keine aktiven Fuhren zur Erfassung.")
        else:
            for _, row in aktive.iterrows():
                with st.container(border=True):
                    st.markdown(f"**Fuhre #{row['id']}** | {row['Schlag']} | LKW: {row['LKW']}")
                    c1, c2, c3 = st.columns(3)
                    brut = c1.number_input("Brutto (kg)", key=f"b{row['id']}", step=100)
                    tara = c2.number_input("Tara (kg)", key=f"t{row['id']}", step=100)
                    feuchte = c3.number_input("Feuchte (%)", key=f"f{row['id']}", step=0.1)
                    if st.button("Fuhre Abschließen", key=f"btn{row['id']}"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("UPDATE fuhren SET brutto_gewicht=?, leer_gewicht=?, netto_gewicht=?, feuchte=?, status='Abgeschlossen', end_time=CURRENT_TIMESTAMP WHERE id=?", (brut, tara, brut-tara, feuchte, row['id']))
                        conn.commit(); conn.close(); st.rerun()

    # --- 3. FLOTTENÜBERSICHT ---
    elif choice == "🚛 Flottenübersicht":
        st.title("🚛 Flottenübersicht")
        conn = get_connection()
        query = """
            SELECT u.full_name as Fahrer, u.role as Rolle, 
            (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Letzter_Kontakt,
            CASE WHEN f.id IS NOT NULL THEN '🚚 Beladen' ELSE '🚜 Leerfahrt/Warten' END as Status
            FROM users u
            LEFT JOIN fuhren f ON u.id = f.abfahrer_id AND f.status = 'Aktiv'
            WHERE u.role != 'Admin'
        """
        df = pd.read_sql(query, conn); conn.close()
        st.dataframe(df, use_container_width=True)

    # --- 4. ERNTEFORTSCHRITT ---
    elif choice == "📊 Erntefortschritt":
        st.title("📊 Erntefortschritt nach Kultur")
        conn = get_connection()
        t_df = pd.read_sql("SELECT s.fruchtart as Kultur, SUM(f.netto_gewicht)/1000.0 as t FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id WHERE f.status = 'Abgeschlossen' GROUP BY s.fruchtart", conn)
        a_df = pd.read_sql("SELECT fruchtart as Kultur, SUM(hektar) as Gesamt_ha, SUM(CASE WHEN status='Abgeschlossen' THEN hektar ELSE 0 END) as Geerntet_ha FROM schlaege GROUP BY fruchtart", conn)
        m_df = pd.merge(a_df, t_df, on='Kultur', how='left').fillna(0)
        m_df['Fortschritt (%)'] = (m_df['Geerntet_ha'] / m_df['Gesamt_ha'] * 100).round(1)
        st.dataframe(m_df, use_container_width=True); conn.close()

    # --- 5. LIVE-KARTE ---
    elif choice == "📍 Live-Karte":
        st.title("📍 Flotten-Live-Karte")
        conn = get_connection()
        f_df = pd.read_sql("SELECT name, fruchtart, status, coords_json FROM schlaege", conn)
        loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id WHERE l.id IN (SELECT MAX(id) FROM locations GROUP BY user_id)", conn)
        conn.close()
        
        m = folium.Map(location=[51.57, 11.73], zoom_start=12, tiles="cartodbpositron")
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json'])
            if c:
                col = get_color(r['fruchtart']); is_fin = r['status'] == 'Abgeschlossen'
                folium.Polygon(locations=c, color='#006633' if is_fin else col, fill=True, fill_color='#006633' if is_fin else col, fill_opacity=0.3, weight=1, popup=r['name']).add_to(m)
        for _, l in loc_df.iterrows():
            if l['lat'] != 0.0:
                folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']} ({l['timestamp']})", icon=folium.Icon(color='red' if l['role']=='Abfahrer' else 'blue', icon='truck' if l['role']=='Abfahrer' else 'cog', prefix='fa')).add_to(m)
        st_folium(m, width=1500, height=700)

    # --- 6. SYSTEM-VERWALTUNG ---
    elif choice == "👥 System-Verwaltung":
        st.title("⚙️ System-Verwaltung")
        tab1, tab2 = st.tabs(["🗺️ Schlag-Status", "👥 Benutzer"])
        with tab1:
            conn = get_connection(); df_s = pd.read_sql("SELECT id, name, fruchtart, hektar, status FROM schlaege", conn)
            edited = st.data_editor(df_s, hide_index=True, use_container_width=True)
            if st.button("Änderungen speichern"):
                cur = conn.cursor()
                for _, r in edited.iterrows():
                    cur.execute("UPDATE schlaege SET status=? WHERE id=?", (r['status'], r['id']))
                conn.commit(); conn.close(); st.success("Erfolgreich aktualisiert!"); st.rerun()
            conn.close()
        with tab2:
            conn = get_connection(); st.table(pd.read_sql("SELECT id, username, full_name, role FROM users", conn)); conn.close()
