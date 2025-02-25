import requests
import sqlite3
import time
import logging
import signal
import math
from flask import Flask, jsonify
from threading import Thread, Event

app = Flask(__name__)

# URL per recuperare i dati del dispositivo
url = "https://demo.thingsboard.io/api/plugins/telemetry/DEVICE/1c5095e0-ea19-11ef-9dbc-834dadad7dd9/values/timeseries?keys=CO2,accelX,accelY,accelZ,latitude,longitude"
# Header di autorizzazione
headers = {
    "Content-Type": "application/json",
    "X-Authorization": "Bearer eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJQU1RDU1QwMU0zMUMzNTFCQHN0dWRpdW0udW5pY3QuaXQiLCJ1c2VySWQiOiIwYmQyYjM4MC1lYTE3LTExZWYtOWRiYy04MzRkYWRhZDdkZDkiLCJzY29wZXMiOlsiVEVOQU5UX0FETUlOIl0sInNlc3Npb25JZCI6IjcyOGNiNzUzLTZjYzYtNGQ1YS05MTU5LWJhYjNiNjRjNzJjMCIsImV4cCI6MTc0MjAyOTc1OCwiaXNzIjoidGhpbmdzYm9hcmQuaW8iLCJpYXQiOjE3NDAyMjk3NTgsImVuYWJsZWQiOnRydWUsInByaXZhY3lQb2xpY3lBY2NlcHRlZCI6dHJ1ZSwiaXNQdWJsaWMiOmZhbHNlLCJ0ZW5hbnRJZCI6IjBhZGE0OWMwLWVhMTctMTFlZi05ZGJjLTgzNGRhZGFkN2RkOSIsImN1c3RvbWVySWQiOiIxMzgxNDAwMC0xZGQyLTExYjItODA4MC04MDgwODA4MDgwODAifQ.x21BS9__JS5KVU-OouFosLLGvC2PWjnTa3QZRR7NmCJyoD2PVWKOHJ39gk8kN_RFodwVTZpa_N1FyzIVDvR-Ww"
}

# Configurazione del database SQLite
DATABASE = 'driving_sessions.db'

# Configurazione del logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def haversine(lat1, lon1, lat2, lon2):
    # Converti le coordinate da gradi a radianti
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Differenze delle coordinate
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # Formula dell'Haversine
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))

    # Raggio della Terra in metri
    r = 6371000

    # Calcola la distanza
    distance = c * r

    return distance

def CO2_g_per_km(total_co2, distance, duration):
    if distance == 0:
        return 250 # Valore max
    return ((total_co2 * 0.0018 * 0.2) * duration) / (distance / 1000)

def EcoScore(gCO2PerKm, distance, duration, acceleration):
    if duration == 0 or distance == 0:
        return 100  # Punteggio massimo

    velocity = distance / duration
    velocity = velocity * 3.6  # Converti la velocità da m/s a km/h

    temp = 100 - (gCO2PerKm - 100) / 1.5
    p1 = 0
    p2 = 0
    if acceleration >= 3.5:
        p1 = -15
    elif acceleration < 3.5 and acceleration > 2.5:
        p1 = -10
    elif acceleration <= 2.5 and acceleration > 2.0:
        p1 = -5

    if velocity >= 130:
        p2 = -10
    elif velocity < 130 and velocity >= 110:
        p2 = -5

    return temp + p1 + p2

def calculate_total_acceleration(accelX, accelY, accelZ):
    g = 9.81  # Accelerazione di gravità in m/s^2
    Ax = float(accelX) * g
    Ay = float(accelY) * g
    Az = (float(accelZ) + 1) * g
    Atot = (Ax**2 + Ay**2 + Az**2)**0.5
    return Atot

