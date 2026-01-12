# --- Standard Library ---
import sys
import time
import math
import json
import random
import socket
import threading
from itertools import combinations

# --- Third‑party / External ---
import requests

# --- SimulaQron / CQC ---
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError, CQCTimeoutError


# Speed of light in fiber (km/s approximation)
C = 3e5

# Local EPR memory
epr_store = {}
nodo_info = {"parEPR": []}


# --------------------------------------------------
# Utility functions of sender
# --------------------------------------------------

def send_info(url, payload):
    """Send payload to a node's HTTP endpoint."""
    try:
        r = requests.post(url, json=payload, timeout=2)
        print(f"[SENDER] Sent info to {url}, status={r.status_code}")
    except Exception as e:
        print(f"[SENDER] Error sending info to {url}: {e}")


def calculate_tdiff(ts1: str, ts2: str) -> float:
    """
    Given two timestamp strings in the format 'MM:SS.mmm',
    compute time difference ts2 - ts1.
    """
    def parse_ts(ts: str) -> float:
        try:
            minutes, rest = ts.split(":")
            seconds, millis = rest.split(".")
            return int(minutes) * 60 + int(seconds) + int(millis) / 1000.0
        except Exception:
            return 0.0

    return parse_ts(ts2) - parse_ts(ts1)


def starting_werner_recalculate_sender(epr_id, result_recv, listener_emiter_port):
    """
    Ask the emitter-side listener to start a Werner recalculation
    for a given EPR id and its receive metadata.
    """
    msg = {"accion": "recalculate", "id": epr_id, "info": result_recv}
    print("Sending recalculating")
    print(listener_emiter_port)
    try:
        with socket.create_connection(("localhost", listener_emiter_port), timeout=3) as s:
            s.send(json.dumps(msg).encode())
            resp = s.recv(4096).decode()
            return json.loads(resp)
    except Exception as e:
        print(f"[SOCKET ERROR] Could not connect to {listener_emiter_port}: {e}")
        return None


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
# Werner decay monitor (sender side)
# --------------------------------------------------

def monitor_werner_swap(new_id, old_id, new_epr, order):
    """
    Erase the old_epr used for swapping, 
    monitor a qubit locally from a swapping, update local node_info, and notify master.
    """
    del epr_store[old_id]

    result_measure = {"id": epr_id, "medicion": m, "state": order}

    # Notify via HTTP
    try:
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=result_measure, timeout=2)
    except Exception as e:
        print(f"[MEASURE_SENDER] Error notifying endpoints: {e}")

    return result_measure


def recalculate_werner(epr_id, result_recv, conn,
                       node_info, role,
                       my_port=None, other_port=None,
                       epr_id_before=None,
                       interval=0.01, threshold=1/3):
    """
    Continuously update Werner fidelity until threshold is reached.
    This runs on the node that owns the qubit in epr_store[epr_id].
    """
    w_in = float(result_recv.get("w_gen", 1.0))
    t_gen = result_recv.get("t_gen", "0")
    tcoh = float(result_recv.get("tcoh", 10.0))
    print(f"[SENDER] Recalculating Werner from {epr_id}")

    while True:
        t_now = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"
        tdif = calculate_tdiff(t_gen, t_now)
        w_out = w_in * math.exp(-tdif / tcoh)

        # Update local EPR store
        if epr_id in epr_store:
            epr_store[epr_id]["w_out"] = w_out
        else:
            break

        # Threshold reached → measure previous EPR if requested
        if w_out <= threshold:
            print(f"[COHERENCE] EPR {epr_id} reached w={w_out:.3f} at {t_now}, measuring...")
            if role == "receiver":
                print(f"Measuring {epr_id}")
                measure_epr(epr_id, node_info, conn, my_port, order="measure")
            break

        time.sleep(interval)


def start_monitor(epr_id, result_recv, conn,
                  node_info, role,
                  my_port=None, other_port=None, epr_id_before=None, ):
    """
    Start coherence monitor in a background thread.
    This is always launched on the node that owns the qubit
    that will eventually be measured.
    """
    threading.Thread(
        target=recalculate_werner,
        args=(epr_id, result_recv, conn, node_info, role, my_port, other_port, epr_id_before),
        daemon=True
    ).start()


