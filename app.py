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
WHITELIST_DRUSCH = ('Winterweichweizen', 'Wintergerste', 'Sommerweichweizen', 'Winterraps', 'Winterdurum', 'Sonnenblumen', 'Mais', 'Sojabohnen', 'Wintertriticale', 'Sommerdurum', 'Silomais')

def get_connection():
    return sqlite3.connect(DB_FILE)

# --- AUTO-MIGRATE ---
def migrate_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT betrieb FROM schlaege LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE schlaege ADD COLUMN betrieb TEXT DEFAULT 'Unbekannt'")
        conn.commit()
    conn.close()

migrate_db()

def get_color(kultur):
    k = str(kultur).lower()
    if 'weichweizen' in k or 'weizen' in k: 
        if 'hartweizen' in k or 'durum' in k: return '#7B2CBF'
        return '#E63946'
    if 'gerste' in k: return '#FFB703'
    if 'raps' in k: return '#BC6C25'
    if 'mais' in k: return '#219EBC'
    return '#8D99AE'

# --- UI SETUP ---
st.set_page_config(page_title="Ernte 2026 | Landgut Nuscheler", layout="wide")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117 !important; color: #FAFAFA !important; }
    section[data-testid="stSidebar"] { background-color: #161B22 !important; }
    h1, h2, h3, label, .stMarkdown, p { color: #FAFAFA !important; }
    .stExpander, div[data-testid="stVerticalBlock"] > div[style*="border"] { background-color: #1C2128 !important; border: 1px solid #30363D !important; border-radius: 8px !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox div { background-color: #0D1117 !important; color: white !important; border: 1px solid #30363D !important; }
    .stDataFrame { background-color: #0D1117 !important; border: 1px solid #30363D !important; }
    .stButton > button { background-color: #E63946 !important; color: white !important; border-radius: 6px !important; }
    .stProgress > div > div > div > div { background-color: #006633 !important; }
    header { visibility: hidden; }
    footer { visibility: hidden; }
    .bio-badge { background-color: #2D6A4F; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    .konvi-badge { background-color: #3D405B; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
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

    st.components.v1.html(f"<script>function sendCoords() {{ navigator.geolocation.getCurrentPosition(pos => {{ const url = new URL(window.parent.location.href); url.searchParams.set('lat', pos.coords.latitude); url.searchParams.set('lon', pos.coords.longitude); window.parent.location.href = url.href; }}, err => {{}}, {{enableHighAccuracy:true, timeout:20000}}); }} if (!window.location.search.includes('lat=')) {{ setTimeout(sendCoords, 5000); }} setInterval(sendCoords, 60000); </script>", height=0)

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
                placeholders = ','.join(['?'] * len(WHITELIST_DRUSCH))
                schlaege = pd.read_sql(f"SELECT id, name, fruchtart, betrieb FROM schlaege WHERE status = 'Aktiv' AND fruchtart IN ({placeholders})", conn, params=WHITELIST_DRUSCH)
                abfahrer = pd.read_sql("SELECT id, full_name FROM users WHERE role='Abfahrer' AND id NOT IN (SELECT abfahrer_id FROM fuhren WHERE status='Aktiv')", conn)
                conn.close()
                if not schlaege.empty and not abfahrer.empty:
                    c1, c2 = st.columns(2)
                    sel_s = c1.selectbox("Schlag", schlaege['id'].tolist(), format_func=lambda x: schlaege[schlaege['id']==x]['name'].values[0])
                    schlag_data = schlaege[schlaege['id'] == sel_s].iloc[0]
                    kultur = schlag_data['fruchtart']
                    betrieb = schlag_data['betrieb']
                    is_bio = "bio" in str(betrieb).lower()
                    st.info(f"🌾 Kultur: **{kultur}** | 🏢 Betrieb: **{betrieb}**")
                    if is_bio: st.success("🍀 BIO-FLÄCHE - Trennung beachten!")
                    sel_a = c2.selectbox("Freie Abfahrer", abfahrer['id'].tolist(), format_func=lambda x: abfahrer[abfahrer['id']==x]['full_name'].values[0])
                    kennz = st.text_input("LKW Kennzeichen")
                    if st.button("Fuhre freigeben"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("INSERT INTO fuhren (schlag_id, drescher_id, abfahrer_id, lkw_kennzeichen, status) VALUES (?,?,?,?,'Aktiv')", (sel_s, user['id'], sel_a, kennz))
                        conn.commit(); conn.close(); st.success("Freigegeben!"); time.sleep(1); st.rerun()
                elif schlaege.empty: st.warning("Keine aktiven Schläge verfügbar.")
                else: st.info("Warten auf freie Abfahrer.")

        st.subheader("⚖️ Aktive Fuhren (Waage)")
        conn = get_connection()
        q = "SELECT f.id, s.name as Schlag, s.fruchtart, s.betrieb, u.full_name as Drescher, f.lkw_kennzeichen as LKW FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u ON f.drescher_id = u.id WHERE f.status = 'Aktiv'"
        if user['role'] != 'Admin': q += f" AND f.abfahrer_id = {user['id']}"
        aktive = pd.read_sql(q, conn); conn.close()
        for _, row in aktive.iterrows():
            with st.container(border=True):
                is_bio = "bio" in str(row['betrieb']).lower()
                badge = "<span class='bio-badge'>🍀 BIO</span>" if is_bio else "<span class='konvi-badge'>⚙️ KONVI</span>"
                st.markdown(f"**#{row['id']} - {row['Schlag']}** ({row['fruchtart']}) {badge} | LKW: {row['LKW']}", unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                brut = c1.number_input("Brutto (kg)", key=f"b{row['id']}", step=100); tara = c2.number_input("Tara (kg)", key=f"t{row['id']}", step=100); feuchte = c3.number_input("Feuchte (%)", key=f"f{row['id']}", step=0.1)
                if st.button("Fuhre abschließen", key=f"btn{row['id']}"):
                    conn = get_connection(); cur = conn.cursor()
                    cur.execute("UPDATE fuhren SET brutto_gewicht=?, leer_gewicht=?, netto_gewicht=?, feuchte=?, status='Abgeschlossen', end_time=CURRENT_TIMESTAMP WHERE id=?", (brut, tara, brut-tara, feuchte, row['id']))
                    conn.commit(); conn.close(); st.rerun()

    # --- 6. SCHLAGVERWALTUNG ---
    elif choice == "🗺️ Schlagverwaltung":
        st.header("🗺️ Schlagverwaltung")
        conn = get_connection()
        placeholders = ','.join(['?'] * len(WHITELIST_DRUSCH))
        if st.sidebar.button("📏 Schlagdaten & Hektar reparieren"):
            if os.path.exists("stammdaten_2026.json"):
                with open("stammdaten_2026.json", "r") as f:
                    data = json.load(f)
                    cur = conn.cursor()
                    for item in data:
                        cur.execute("UPDATE schlaege SET hektar=?, betrieb=? WHERE name=?", (item.get('Hektar', 0), item.get('Betrieb', '-'), item.get('Schlag')))
                    conn.commit()
                st.sidebar.success("Daten aktualisiert!")
                time.sleep(1); st.rerun()
        df_s = pd.read_sql(f"SELECT id, name, fruchtart, betrieb, hektar, status FROM schlaege WHERE fruchtart IN ({placeholders})", conn, params=WHITELIST_DRUSCH)
        search = st.text_input("🔍 Suche nach Schlagname oder Kultur...", "")
        if search:
            df_s = df_s[df_s['name'].str.contains(search, case=False) | df_s['fruchtart'].str.contains(search, case=False)]
        df_s['Aktiv'] = df_s['status'] == 'Aktiv'
        df_s['Abgeerntet'] = df_s['status'] == 'Abgeerntet'
        edited = st.data_editor(df_s[['id', 'name', 'fruchtart', 'betrieb', 'hektar', 'Aktiv', 'Abgeerntet']], hide_index=True, use_container_width=True, disabled=['id', 'name', 'fruchtart', 'betrieb'])
        if st.button("💾 Alle Änderungen speichern"):
            cur = conn.cursor()
            for _, r in edited.iterrows():
                new_status = 'Abgeerntet' if r['Abgeerntet'] else ('Aktiv' if r['Aktiv'] else 'Inaktiv')
                cur.execute("UPDATE schlaege SET status=?, hektar=? WHERE id=?", (new_status, r['hektar'], r['id']))
            conn.commit(); conn.close(); st.success("Gespeichert!"); time.sleep(1); st.rerun()
        conn.close()

    # --- 7. NUTZERVERWALTUNG ---
    elif choice == "👥 Nutzerverwaltung":
        st.header("👥 Nutzerverwaltung")
        conn = get_connection()
        df_u = pd.read_sql("SELECT id, username, full_name, role, password FROM users", conn)
        edited_u = st.data_editor(df_u, hide_index=True, use_container_width=True, disabled=['id', 'username'])
        if st.button("💾 Nutzer-Daten speichern"):
            cur = conn.cursor()
            for _, r in edited_u.iterrows():
                cur.execute("UPDATE users SET full_name=?, role=?, password=? WHERE id=?", (r['full_name'], r['role'], r['password'], r['id']))
            conn.commit(); st.success("Gespeichert!"); time.sleep(1); st.rerun()
        with st.expander("➕ Neuen Nutzer hinzufügen"):
            nu = st.text_input("Nutzername")
            nf = st.text_input("Vollständiger Name")
            nr = st.selectbox("Rolle", ["Abfahrer", "Drescher", "Admin"])
            np = st.text_input("Passwort festlegen", value="Ernte2026")
            if st.button("Hinzufügen"):
                try:
                    conn.cursor().execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)", (nu, np, nr, nf))
                    conn.commit(); st.success("Angelegt!"); time.sleep(1); st.rerun()
                except: st.error("Fehler.")
        conn.close()

    # --- OTHERS ---
    elif choice == "📋 Fuhrenliste":
        st.header("📋 Fuhrenhistorie"); conn = get_connection(); df = pd.read_sql("SELECT f.id, f.start_time as Datum, s.name as Schlag, s.fruchtart as Kultur, s.betrieb as Betrieb, u1.full_name as Drescher, u2.full_name as Abfahrer, f.netto_gewicht as 'Netto (kg)' FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u1 ON f.drescher_id = u1.id JOIN users u2 ON f.abfahrer_id = u2.id WHERE f.status = 'Abgeschlossen' ORDER BY f.start_time DESC", conn); conn.close(); df['Typ'] = df['Betrieb'].apply(lambda x: "🍀 BIO" if "bio" in str(x).lower() else "⚙️ KONVI"); st.dataframe(df[['id', 'Datum', 'Schlag', 'Kultur', 'Typ', 'Netto (kg)', 'Abfahrer']], use_container_width=True)
    elif choice == "📈 Erntefortschritt":
        st.header("📈 Live Erntefortschritt"); conn = get_connection(); placeholders = ','.join(['?'] * len(WHITELIST_DRUSCH)); t_df = pd.read_sql(f"SELECT s.fruchtart as Kultur, SUM(f.netto_gewicht)/1000.0 as t FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id WHERE f.status = 'Abgeschlossen' AND s.fruchtart IN ({placeholders}) GROUP BY s.fruchtart", conn, params=WHITELIST_DRUSCH); a_df = pd.read_sql(f"SELECT fruchtart as Kultur, SUM(hektar) as Gesamt_ha, SUM(CASE WHEN status='Abgeerntet' THEN hektar ELSE 0 END) as Geerntet_ha FROM schlaege WHERE fruchtart IN ({placeholders}) GROUP BY fruchtart", conn, params=WHITELIST_DRUSCH); conn.close(); m_df = pd.merge(a_df, t_df, on='Kultur', how='left').fillna(0); 
        for _, r in m_df.iterrows():
            with st.container(border=True):
                perc = (r['Geerntet_ha'] / r['Gesamt_ha']) if r['Gesamt_ha'] > 0 else 0; st.subheader(f"🌾 {r['Kultur']}"); c1, c2, c3 = st.columns([2, 1, 1]); c1.progress(perc, text=f"{perc*100:.1f}%"); c2.metric("Geerntet", f"{r['Geerntet_ha']:.1f} ha"); c3.metric("Ertrag (ist)", f"{r['t']:.1f} t"); st.caption(f"Gesamtfläche: {r['Gesamt_ha']:.1f} ha | Offen: {r['Gesamt_ha'] - r['Geerntet_ha']:.1f} ha")
    elif choice == "🚛 Fahrzeugliste":
        st.header("🚛 Fahrzeugstatus"); conn = get_connection(); query = "SELECT u.full_name as Fahrer, (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Letzter_Kontakt FROM users u WHERE u.role != 'Admin'"; df = pd.read_sql(query, conn); conn.close(); st.dataframe(df, use_container_width=True)
    elif choice == "📍 Live-Karte":
        st.header("📍 Live-Karte"); conn = get_connection(); placeholders = ','.join(['?'] * len(WHITELIST_DRUSCH)); f_df = pd.read_sql(f"SELECT name, fruchtart, status, coords_json FROM schlaege WHERE fruchtart IN ({placeholders})", conn, params=WHITELIST_DRUSCH); loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id WHERE l.id IN (SELECT MAX(id) FROM locations GROUP BY user_id)", conn); conn.close(); m = folium.Map(location=[51.57, 11.73], zoom_start=12, tiles="cartodbpositron"); 
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json']); 
            if c: col = get_color(r['fruchtart']); is_fin = r['status'] == 'Abgeerntet'; folium.Polygon(locations=c, color='#006633' if is_fin else col, fill=True, fill_color='#006633' if is_fin else col, fill_opacity=0.4, weight=1, popup=r['name']).add_to(m)
        for _, l in loc_df.iterrows():
            if l['lat'] != 0.0: folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']} ({l['timestamp']})", icon=folium.Icon(color='red' if l['role']=='Abfahrer' else 'blue', icon='truck' if l['role']=='Abfahrer' else 'cog', prefix='fa')).add_to(m)
        st_folium(m, width=1500, height=800)