def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (id INTEGER PRIMARY KEY, start_time TEXT, end_time TEXT, total_co2 REAL, duration REAL,
                  total_distance REAL, coordinates TEXT, avg_acceleration REAL, eco_score REAL)''')
    conn.commit()
    conn.close()
    logging.info("Database initialized.")

def insert_session(start_time, end_time, total_co2, duration, total_distance, coordinates, avg_acceleration, eco_score):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (start_time, end_time, total_co2, duration, total_distance, coordinates, avg_acceleration, eco_score) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (start_time, end_time, total_co2, duration, total_distance, coordinates, avg_acceleration, eco_score))
    conn.commit()
    conn.close()
    logging.info(f"Session added to database: start_time={start_time}, end_time={end_time}, total_co2={total_co2}, duration={duration:.2f} minutes, total_distance={total_distance}, coordinates={coordinates}, avg_acceleration={avg_acceleration}, eco_score={eco_score}")

# Cache per memorizzare i dati di CO2
co2_cache = []

# Variabili di stato per la sessione di guida
session_active = False
start_time = None
total_co2 = 0
high_values_count = 0
low_values_count = 0
total_distance = 0
coordinates = []
total_acceleration_values = []
total_acceleration = 0

stop_event = Event()

def get_device_attribute():
    response = requests.get(url, headers=headers)
    logging.info(f"HTTP response status: {response.status_code}")
    logging.info(f"HTTP response text: {response.text}")
    if response.status_code == 200:
        data = response.json()
        logging.info(f"Response JSON: {data}")
        co2 = data.get('CO2', [{}])[0].get('value')
        accelX = data.get('accelX', [{}])[0].get('value')
        accelY = data.get('accelY', [{}])[0].get('value')
        accelZ = data.get('accelZ', [{}])[0].get('value')
        latitude = data.get('latitude', [{}])[0].get('value')
        longitude = data.get('longitude', [{}])[0].get('value')
        if co2 is not None:
            logging.info(f"CO2 value retrieved from ThingsBoard: {co2}")
        else:
            logging.warning("CO2 attribute not found in the response.")
        return co2, accelX, accelY, accelZ, latitude, longitude
    else:
        logging.error(f"Failed to retrieve data: {response.status_code}, {response.text}")
        return None, None, None, None, None, None

def monitor_co2():
    global session_active, start_time, total_co2, high_values_count, low_values_count, total_distance, coordinates, total_acceleration_values

    while not stop_event.is_set():
        co2, accelX, accelY, accelZ, latitude, longitude = get_device_attribute()
        if co2 is not None:
            co2 = float(co2)  # Converti co2 in un numero a virgola mobile
            co2_cache.append(co2)
            if len(co2_cache) > 10:
                co2_cache.pop(0)
            logging.info(f"CO2 cache updated: {co2_cache}")

            if session_active:
                total_co2 += co2 * 22.5
                if len(coordinates) >= 1:
                    last_lat, last_lon = coordinates[-1]
                    distance = haversine(float(last_lat), float(last_lon), float(latitude), float(longitude))
                    total_distance += distance
                coordinates.append((latitude, longitude))
                total_acceleration = calculate_total_acceleration(accelX, accelY, accelZ)
                total_acceleration_values.append(total_acceleration)

                if co2 <= 5:
                    low_values_count += 1
                    if low_values_count >= 15:
                        end_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        duration = time.time() - start_time_timestamp  # durata in secondi
                        avg_acceleration = sum(total_acceleration_values) / len(total_acceleration_values)
                        gCO2PerKm = CO2_g_per_km(total_co2, total_distance, duration)
                        eco_score = EcoScore(gCO2PerKm, total_distance, duration, avg_acceleration)
                        insert_session(start_time, end_time, total_co2, duration, total_distance, str(coordinates), avg_acceleration, eco_score)
                        session_active = False
                        start_time = None
                        total_co2 = 0
                        low_values_count = 0
                        total_distance = 0
                        coordinates = []
                        total_acceleration_values = []
                        logging.info("Session ended.")
                else:
                    low_values_count = 0
            else:
                if co2 > 5:
                    high_values_count += 1
                    if high_values_count >= 3:
                        session_active = True
                        start_time = time.strftime('%Y-%m-%d %H:%M:%S')
                        start_time_timestamp = time.time()  # timestamp per il calcolo della durata
                        total_co2 = co2
                        high_values_count = 0
                        logging.info("Session started.")
                else:
                    high_values_count = 0

        time.sleep(3)

@app.route('/attributes/co2', methods=['GET'])
def attribute_co2():
    return jsonify(co2_cache)

@app.route('/sessions', methods=['GET'])
def get_sessions():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions")
    sessions = c.fetchall()
    conn.close()
    return jsonify(sessions)

@app.route('/view_db', methods=['GET'])
def view_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM sessions")
    sessions = c.fetchall()
    conn.close()
    return jsonify(sessions)

def signal_handler(sig, frame):
    logging.info("Signal received, shutting down...")
    stop_event.set()
    monitoring_thread.join()
    logging.info("Server stopped.")
    exit(0)

if __name__ == "__main__":
    init_db()
    monitoring_thread = Thread(target=monitor_co2)
    monitoring_thread.start()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    app.run(host='0.0.0.0', port=5000)