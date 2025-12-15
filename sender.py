import sys
import random
import json
import requests
import time
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError
import socket
import math


# Local memory of EPRs
C = 3e5  # km/s
epr_store = {}
nodo_info = {"parEPR": []}

def send_info(url, payload):
    """Send payload to a node's /parEPR/add endpoint."""
    try:
        r = requests.post(url, json=payload)
        print(f"[SENDER] Sent info to {url}, status={r.status_code}")
    except Exception as e:
        print(f"[SENDER] Error sending info to {url}: {e}")

def generar_epr(emisor, receptor, conn, emisor_port, receptor_port, pgen, epr_id, node_info):
    print(f"[SENDER] {emisor} attempting EPR with {receptor} (pgen={pgen})")

    # comprobar si receptor está en la lista de vecinos de node_info
    vecinos = [n["id"] for n in node_info["neighbors"]]
    if receptor not in vecinos:
        print(f"[SENDER] Error: {receptor} no es vecino de {emisor} según node_info")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor, 
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        return

    # Probabilistic check
    if random.random() > pgen:
        print(f"[SENDER] Probabilistic failure, no EPR created")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor,  # el otro extremo
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload_receptor = {
            "id": epr_id,
            "vecino": emisor,    # el otro extremo
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)
        return

    try:
        print("[DEBUG] Conexión abierta correctamente con", emisor)
        q = conn.createEPR(receptor)
        # store both the qubit and initial w_out (same as w_gen)
        epr_store[epr_id] = {"q": q, "w_out": 1.0, "other_port":receptor_port}
    except CQCNoQubitError:
        print(f"[SENDER] Error: no quantum memory available")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload_receptor = {
            "id": epr_id,
            "vecino": emisor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)
        return
    except Exception as e:
        print(f"[SENDER] Unexpected error: {e}")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload_receptor = {
            "id": epr_id,
            "vecino": emisor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)
        return

    # Success payload
    t_gen = time.strftime("%M:%S.") + f"{int((time.time() % 1)*1000):03d}"
    payload_emisor = {
        "id": epr_id,
        "vecino": receptor,  # el otro extremo
        "t_gen": t_gen,
        "w_gen": 1.0
    }
    payload_receptor = {
        "id": epr_id,
        "vecino": emisor,    # el otro extremo
        "t_gen": t_gen,
        "w_gen": 1.0
    }

    send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
    send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)
import threading


def measure_epr_sender(epr_id_before, epr_id, node_info, conn, my_port=None, other_port=None, order=None):
    entry = epr_store.get(epr_id_before)
    if entry:
        q = entry["q"]

        m = q.measure()
        for epr in node_info["parEPR"]:
            if epr["id"] == epr_id:
                epr["estado"] = order
                epr["medicion"] = m
        del epr_store[epr_id_before]
        del epr_store[epr_id]
        result_measure = {"id": epr_id, "medicion": m, "estado": order}
        # notificar al propio nodo y al emisor
        try:
            if my_port:
                requests.post(f"http://localhost:{my_port}/parEPR/recv", json=result_measure, timeout=2)
            if other_port:
                requests.post(f"http://localhost:{other_port}/parEPR/recv", json=result_measure, timeout=2)    
        except Exception as e:
            print(f"[RECEIVER] Error notificando endpoints: {e}")
        return result_measure
    return None


def calculate_tdiff(ts1: str, ts2: str):
    """
    Given two timestamp strings in the format 'MM:SS.mmm',
    compute the difference ts2 - ts1.
    Returns (val1, val2, diff).
    """
    def parse_ts(ts: str) -> float:
        try:
            minutes, rest = ts.split(":")
            seconds, millis = rest.split(".")
            return int(minutes) * 60 + int(seconds) + int(millis) / 1000.0
        except Exception:
            return 0.0

    val1 = parse_ts(ts1)
    val2 = parse_ts(ts2)
    diff = val2 - val1
    return diff
