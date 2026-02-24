import socket
from flask import Flask, render_template, jsonify, request, Response
import json
import sys
from multiprocessing import Process
from flask_cors import CORS
from time import time, sleep, perf_counter
import subprocess
import requests
import queue
event_queue = queue.Queue()
import os

import zmq
import msgpack
import threading
# --------------------------------------------------
# HIGH PRECISION TIMESTAMPS
# --------------------------------------------------

def timestamp_precise():
    """
    Returns a monotonic timestamp in seconds with microsecond precision
    using the format SS.xxxxxx.
    """
    return f"{perf_counter():.6f}"


def timestamp_to_seconds(ts):
    """
    Convert 'SS.xxxxxx' or legacy 'MM:SS.xxxxxx' into float seconds.
    """
    if ":" in ts:
        mm, rest = ts.split(":")
        ss, us = rest.split(".")
        return int(mm) * 60 + int(ss) + int(us) / 1_000_000
    return float(ts)


def diff_precise(t1, t2):
    """
    Compute difference between two precise timestamps.
    """
    return timestamp_to_seconds(t2) - timestamp_to_seconds(t1)

TIMESTAMP_LOG = "latencies/timestamps_log_afterx2_14.txt"

def log_timestamp(event_type, epr_id, **fields):
    line = f"[{event_type}]  ID={epr_id}"
    for k, v in fields.items():
        line += f"  {k}={v}"
    line += "\n"
    with open(TIMESTAMP_LOG, "a") as f:
        f.write(line)

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
epr_ready = {}   # id → payload
epr_ready_cv = threading.Condition()
receive_dispatch_lock = threading.Lock()
pending_receive_orders = {}  # id -> orden
inflight_receive_ids = set()


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

    worker_state_lock = threading.Lock()
    
    def processing_receive_epr(orden, epr_obj=None):
        global worker_started
        epr_id = orden["id"]  # EPR id specified in the order
        try:
            receiver_id = node_info["id"]
            log_timestamp("ORDER_RECV_STARTING",epr_id, t_start = timestamp_precise())
            print(receiver_id, " will receive EPR with:", orden["source"])
            if epr_obj is None:
                print("Waiting for EPR ",epr_id ," via ZMQ starting at ", timestamp_precise())
                timeout = 5.0

                # Wait for this EPR id without busy-waiting.
                deadline = perf_counter() + timeout
                with epr_ready_cv:
                    while epr_obj is None:
                        epr_obj = epr_ready.pop(epr_id, None)
                        if epr_obj is not None:
                            break

                        remaining = deadline - perf_counter()
                        if remaining <= 0:
                            break
                        epr_ready_cv.wait(timeout=remaining)

            if epr_obj is None:
                print(f"[RECEIVER] Timeout waiting for EPR {epr_id} at {timestamp_precise()}")
                return
            
            my_port = get_port_by_id(node_info["id"])
            emisor_port = get_port_by_id(orden["source"])
            print(f"[RECEIVER] Processing EPR {epr_id} between {node_info['id']}:{my_port} "
                f"and {orden['source']}:{emisor_port}")
            
            log_timestamp("ORDER_RECV_EXECUTING_AFTER_FOUND",epr_id, t_start = timestamp_precise())
            with worker_state_lock:
                need_init = not worker_started
                if need_init:
                    print("[INFO] Starting worker.py in receiver_init mode for the first time at ", timestamp_precise())
                    subprocess.Popen([
                        sys.executable, "worker.py",
                        "receiver_init",
                        json.dumps(epr_obj),
                        json.dumps(node_info),
                        str(my_port),
                        str(emisor_port),
                        str(listener_port)
                    ])
                    worker_started = True
                    # Warm up internal fast command channel to reduce first-send latency.
                    get_zmq_socket(f"tcp://localhost:{listener_port + 2000}")

            if not need_init:
                print("[INFO] Receiver already running, sending order via ZMQ at ", timestamp_precise())
                payload = {
                    "comand": "receive EPR",
                    "id": epr_id,
                    "source": orden["source"],
                    "epr_obj": epr_obj,
                    "my_port": my_port,
                    "emisor_port": emisor_port,
                    "listener_port": listener_port
                }
                cmd_addr = f"tcp://localhost:{listener_port + 2000}"
                send_info(
                    cmd_addr,
                    {
                        "route": "worker/receive_epr",
                        "payload": payload
                    }
                )
        finally:
            with receive_dispatch_lock:
                inflight_receive_ids.discard(epr_id)

    def _maybe_dispatch_receive(epr_id):
        with receive_dispatch_lock:
            if epr_id in inflight_receive_ids:
                return

            orden = pending_receive_orders.get(epr_id)
            with epr_ready_cv:
                epr_obj = epr_ready.pop(epr_id, None)
            if orden is None or epr_obj is None:
                if epr_obj is not None:
                    # Put it back if the order has not arrived yet.
                    with epr_ready_cv:
                        epr_ready[epr_id] = epr_obj
                return

            pending_receive_orders.pop(epr_id, None)
            inflight_receive_ids.add(epr_id)

        threading.Thread(
            target=processing_receive_epr,
            args=(orden, epr_obj),
            daemon=True
        ).start()


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
            try:
                source_port = get_port_by_id(source_id)
                target_port = get_port_by_id(target_id)
            except ValueError as exc:
                print(f"[ERROR] Invalid node id in generate EPR order: {exc}")
                return

            # Find pgen of the neighbor whose id matches target_id
            pgen_source = None
            for neighbor in node_info.get("neighbors", []):
                if neighbor["id"] == target_id:
                    pgen_source = str(neighbor["pgen"])
                    break

            # Fallback: if source->target is missing, try target->source link data.
            if pgen_source is None:
                target_info = next(
                    (info for info in PORT_NODE_MAP.values() if info.get("id") == target_id),
                    None
                )
                if target_info:
                    for neighbor in target_info.get("neighbors", []):
                        if neighbor.get("id") == source_id:
                            pgen_source = str(neighbor.get("pgen"))
                            break

            if pgen_source is None:
                print(
                    f"[ERROR] Missing pgen for link {source_id} -> {target_id}. "
                    "Cannot launch worker.py."
                )
                return

            print(source_id, "will generate EPR with:", target_id)

            if not worker_started:
                print("[INFO] Starting worker.py in sender_init mode for the first time")
                subprocess.Popen([
                    sys.executable, "worker.py",
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
                # Warm up internal fast command channel to reduce first-send latency.
                get_zmq_socket(f"tcp://localhost:{listener_port + 2000}")
            else:
                print("[INFO] Sender already running, sending order via ZMQ")
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
                cmd_addr = f"tcp://localhost:{listener_port + 2000}"
                send_info(
                    cmd_addr,
                    {
                        "route": "worker/generate_epr",
                        "payload": payload
                    }
                )

        # --------------------------------------------------
        # Receive EPR (this node receives an EPR created by another node)
        # --------------------------------------------------
        elif comand == "receive EPR":
            epr_id = orden["id"]
            with receive_dispatch_lock:
                pending_receive_orders[epr_id] = orden
            _maybe_dispatch_receive(epr_id)
            return


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


    

    def pairEPR_add(data):
        pares = node_info.setdefault("pairEPR", [])
        epr_id = data.get("id") or (max((p["id"] for p in pares), default=0) + 1)


        nuevo_epr = {
            "id": epr_id,
            "neighbor": data["neighbor"],
            "t_gen": data["t_gen"],
            "w_gen": data["w_gen"],
            "state": data["state"]
        }

        # actualizar si existe
        for i, epr in enumerate(pares):
            if str(epr["id"]) == str(epr_id):
                # Because of the timing, dont change the final results
                if epr.get("state") in ("active", "measure"): 
                    nuevo_epr["state"] = epr["state"]
                pares[i].update(nuevo_epr)
                break
        else:
            pares.append(nuevo_epr)

        node_info["pairEPR"] = pares
        notificar_master_pairEPR_zmq(node_info, epr_id)

        print("[ZeroMQ] pairEPR updated:", nuevo_epr)

    def pairEPR_recv(data):
        pares = node_info.setdefault("pairEPR", [])
        epr_id = data.get("id")

        updated = False
        for i, epr in enumerate(pares):
            if str(epr.get("id")) == str(epr_id):
                pares[i].update(data)
                updated = True
                break

        if not updated:
            pares.append(data)

        node_info["pairEPR"] = pares
        notificar_master_pairEPR_zmq(node_info, epr_id)

        print("[ZeroMQ] pairEPR received & updated:", data)

    def execute_operation(payload):
        """
        Execute an operation sent by the master via ZeroMQ.
        This mirrors the structure of pairEPR_add, pairEPR_recv, etc.
        """
        global ORDERS
        ORDERS.clear()
        # 1. Append to ORDERS so the HTML can show it global ORDERS 
        ORDERS.append(payload) 
        
        # 2. Notify the HTML UI (SSE) 
        event_queue.put("mandate")
        t_start = timestamp_precise()

        log_timestamp("ORDER_RECEIVE",payload["id"],t_start=t_start)
        print("[ZeroMQ] Executing operation:", payload, "at ",timestamp_precise())

        # Run aplicar_orden in a background thread (non-blocking)
        threading.Thread(
            target=aplicar_orden,
            args=(payload, node_info),
            daemon=True
        ).start()
        
        
        #aplicar_orden(payload, node_info)



    def handle_epr_ready(payload):
        epr_id = payload["id"]
        with epr_ready_cv:
            epr_ready[epr_id] = payload
            epr_ready_cv.notify_all()
        _maybe_dispatch_receive(epr_id)



    zmq_port = PUERTO + 1000 # Puerto exclusivo para ZeroMQ
    ROUTES = {
        "pairEPR/add": pairEPR_add,
        "pairEPR/recv": pairEPR_recv,
        "sender/epr_ready": handle_epr_ready,
        "operations": execute_operation
    }

    def zmq_listener():
        context = zmq.Context()
        sock = context.socket(zmq.PULL)
        sock.bind(f"tcp://*:{zmq_port}")

        print(f"[ZeroMQ] Listening on tcp://*:{zmq_port}")

        while True:
            msg = sock.recv()
            data = msgpack.unpackb(msg, raw=False)

            route = data.get("route")
            payload = data.get("payload")

            if route in ROUTES:
                ROUTES[route](payload)
            else:
                print(f"[ZeroMQ] Unknown route: {route}")



    @app.route("/pairEPR/recv", methods=["POST"])
    def pairEPR_recv_request():
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
    
    import zmq
    import msgpack

    # Global ZeroMQ context shared by all sockets
    context = zmq.Context()

    # Cache of PUSH sockets (one per destination)
    zmq_sockets = {}

    def get_zmq_socket(addr):
        """Return a cached PUSH socket or create a new one."""
        if addr not in zmq_sockets:
            sock = context.socket(zmq.PUSH)
            sock.connect(addr)
            zmq_sockets[addr] = sock
            print(f"[ZeroMQ] Connected PUSH → {addr}")
        return zmq_sockets[addr]

    def send_info(addr, payload):
        """Send a msgpack payload via ZeroMQ PUSH."""
        try:
            sock = get_zmq_socket(addr)
            sock.send(msgpack.packb(payload))
            print(f"[NODE → MASTER ZMQ] Sent to {addr}")
        except Exception as e:
            print(f"[NODE → MASTER ZMQ ERROR] {e}")

    def notificar_master_pairEPR_zmq(node_info, epr_id):
        payload = {
            "route": "master/pairEPR",
            "payload": { node_info["id"]: node_info.get("pairEPR", []) },
            "epr_id": epr_id
        }

        master_zmq_addr = "tcp://localhost:9001"   # ZMQ port of the master

        send_info(master_zmq_addr, payload)

        # Optional timestamp logging
        log_timestamp(
            "SENDING TO MASTER (ZMQ)",
            epr_id,
            t_start=timestamp_precise()
        )

    def notificar_master_pairEPR(node_info, epr_id = None):
        def _send():
            t_start = timestamp_precise()
            if(epr_id != None):
                
                log_timestamp("SENDING TO MASTER", epr_id, t_start = t_start)
            try:
                requests.post(
                    "http://localhost:8000/master/pairEPR",
                    json={node_info["id"]: node_info.get("pairEPR", [])},
                    timeout=2
                )
                t_end = timestamp_precise()
                log_timestamp("RECEIVING FROM MASTER", epr_id, t_start = t_start, t_end = t_end, t_diff = diff_precise(t_start,t_end))
        
            except Exception as e:
                print("[DEBUG] Error notificando al master:", e)

        threading.Thread(target=_send, daemon=True).start()


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
    def operations_http():
        data = request.get_json()
        print(">>> Orden recibida en /operations:", data, "at", timestamp_precise())

        if not isinstance(data, dict):
            return jsonify({"error": "Formato inválido"}), 400
        if "comand" not in data:
            return jsonify({"error": "Falta 'comand'"}), 400

        try:
            threading.Thread(
                target=aplicar_orden,
                args=(data, node_info),
                daemon=True
            ).start()

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


    threading.Thread(target=zmq_listener, daemon=True).start()




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
