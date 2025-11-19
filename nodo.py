import socket
from flask import Flask, render_template, jsonify, request
import json
import sys
from multiprocessing import Process, Manager
from flask_cors import CORS
from time import time


def puerto_disponible(puerto: int) -> bool:
    """Devuelve True si el puerto está libre en localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", puerto)) != 0

def seleccionar_puerto(inicio=5000, fin=5010, excluir=None):
    """
    Recorre los puertos en el rango [inicio, fin].
    Devuelve el primer puerto libre que no esté en 'excluir'.
    """
    excluir = excluir or []
    for puerto in range(inicio, fin + 1):
        if puerto in excluir:
            continue
        if puerto_disponible(puerto):
            print(f"[INFO] Puerto libre encontrado: {puerto}")
            return puerto
    return None

def app_open(PUERTO):
    # Diccionario que mapea puertos a nodos completos
    PORT_NODE_MAP = {
        5000: {
            "id": "node_alice",
            "name": "Alice",
            "x": 100,
            "y": 100,
            "pgen": 0.8,
            "roles": ["emisor", "receptor"],
            "neighbors": [],   # Alice no tiene vecinos iniciales
            "parEPR": []

        },
        5002: {
            "id": "node_bob",
            "name": "Bob",
            "x": 300,
            "y": 100,
            "pgen": 0.7,
            "roles": ["receptor", "repeater"],
            "neighbors": [
                {"name": "Alice", "distanceKm": 50}
            ],
            "parEPR": []

        },
        5003: {
            "id": "node_charlie",
            "name": "Charlie",
            "x": 200,
            "y": 250,
            "pgen": 0.9,
            "roles": ["emisor", "repeater"],
            "neighbors": [
                {"name": "Alice", "distanceKm": 70},
                {"name": "Bob", "distanceKm": 40}
            ],
            "parEPR": []

        }
    }
    nodo_info = PORT_NODE_MAP.get(PUERTO, {"id": "node_unknown", "name": "Desconocido", "neighbors": []})
    app = Flask(__name__)
    CORS(app)  # Esto permite peticiones desde cualquier origen

    # Si quieres restringirlo solo al frontend:
    # CORS(app, resources={r"/*": {"origins": "http://127.0.0.1:8000"}})

    @app.route("/")
    def index():
        return render_template(
                "nodo.html",
                nodo_info=nodo_info
        )
    # Endpoint JSON del estado del nodo
    @app.route("/info")
    def info():
        return jsonify(nodo_info)
    
    # Añadir un nuevo par EPR
    @app.route("/add_parEPR", methods=["POST"])
    def add_parEPR():
        data = request.get_json()
        if "vecino" in data and "t_gen" in data and "w_gen" in data:
            # Asignar ID incremental
            next_id = max([p["id"] for p in nodo_info["parEPR"]] + [0]) + 1
            data["id"] = next_id
            nodo_info["parEPR"].append(data)
            return jsonify({"status": "added", "parEPR": nodo_info["parEPR"]})
        return jsonify({"error": "Datos incompletos"}), 400

    # Eliminar un par EPR por ID
    @app.route("/delete_parEPR/<int:pair_id>", methods=["DELETE"])
    def delete_parEPR(pair_id):
        original = len(nodo_info["parEPR"])
        nodo_info["parEPR"] = [p for p in nodo_info["parEPR"] if p["id"] != pair_id]
        if len(nodo_info["parEPR"]) < original:
            return jsonify({"status": "deleted", "parEPR": nodo_info["parEPR"]})
        return jsonify({"error": "ID no encontrado"}), 404
    
    # Endpoint para actualizar el estado del nodo
    @app.route("/update", methods=["POST"])
    def update():
        data = request.get_json()
        for key in ["id", "name", "pgen", "pswap", "roles", "neighbors", "parEPR"]:
            if key in data:
                nodo_info[key] = data[key]
            # Guardar timestamp de última actualización
        nodo_info["lastUpdated"] = data.get("lastUpdated", time())
        return jsonify({"status": "ok", "nodo_info": nodo_info})
    
    print(f"[SERVIDOR] Inicializando nodo en el puerto {PUERTO}...")
    app.run(host="127.0.0.1", port=PUERTO, debug=True, use_reloader=False) #Quitar debug=True si no estoy en produccion

    
if __name__ == "__main__":
    # Alice en cualquier puerto libre del rango, excepto 5001
    PUERTO = seleccionar_puerto(5000, 5010, excluir=[5001])
    if PUERTO is None:
        print("[ERROR] No hay puertos disponibles para Alice.")
        sys.exit(1)

    
    proceso = Process(target=app_open, args=(PUERTO,))
    proceso.start()
    proceso.join()
