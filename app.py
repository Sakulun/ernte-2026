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

def get_color(kultur):
    k = str(kultur).lower()
    if 'weichweizen' in k or 'weizen' in k: 
        if 'hartweizen' in k or 'durum' in k: return 'purple'
        return 'red'
    if 'gerste' in k: return 'yellow'
    if 'raps' in k: return 'brown'
    if 'mais' in k: return 'blue'
    return 'gray'

def send_daily_report():
    conn = get_connection()
    today = datetime.now().strftime('%Y-%m-%d')
    query = """
        SELECT f.id, f.start_time as Datum, s.name as Schlag, s.fruchtart as Kultur, 
               u1.full_name as Drescher, u2.full_name as Abfahrer, f.lkw_kennzeichen as LKW,
               f.netto_gewicht as 'Netto (kg)', f.feuchte as 'H2O (%)', 
               f.hl_gewicht as 'HL', f.protein as 'Prot (%)'
        FROM fuhren f 
        JOIN schlaege s ON f.schlag_id = s.id 
        JOIN users u1 ON f.drescher_id = u1.id 
        JOIN users u2 ON f.abfahrer_id = u2.id 
        WHERE DATE(f.start_time) = ?
    """
    df = pd.read_sql(query, conn, params=(today,))
    conn.close()
    if df.empty: return False
    filename = f"Erntebericht_{today}.xlsx"
    df.to_excel(filename, index=False)
    MAIL_SERVER = "web41.alfahosting-server.de"; MAIL_PORT = 587
    MAIL_USER = "web22347992p105"; MAIL_PASS = "deOvnNet"; MAIL_TO = "lukas@landgut-nuscheler.de"
    msg = MIMEMultipart(); msg['From'] = MAIL_TO; msg['To'] = MAIL_TO; msg['Subject'] = f"Erntebericht - {today}"
    msg.attach(MIMEText(f"Anbei der Erntebericht vom {today}.", 'plain'))
    with open(filename, "rb") as f:
        part = MIMEBase('application', 'octet-stream'); part.set_payload(f.read()); encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {filename}"); msg.attach(part)
    try:
        server = smtplib.SMTP(MAIL_SERVER, MAIL_PORT); server.starttls(); server.login(MAIL_USER, MAIL_PASS)
        server.sendmail(MAIL_TO, MAIL_TO, msg.as_string()); server.quit()
        return True
    except: return False

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
    
    # --- DIAGNOSE GPS (v8.2) ---
    st.components.v1.html(
        f"""
        <script>
        function sendLoc() {{
            if (!navigator.geolocation) {{
                window.parent.postMessage({{type: 'streamlit:setComponentValue', value: 'ERROR_NO_GEO'}}, '*');
                return;
            }}
            navigator.geolocation.getCurrentPosition(
                function(pos) {{
                    const data = {{lat: pos.coords.latitude, lon: pos.coords.longitude, user: {user['id']}}};
                    fetch('/api/gps_update', {{ // Note: This won't work directly in Streamlit but triggers JS logs
                        method: 'POST',
                        body: JSON.stringify(data)
                    }}).catch(e => {{}});
                    // We use the Streamlit message bridge:
                    window.parent.postMessage({{type: 'streamlit:setComponentValue', value: data}}, '*');
                }},
                function(err) {{
                    window.parent.postMessage({{type: 'streamlit:setComponentValue', value: 'ERROR_' + err.code}}, '*');
                }},
                {{enableHighAccuracy: true, timeout: 10000, maximumAge: 0}}
            );
        }}
        // Button in JS to bypass browser interaction block
        document.body.innerHTML = '<button onclick="sendLoc()" style="width:100%; height:40px; background:#ff4b4b; color:white; border:none; border-radius:5px; cursor:pointer;">📍 Standort JETZT senden</button>';
        </script>
        """, height=50
    )
    
    # Handle the value from JS
    if 'gps_data' not in st.session_state: st.session_state.gps_data = None
    
    # Check if a new message from JS arrived (via query params or similar Streamlit tricks)
    # Since we can't easily get value back from components.html in all Cloud versions, 
    # we use the streamlit-js-eval method one more time but with better error handling.
    from streamlit_js_eval import streamlit_js_eval
    
    if st.sidebar.button("🛠️ GPS Diagnose-Scan"):
        res = streamlit_js_eval(js_expressions="navigator.geolocation.getCurrentPosition(pos => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: pos.coords.latitude + ',' + pos.coords.longitude}, '*') }, err => { window.parent.postMessage({type: 'streamlit:setComponentValue', value: 'ERR:' + err.message}, '*') })", key="diag_geo")
        if res:
            if str(res).startswith("ERR:"):
                st.sidebar.error(f"Fehler: {res}")
            else:
                lat, lon = map(float, str(res).split(","))
                conn = get_connection(); cur = conn.cursor()
                cur.execute("INSERT INTO locations (user_id, lat, lon) VALUES (?, ?, ?)", (user['id'], lat, lon))
                conn.commit(); conn.close()
                st.sidebar.success(f"Gefunden: {lat}, {lon}")

    if st.sidebar.button("🔄 Aktualisieren"): st.rerun()

    menu = ["🏠 Fuhrenverwaltung", "📋 Fuhrenliste", "🚛 Fahrzeugliste", "📈 Erntefortschritt", "📍 Live-Karte"]
    if user['role'] == 'Admin': menu += ["🗺️ Schlagverwaltung", "👥 Nutzerverwaltung"]
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
                elif abfahrer.empty: st.info("Keine freien Abfahrer.")
                else:
                    c1, c2 = st.columns(2)
                    sel_s = c1.selectbox("Schlag", schlaege['id'].tolist(), format_func=lambda x: schlaege[schlaege['id']==x]['name'].values[0])
                    sel_a = c2.selectbox("Abfahrer", abfahrer['id'].tolist(), format_func=lambda x: abfahrer[abfahrer['id']==x]['full_name'].values[0])
                    kennz = st.text_input("Kennzeichen")
                    if st.button("Fuhre freigeben"):
                        conn = get_connection(); cur = conn.cursor()
                        cur.execute("INSERT INTO fuhren (schlag_id, drescher_id, abfahrer_id, lkw_kennzeichen, status) VALUES (?,?,?,?,'Aktiv')", (sel_s, user['id'], sel_a, kennz))
                        conn.commit(); conn.close(); st.success("Freigegeben!"); st.rerun()

        st.subheader("⚖️ Aktive Fuhren (Waage)")
        conn = get_connection()
        q = "SELECT f.id, s.name as Schlag, u.full_name as Drescher, f.lkw_kennzeichen as LKW FROM fuhren f JOIN schlaege s ON f.schlag_id = s.id JOIN users u ON f.drescher_id = u.id WHERE f.status = 'Aktiv'"
        if user['role'] != 'Admin': q += f" AND f.abfahrer_id = {user['id']}"
        aktive = pd.read_sql(q, conn); conn.close()
        if aktive.empty: st.info("Keine offenen Fuhren.")
        else:
            for _, row in aktive.iterrows():
                with st.container(border=True):
                    st.write(f"**#{row['id']} - {row['Schlag']}**")
                    c1, c2, c3 = st.columns(3)
                    brut = c1.number_input("Brutto (kg)", key=f"b{row['id']}", step=100)
                    tara = c2.number_input("Tara (kg)", key=f"t{row['id']}", step=100)
                    feuchte = c3.number_input("Feuchte (%)", key=f"f{row['id']}", step=0.1)
                    st.caption(f"Netto: **{(brut-tara):,.0f} kg**".replace(",","."))
                    if st.button("Abschließen", key=f"btn{row['id']}"):
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
        query = """SELECT u.id as user_id, u.full_name as Fahrer, u.role as Rolle, CASE WHEN f.id IS NOT NULL THEN '🚚 Voll' ELSE '🚜 Frei' END as Status, COALESCE(s.name, '-') as Schlag FROM users u LEFT JOIN fuhren f ON u.id = f.abfahrer_id AND f.status = 'Aktiv' LEFT JOIN schlaege s ON f.schlag_id = s.id WHERE u.role != 'Admin'"""
        fahrzeuge = pd.read_sql(query, conn); conn.close()
        for _, row in fahrzeuge.iterrows():
            with st.container(border=True):
                c1, c2, c3 = st.columns([2, 2, 1])
                c1.write(f"**{row['Fahrer']}**"); c2.write(f"{row['Status']} ({row['Schlag']})")
                if c3.button("📍 Finden", key=f"find_{row['user_id']}"): st.session_state.map_center_user = row['user_id']; st.success("Markiert!")

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
        loc_df = pd.read_sql("SELECT l.lat, l.lon, u.full_name, u.role, u.id as user_id, l.timestamp FROM locations l JOIN users u ON l.user_id = u.id GROUP BY l.user_id HAVING MAX(l.timestamp)", conn)
        conn.close()
        center = [51.57, 11.73]; zoom = 12
        if 'map_center_user' in st.session_state:
            target = loc_df[loc_df['user_id'] == st.session_state.map_center_user]
            if not target.empty: center = [target.iloc[0]['lat'], target.iloc[0]['lon']]; zoom = 16
            del st.session_state.map_center_user
        m = folium.Map(location=center, zoom_start=zoom, tiles="cartodbpositron")
        for _, r in f_df.iterrows():
            c = json.loads(r['coords_json'])
            if c:
                col = get_color(r['fruchtart']); is_fin = r['status'] == 'Abgeschlossen'
                folium.Polygon(locations=c, color='green' if is_fin else col, fill=True, fill_color='green' if is_fin else col, fill_opacity=0.5, weight=3 if is_fin else 1, dash_array='5,5' if is_fin else None, popup=f"{r['name']} ({r['fruchtart']})").add_to(m)
        for _, l in loc_df.iterrows():
            icon_name = 'cog' if l['role'] == 'Drescher' else 'truck'
            folium.Marker([l['lat'], l['lon']], popup=f"{l['full_name']} ({l['timestamp']})", icon=folium.Icon(color='blue' if l['role']=='Drescher' else 'red', icon=icon_name, prefix='fa')).add_to(m)
        st_folium(m, width=1200, height=800)

    # --- 6. SCHLAGVERWALTUNG ---
    elif choice == "🗺️ Schlagverwaltung":
        st.header("🗺️ Schlagverwaltung")
        conn = get_connection(); df_s = pd.read_sql("SELECT id, name, fruchtart, hektar, status FROM schlaege", conn)
        search = st.text_input("🔍 Suche...", ""); df_s['Aktiv'] = df_s['status'] == 'Aktiv'; df_s['Abgeschlossen'] = df_s['status'] == 'Abgeschlossen'
        if search: df_s = df_s[df_s['name'].str.contains(search, case=False)]
        edited = st.data_editor(df_s[['id','name','fruchtart','hektar','Aktiv','Abgeschlossen']], disabled=['id','name','fruchtart','hektar'], hide_index=True)
        if st.button("💾 Speichern"):
            cur = conn.cursor()
            for _, r in edited.iterrows():
                ns = 'Abgeschlossen' if r['Abgeschlossen'] else ('Aktiv' if r['Aktiv'] else 'Inaktiv')
                cur.execute("UPDATE schlaege SET status=? WHERE id=?", (ns, r['id']))
            conn.commit(); conn.close(); st.success("Gespeichert!"); st.rerun()
        conn.close()

    # --- 7. NUTZERVERWALTUNG ---
    elif choice == "👥 Nutzerverwaltung":
        st.header("👥 Nutzerverwaltung")
        conn = get_connection(); st.table(pd.read_sql("SELECT id, username, full_name, role FROM users", conn))
        with st.expander("➕ Nutzer anlegen"):
            nu = st.text_input("Login"); nf = st.text_input("Name"); nr = st.selectbox("Rolle", ["Abfahrer", "Drescher", "Admin"])
            if st.button("Hinzufügen"):
                cur = conn.cursor(); cur.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, 'Ernte2026', ?, ?)", (nu, nr, nf))
                conn.commit(); conn.close(); st.success("Angelegt!"); st.rerun()
        if st.button("📧 Bericht senden"):
            if send_daily_report(): st.success("Gesendet!")
            else: st.error("Fehler.")
        conn.close()