# --------------------------------------------------
# EPR receiving
# --------------------------------------------------

def recibir_epr(payload, node_info, conn, my_port, emisor_port, listener_port):
    epr_id = payload.get("id", 0)
    state = payload.get("state", "fallo")
    resultado_recv = {
        "id": epr_id,
        "vecino": payload.get("vecino"),
        "t_gen": payload.get("t_gen"),
        "t_recv": None,
        "t_diff": None,
        "w_gen": payload.get("w_gen"),
        "w_out": None,
        "state": state,
        "medicion": None,
        "distancia_nodos": None,
        "listener_port": None
    }

    if state == "ok":
        try:
            q = conn.recvEPR()
            # Store qubit in local memory
            epr_store[epr_id] = {
                "q": q,
                "other_port": emisor_port
            }

            w_in = float(payload.get("w_gen", 1.0))

            # Time stamps
            t_gen_str = payload.get("t_gen", "0")
            t_recv_str = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"

            tdif = calculate_tdiff(t_gen_str, t_recv_str)

            dist_km = float(node_info.get("distkm", 0.0))
            tcoh = float(node_info.get("tcoh", 10.0))
            tesp = dist_km / (2.0/3.0 * C)

            w_out = w_in * math.exp(-(tdif + tesp) / tcoh)

            resultado_recv["w_out"] = w_out
            resultado_recv["t_recv"] = t_recv_str
            resultado_recv["t_diff"] = tdif
            resultado_recv["state"] = "active"
            vecino = payload["vecino"]

            resultado_recv["distancia_nodos"] = next(
                v["distanceKm"] for v in node_info["neighbors"] if v["id"] == vecino
            )

            resultado_recv["listener_port"] = listener_port

            # Start the background coherence monitor HERE on the receiver side
            start_monitor(
                epr_id,
                resultado_recv,
                conn,
                node_info,
                role = "receiver",
                my_port=my_port,
                other_port=emisor_port
            )

        except CQCTimeoutError:
            resultado_recv["state"] = "timeout"
        except Exception as e:
            print(f"[RECEIVER] Error : {e}")
            resultado_recv["state"] = "error"
    else:
        resultado_recv["state"] = "EPR not received"

    # Update local memory
    pares = node_info.get("parEPR", [])
    updated = False
    for i, epr in enumerate(pares):
        if epr.get("id") == epr_id:
            pares[i] = resultado_recv
            updated = True
            break
    if not updated:
        pares.append(resultado_recv)
    node_info["parEPR"] = pares

    # Notify endpoints
    try:
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=resultado_recv, timeout=2)
        if emisor_port:
            resultado_recv["vecino"] = node_info["id"]
            requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=resultado_recv, timeout=2)
            listener_emiter_port = emisor_port + 4000
            starting_werner_recalculate_sender(epr_id, resultado_recv, listener_emiter_port)

    except Exception as e:
        print(f"[RECEIVER] Error notifying endpoints: {e}")

    return resultado_recv


def measure_epr(epr_id, node_info, conn, my_port=None, order=None):
    """
    Measure a locally stored EPR (receiver side) and notify both this node
    and the original emitter.
    """
    entry = epr_store.get(epr_id)
    print("MEASURING!!")
    if entry:
        q = entry["q"]
        other_port = entry.get("other_port")

        print("EPR ID:", epr_id, "emitter port:", other_port)

        # Only skip measurement if truly marked as 'swapped' OR 'consumed'
        if order not in ("swapped", "consumed"):
            m = q.measure()
        else:
            m = None

        for epr in node_info["parEPR"]:
            if epr["id"] == epr_id:
                epr["state"] = order
                epr["medicion"] = m

        del epr_store[epr_id]
        result_measure = {"id": epr_id, "medicion": m, "state": order}

        try:
            if my_port:
                requests.post(f"http://localhost:{my_port}/parEPR/recv", json=result_measure, timeout=2)
            if emisor_port:
                requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=result_measure, timeout=2)
        except Exception as e:
            print(f"[RECEIVER] Error notifying endpoints: {e}")

        return result_measure

    return None