def recalculate_werner(epr_id, result_recv, conn=None, my_port=None, other_port=None, epr_id_before = None, interval=0.01, threshold=1/3):
    """
    Continuously recomputes w_out for the given EPR until it falls below the threshold.
    Uses t_gen from result_recv to calculate time difference.
    Updates only epr_store[epr_id]["w_out"].
    """
    if result_recv.get("id") != epr_id:
        print(f"[WER] result_recv does not match EPR {epr_id}")
        return None

    # Initial parameters
    w_in = float(result_recv.get("w_gen", 1.0))
    t_gen_str = result_recv.get("t_gen", "0")
    tcoh = float(result_recv.get("tcoh", 10.0)) if "tcoh" in result_recv else 10.0

    while True:
        # Current timestamp string
        t_recv_str = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"

        # Calculate time difference
        tdif = calculate_tdiff(t_gen_str, t_recv_str)

        # Werner fidelity decay
        w_out = w_in * math.exp(-(tdif) / tcoh)

        # Update only epr_store
        if epr_id in epr_store:
            epr_store[epr_id]["w_out"] = w_out

        if w_out <= threshold:
            print(f"[COHERENCE] EPR {epr_id} reached w={w_out:.3f} in {t_recv_str}, measuring...")
            if(my_port!= None and other_port!=None):
                measure_epr_sender(epr_id_before, epr_id, result_recv, conn, my_port, other_port, order="measure")
            break
        time.sleep(interval)

    
def start_monitor(epr, result_recv, conn, my_port, other_port=None, epr_before=None):
    """
    Launches the coherence monitor in the background for a given EPR.
    """
    threading.Thread(
        target=recalculate_werner,
        args=(epr, result_recv, conn, my_port, other_port, epr_before),
        daemon=True
    ).start()

def socket_listener(node_info, conn, port=10000, my_port=None, emisor_port=None):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(5)
    print(time.time())
    print(f"[RECEIVER] Escuchando órdenes en puerto {port}...")

    try:
        while True:
            try: 
                conn_sock, addr = server.accept()
                data = conn_sock.recv(4096).decode()
                print("[DEBUG SENDER] Recibido:", repr(data))
                if not data:
                    conn_sock.close()
                    continue

                payload = json.loads(data)

                if payload.get("accion") == "generate EPR":
                    # Extraer parámetros del payload
                    origen_id    = payload.get("origen")
                    destino_id   = payload.get("destino")
                    origen_port  = int(payload.get("origen_port"))
                    destino_port = int(payload.get("destino_port"))
                    pgen         = float(payload.get("pgen", 1.0))
                    epr_id       = payload.get("id")
                    node_info_in = payload.get("node_info", node_info)

                    print(f"[SENDER] {origen_id} generating EPR with {destino_id} (pgen={pgen})")

                    # Llamar a la función de generación
                    generar_epr(origen_id, destino_id, conn,
                                origen_port, destino_port,
                                pgen, epr_id, node_info_in)

                    # Responder al cliente que envió la orden
                    response = {"status": "EPR generated", "id": epr_id}
                    conn_sock.send(json.dumps(response).encode())

                elif payload.get("accion") == "recalculate":
                    print("Recalculating")
                    epr_id = payload["id"]
                    result_recv = payload["info"]
                    start_monitor(epr_id, result_recv, conn, my_port)
                    response = {"status": "monitor started", "id": epr_id}
                    conn_sock.send(json.dumps(response).encode())

                elif payload.get("accion") == "watch_over":
                    print("Monitoring new EPR")
                    epr_id = payload["id"]
                    result_recv = payload.get("EPR_pair", [])
                    my_port = payload["my_port"]
                    other_port = payload["other_port"]
                    epr_id_before = payload["id_before"]
                    start_monitor(epr_id, result_recv, conn, my_port, other_port, epr_id_before)
                    response = {"status": "EPR whatched", "id": epr_id}
                    conn_sock.send(json.dumps(response).encode())

                conn_sock.close()

            except socket.timeout:
                print("[SENDER] No se recibió nada en el intervalo, sigo escuchando...")
                continue
    except KeyboardInterrupt:
        print("[RECEIVER] Listener interrumpido manualmente, cerrando...")
    finally:
        server.close()


if __name__ == "__main__":
    emisor = sys.argv[1]       
    receptor = sys.argv[2]      
    emisor_port = int(sys.argv[3])
    receptor_port = int(sys.argv[4])
    pgen = float(sys.argv[5])   # probability of generation
    epr_id = sys.argv[6]
    node_info = json.loads(sys.argv[7])
    listener_port = int(sys.argv[8])
    with CQCConnection(emisor) as conn:
        generar_epr(emisor, receptor, conn, emisor_port, receptor_port, pgen, epr_id, node_info)

        socket_listener(nodo_info, conn, port=listener_port, my_port=emisor_port)

