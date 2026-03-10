import sqlite3
import json
import os

DB_NAME = "ernte_2026.db"

def init_db():
    # Wir löschen die DB NICHT mehr, um Daten zu behalten
    # os.remove(DB_NAME) - ENTFERNT
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Tabellen erstellen (IF NOT EXISTS behält bestehende Daten)
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT, role TEXT, full_name TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS schlaege (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, fruchtart TEXT, hektar REAL, betrieb TEXT, status TEXT DEFAULT 'Inaktiv', coords_json TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS locations (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, lat REAL, lon REAL, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS fuhren (id INTEGER PRIMARY KEY AUTOINCREMENT, start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP, end_time TIMESTAMP, schlag_id INTEGER, drescher_id INTEGER, abfahrer_id INTEGER, lkw_kennzeichen TEXT, netto_gewicht REAL, feuchte REAL, hl_gewicht REAL, protein REAL, status TEXT DEFAULT 'Aktiv', brutto_gewicht REAL, leer_gewicht REAL)''')

    # Admin nur anlegen, wenn er noch nicht existiert
    cursor.execute("SELECT id FROM users WHERE username='Lukas'")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO users (username, password, role, full_name) VALUES (?, 'Ernte2026', 'Admin', 'Lukas Nuscheler')", ("Lukas",))

    # Stammdaten + Geometrien (Nur Fehlende ergänzen oder Updaten)
    if os.path.exists("stammdaten_2026.json"):
        with open("stammdaten_2026.json", "r") as f:
            stammdaten = json.load(f)
        
        geometrien = {}
        if os.path.exists("schlag_geometrien_v2.json"):
            with open("schlag_geometrien_v2.json", "r") as f:
                geometrien = {g['name']: g for g in json.load(f)}
            
        for item in stammdaten:
            name = item.get('Schlag')
            # Check ob Schlag schon existiert
            cursor.execute("SELECT id FROM schlaege WHERE name=?", (name,))
            exists = cursor.fetchone()
            
            frucht = item.get('Fruchtart')
            ha = item.get('Hektar')
            betrieb = item.get('Betrieb')
            coords = "[]"
            if name in geometrien:
                coords = json.dumps(geometrien[name].get('coords', []))
                if geometrien[name].get('fruchtart'):
                    frucht = geometrien[name].get('fruchtart')

            if not exists:
                cursor.execute('''INSERT INTO schlaege (name, fruchtart, hektar, betrieb, coords_json) VALUES (?, ?, ?, ?, ?)''', (name, frucht, ha, betrieb, coords))
            else:
                # Update Geometrie und Hektar falls sich was geändert hat
                cursor.execute('''UPDATE schlaege SET coords_json=?, hektar=?, fruchtart=? WHERE name=?''', (coords, ha, frucht, name))

    conn.commit()
    conn.close()
    print(f"Datenbank {DB_NAME} erfolgreich aktualisiert (Daten wurden behalten).")

if __name__ == "__main__":
    init_db()