def pick_pair_same_edge_swap(node_info, my_port, timeout=5.0, interval=0.01):
    """
    Wait up to `timeout` seconds for two 'active' EPRs on the same node,
    but each one must have a different neighbor.
    Returns (epr1, epr2, status):
      status = "valid" -> two 'active' with different neighbors
      status = "none"  -> no usable pair
    """
    start = time.time()
    while time.time() - start < timeout:
        active = [e for e in node_info.get("parEPR", []) if e.get("state") == "active"]
        for e1, e2 in combinations(active, 2):
            if e1.get("vecino") != e2.get("vecino"):
                return e1, e2, "valid"
        try:
            node_info = requests.get(f"http://localhost:{my_port}/info", timeout=2).json()
        except Exception:
            pass
        time.sleep(interval)
    return None, None, "none"


def sending_monitor(msg, listener_port):
    """
    Send a generic monitor message to a node-side listener via TCP.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", listener_port))
    s.send(json.dumps(msg).encode())
    resp = s.recv(4096).decode()
    s.close()
    return json.loads(resp)


def do_swapping(epr1, epr2, id_swap, node_info, conn,
                destinatarios=None, destinatarios_ports=None,
                pswap=1.0, listener_port=None,
                my_port=None, ports_involved=None):
    """
    Perform entanglement swapping between two EPRs.
    """
    print(f"[SWAP] Starting swapping for EPRs {epr1['id']},{epr2['id']} at node {node_info['id']}")
    print("[DEBUG] epr_store:", epr_store)

    # Retrieve qubits
    entry1 = epr_store.get(epr1["id"])
    entry2 = epr_store.get(epr2["id"])
    if not entry1 or not entry2:
        return {"error": "One or both EPRs not found"}

    # Extract qubits
    q1 = entry1["q"]
    q2 = entry2["q"]

    # Bell measurement: CNOT + Hadamard
    q1.cnot(q2)
    q1.H()


    order = "swapped"

    # Consume original EPRs
    measure_epr(epr1["id"], node_info, conn, my_port, order)
    measure_epr(epr2["id"], node_info, conn, my_port, order)

    # Derived fields
    t_gen_str = epr1.get("t_gen")
    t_recv_str = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"
    tdif = calculate_tdiff(t_gen_str, t_recv_str)
    w_gen_tuple = (epr1.get("w_out"), epr2.get("w_out"))
    w_out_new = (w_gen_tuple[0] * w_gen_tuple[1]) if all(w_gen_tuple) else None
    distancia_total = (epr1.get("distancia_nodos") or 0) + (epr2.get("distancia_nodos") or 0)

    # New swapped EPR (metadata)
    swapped_epr = {
        "id": id_swap,
        "vecino": destinatarios,
        "state": "active",
        "medicion": None,
        "t_gen": t_gen_str,
        "t_recv": t_recv_str,
        "t_diff": tdif,
        "w_gen": w_gen_tuple,
        "w_out": w_out_new,
        "distancia_nodos": distancia_total,
        "listener_port": None
    }
    node_info["parEPR"].append(swapped_epr)

    # Notify endpoints
    result_swap = {
        "id": f"{str(epr1['id'])}_{str(epr2['id'])}",
        "vecino": swapped_epr["vecino"],
        "state": "swapper",
    }
    try:
        monitor_msg = {
            "accion": "watch_over_and _kill",
            "new_id": id_swap,
            "old_id" : None,
            "new_epr": swapped_epr.copy,
            "order": None
        }

        if destinatarios_ports and len(destinatarios_ports) == 2 and len(destinatarios) == 2:
            # Send swapped EPR metadata to each neighbor
            epr_msg1 = swapped_epr.copy()
            epr_msg1["vecino"] = destinatarios[1]
            epr_msg1["w_gen"] = w_gen_tuple[0]
            epr_msg1["listener_port"] = ports_involved[0]
            print("Notifying", destinatarios[0], "on port", destinatarios_ports[0])
            requests.post(f"http://localhost:{destinatarios_ports[0]}/parEPR/recv", json=epr_msg1, timeout=2)

            epr_msg2 = swapped_epr.copy()
            epr_msg2["vecino"] = destinatarios[0]
            epr_msg2["w_gen"] = w_gen_tuple[1]
            epr_msg2["listener_port"] = ports_involved[1]
            print("Notifying", destinatarios[1], "on port", destinatarios_ports[1])
            requests.post(f"http://localhost:{destinatarios_ports[1]}/parEPR/recv", json=epr_msg2, timeout=2)

        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/swap", json=result_swap, timeout=2)

        # Updating their EPR and watch over it, making one of them measured it if it reaches the threshold
        monitor_msg["old_id"] = epr1["id"]
        monitor_msg["order"] = "measured" 
        sending_monitor(monitor_msg, ports_involved[0])
        monitor_msg["old_id"] = epr2["id"]
        monitor_msg["order"] = "just_watch_over" 
        sending_monitor(monitor_msg, ports_involved[1])

    except Exception as e:
        print(f"[SWAP] Error notifying endpoints: {e}")

    print(f"[SWAP] Swapping complete, new EPR {swapped_epr['id']} registered in the extreme nodes")
    return {"status": "ok", "swapped_epr": result_swap}


# --------------------------------------------------
# Socket handling (unified)
# --------------------------------------------------

def handle_client_unified(conn_sock,
                          node_info, conn,
                          my_port, emisor_port):
    """Unified handler for ALL socket actions."""
    try:
        conn_sock.settimeout(5.0)
        data = conn_sock.recv(4096)
        if not data:
            return

        payload = json.loads(data.decode())
        accion = payload.get("accion")

        print(f"[LISTENER] Acción recibida: {accion}")

        # --------------------------------------------------
        # GENERATE EPR
        # --------------------------------------------------
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

        # --------------------------------------------------
        # RECIBE EPR
        # --------------------------------------------------
        elif accion == "recibe EPR":
            resultado = recibir_epr(
                payload.get("epr_obj"),
                payload.get("node_info", node_info),
                conn,
                payload.get("my_port", my_port),
                payload.get("emisor_port", emisor_port),
                payload.get("listener_port")
            )
            conn_sock.send(json.dumps(resultado).encode())

        # --------------------------------------------------
        # MEASURE (purified)
        # --------------------------------------------------
        elif accion == "purified":
            epr_id = payload.get("id")
            result = measure_epr(epr_id, node_info, conn, my_port, "Consumed")
            conn_sock.send(json.dumps(result or {"error": "EPR not found"}).encode())

        # --------------------------------------------------
        # MONITOR WERNER
        # (rarely used now; main path is 'recalculate')
        # --------------------------------------------------
        elif accion == "monitor_werner":
            start_monitor(
                payload.get("id"),
                payload.get("info"),
                conn,
                node_info,
                role = "receiver",
                my_port=my_port,
                other_port=payload.get("other_port"),
                epr_id_before=payload.get("id_before")
            )
            conn_sock.send(json.dumps({"status": "monitoring"}).encode())

        # --------------------------------------------------
        # RECALCULATE (sender-side monitor start)
        # --------------------------------------------------
        elif accion == "recalculate":
            start_monitor(
                payload["id"],
                payload["info"],
                conn,
                node_info,
                role = "sender",
                my_port=my_port,
                other_port=payload.get("other_port"),
                epr_id_before=payload.get("id_before")
            )
            conn_sock.send(json.dumps({"status": "monitor started"}).encode())

        # --------------------------------------------------
        # WATCH OVER (swapped EPR monitor)
        # --------------------------------------------------
        elif accion == "watch_over_and _kill":
            start_monitor(
                payload["id"],              # new swapped EPR id
                payload.get("EPR_pair"),    # metadata of the new EPR
                conn,
                node_info,
                role = "swapped_epr",
                my_port=payload.get("my_port"),
                other_port=payload.get("other_port"),
                epr_id_before=payload.get("id_before")
            )
            conn_sock.send(json.dumps({"status": "watching"}).encode())

        # --------------------------------------------------
        # DO SWAPPING
        # --------------------------------------------------
        elif accion == "do swapping":
            node_info_in = payload.get("node_info", node_info)
            destinatarios = payload.get("destinatarios", [])
            destinatarios_ports = payload.get("destinatarios_ports", [])
            pswap = float(payload.get("pswap", 1.0))
            listener_port_in = payload.get("listener_port")
            my_port_in = payload.get("my_port", my_port)
            ports_involved = payload.get("ports_involved", [])
            id_swap = str(payload.get("id", 0))

            epr1, epr2, status = pick_pair_same_edge_swap(node_info_in, my_port_in)

            if status != "valid":
                conn_sock.send(json.dumps({"error": "No valid pair"}).encode())
            else:
                result = do_swapping(
                    epr1=epr1,
                    epr2=epr2,
                    id_swap=id_swap,
                    node_info=node_info_in,
                    conn=conn,
                    destinatarios=destinatarios,
                    destinatarios_ports=destinatarios_ports,
                    pswap=pswap,
                    listener_port=listener_port_in,
                    my_port=my_port_in,
                    ports_involved=ports_involved
                )
                conn_sock.send(json.dumps(result).encode())

        else:
            conn_sock.send(json.dumps({"error": f"Unknown action {accion}"}).encode())

    except Exception as e:
        print(f"[LISTENER ERROR] {e}")
    finally:
        conn_sock.close()


def socket_listener(node_info, conn, port,
                    my_port=None, emisor_port=None):
    """Unified TCP listener for ALL EPR actions."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(50)

    print(f"[LISTENER] Listening on port {port}")

    try:
        while True:
            conn_sock, addr = server.accept()
            threading.Thread(
                target=handle_client_unified,
                args=(conn_sock, node_info, conn, my_port, emisor_port),
                daemon=True
            ).start()

    except KeyboardInterrupt:
        print("[LISTENER] Interrupted, closing...")
    finally:
        server.close()


