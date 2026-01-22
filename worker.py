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

    return abs(parse_ts(ts2) - parse_ts(ts1))


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
        print("\n================ SIMULAQRON DEBUG ================")
        print("[DEBUG] Attempting createEPR")
        print("[DEBUG] Local node:", conn.name)
        print("[DEBUG] Target node (raw):", repr(receptor))
        print("==================================================\n")


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
def recalculate_werner(epr_id, result_recv, conn,
                       node_info, role,
                       my_port=None, other_port=None,
                       old_id = None,
                       interval=0.01, threshold=1/3):
    """
    Continuously update Werner fidelity until threshold is reached.
    This runs on the node that owns the qubit in epr_store[epr_id].
    """

    w_in = float(result_recv.get("w_out", 1.0)) #Recalculates from the last updated Werner
    t_gen = result_recv.get("t_gen", "0")
    tcoh = float(result_recv.get("tcoh", 10.0))
    print(f"[MONITOR] Recalculating Werner from {epr_id}")

    if old_id != None:
        print(f"[MONITOR] Deleting from the cache the old_id {old_id} because of swapping")
        del epr_store[old_id]

    print(f"Hi, im monitorizing {epr_id} that enter with {w_in}")
    while True:
        if epr_id in epr_store and epr_store[epr_id].get("protected"):
            print(f"[MONITOR] EPR {epr_id} protected. Stopping monitor.")
            break

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
            if role in ("receiver", "kill_if_reached"):
                print(f"Measuring {epr_id}")
                measure_epr(epr_id, node_info, conn, my_port, order="measure")
            elif role == "no_kill":
                print(f"Changing state{epr_id}")
            break

        time.sleep(interval)


def start_monitor(epr_id, result_recv, conn,
                  node_info, role,
                  my_port=None, other_port=None, old_id=None):
    """
    Start coherence monitor in a background thread.
    This is always launched on the node that owns the qubit
    that will eventually be measured.
    """
    threading.Thread(
        target=recalculate_werner,
        args=(epr_id, result_recv, conn, node_info, role, my_port, other_port, old_id),
        daemon=True
    ).start()

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

        print("EPR ID:", epr_id, ", my_port", my_port,", other_port", other_port)

        # Only skip measurement if truly marked as 'swapped' OR 'consumed'
        if order not in ("swapped", "consumed", "no_kill"):
            try:
                m = q.measure()
            except Exception as e:
                print(f"[MEASURE] Could not measure {epr_id}: {e}")
                m = None
        else:
            m = None
        for epr in node_info["parEPR"]:
            if epr["id"] == epr_id and epr["state"] == "active":
                epr["state"] = order
                epr["medicion"] = m

        del epr_store[epr_id]
        result_measure = {"id": epr_id, "medicion": m, "state": order}

        try:
            if my_port:
                requests.post(f"http://localhost:{my_port}/parEPR/recv", json=result_measure, timeout=2)
            if other_port:
                requests.post(f"http://localhost:{other_port}/parEPR/recv", json=result_measure, timeout=2)
        except Exception as e:
            print(f"[ORDER] Error notifying endpoints of a measure with ports: {my_port}, {other_port} with this msg: {result_measure} and error: {e}")

        return result_measure

    return None


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
        print("[RECEIVER] EPR not reveived")
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
        print("[RECEIVER] Success on receiving the EPR, sending update states to sender and master")
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=resultado_recv, timeout=2)
        if emisor_port:
            resultado_recv["vecino"] = node_info["id"]
            requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=resultado_recv, timeout=2)
            listener_emiter_port = emisor_port + 4000
            starting_werner_recalculate_sender(epr_id, resultado_recv, listener_emiter_port)

    except Exception as e:
        print(f"[RECEIVER] Error notifying endpoints of a receiving with ports: {my_port}, {emisor_port} with this msg: {resultado_recv} and error: {e}")

    return resultado_recv


