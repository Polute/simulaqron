import socket
from flask import Flask, render_template, jsonify, request
import json
import sys
from multiprocessing import Process
from flask_cors import CORS
from time import time
import subprocess
import requests

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


ORDERS = []

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
                {"id": "node_alice", "distanceKm": 50}
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
                {"id": "node_alice", "distanceKm": 70},
                {"id": "node_bob", "distanceKm": 40}
            ],
            "parEPR": []
        }
    }
    nodo_info = PORT_NODE_MAP.get(PUERTO, {"id": "node_unknown", "name": "Desconocido", "neighbors": []})

    # --- Auxiliar: obtener puerto a partir del id ---
    def get_port_by_id(node_id: str) -> int:
        for port, info in PORT_NODE_MAP.items():
            if info["id"] == node_id:
                return port
        raise ValueError(f"No se encontró puerto para {node_id}")

    def aplicar_orden(orden, node_info):
        accion = orden["accion"]
        origen_id = node_info["id"]

        print("APLICO ORDEN!!!")

        if accion in ["genera EPR", "generar"]:
            destino_id = orden["destino"]
            origen_port = get_port_by_id(origen_id)
            destino_port = get_port_by_id(destino_id)
            pgen_origen = str(node_info["pgen"])

            print(origen_id, "va a generarEPR con:", destino_id)
            subprocess.run([
                "python", "sender.py",
                origen_id, destino_id,
                str(origen_port), str(destino_port),
                pgen_origen
            ], check=True)

        elif accion in ["recibe EPR"]:
            # Procesa los pares recibidos
            for epr in node_info.get("parEPR", []):
                if epr.get("estado") == "ok":
                    subprocess.run([
                        "python", "receiver.py",
                        json.dumps(epr),
                        json.dumps(node_info)
                    ])
                else:
                    print(f"[RECEIVER] Qubit {epr.get('id')} marcado como fallo, se descarta")

        elif accion in ["purifica", "purificar"]:
            print(f"[{origen_id}] Ejecutando protocolo de purificación...")
            subprocess.run([
                "python", "purify.py",
                json.dumps(node_info)
            ])

        elif accion in ["swap", "swapping"]:
            destinatarios = orden["con"]
            destinatarios_ports = [str(get_port_by_id(n)) for n in destinatarios]
            pswap_origen = str(node_info.get("pswap", 0))
            subprocess.run([
                "python", "swap.py", pswap_origen
            ] + destinatarios + destinatarios_ports)

        else:
            raise ValueError(f"Acción desconocida: {accion}")

    app = Flask(__name__)
    CORS(app)

    @app.route("/")
    def index():
        return render_template("nodo.html", nodo_info=nodo_info)

    @app.route("/info")
    def info():
        return jsonify(nodo_info)

    @app.route("/parEPR/add", methods=["POST"])
    def parEPR_add():
        data = request.get_json()
        print("Datos a actualizar/agregar", data)
        if "vecino" not in data or "t_gen" not in data or "w_gen" not in data:
            return jsonify({"error": "Datos incompletos"}), 400

        pares = nodo_info.setdefault("parEPR", [])
        if pares:
            next_id = max(p["id"] for p in pares) + 1
        else:
            next_id = 1

        estado = "fallo" if str(data["w_gen"]).lower() == "fallo" else "ok"

        nodo_info.setdefault("parEPR", []).append({
            "id": next_id,
            "vecino": data["vecino"],
            "t_gen": data["t_gen"],
            "w_gen": data["w_gen"],
            "estado": estado
        })
        print(nodo_info)
        return jsonify({"status": "added", "parEPR": nodo_info["parEPR"]})

    @app.route("/parEPR/delete", methods=["POST"])
    def parEPR_delete():
        data = request.get_json()
        pair_id = data.get("id")

        if pair_id is None:
            return jsonify({"error": "Falta id"}), 400

        original = len(nodo_info["parEPR"])
        nodo_info["parEPR"] = [p for p in nodo_info["parEPR"] if p["id"] != pair_id]

        if len(nodo_info["parEPR"]) < original:
            return jsonify({"status": "deleted", "parEPR": nodo_info["parEPR"]})

        return jsonify({"error": "ID no encontrado"}), 404

    @app.route("/update", methods=["POST"])
    def update():
        data = request.get_json()

        for key in ["id", "name", "pgen", "pswap", "roles", "neighbors", "parEPR"]:
            if key in data:
                nodo_info[key] = data[key]

        source = data.get("source")
        target = data.get("target")
        distancia = data.get("distanciaKm")
        if source and target and distancia is not None:
            if nodo_info.get("id") == source:
                for v in nodo_info.get("neighbors", []):
                    if v.get("id") == target:
                        v["distanceKm"] = distancia
            if nodo_info.get("id") == target:
                for v in nodo_info.get("neighbors", []):
                    if v.get("id") == source:
                        v["distanceKm"] = distancia

            vecino_id = target if nodo_info["id"] == source else source
            vecino_port = get_port_by_id(vecino_id)
            try:
                requests.post(f"http://localhost:{vecino_port}/update", json=data)
            except Exception as e:
                print(f"Error propagando actualización a {vecino_id}: {e}")

        nodo_info["lastUpdated"] = data.get("lastUpdated", time())
        return jsonify({"status": "ok", "nodo_info": nodo_info})

    @app.route("/mandate", methods=["POST"])
    def receive_mandate():
        global ORDERS
        ORDERS.clear()
        data = request.get_json()

        if isinstance(data, dict):
            for nodo_id, instrucciones in data.items():
                if isinstance(instrucciones, list):
                    for instr in instrucciones:
                        ORDERS.append(instr)
                else:
                    ORDERS.append(instrucciones)
        elif isinstance(data, list):
            for item in data:
                ORDERS.append(item)
        else:
            ORDERS.append(data)

        return jsonify({"status": "ok", "ORDERS": ORDERS})

    @app.route("/orders", methods=["GET"])
    def get_orders():
        global ORDERS
        return jsonify(ORDERS)

    @app.route("/operations", methods=["POST"])
    def operations():
        data = request.get_json()
        print(">>> Orden recibida en /operations:", data)

        if not isinstance(data, dict):
            return jsonify({"error": "Formato inválido"}), 400
        if "accion" not in data:
            return jsonify({"error": "Falta 'accion'"}), 400

        try:
            aplicar_orden(data, nodo_info)
            print(">>> Orden aplicada correctamente")
            return jsonify({"status": "ok", "nodo_info": nodo_info})
        except Exception as e:
            print(">>> Excepción en aplicar_orden:", repr(e))
            return jsonify({"error": str(e)}), 500

    print(f"[SERVIDOR] Inicializando nodo en el puerto {PUERTO}...")
    app.run(host="127.0.0.1", port=PUERTO, debug=True, use_reloader=False)


if __name__ == "__main__":
    # Seleccionar un puerto libre en el rango, excepto 5001
    PUERTO = seleccionar_puerto(5000, 5010, excluir=[5001])
    if PUERTO is None:
        print("[ERROR] No hay puertos disponibles.")
        sys.exit(1)

    proceso = Process(target=app_open, args=(PUERTO,))
    proceso.start()
    proceso.join()
