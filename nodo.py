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
            "parEPR": []
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
            "parEPR": []
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
            "parEPR": []
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
            "parEPR": []
        }
    }

    nodo_info = PORT_NODE_MAP.get(PUERTO, {"id": "node_unknown", "name": "Desconocido", "neighbors": []})
    print(nodo_info)

    # --- Auxiliar: obtener puerto a partir del id ---
    def get_port_by_id(node_id: str) -> int:
        for port, info in PORT_NODE_MAP.items():
            if info["id"] == node_id:
                return port
        raise ValueError(f"No se encontró puerto para {node_id}")
    

    def aplicar_orden(orden, node_info):
        global worker_started
        accion = orden["accion"]
        source_id = node_info["id"]
        epr_id = orden.get("id")

        print("APPLYING ORDER!!!")
        print("\n===== DEBUG: FULL parEPR DUMP =====")
        for e in node_info.get("parEPR", []):
            print(f"ID: {e.get('id')}")
            for k, v in e.items():
                print(f"   {k}: {v}")
        print("====================================\n")

        # --------------------------------------------------
        # Generate EPR (this node is the sender)
        # --------------------------------------------------
        if accion in ["genera EPR", "generar"]:
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
                print("Lo hace en: ")
                print(listener_port)
                

                payload = {
                    "accion": "generate EPR",
                    "id": epr_id,
                    "source": source_id,
                    "target": target_id,
                    "node_info": node_info,
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
        elif accion == "recibe EPR":
            epr_id = orden["id"]  # EPR id specified in the order
            timeout = 5.0         # max wait time in seconds
            interval = 0.1        # polling interval
            start = time()
            epr_obj = None

            print("Searching for EPR in node_info['parEPR']...")
            while time() - start < timeout:
                epr_obj = next(
                    (e for e in node_info.get("parEPR", []) if str(e["id"]) == str(epr_id)),
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
                    "accion": "recibe EPR",
                    "id": epr_id,
                    "source": orden["source"],
                    "epr_obj": epr_obj,
                    "node_info": node_info,
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
        elif accion in ["purifica", "purificar"]:
            print(f"[{source_id}] Running purification protocol...")
            my_port = get_port_by_id(node_info["id"])
            emisor_port = get_port_by_id(orden["con"])   # node with which we purify
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
        elif accion in ["swap", "swapping"]:
            print(f"[{source_id}] Running swapping protocol...")
            payload = {
                "accion": "do swapping",
                "id": epr_id,
                "source": node_info["id"],
                "node_info": node_info,
                "destinatarios": orden["con"],
                "destinatarios_ports": [str(get_port_by_id(n)) for n in orden["con"]],
                "pswap": str(node_info.get("pswap", 1)),
                "listener_port": listener_port,
                "ports_involved": [str(get_port_by_id(n) + 4000) for n in orden["con"]]
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
        elif accion in ["swap recibido"]:
            print("Swap attempt between:", orden["con"])

        else:
            raise ValueError(f"Unknown action: {accion}")


    app = Flask(__name__)
    CORS(app)

    @app.route("/")
    def index():
        print(nodo_info)
        return render_template("nodo.html", nodo_info=nodo_info)

    @app.route("/info")
    def info():
        return jsonify(nodo_info)

    @app.route("/parEPR/add", methods=["POST"])
    def parEPR_add():
        data = request.get_json()
        pares = nodo_info.setdefault("parEPR", [])
        epr_id = data.get("id") or (max((p["id"] for p in pares), default=0) + 1)

        print(f"ESTO MANDO SENDER: {data}")

        state = "fallo" if float(data["w_gen"]) == 0.0 else "ok"


        nuevo_epr = {
            "id": epr_id,
            "vecino": data["vecino"],
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

        nodo_info["parEPR"] = pares
        notificar_master_parEPR(nodo_info)

        return jsonify({"status": "added", "parEPR": nodo_info["parEPR"]})


    @app.route("/parEPR/recv", methods=["POST"])
    def parEPR_recv():
        data = request.get_json()
        pares = nodo_info.setdefault("parEPR", [])
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

        nodo_info["parEPR"] = pares
        print("Enviando a Emisor y a Master: ",nodo_info)
        notificar_master_parEPR(nodo_info)
        return jsonify({"status": "updated", "parEPR": nodo_info["parEPR"]})
    
    @app.route("/parEPR/failed_pur", methods=["POST"])
    def parEPR_failed_pur():
        data = request.get_json()
        nodo_info["parEPR"].append(data)
        notificar_master_parEPR(nodo_info)
        return jsonify({"status": "added", "parEPR": nodo_info["parEPR"]})

    @app.route("/parEPR/swap", methods=["POST"])
    def parEPR_swap():
        data = request.get_json()
        pares = nodo_info.setdefault("parEPR", [])
        # Usa el id recibido o genera uno nuevo
        epr_id = data.get("id") or (max((p["id"] for p in pares), default=0) + 1)
        # Construye el nuevo EPR de swapping
        nuevo_epr = {
            "id": epr_id,
            "vecino": data.get("vecino"),          # normalmente lista de destinatarios
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

        nodo_info["parEPR"] = pares
        notificar_master_parEPR(nodo_info)

        return jsonify({"status": "swapped", "parEPR": nodo_info["parEPR"]})



    def notificar_master_parEPR(nodo_info):
        try:
            res = requests.post(
                "http://localhost:8000/master/parEPR",  # puerto donde corre el master
                json={nodo_info["id"]: nodo_info.get("parEPR", [])},
                timeout=2

            )
            print("[DEBUG] Historial parEPR enviado al master:", res.status_code)
            print("[DEBUG] Master recibio esto:", nodo_info)
        except Exception as e:
            print("[DEBUG] Error notificando al master:", e)

    @app.route("/update", methods=["POST"])
    def update():
        data = request.get_json()
        print(data)
        for key in ["id", "name", "pswap", "roles", "neighbors"]:
            if key in data:
                nodo_info[key] = data[key]

        source = data.get("source")
        target = data.get("target")
        fields = ["distanceKm", "pgen", "lat", "lon"]

        if source and target:
            for node_id, neighbor_id in [(source, target), (target, source)]:
                if nodo_info.get("id") == node_id:
                    for v in nodo_info.get("neighbors", []):
                        if v.get("id") == neighbor_id:
                            for f in fields:
                                if f in data:
                                    v[f] = data[f]



            vecino_id = target if nodo_info["id"] == source else source
            vecino_port = get_port_by_id(vecino_id)
            try:
                requests.post(f"http://localhost:{vecino_port}/update", json=data)
            except Exception as e:
                print(f"Error propagando actualización a {vecino_id}: {e}")

        nodo_info["lastUpdated"] = data.get("lastUpdated", time())
        event_queue.put("update")
        return jsonify({"status": "ok", "nodo_info": nodo_info})
    @app.route("/history", methods=["POST"])
    def update_history():
        data = request.get_json()
        print(data)
        for key in ["parEPR"]:
            if key in data:
                nodo_info[key] = data[key]


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
        return jsonify({"status": "ok", "ORDERS": ORDERS})
    

    @app.route("/updates/stream")
    def mandate_stream():
        def event_stream():
            msg = event_queue.get()  #  espera bloqueante
            yield f"data: {msg}\n\n"
        return Response(event_stream(), mimetype="text/event-stream")

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
