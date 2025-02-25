# %%
import requests
import numpy as np
import sqlite3
import logging

DATABASE = 'driving_sessions.db'
url = "http://127.0.0.1:9999"


def generate_path(start, end, num_points=100):
    latitudes = []
    longitudes = []
    
    # Interpolazione tra il punto di partenza e quello di arrivo
    for t in np.linspace(0, 1, num_points):
        lat = start[0] + t * (end[0] - start[0])
        lon = start[1] + t * (end[1] - start[1])
        latitudes.append(lat)
        longitudes.append(lon)
    
    return latitudes, longitudes

def get_latest_session():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT start_time, end_time, total_co2, duration, total_distance, coordinates, avg_acceleration, eco_score FROM sessions ORDER BY id DESC LIMIT 1")
    session = c.fetchone()
    conn.close()
    return session

# Recupera l'ultima sessione dal database
session = get_latest_session()

if session:
    start_time, end_time, total_co2, duration, total_distance, coordinates, avg_acceleration, eco_score = session
    coordinates = eval(coordinates)  # Converti la stringa in una lista di tuple

    # Costruisci il JSON da inviare
    data = {
        "latitudine": [coord[0] for coord in coordinates],
        "longitudine": [coord[1] for coord in coordinates],
        "co2_media": total_co2,
        "accelerazione_media": avg_acceleration,
        "tempo": start_time
    }

    response = requests.post(url, json=data)
    print(response.json())
else:
    print("No session data found in the database.")
