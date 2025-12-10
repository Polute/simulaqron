import sys
import random
import json
import requests
import time
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError
import socket


# Local memory of EPRs

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
        epr_store[epr_id] = q
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

def measure_epr(epr_id, node_info, conn, my_port=None, emisor_port=None, order=None):
    q = epr_store.get(epr_id)
    if q:
        m = q.measure()
        for epr in node_info["parEPR"]:
            if epr["id"] == epr_id:
                epr["estado"] = order
                epr["medicion"] = m
        del epr_store[epr_id]
        result_measure = {"id": epr_id, "medicion": m, "estado": order}
        # notificar al propio nodo y al emisor
        try:
            if my_port:
                requests.post(f"http://localhost:{my_port}/parEPR/recv", json=result_measure, timeout=2)  
        except Exception as e:
            print(f"[RECEIVER] Error notificando endpoints: {e}")
        return result_measure
    return None

def socket_listener(node_info, conn, port=9000, my_port=None, emisor_port=None):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(5)
    server.settimeout(5.0)   # timeout de 5 segundos
    print(f"[RECEIVER] Escuchando órdenes en puerto {port}...")

    try:
        while True:
            conn_sock, addr = server.accept()
            data = conn_sock.recv(4096).decode()
            print("[DEBUG RECV] Recibido:", repr(data))
            if not data:
                conn_sock.close()
                continue

            payload = json.loads(data)

            if payload.get("accion") == "measure":
                epr_id = payload["id"]
                order = "Consumed"
                result = measure_epr(epr_id, node_info, conn, my_port, emisor_port, order)
                conn_sock.send(json.dumps(result or {"error": "EPR no encontrado"}).encode())

            elif payload.get("accion") == "start_countdown":
                epr_id = payload["id"]
                delay = int(payload.get("delay", 5))
                print(f"[RECEIVER] Starting countdown of {delay}s for EPR {epr_id}...")
                def delayed_measure():
                    result = measure_epr(epr_id, node_info, conn, my_port, emisor_port, order="Consumed")
                    if result:
                        print(f"[RECEIVER] Countdown finished, measured EPR {epr_id}: {result['medicion']}")
                threading.Timer(delay, delayed_measure).start()
                conn_sock.send(json.dumps({"status": "countdown started", "id": epr_id}).encode())
            conn_sock.close()

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

        #socket_listener(nodo_info, conn, port=listener_port+1000, my_port=emisor_port)

