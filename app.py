import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import folium
from streamlit_folium import st_folium
import time

# --- CONFIG & DB ---
DB_FILE = "ernte_2026.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

# --- DATABASE INITIALIZATION ---
def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT, logged_in INTEGER DEFAULT 0)")
    cur.execute("CREATE TABLE IF NOT EXISTS schlaege (id INTEGER PRIMARY KEY AUTOINCREMENT, parzellennummer TEXT, name TEXT, fruchtart TEXT, hektar REAL, betrieb TEXT, bio_status TEXT, status TEXT DEFAULT 'Inaktiv', coords_json TEXT DEFAULT '[]')")
    cur.execute("CREATE TABLE IF NOT EXISTS fuhren (id INTEGER PRIMARY KEY AUTOINCREMENT, schlag_id INTEGER, drescher_id INTEGER, abfahrer_id INTEGER, lkw_kennzeichen TEXT, brutto_gewicht REAL, leer_gewicht REAL, netto_gewicht REAL, feuchte REAL, status TEXT, start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, end_time TIMESTAMP)")
    cur.execute("CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, lat REAL, lon REAL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    conn.commit()
    conn.close()

init_db()

def get_color(kultur):
    k = str(kultur).lower()
    if 'weichweizen' in k or 'weizen' in k: 
        if 'hartweizen' in k or 'durum' in k: return '#7B2CBF'
        return '#E63946'
    if 'gerste' in k: return '#FFB703'
    if 'raps' in k: return '#BC6C25'
    if 'mais' in k or 'silomais' in k: return '#219EBC'
    if 'sonnenblume' in k: return '#FFD166'
    if 'soja' in k: return '#06D6A0'
    return '#8D99AE'

# --- UI SETUP ---
st.set_page_config(page_title="Ernte 2026 | Landgut Nuscheler", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .stApp { background-color: #0E1117 !important; color: #FAFAFA !important; }
    button[kind="headerNoPadding"] { background-color: #E63946 !important; color: white !important; border-radius: 50% !important; }
    section[data-testid="stSidebar"] { background-color: #161B22 !important; min-width: 250px !important; }
    h1, h2, h3, label, .stMarkdown, p { color: #FAFAFA !important; }
    .stExpander, div[data-testid="stVerticalBlock"] > div[style*="border"] { background-color: #1C2128 !important; border: 1px solid #30363D !important; border-radius: 8px !important; }
    .stTextInput input, .stNumberInput input, .stSelectbox div { background-color: #0D1117 !important; color: white !important; border: 1px solid #30363D !important; }
    .stDataFrame { background-color: #0D1117 !important; border: 1px solid #30363D !important; }
    .stButton > button { background-color: #E63946 !important; color: white !important; border-radius: 6px !important; }
    .stProgress > div > div > div > div { background-color: #006633 !important; }
    header { visibility: visible !important; background: rgba(14,17,23,0.8); }
    footer { visibility: hidden; }
    .bio-badge { background-color: #2D6A4F; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    .konvi-badge { background-color: #3D405B; color: white; padding: 2px 8px; border-radius: 4px; font-weight: bold; font-size: 0.8rem; }
    .status-card { padding: 1.5rem; border-radius: 12px; text-align: center; margin-bottom: 1.5rem; font-size: 1.2rem; font-weight: bold; box-shadow: 0 4px 6px rgba(0,0,0,0.3); }
    .status-voll { background-color: #E63946; color: white; border: 2px solid #ff4d4d; }
    .status-leer { background-color: #2D6A4F; color: white; border: 2px solid #3db37a; }
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
                if not res.empty: 
                    u_data = res.iloc[0].to_dict()
                    cur = conn.cursor()
                    cur.execute("UPDATE users SET logged_in = 1 WHERE id = ?", (u_data['id'],))
                    conn.commit(); conn.close()
                    st.session_state.user = u_data
                    st.rerun()
                else: 
                    conn.close()
                    st.error("Login fehlgeschlagen.")
else:
    user = st.session_state.user
    conn = get_connection(); conn.cursor().execute("UPDATE users SET logged_in = 1 WHERE id = ?", (user['id'],)); conn.commit(); conn.close()
    st.sidebar.title(f"👤 {user['full_name']}")
    
    st.components.v1.html(f"<script>function sendCoords() {{ navigator.geolocation.getCurrentPosition(pos => {{ const url = new URL(window.parent.location.href); url.searchParams.set('lat', pos.coords.latitude); url.searchParams.set('lon', pos.coords.longitude); window.parent.location.href = url.href; }}, err => {{}}, {{enableHighAccuracy:true, timeout:20000}}); }} if (!window.location.search.includes('lat=')) {{ setTimeout(sendCoords, 5000); }} setInterval(sendCoords, 60000); </script>", height=0)
    params = st.query_params
    if "lat" in params and "lon" in params:
        try:
            lat, lon = float(params["lat"]), float(params["lon"])
            conn = get_connection(); cur = conn.cursor()
            cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user['id'], lat, lon))
            conn.commit(); conn.close()
            st.query_params.clear(); st.rerun()
        except: pass

    menu = ["🚛 Abfahrlogistik", "📋 Fuhrenliste", "🚜 Fahrzeugliste", "📈 Erntefortschritt", "📍 Live-Karte", "🗺️ Schlagverwaltung", "👥 Nutzerverwaltung"]
    choice = st.sidebar.radio("Navigation", menu)
    st.sidebar.markdown("---")
    if st.sidebar.button("Abmelden"): 
        conn = get_connection(); cur = conn.cursor()
        cur.execute("UPDATE users SET logged_in = 0 WHERE id = ?", (user['id'],))
        conn.commit(); conn.close()
        st.session_state.user = None; st.rerun()

    # --- 1. ABFAHRLOGISTIK (MODIFIED) ---
    if choice == "🚛 Abfahrlogistik":
        st.header("🚛 Abfahrlogistik")
        conn = get_connection()
        aktive_query = """
            SELECT f.id, f.schlag_id, f.drescher_id, f.lkw_kennzeichen as LKW,
                   (SELECT name FROM schlaege WHERE id = f.schlag_id) as Schlag,
                   (SELECT fruchtart FROM schlaege WHERE id = f.schlag_id) as fruchtart,
                   (SELECT bio_status FROM schlaege WHERE id = f.schlag_id) as bio_status,
                   (SELECT full_name FROM users WHERE id = f.drescher_id) as Drescher
            FROM fuhren f WHERE f.status = 'Aktiv'
        """
        if user['role'] == 'Abfahrer': aktive_query += f" AND f.abfahrer_id = {user['id']}"
        aktive_fuhren = pd.read_sql(aktive_query, conn); conn.close()

        if user['role'] == 'Abfahrer':
            if not aktive_fuhren.empty:
                sch_name = aktive_fuhren.iloc[0]['Schlag'] if aktive_fuhren.iloc[0]['Schlag'] else "Unbekannter Schlag"
                st.markdown(f'<div class="status-card status-voll">🚚 STATUS: VOLL ZUR WAAGE<br><small>Ladung von Schlag: {sch_name}</small></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="status-card status-leer">🚜 STATUS: LEER ZUM FELD<br><small>Bereit für nächste Beladung</small></div>', unsafe_allow_html=True)

        if user['role'] in ['Drescher', 'Admin']:
            with st.expander("🚜 Neue Fuhre starten", expanded=True):
                conn = get_connection()
                schlaege = pd.read_sql("SELECT id, name, parzellennummer, fruchtart, betrieb, bio_status FROM schlaege WHERE status = 'Aktiv' ORDER BY name ASC", conn)
                abfahrer = pd.read_sql("SELECT id, full_name FROM users WHERE role = 'Abfahrer' AND logged_in = 1 AND id NOT IN (SELECT abfahrer_id FROM fuhren WHERE status = 'Aktiv')", conn)
                conn.close()
                if not schlaege.empty and not abfahrer.empty:
                    c1, c2 = st.columns(2)
                    sel_s = c1.selectbox("Schlag auswählen", schlaege['id'].tolist(), format_func=lambda x: f"{schlaege[schlaege['id']==x]['name'].values[0]} ({schlaege[schlaege['id']==x]['parzellennummer'].values[0]})")
                    s_info = schlaege[schlaege['id'] == sel_s].iloc[0]
                    st.info(f"🌾 Kultur: **{s_info['fruchtart']}** | 🏢 Betrieb: **{s_info['betrieb']}**")
                    if s_info['bio_status'] == 'Ja': st.success("🍀 BIO-FLÄCHE - Trennung beachten!")
                    sel_a = c2.selectbox("Abfahrer (bereit)", abfahrer['id'].tolist(), format_func=lambda x: abfahrer[abfahrer['id']==x]['full_name'].values[0])
                    # LKW Kennzeichen input REMOVED as per request
                    if st.button("Fuhre freigeben"):
                        conn = get_connection(); cur = conn.cursor()
                        # Insert empty string for lkw_kennzeichen to maintain DB compatibility
                        cur.execute("INSERT INTO fuhren (schlag_id, drescher_id, abfahrer_id, lkw_kennzeichen, status) VALUES (?,?,?,?,'Aktiv')", (sel_s, user['id'], sel_a, ""))
                        conn.commit(); conn.close(); st.success("OK!"); time.sleep(1); st.rerun()
                elif schlaege.empty: st.warning("Keine AKTIVEN Schläge.")
                elif abfahrer.empty: st.info("⏸️ Warten auf freie Abfahrer.")

        st.subheader("⚖️ Aktive Fuhren (Waage / Abfahrer)")
        for _, row in aktive_fuhren.iterrows():
            with st.container(border=True):
                is_bio = str(row['bio_status']).lower() == 'ja'
                badge = "<span class='bio-badge'>🍀 BIO</span>" if is_bio else "<span class='konvi-badge'>⚙️ KONVI</span>"
                schlag_disp = row['Schlag'] if row['Schlag'] else "Gelöschter Schlag"
                st.markdown(f"**#{row['id']} - {schlag_disp}** ({row['fruchtart']}) {badge}", unsafe_allow_html=True)
                if user['role'] in ['Admin', 'Abfahrer']:
                    c1, c2, c3 = st.columns(3)
                    # Changed to t (tons) and step 0.01 as per request
                    brut = c1.number_input("Brutto (t)", key=f"b{row['id']}", step=0.01, min_value=0.0, format="%.2f")
                    tara = c2.number_input("Tara (t)", key=f"t{row['id']}", step=0.01, min_value=0.0, format="%.2f")
                    feuchte = c3.number_input("Feuchte (%)", key=f"f{row['id']}", step=0.1)
                    if st.button("Abkippen & Abschließen", key=f"btn{row['id']}"):
                        if brut < tara and brut > 0:
                            st.error("❌ FEHLER: Bruttogewicht darf nicht kleiner als Leergewicht sein!")
                        elif brut == 0:
                            st.warning("⚠️ Bitte Bruttogewicht eingeben.")
                        else:
                            conn = get_connection(); cur = conn.cursor()
                            # Store in kg for DB consistency (t * 1000)
                            cur.execute("UPDATE fuhren SET brutto_gewicht=?, leer_gewicht=?, netto_gewicht=?, feuchte=?, status='Abgeschlossen', end_time=CURRENT_TIMESTAMP WHERE id=?", 
                                       (brut*1000, tara*1000, (brut-tara)*1000, feuchte, row['id']))
                            conn.commit(); conn.close(); st.success("Fuhre abgeschlossen!"); time.sleep(1); st.rerun()

    # --- 3. FAHRZEUGLISTE ---
    elif choice == "🚜 Fahrzeugliste":
        st.header("🚜 Fahrzeugstatus")
        conn = get_connection()
        query = """SELECT u.id, u.full_name as Fahrer, u.role, u.logged_in, (SELECT timestamp FROM locations WHERE user_id = u.id ORDER BY id DESC LIMIT 1) as Kontakt, (SELECT COUNT(*) FROM fuhren WHERE abfahrer_id = u.id AND status = 'Aktiv') as IsVoll FROM users u WHERE u.role != 'Admin'"""
        df = pd.read_sql(query, conn); conn.close()
        df['Registriert'] = df['logged_in'].apply(lambda x: "✅ Online" if x == 1 else "❌ Offline")
        df['Status'] = df['IsVoll'].apply(lambda x: "Voll zur Waage" if x > 0 else "leer zum Feld")
        st.dataframe(df[['Fahrer', 'Registriert', 'Status', 'Kontakt']], use_container_width=True)
        if user['role'] == 'Admin':
            st.markdown("---"); st.subheader("🛠️ Status-Korrektur")
            sel_f = st.selectbox("Fahrer", df['Fahrer'].tolist())
            if st.button("Reset auf LEER"):
                u_id = df[df['Fahrer'] == sel_f]['id'].values[0]
                conn = get_connection(); cur = conn.cursor(); cur.execute("UPDATE fuhren SET status='Abgebrochen' WHERE abfahrer_id=? AND status='Aktiv'", (int(u_id),)); conn.commit(); conn.close(); st.rerun()

    # --- 4. ERNTEFORTSCHRITT ---
    elif choice == "📈 Erntefortschritt":
        st.header("📈 Live Erntefortschritt")
        conn = get_connection()
        t_df = pd.read_sql("SELECT s.fruchtart as Kultur, SUM(f.netto_gewicht)/1000.0 as t FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id WHERE f.status = 'Abgeschlossen' GROUP BY s.fruchtart", conn)
        a_df = pd.read_sql("SELECT fruchtart as Kultur, SUM(hektar) as Gesamt_ha, SUM(CASE WHEN status='Abgeerntet' THEN hektar ELSE 0 END) as Geerntet_ha FROM schlaege GROUP BY fruchtart", conn); conn.close()
        m_df = pd.merge(a_df, t_df, on='Kultur', how='left').fillna(0).sort_values(by='Gesamt_ha', ascending=False)
        total_ha = m_df['Gesamt_ha'].sum(); total_done = m_df['Geerntet_ha'].sum(); total_perc = (total_done / total_ha) if total_ha > 0 else 0
        st.subheader("🌍 Gesamtfortschritt")
        c1, c2, c3 = st.columns([2, 1, 1]); c1.progress(total_perc, text=f"{total_perc*100:.1f}%"); c2.metric("Gesamtfläche", f"{total_ha:.1f} ha"); c3.metric("Abgeerntet", f"{total_done:.1f} ha")
        for _, r in m_df.iterrows():
            with st.container(border=True):
                perc = (r['Geerntet_ha'] / r['Gesamt_ha']) if r['Gesamt_ha'] > 0 else 0
                st.subheader(f"🌾 {r['Kultur']}"); c1, c2, c3 = st.columns([2, 1, 1]); c1.progress(perc, text=f"{perc*100:.1f}%"); c2.metric("Fläche", f"{r['Gesamt_ha']:.1f} ha"); c3.metric("Ertrag", f"{r['t']:.1f} t")

    # (Remaining pages: Fuhrenliste, Schlagverwaltung, Nutzerverwaltung, Live-Karte unchanged)
    elif choice == "📋 Fuhrenliste":
        st.header("📋 Fuhrenhistorie"); conn = get_connection(); df = pd.read_sql("""SELECT f.id, f.start_time as Datum, s.name as Schlag, s.fruchtart as Kultur, s.betrieb as Betrieb, s.bio_status, u1.full_name as Drescher, u2.full_name as Abfahrer, f.netto_gewicht as 'Netto (kg)' FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u1 ON f.drescher_id = u1.id JOIN users u2 ON f.abfahrer_id = u2.id WHERE f.status = 'Abgeschlossen' ORDER BY f.start_time DESC""", conn); conn.close(); df['Typ'] = df['bio_status'].apply(lambda x: "🍀 BIO" if x == 'Ja' else "⚙️ KONVI"); st.dataframe(df, use_container_width=True)
    elif choice == "🗺️ Schlagverwaltung":
        st.header("🗺️ Schlagverwaltung"); 
        with st.expander("📥 Excel-Import"):
            up = st.file_uploader("Excel", type=['xlsx']); 
            if up and st.button("Importieren"):
                df_ex = pd.read_excel(up).dropna(subset=['Parzellennummer']); conn = get_connection(); cur = conn.cursor(); cur.execute("DELETE FROM schlaege")
                for _, r in df_ex.iterrows(): is_bio = 'Ja' if pd.notna(r.get('Bio?')) and str(r.get('Bio?')).lower() == 'x' else 'Nein'; cur.execute("INSERT INTO schlaege (parzellennummer, name, fruchtart, hektar, betrieb, bio_status, status) VALUES (?,?,?,?,?,?,'Inaktiv')", (str(int(r['Parzellennummer'])), str(r['Parzellenname']), str(r['Nutzungsbezeichnung']), float(r['Nettofläche (ha)']), str(r['Bewirtschafter']), is_bio))
                conn.commit(); conn.close(); st.success("OK!"); st.rerun()
        conn = get_connection(); df_s = pd.read_sql("SELECT id, parzellennummer, name, fruchtart, hektar, betrieb, bio_status, status FROM schlaege", conn); df_s['Aktiv'] = df_s['status'] == 'Aktiv'; df_s['Abgeerntet'] = df_s['status'] == 'Abgeerntet'; edited = st.data_editor(df_s, hide_index=True, use_container_width=True, disabled=['id'])
        if st.button("Speichern"):
            cur = conn.cursor()
            for _, r in edited.iterrows(): new_status = 'Abgeerntet' if r['Abgeerntet'] else ('Aktiv' if r['Aktiv'] else 'Inaktiv'); cur.execute("UPDATE schlaege SET parzellennummer=?, name=?, fruchtart=?, hektar=?, betrieb=?, bio_status=?, status=? WHERE id=?", (r['parzellennummer'], r['name'], r['fruchtart'], r['hektar'], r['betrieb'], r['bio_status'], new_status, r['id']))
            conn.commit(); conn.close(); st.success("OK!"); st.rerun()
    elif choice == "👥 Nutzerverwaltung":
        st.header("👥 Nutzerverwaltung"); conn = get_connection(); df_u = pd.read_sql("SELECT id, username, full_name, role, password FROM users", conn); edited_u = st.data_editor(df_u, hide_index=True, use_container_width=True, disabled=['id', 'username'])
        if st.button("Nutzer speichern"):
            cur = conn.cursor(); 
            for _, r in edited_u.iterrows(): cur.execute("UPDATE users SET full_name=?, role=?, password=? WHERE id=?", (r['full_name'], r['role'], r['password'], r['id']))
            conn.commit(); st.success("OK!"); st.rerun()
        with st.expander("➕ Neu"):
            nu = st.text_input("User"); nf = st.text_input("Name"); nr = st.selectbox("Rolle", ["Abfahrer", "Drescher", "Admin"]); np = st.text_input("PWD", value="Ernte2026")
            if st.button("Anlegen"): cur = conn.cursor(); cur.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, ?, ?, ?)", (nu, np, nr, nf)); conn.commit(); st.success("OK!"); st.rerun()
    elif choice == "📍 Live-Karte":
        st.header("📍 Live-Karte"); conn = get_connection(); f_df = pd.read_sql("SELECT name, fruchtart, status, coords_json FROM schlaege", conn); loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id WHERE l.id IN (SELECT MAX(id) FROM locations GROUP BY user_id)", conn); conn.close(); m = folium.Map(location=[51.57, 11.73], zoom_start=12, tiles="cartodbpositron")
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json']) if pd.notna(r.get('coords_json')) and r.get('coords_json') != '' else None
            if c: col = get_color(r['fruchtart']); is_fin = r['status'] == 'Abgeerntet'; folium.Polygon(locations=c, color='#006633' if is_fin else col, fill=True, fill_color='#006633' if is_fin else col, fill_opacity=0.4, weight=1, popup=r['name']).add_to(m)
        for _, l in loc_df.iterrows():
            if l['lat'] != 0.0: folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']} ({l['timestamp']})", icon=folium.Icon(color='red' if l['role']=='Abfahrer' else 'blue', icon='truck' if l['role']=='Abfahrer' else 'cog', prefix='fa')).add_to(m)
        st_folium(m, width=1500, height=800)
