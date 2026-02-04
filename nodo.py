import socket
from flask import Flask, render_template, jsonify, request, Response
import json
import sys
from multiprocessing import Process
from flask_cors import CORS
from time import time, sleep
import subprocess
import requests
import queue
event_queue = queue.Queue()
import os

def port_available(port: int) -> bool:
    """Returns True if the port is free on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0

def select_port(start=5000, end=5010, exclude=None):
    """
    Iterate through the ports in the range [start, end].
    Returns the first free port that is not in 'exclude'.
    """
    exclude = exclude or []
    for port in range(start, end + 1):
        if port in exclude:
            continue
        if port_available(port):
            print(f"[INFO] Free port found: {port}")
            return port
    return None

def wait_for_listener(port, timeout=5.0, interval=0.01):
    start = time()
    while time() - start < timeout:
        try:
            with socket.create_connection(("localhost", port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError):
            sleep(interval)
    return False
ORDERS = []
# global flag
worker_started = False

def app_open(PUERTO, listener_port):
    # Json that contains all the nodes in the network
    PORT_NODE_MAP = {
        5000: {
            "id": "node_rectorado_upm",
            "name": "Rectorado UPM",
            "lat": 40.448240,
            "lon": -3.717599,
            "pswap": 0.85,
            "roles": ["emisor", "receptor", "repeater"],
            "neighbors": [],
            "pairEPR": []
        },

        5002: {
            "id": "node_cedint_upm",
            "name": "Cedint UPM",
            "lat": 40.4042562,
            "lon": -3.8355074,
            "pswap": 0.90,
            "roles": ["emisor", "receptor", "repeater"],
            "neighbors": [
            { 
                "id": "node_rectorado_upm", 
                "lat": 40.448240, 
                "lon": -3.717599, 
                "distanceKm": 23.3, 
                "pgen": 0.85 
            }
            ],
            "pairEPR": []
        },

        5003: {
            "id": "node_etsiinf_upm",
            "name": "ETSIINF UPM",
            "lat": 40.406194,
            "lon": -3.8390397,
            "pswap": 0.88,
            "roles": ["emisor", "receptor", "repeater"],
            "neighbors": [
            { 
                "id": "node_cedint_upm", 
                "lat": 40.4042562, 
                "lon": -3.8355074, 
                "distanceKm": 1, 
                "pgen": 0.9 
            }
            ],
            "pairEPR": []
        },

        5004: {
            "id": "node_cait_upm",
            "name": "CAIT UPM",
            "lat": 40.4079790,
            "lon": -3.8346741,
            "pswap": 0.92,
            "roles": ["emisor", "receptor"],
            "neighbors": [
            { 
                "id": "node_etsiinf_upm", 
                "lat": 40.406194, 
                "lon": -3.8390397, 
                "distanceKm": 1, 
                "pgen": 0.9 
            }
            ],
            "pairEPR": []
        }
    }

    node_info = PORT_NODE_MAP.get(PUERTO, {"id": "node_unknown", "name": "Desconocido", "neighbors": []})
    print(node_info)

    # --- Auxiliar: obtener puerto a partir del id ---
    def get_port_by_id(node_id: str) -> int:
        for port, info in PORT_NODE_MAP.items():
            if info["id"] == node_id:
                return port
        raise ValueError(f"No se encontró puerto para {node_id}")
    

    def aplicar_orden(orden, node_info):
        global worker_started
        comand = orden["comand"]
        source_id = node_info["id"]
        epr_id = orden.get("id")

        print("APPLYING ORDER!!!")
        print("\n===== DEBUG: FULL pairEPR DUMP =====")
        for e in node_info.get("pairEPR", []):
            print(f"ID: {e.get('id')}")
            for k, v in e.items():
                print(f"   {k}: {v}")
        print("====================================\n")

        # --------------------------------------------------
        # Generate EPR (this node is the sender)
        # --------------------------------------------------
        if comand in ["generate EPR", "generar"]:
            target_id = orden["target"]
            source_port = get_port_by_id(source_id)
            target_port = get_port_by_id(target_id)

            # Find pgen of the neighbor whose id matches target_id
            pgen_source = None
            for neighbor in node_info.get("neighbors", []):
                if neighbor["id"] == target_id:
                    pgen_source = str(neighbor["pgen"])
                    break

            print(source_id, "will generate EPR with:", target_id)

            if not worker_started:
                print("[INFO] Starting worker.py in sender_init mode for the first time")
                print(node_info)
                subprocess.Popen([
                    "python", "worker.py",
                    "sender_init",
                    source_id,             # emitter id
                    target_id,             # receiver id
                    str(source_port),      # my_port (this node)
                    str(target_port),      # target_port (other node)
                    pgen_source,           # pgen
                    str(epr_id),
                    json.dumps(node_info),
                    str(listener_port)
                ])
                worker_started = True
            else:
                print("[INFO] Sender already running, sending order via socket")
                print(f"Using this listener_port {listener_port}")

                payload = {
                    "comand": "generate EPR",
                    "id": epr_id,
                    "source": source_id,
                    "target": target_id,
                    "source_port": source_port,
                    "target_port": target_port,
                    "pgen": pgen_source,
                    "listener_port": listener_port
                }
                if wait_for_listener(listener_port):
                    # Connect to the sender listener and send the order
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect(("localhost", listener_port))
                        s.send(json.dumps(payload).encode())
                        resp = s.recv(4096).decode()
                        print("[SENDER] Response:", resp)

        # --------------------------------------------------
        # Receive EPR (this node receives an EPR created by another node)
        # --------------------------------------------------
        elif comand == "receive EPR":
            epr_id = orden["id"]  # EPR id specified in the order
            timeout = 5.0         # max wait time in seconds
            interval = 0.1        # polling interval
            start = time()
            epr_obj = None

            print("Searching for EPR in node_info['pairEPR']...")
            while time() - start < timeout:
                epr_obj = next(
                    (e for e in node_info.get("pairEPR", []) if str(e["id"]) == str(epr_id)),
                    None
                )
                print("...\n")
                if epr_obj:
                    print(f"[RECEIVER] EPR {epr_id} found")
                    break
                sleep(interval)

            if epr_obj is None:
                print(f"[RECEIVER] Timeout waiting for EPR {epr_id}")
                return

            my_port = get_port_by_id(node_info["id"])
            emisor_port = get_port_by_id(orden["source"])

            print(f"[RECEIVER] Processing EPR {epr_id} between {node_info['id']}:{my_port} "
                f"and {orden['source']}:{emisor_port}")

            if not worker_started:
                print("[INFO] Starting worker.py in receiver_init mode for the first time")
                subprocess.Popen([
                    "python", "worker.py",
                    "receiver_init",
                    json.dumps(epr_obj),
                    json.dumps(node_info),
                    str(my_port),
                    str(emisor_port),
                    str(listener_port)
                ])
                worker_started = True
            else:
                print("[INFO] Receiver already running, sending order via socket")
                payload = {
                    "comand": "receive EPR",
                    "id": epr_id,
                    "source": orden["source"],
                    "epr_obj": epr_obj,
                    "my_port": my_port,
                    "emisor_port": emisor_port,
                    "listener_port": listener_port
                }
                if wait_for_listener(listener_port):
                    # Connect to the receiver listener and send the order
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        print("USING", listener_port)
                        s.connect(("localhost", listener_port))
                        s.send(json.dumps(payload).encode())
                        resp = s.recv(4096).decode()
                        print("[RECEIVER] Response:", resp)

        # --------------------------------------------------
        # Purification protocol
        # --------------------------------------------------
        elif comand in ["purify", "purificar"]:
            print(f"[{source_id}] Running purification protocol...")
            my_port = get_port_by_id(node_info["id"])
            emisor_port = get_port_by_id(orden["with"])   # node with which we purify
            subprocess.run([
                "python", "purify.py",
                json.dumps(node_info),
                str(epr_id),
                str(my_port),
                str(emisor_port)
            ], check=True)

        # --------------------------------------------------
        # Swapping protocol
        # --------------------------------------------------
        elif comand in ["swap", "swapping"]:
            print(f"[{source_id}] Running swapping protocol...")
            payload = {
                "comand": "do swapping",
                "id": epr_id,
                "source": node_info["id"],
                "destinatarios": orden["with"],
                "destinatarios_ports": [str(get_port_by_id(n)) for n in orden["with"]],
                "pswap": str(node_info.get("pswap", 1)),
                "listener_port": listener_port,
                "ports_involved": [str(get_port_by_id(n) + 4000) for n in orden["with"]]
            }
            if wait_for_listener(listener_port):
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.connect(("localhost", listener_port))
                    s.send(json.dumps(payload).encode())
                    resp = s.recv(4096).decode()
                    print("[RECEIVER] Response:", resp)

        # --------------------------------------------------
        # Swap received (just logs for now)
        # --------------------------------------------------
        elif comand in ["received swap"]:
            print("Swap attempt between:", orden["with"])

        else:
            raise ValueError(f"Unknown action: {comand}")


    app = Flask(__name__)
    CORS(app)

    @app.route("/")
    def index():
        print(node_info)
        return render_template("nodo.html", node_info=node_info)

    @app.route("/info")
    def info():
        return jsonify(node_info), 200, {"Connection": "close"}

    @app.route("/pairEPR/add", methods=["POST"])
    def pairEPR_add():
        data = request.get_json()
        pares = node_info.setdefault("pairEPR", [])
        epr_id = data.get("id") or (max((p["id"] for p in pares), default=0) + 1)

        print(f"ESTO MANDO SENDER: {data}")

        state = "fallo" if float(data["w_gen"]) == 0.0 else "ok"


        nuevo_epr = {
            "id": epr_id,
            "neighbor": data["neighbor"],
            "t_gen": data["t_gen"],
            "w_gen": data["w_gen"],
            "state": state
        }

        updated = False
        for i, epr in enumerate(pares):
            if str(epr.get("id")) == str(epr_id):
                epr.update(nuevo_epr)
                pares[i] = epr
                updated = True
                break
        if not updated:
            pares.append(nuevo_epr)

        node_info["pairEPR"] = pares
        notificar_master_pairEPR(node_info)

        return jsonify({"status": "added", "pairEPR": node_info["pairEPR"]}), 200, {"Connection": "close"}


    @app.route("/pairEPR/recv", methods=["POST"])
    def pairEPR_recv():
        data = request.get_json()
        pares = node_info.setdefault("pairEPR", [])
        updated = False
        print("DATA: ", data)
        for i, epr in enumerate(pares):
            if str(epr.get("id")) == str(data.get("id")):
                epr.update(data)   # <-- aquí se fusionan los campos nuevos
                pares[i] = epr
                updated = True
                break
        if not updated:
            pares.append(data)

        node_info["pairEPR"] = pares
        print("Sending to the emiter and the master: ",node_info)
        notificar_master_pairEPR(node_info)
        return jsonify({"status": "updated", "pairEPR": node_info["pairEPR"]}), 200, {"Connection": "close"}
    
    @app.route("/pairEPR/failed_pur", methods=["POST"])
    def pairEPR_failed_pur():
        data = request.get_json()
        node_info["pairEPR"].append(data)
        notificar_master_pairEPR(node_info)
        return jsonify({"status": "added", "pairEPR": node_info["pairEPR"]}), 200, {"Connection": "close"}

    @app.route("/pairEPR/swap", methods=["POST"])
    def pairEPR_swap():
        data = request.get_json()
        pares = node_info.setdefault("pairEPR", [])
        # Usa el id recibido o genera uno nuevo
        epr_id = data.get("id") or (max((p["id"] for p in pares), default=0) + 1)
        # Construye el nuevo EPR de swapping
        nuevo_epr = {
            "id": epr_id,
            "neighbor": data.get("neighbor"),          # normalmente lista de destinatarios
            "state": data.get("state", "swapped"),
            "medicion": data.get("medicion")
        }

        # Actualiza si ya existe, si no lo añade
        updated = False
        for i, epr in enumerate(pares):
            if str(epr.get("id")) == str(epr_id):
                epr.update(nuevo_epr)
                pares[i] = epr
                updated = True
                break
        if not updated:
            pares.append(nuevo_epr)

        node_info["pairEPR"] = pares
        notificar_master_pairEPR(node_info)

        return jsonify({"status": "swapped", "pairEPR": node_info["pairEPR"]}), 200, {"Connection": "close"}



    def notificar_master_pairEPR(node_info):
        try:
            res = requests.post(
                "http://localhost:8000/master/pairEPR",  # puerto donde corre el master
                json={node_info["id"]: node_info.get("pairEPR", [])},
                timeout=2

            )
            print("[DEBUG] Historial pairEPR enviado al master:", res.status_code)
            print("[DEBUG] Master recibio esto:", node_info)
        except Exception as e:
            print("[DEBUG] Error notificando al master:", e)

    @app.route("/update", methods=["POST"])
    def update():
        data = request.get_json()
        print(data)
        for key in ["id", "name", "pswap", "roles", "neighbors"]:
            if key in data:
                node_info[key] = data[key]

        source = data.get("source")
        target = data.get("target")
        fields = ["distanceKm", "pgen", "lat", "lon", "pgenOverride"]

        if source and target:
            for node_id, neighbor_id in [(source, target), (target, source)]:
                if node_info.get("id") == node_id:
                    for v in node_info.get("neighbors", []):
                        if v.get("id") == neighbor_id:
                            for f in fields:
                                if f in data:
                                    v[f] = data[f]



            neighbor_id = target if node_info["id"] == source else source
            neighbor_port = get_port_by_id(neighbor_id)
            try:
                requests.post(f"http://localhost:{neighbor_port}/update", json=data)
            except Exception as e:
                print(f"Error propagando actualización a {neighbor_id}: {e}")

        node_info["lastUpdated"] = data.get("lastUpdated", time())
        event_queue.put("update")
        return jsonify({"status": "ok", "node_info": node_info}), 200, {"Connection": "close"}
    @app.route("/history", methods=["POST"])
    def update_history():
        data = request.get_json()
        print(data)
        for key in ["pairEPR"]:
            if key in data:
                node_info[key] = data[key]
        return jsonify({"status": "ok"}), 200, {"Connection": "close"}


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
        event_queue.put("mandate")
        return jsonify({"status": "ok", "ORDERS": ORDERS}), 200, {"Connection": "close"}
    

    @app.route("/updates/stream")
    def mandate_stream():
        def event_stream():
            msg = event_queue.get()  #  espera bloqueante
            yield f"data: {msg}\n\n"
        return Response(event_stream(), mimetype="text/event-stream")

    @app.route("/orders", methods=["GET"])
    def get_orders():
        global ORDERS
        return jsonify(ORDERS), 200, {"Connection": "close"}

    @app.route("/operations", methods=["POST"])
    def operations():
        data = request.get_json()
        print(">>> Orden recibida en /operations:", data)

        if not isinstance(data, dict):
            return jsonify({"error": "Formato inválido"}), 400
        if "comand" not in data:
            return jsonify({"error": "Falta 'comand'"}), 400

        try:
            aplicar_orden(data, node_info)
            print(">>> Orden aplicada correctamente")
            return jsonify({"status": "ok", "node_info": node_info})
        except Exception as e:
            print(">>> Excepción en aplicar_orden:", repr(e))
            try:
                res = requests.post(
                    "http://localhost:8000/master/saving_history",  # puerto donde corre el master
                    json={},
                    timeout=2
                )
                print("[DEBUG] Saving history for a error:", res.status_code)
                print("DEBUG] Deleting pairEPR history")
            except Exception as e:
                print("[DEBUG] Error notificando al master:", e)
            print(f"Order: {data}")
            return jsonify({"error": str(e)}), 500

    print(f"[SERVIDOR] Inicializando nodo en el puerto {PUERTO}...")
    app.run(host="127.0.0.1", port=PUERTO, debug=True, use_reloader=False)


if __name__ == "__main__":
    # Seleccionar un puerto libre en el rango, excepto 5001
    PUERTO = select_port(5000, 5010, exclude=[5001])
    if PUERTO is None:
        print("[ERROR] No ports available")
        sys.exit(1)

    proceso = Process(target=app_open, args=(PUERTO, PUERTO+4000))
    proceso.start()
    proceso.join()