# --------------------------------------------------
# Main
# --------------------------------------------------

if __name__ == "__main__":
    mode = sys.argv[1]

    # -----------------------------------------
    # MODE: start as SENDER
    # -----------------------------------------
    if mode == "sender_init":
        emisor        = sys.argv[2]
        receptor      = sys.argv[3]
        my_port       = int(sys.argv[4])
        target_port   = int(sys.argv[5])
        pgen          = float(sys.argv[6])
        epr_id        = sys.argv[7]
        node_info     = json.loads(sys.argv[8])
        listener_port = int(sys.argv[9])

        print(f"[SENDER INIT] {emisor}")
        with CQCConnection(emisor) as conn:
            print("Running in sender mode")
            generar_epr(
                emisor, receptor, conn,
                my_port, target_port,
                pgen, epr_id, node_info
            )

            socket_listener(
                node_info,
                conn,
                port=listener_port,
                my_port=my_port,
                emisor_port=target_port
            )

    # -----------------------------------------
    # MODE: start as RECEIVER
    # -----------------------------------------
    elif mode == "receiver_init":
        payload       = json.loads(sys.argv[2])  # epr_obj
        node_info     = json.loads(sys.argv[3])
        my_port       = int(sys.argv[4])
        emisor_port   = int(sys.argv[5])
        listener_port = int(sys.argv[6])

        print(f"[RECEIVER INIT] {node_info['id']}")
        with CQCConnection(node_info["id"]) as conn:
            resultado = recibir_epr(payload, node_info, conn, my_port, emisor_port, listener_port)
            print(f"[RECEIVER] Initial synchronization result: {resultado}")

            socket_listener(
                node_info,
                conn,
                port=listener_port,
                my_port=my_port,
                emisor_port=emisor_port
            )

    else:
        raise ValueError(f"Unknown mode in worker.py: {mode}")
