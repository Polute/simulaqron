import sys
import random
import json
import requests
import time
import socket
import math
import threading

from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError

# Speed of light in fiber (km/s approximation)
C = 3e5

# Local EPR memory
epr_store = {}
nodo_info = {"parEPR": []}


# --------------------------------------------------
# Utility functions
# --------------------------------------------------

def send_info(url, payload):
    """Send payload to a node's HTTP endpoint."""
    try:
        r = requests.post(url, json=payload, timeout=2)
        print(f"[SENDER] Sent info to {url}, status={r.status_code}")
    except Exception as e:
        print(f"[SENDER] Error sending info to {url}: {e}")


def calculate_tdiff(ts1: str, ts2: str) -> float:
    """Compute time difference ts2 - ts1 for timestamps MM:SS.mmm."""
    def parse_ts(ts: str) -> float:
        try:
            minutes, rest = ts.split(":")
            seconds, millis = rest.split(".")
            return int(minutes) * 60 + int(seconds) + int(millis) / 1000.0
        except Exception:
            return 0.0

    return parse_ts(ts2) - parse_ts(ts1)


# --------------------------------------------------
# EPR generation
# --------------------------------------------------

def generar_epr(emisor, receptor, conn, emisor_port, receptor_port,
                pgen, epr_id, node_info):
    """Attempt to generate an EPR pair with probabilistic success."""
    print(f"[SENDER] {emisor} attempting EPR with {receptor} (pgen={pgen})")

    neighbors = [n["id"] for n in node_info.get("neighbors", [])]
    if receptor not in neighbors:
        print(f"[SENDER] {receptor} is not a neighbor of {emisor}")
        send_info(
            f"http://localhost:{emisor_port}/parEPR/add",
            {"id": epr_id, "vecino": receptor, "t_gen": "0", "w_gen": "0"}
        )
        return

    if random.random() > pgen:
        print("[SENDER] Probabilistic failure, no EPR created")
        for port, vecino in [(emisor_port, receptor), (receptor_port, emisor)]:
            send_info(
                f"http://localhost:{port}/parEPR/add",
                {"id": epr_id, "vecino": vecino, "t_gen": "0", "w_gen": "0"}
            )
        return

    try:
        print("[DEBUG] conn object:", conn)
        print("[DEBUG] conn.name:", getattr(conn, "name", None))
        print("[DEBUG] conn._name:", getattr(conn, "_name", None))
        print("[DEBUG] conn._appID:", getattr(conn, "_appID", None))


        q = conn.createEPR(receptor)
        epr_store[epr_id] = {"q": q, "w_out": 1.0, "other_port": receptor_port}
    except CQCNoQubitError:
        print("[SENDER] No quantum memory available")
        for port, vecino in [(emisor_port, receptor), (receptor_port, emisor)]:
            send_info(
                f"http://localhost:{port}/parEPR/add",
                {"id": epr_id, "vecino": vecino, "t_gen": "0", "w_gen": "0"}
            )
        return
    except Exception as e:
        print(f"[SENDER] Unexpected error: {e}")
        return

    t_gen = time.strftime("%M:%S.") + f"{int((time.time() % 1)*1000):03d}"
    for port, vecino in [(emisor_port, receptor), (receptor_port, emisor)]:
        send_info(
            f"http://localhost:{port}/parEPR/add",
            {"id": epr_id, "vecino": vecino, "t_gen": t_gen, "w_gen": 1.0}
        )


# --------------------------------------------------
# Werner decay monitor
# --------------------------------------------------
def measure_epr_sender(epr_id, node_info, conn, target_port, my_port=None, order=None):
    """
    Measure a qubit locally, update local node_info, and notify the target node via socket.
    """
    entry = epr_store.get(epr_id)
    if not entry:
        return {"error": "EPR not found"}

    q = entry["q"]
    emisor_port = entry.get("emisor_port")
    
    # Perform measurement
    m = q.measure()
    
    # Update local state
    for epr in node_info.get("parEPR", []):
        if epr["id"] == epr_id:
            epr["state"] = order
            epr["medicion"] = m
    
    del epr_store[epr_id]
    
    result_measure = {"id": epr_id, "medicion": m, "state": order}

    # Notify via HTTP
    try:
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=result_measure, timeout=2)
        if target_port:
            requests.post(f"http://localhost:{target_port}/parEPR/recv", json=result_measure, timeout=2)
    except Exception as e:
        print(f"[MEASURE_SENDER] Error notifying endpoints: {e}")


    return result_measure