def pick_pair_same_edge_swap(node_info, my_port, dest1, dest2, timeout=5.0, interval=0.01):
    """
    Pick two 'active' EPRs on this node that:
      - have different neighbors and the repeater shares a EPR with both
      - have NOT been used already in a previous swap (swapped).
    """
    start = time.time()
    my_id = node_info["id"]

    while time.time() - start < timeout:
        par = node_info.get("parEPR", [])
        # 1. EPRs already used in a swap
        used_ids = set()
        for e in par:
            if e.get("state") == "swapper":
                used_ids.update(str(e["id"]).split("_"))
        # 2. EPRs whose qubit is still active
        alive = [
            e for e in par
            if e["id"] in epr_store and e.get("state") == "active" and e["id"] not in used_ids
        ]
        # 3. Find two EPRs with different endpoints AND valid for this repeater
        for e1, e2 in combinations(alive, 2):
            if e1["vecino"] in (dest1, dest2) and e2["vecino"] in (dest1, dest2):
                if e1["vecino"] != e2["vecino"]:
                    return e1, e2, "valid"

        
        
        # 4. Refresh
        try:
            node_info = requests.get(f"http://localhost:{my_port}/info", timeout=2).json()
        except:
            pass

        time.sleep(interval)

    return None, None, "none"

def assign_old_ids(node_info, old_id1, old_id2, dest1, dest2):
    """
    Given node_info, two old_ids (the ones used in THIS swap),
    and two destination neighbors, determine which old_id belongs
    to which destination, considering ONLY those two ids.
    """

    candidates = {old_id1, old_id2}

    def get_old_id_for_neighbor(neighbor):
        for epr in node_info.get("parEPR", []):
            if epr.get("vecino") == neighbor and epr.get("id") in candidates:
                return epr.get("id")
        return None

    correct1 = get_old_id_for_neighbor(dest1)
    correct2 = get_old_id_for_neighbor(dest2)

    # If already correct
    if old_id1 == correct1 and old_id2 == correct2:
        return old_id1, old_id2

    # If swapped
    if old_id1 == correct2 and old_id2 == correct1:
        return correct1, correct2

    # Fallback: enforce mapping from node_info
    return correct1, correct2



def sending_monitor(msg, listener_port):
    """
    Send a generic monitor message to a node-side listener via TCP.
    """
    # Force conversion to int if needed 
    try: 
        listener_port = int(listener_port) 
    except Exception: 
        raise ValueError(f"Invalid listener_port: {listener_port}")
    
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

    # refresh node_info once after swap to catch latest parEPR 
    try: 
        node_info = requests.get(f"http://localhost:{my_port}/info", timeout=2).json() 
    except: 
        pass

    old_id_A, old_id_B = assign_old_ids(
        node_info,
        epr1["id"],
        epr2["id"],
        destinatarios[0],
        destinatarios[1]
    )
    print("Sin ordenar",epr1["id"],epr2["id"])
    print("Ordenados",old_id_A,old_id_B)
    print(f"[SWAP] It has: {node_info}")


    # Tell both endpoints to stop monitoring the old EPRs
    stop_msg_1 = {
        "accion": "stop_monitor",
        "id": old_id_A
    }
    stop_msg_2 = {
        "accion": "stop_monitor",
        "id": old_id_B
    }
    sending_monitor(stop_msg_1, str(ports_involved[0]))
    sending_monitor(stop_msg_2, str(ports_involved[1]))


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
        "t_gen": t_recv_str,
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
        monitor_msg_A = {
            "accion": "watch_over",
            "order": "kill_if_reached",
            "id": id_swap,
            "old_id": old_id_A,
            "EPR_pair": epr_msg1,
            "my_port": int(destinatarios_ports[0]),
            "other_port": int(destinatarios_ports[1])
        }
        monitor_msg_B = {
            "accion": "watch_over",
            "order": "no_kill",
            "id": id_swap,
            "old_id": old_id_B,
            "EPR_pair": epr_msg2,
            "my_port": int(destinatarios_ports[1]),
            "other_port": int(destinatarios_ports[0])
        }

        print(f"Mando el watch a estos puertos: {ports_involved}")

        print("AAAAAAAAAAAAAAAAAAAAAAAAAA")
        print(monitor_msg_A)
        sending_monitor(monitor_msg_A, str(ports_involved[0]))
        print("AAAAAAAAAAAAAAAAAAAAAAAAAA")
        print("BBBBBBBBBBBBBBBBBBBBBBBBBB")
        print(monitor_msg_B)
        sending_monitor(monitor_msg_B, str(ports_involved[1]))
        print("BBBBBBBBBBBBBBBBBBBBBBBBBB")

    except Exception as e:
        print(f"[SWAP] Error notifying endpoints: {e}")

    print(f"[SWAP] Swapping complete, new EPR {swapped_epr['id']} registered in the extreme nodes")
    return {"status": "ok", "swapped_epr": result_swap}


