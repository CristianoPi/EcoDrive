from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget, QLabel
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtCore import QUrl, QTimer, pyqtSignal, QObject
from http.server import BaseHTTPRequestHandler, HTTPServer
import plotly.express as px
import pandas as pd
import json
import sys
import threading
import os

class DataUpdater(QObject):
    # DataUpdater è una classe che estende QObject e funge da intermediario per l'aggiornamento dei dati nell'interfaccia utente. 
    # Essa definisce un segnale chiamato data_received, che viene emesso quando nuovi dati vengono ricevuti dal server HTTP. 
    # In questo contesto, DataUpdater consente di gestire la comunicazione tra il server e l'interfaccia utente, 
    # permettendo all'applicazione di reagire agli aggiornamenti dei dati in modo asincrono.

    # Quando i dati vengono ricevuti nel metodo do_POST della classe RequestHandler, 
    # il segnale data_received viene emesso con i dati ricevuti, e questo attiva il metodo update_ui nella classe DataViewer. 
    # Questo metodo aggiorna l'interfaccia utente con i nuovi dati, come la generazione della mappa e l'aggiornamento della label con le informazioni pertinenti.
    data_received = pyqtSignal(dict)

class DataViewer(QMainWindow):
    def __init__(self, server_address=('localhost', 9999)):
        super().__init__()

        # Titolo e dimensioni della finestra
        self.setWindowTitle("Applicazione IoT")
        self.setGeometry(100, 100, 800, 600)

        # Funzionamento UI:
        # - Esiste una finestra pricipale (QMainWindow)
        # - La finestra principale contiene un widget principale (QWidget)
        # - Il widget principale contiene un layout orizzontale (QHBoxLayout)
        # - Il layout orizzontale contiene due componenti: browser (QWebEngineView) e label (QLabel)

        # Inizializzazione dei componenti: browser (mappa) e label (dati)
        self.browser_title = QLabel("Mappa percorso")
        self.browser_title.setStyleSheet("font-size: 24px; font-weight: bold;")
        self.browser_title.setMaximumHeight(60)  
        self.browser = QWebEngineView()

        self.data_title = QLabel("Dati percorso")
        self.data_title.setStyleSheet("font-size: 28px; font-weight: bold; margin-top: 30px")
        self.data_title.setMaximumHeight(60)  
        self.data_label = QLabel("In attesa di dati...")
        self.data_label.setMaximumHeight(90)  
        self.data_label.setStyleSheet("font-size: 15px;")


        # Widget principale
        central_widget = QWidget()

        # Layout orizzontale per browser e label
        layout = QVBoxLayout()

        # Aggiunta dei componenti al layout
        layout.addWidget(self.browser_title)
        layout.addWidget(self.browser)
        layout.addWidget(self.data_title)
        layout.addWidget(self.data_label)

        # Impostazione del layout come layout principale
        central_widget.setLayout(layout)

        # Impostazione del widget principale
        self.setCentralWidget(central_widget)

        # Inizializzazione del data updater
        self.data_updater = DataUpdater()
        self.data_updater.data_received.connect(self.update_ui)

        # Inizializzazione del server
        self.start_server(server_address)

    def start_server(self, server_address):

        # Avvia un server HTTP in un thread separato
        server = HTTPServer(server_address, lambda *args, **kwargs: RequestHandler(self.data_updater, *args, **kwargs))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        print(f"Server in ascolto su {server_address}")

    def update_ui(self, data):
        lat = [float(coord) for coord in data['latitudine']]
        lon = [float(coord) for coord in data['longitudine']]
        self.generate_map(lat, lon)
        self.data_label.setText(f"CO2: {data['co2_media']} ppm\nAccelerazione Media: {data['accelerazione_media']} m/s²\nInizio Sessione: {data['tempo']}")

    def generate_map(self, lat, lon):
        output_html = "map.html"
        df = pd.DataFrame({'Latitudine': lat, 'Longitudine': lon})
        df['Indice'] = df.index
        fig = px.scatter_mapbox(df, 
                                lat='Latitudine', 
                                lon='Longitudine',
                                zoom=9, 
                                mapbox_style="open-street-map", 
                                color='Indice')
        
        # Impostazione dei margini e salvataggio immagine
        fig.update_layout(
            margin=dict(l=0, r=0, t=0, b=0)
        )
        fig.write_html(output_html)

        # Usa un server locale per evitare che la mappa sia bloccata
        local_url = f"http://localhost:8000/{output_html}"
        threading.Thread(target=lambda: os.system(f"python -m http.server 8000"), daemon=True).start()

        # Aggiorna il browser con la mappa
        self.browser.setUrl(QUrl(local_url))


class RequestHandler(BaseHTTPRequestHandler):
    def __init__(self, data_updater, *args, **kwargs):
        self.data_updater = data_updater
        super().__init__(*args, **kwargs)

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data.decode('utf-8'))
            self.data_updater.data_received.emit(data)
            self.send_response(200)
        except:
            self.send_response(400)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({"status": "received"}).encode('utf-8'))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DataViewer()
    window.show()
    sys.exit(app.exec())