def recalculate_werner(epr_id, result_recv, conn,
                       my_port=None, other_port=None,
                       epr_id_before=None,
                       interval=0.01, threshold=1/3):
    """Continuously update Werner fidelity until threshold is reached."""
    w_in = float(result_recv.get("w_gen", 1.0))
    t_gen = result_recv.get("t_gen", "0")
    tcoh = float(result_recv.get("tcoh", 10.0))

    while True:
        t_now = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"
        tdif = calculate_tdiff(t_gen, t_now)
        w_out = w_in * math.exp(-tdif / tcoh)

        if epr_id in epr_store:
            epr_store[epr_id]["w_out"] = w_out

        if w_out <= threshold:
            print(f"[COHERENCE] EPR {epr_id} reached w={w_out:.3f} in {t_now}, measuring...")
            if epr_id_before is not None and my_port and other_port:
                print(f"[COHERENCE] EPR {epr_id} reached w={w_out:.3f} in {t_now}, measuring...")
                measure_epr_sender(epr_id_before, epr_id, result_recv,
                                   conn, my_port, other_port, order="measure")
            break

        time.sleep(interval)


def start_monitor(epr_id, result_recv, conn,
                  my_port=None, other_port=None, epr_before=None):
    """Start coherence monitor in a background thread."""
    threading.Thread(
        target=recalculate_werner,
        args=(epr_id, result_recv, conn, my_port, other_port, epr_before),
        daemon=True
    ).start()


# --------------------------------------------------
# Socket handling (CORRECTED)
# --------------------------------------------------

def handle_client(conn_sock, addr,
                  node_info, conn,
                  my_port, emisor_port):
    """Handle a single TCP client connection."""
    try:
        conn_sock.settimeout(5.0)
        data = conn_sock.recv(4096)
        if not data:
            return

        payload = json.loads(data.decode())
        accion = payload.get("accion")

        if accion == "generate EPR":
            generar_epr(
                payload["source"],
                payload["target"],
                conn,
                int(payload["source_port"]),
                int(payload["target_port"]),
                float(payload.get("pgen", 1.0)),
                payload["id"],
                payload.get("node_info", node_info)
            )
            conn_sock.send(json.dumps({"status": "ok"}).encode())

        elif accion == "recalculate":
            start_monitor(payload["id"], payload["info"], conn, my_port)
            conn_sock.send(json.dumps({"status": "monitor started"}).encode())

        elif accion == "watch_over":
            start_monitor(
                payload["id"],
                payload.get("EPR_pair"),
                conn,
                payload.get("my_port"),
                payload.get("other_port"),
                payload.get("id_before")
            )
            conn_sock.send(json.dumps({"status": "watching"}).encode())

    except socket.timeout:
        print("[CLEANUP] Client timeout")
    except KeyboardInterrupt:
        print("[SENDER] Listener interrumpido manualmente, cerrando...")
    except Exception as e:
        print(f"[ERROR] Client {addr}: {e}")
    finally:
        conn_sock.close()


def socket_listener(node_info, conn, port=10000,
                    my_port=None, emisor_port=None):
    """Main TCP listener that never blocks or dies."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(50)

    print(f"[LISTENER] Listening on port {port}")

    try:
        while True:
            conn_sock, addr = server.accept()
            threading.Thread(
                target=handle_client,
                args=(conn_sock, addr, node_info, conn, my_port, emisor_port),
                daemon=True
            ).start()
    except KeyboardInterrupt:
        print("[SENDER] Ctrl+C recibido, cerrando listener...")
    finally:
        server.close()



# --------------------------------------------------
# Main
# --------------------------------------------------

if __name__ == "__main__":
    emisor        = sys.argv[1]
    receptor      = sys.argv[2]
    emisor_port   = int(sys.argv[3])
    receptor_port = int(sys.argv[4])
    pgen          = float(sys.argv[5])
    epr_id        = sys.argv[6]
    node_info     = json.loads(sys.argv[7])
    listener_port = int(sys.argv[8])
    print(emisor)
    with CQCConnection(emisor) as conn:
        print("In emiter.py")
        generar_epr(
            emisor, receptor, conn,
            emisor_port, receptor_port,
            pgen, epr_id, node_info
        )

        socket_listener(
            nodo_info,
            conn,
            port=listener_port,
            my_port=emisor_port,
            emisor_port=receptor_port
        )