# --------------------------------------------------
# Socket handling (unified)
# --------------------------------------------------
def handle_client_unified(conn_sock, conn, my_port, emisor_port):
    """Unified handler for ALL socket actions."""
    try:
        conn_sock.settimeout(5.0)
        data = conn_sock.recv(4096)
        if not data:
            return

        payload = json.loads(data.decode())
        accion = payload.get("accion")

        print(f"[LISTENER] Acción recibida: {accion}")
        try: 
            node_info = requests.get(f"http://localhost:{my_port}/info", timeout=2).json() 
        except: 
            pass

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
                node_info
            )
            conn_sock.send(json.dumps({"status": "ok"}).encode())

        # --------------------------------------------------
        # RECIBE EPR
        # --------------------------------------------------
        elif accion == "recibe EPR":
            resultado = recibir_epr(
                payload.get("epr_obj"),
                node_info,
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
        # RECALCULATE (sender-side monitor start)
        # --------------------------------------------------
        elif accion == "recalculate":
            if payload["info"] != "active":
                 print("[LISTENER] Ignoring recalculate because EPR is not active") 
                 conn_sock.send(json.dumps({"status": "monitor ignored"}).encode())
            else:
                start_monitor(
                    payload["id"],
                    payload["info"],
                    conn,
                    node_info,
                    role = "sender",
                    my_port=my_port,
                    other_port=payload.get("other_port")
                )
                conn_sock.send(json.dumps({"status": "monitor started"}).encode())

        # --------------------------------------------------
        # WATCH OVER (swapped EPR monitor)
        # --------------------------------------------------
        elif accion == "watch_over":
            other_port=payload.get("other_port")
            old_id=payload.get("old_id", None)
            print(f"Watching over {payload['id']}, that was {old_id} before")
            print("[DEBUG] epr_store full:", epr_store)

            if old_id not in epr_store:
                print(f"[WATCH_OVER] old_id {old_id} no existe en este nodo. Creando entrada vacía.")
                epr_store[payload["id"]] = {"q": None, "other_port": other_port}
            else:
                epr_store[payload["id"]] = {
                    "q": epr_store[old_id]["q"],
                    "other_port": other_port
                }
            start_monitor(
                payload["id"],              # new swapped EPR id
                payload.get("EPR_pair"),    # metadata of the new EPR
                conn,
                node_info,
                role = payload.get("order"),   # <--- Diference between measuring or just watch
                my_port=payload.get("my_port"),
                other_port=other_port,
                old_id=old_id
            )
            conn_sock.send(json.dumps({"status": "watching"}).encode())


        # --------------------------------------------------
        # DO SWAPPING
        # --------------------------------------------------
        elif accion == "do swapping":
            destinatarios = payload.get("destinatarios", [])
            destinatarios_ports = payload.get("destinatarios_ports", [])
            pswap = float(payload.get("pswap", 1.0))
            listener_port_in = payload.get("listener_port")
            my_port_in = payload.get("my_port", my_port)
            ports_involved = payload.get("ports_involved", [])
            id_swap = str(payload.get("id", 0))

            epr1, epr2, status = pick_pair_same_edge_swap(node_info, my_port_in, destinatarios[0], destinatarios[1])

            if status != "valid":
                conn_sock.send(json.dumps({"error": "No valid pair"}).encode())
            else:
                result = do_swapping(
                    epr1=epr1,
                    epr2=epr2,
                    id_swap=id_swap,
                    node_info=node_info,
                    conn=conn,
                    destinatarios=destinatarios,
                    destinatarios_ports=destinatarios_ports,
                    pswap=pswap,
                    listener_port=listener_port_in,
                    my_port=my_port_in,
                    ports_involved=ports_involved
                )
                conn_sock.send(json.dumps(result).encode())
        elif accion == "stop_monitor":
            epr_id = payload["id"]
            print(f"[LISTENER] Stop monitor for {epr_id}")
            if epr_id in epr_store:
                epr_store[epr_id]["protected"] = True
            conn_sock.send(json.dumps({"status": "stopped"}).encode())


        else:
            conn_sock.send(json.dumps({"error": f"Unknown action {accion}"}).encode())

    except Exception as e:
        print(f"[LISTENER ERROR] {e}")
    finally:
        conn_sock.close()


def socket_listener(conn, port,
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
                args=(conn_sock, conn, my_port, emisor_port),
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
                conn,
                port=listener_port,
                my_port=my_port,
                emisor_port=emisor_port
            )

    else:
        raise ValueError(f"Unknown mode in worker.py: {mode}")
