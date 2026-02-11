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

#session = requests.Session()

conn_lock = threading.Lock()


# Speed of light in fiber (km/s approximation)
C = 3e5

# Local EPR memory
epr_store = {}
nodo_info = {"pairEPR": []}

# ---------------------------
# CVS & PLOTS
# ---------------------------
import csv


def export_timestamps_to_csv(log_file="latencies/timestamps_log_afterx2_2.txt",
                             csv_file="latencies/timestamps_afterx2_2.csv"):
    rows = []

    with open(log_file, "r") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) < 3:
                continue

            # --- FIX: skip any line that does NOT contain an ID= field ---
            if "ID=" not in parts[1]:
                continue

            event = parts[0].strip("[]")
            epr_id = parts[1].split("=")[1]

            entry = {"event": event, "id": epr_id}

            for p in parts[2:]:
                if "=" in p:
                    k, v = p.split("=")
                    entry[k] = v

            rows.append(entry)

    fieldnames = sorted({key for row in rows for key in row.keys()})

    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] CSV generated: {csv_file}")


import matplotlib
matplotlib.use("Agg")   # backend sin GUI
import matplotlib.pyplot as plt


def plot_latencies(csv_file="latencies/timestamps_afterx2_2.csv"):
    df = pd.read_csv(csv_file)

    backend = df[df["event"] == "CreateEPR_backend"]["t_diff"].astype(float)
    notify  = df[df["event"] == "CreateEPR_notify"]["t_diff"].astype(float)
    total   = df[df["event"] == "CreateEPR_total"]["t_diff"].astype(float)
    master = df[df["event"] == "MASTER PROCESSED (ZMQ)"]["t_diff"].astype(float)

    plt.close('all')
    fig = plt.figure(figsize=(10,6))
    plt.plot(backend.values, label="Backend latency (createEPR)")
    plt.plot(notify.values, label="Notify latency (HTTP)")
    plt.plot(master.values, label="Master updates")
    plt.plot(total.values, label="Total EPR generation latency")
    

    plt.xlabel("EPR index")
    plt.ylabel("Tiempo (s)")
    plt.title("Latencias de generación EPR")
    plt.grid(True)
    plt.legend()
    plt.tight_layout()

    fig.savefig("latencies/latencias_epr_afterx2_2.png")
    plt.close(fig)
    print("[OK] Gráfica guardada en latencies/latencias_epr.png")

import pandas as pd

def compute_latency_stats(csv_file="latencies/timestamps_afterx2_2.csv"):

    df = pd.read_csv(csv_file)

    backend = df[df["event"] == "CreateEPR_backend"]["t_diff"].astype(float)
    notify  = df[df["event"] == "CreateEPR_notify"]["t_diff"].astype(float)
    total   = df[df["event"] == "CreateEPR_total"]["t_diff"].astype(float)
    master = df[df["event"] == "MASTER PROCESSED (ZMQ)"]["t_diff"].astype(float)

    # Compute stats and store them in variables
    media_create = backend.mean()
    std_create   = backend.std()
    min_create   = backend.min()
    max_create   = backend.max()

    media_notify = notify.mean()
    std_notify   = notify.std()
    min_notify   = notify.min()
    max_notify   = notify.max()

    media_total = total.mean()
    std_total   = total.std()
    min_total   = total.min()
    max_total   = total.max()

    media_master = master.mean()
    std_master   = master.std()
    min_master   = master.min()
    max_master   = master.max()
    

    # Print to console
    print("\n===== ESTADÍSTICAS DE LATENCIA =====")
    print("Backend createEPR:")
    print("  media:", media_create)
    print("  std:", std_create)
    print("  min:", min_create)
    print("  max:", max_create)

    print("\nNotificación HTTP:")
    print("  media:", media_notify)
    print("  std:", std_notify)
    print("  min:", min_notify)
    print("  max:", max_notify)

    print("\nTotal generación EPR:")
    print("  media:", media_total)
    print("  std:", std_total)
    print("  min:", min_total)
    print("  max:", max_total)



    # Save to TXT
    with open("latencies/latencias_epr_afterx2_2.txt", "w") as f:
        f.write("===== ESTADÍSTICAS DE LATENCIA =====\n")
        f.write("Backend createEPR:\n")
        f.write(f"  media: {media_create}\n")
        f.write(f"  std: {std_create}\n")
        f.write(f"  min: {min_create}\n")
        f.write(f"  max: {max_create}\n\n")

        f.write("Notificación HTTP:\n")
        f.write(f"  media: {media_notify}\n")
        f.write(f"  std: {std_notify}\n")
        f.write(f"  min: {min_notify}\n")
        f.write(f"  max: {max_notify}\n\n")

        f.write("Noticicación master zmq:\n")
        f.write(f"  media: {media_master}\n")
        f.write(f"  std: {std_master}\n")
        f.write(f"  min: {min_master}\n")
        f.write(f"  max: {max_master}\n\n")

        f.write("Total generación EPR:\n")
        f.write(f"  media: {media_total}\n")
        f.write(f"  std: {std_total}\n")
        f.write(f"  min: {min_total}\n")
        f.write(f"  max: {max_total}\n")


    print("[OK] Estadísticas guardadas en latencias_epr.txt")







# --------------------------------------------------
# HIGH PRECISION TIMESTAMPS
# --------------------------------------------------

def timestamp_precise():
    """
    Returns a timestamp in the same style as t_gen/t_recv (MM:SS.xxxxxx)
    but with microsecond precision.
    """
    now = time.time()
    mmss = time.strftime("%M:%S.", time.localtime(now))
    usec = int((now % 1) * 1_000_000)
    return f"{mmss}{usec:06d}"


def timestamp_to_seconds(ts):
    """
    Convert 'MM:SS.xxxxxx' into float seconds.
    """
    mm, rest = ts.split(":")
    ss, us = rest.split(".")
    return int(mm)*60 + int(ss) + int(us)/1_000_000


def diff_precise(t1, t2):
    """
    Compute difference between two precise timestamps.
    """
    return timestamp_to_seconds(t2) - timestamp_to_seconds(t1)

# --------------------------------------------------
# TIMESTAMPS DEBUGGER
# --------------------------------------------------
TIMESTAMP_LOG = "latencies/timestamps_log_afterx2_2.txt"

def log_timestamp(event_type, epr_id, **fields):
    line = f"[{event_type}]  ID={epr_id}"
    for k, v in fields.items():
        line += f"  {k}={v}"
    line += "\n"
    with open(TIMESTAMP_LOG, "a") as f:
        f.write(line)


# --------------------------------------------------
# Utility functions of sender
# --------------------------------------------------
import zmq
import msgpack

# Global ZeroMQ context shared by all sockets.
context = zmq.Context()

# Cache of PUSH sockets, one per destination address.
# This avoids reconnecting on every send, which is expensive.
zmq_sockets = {}

def get_zmq_socket(addr):
    """
    Returns a PUSH socket connected to the given ZeroMQ address.
    If the socket does not exist yet, it is created and cached.
    This ensures persistent connections and minimal overhead.
    """
    if addr not in zmq_sockets:
        sock = context.socket(zmq.PUSH)
        sock.connect(addr)  # Establish a persistent connection
        zmq_sockets[addr] = sock
        print(f"[ZeroMQ] Connected PUSH → {addr}")
    return zmq_sockets[addr]

def send_info(url, payload):
    """
    Sends a message using ZeroMQ PUSH.
    
    Parameters:
        url:     A ZeroMQ address, e.g. 'tcp://localhost:5002'
        payload: A Python dict that will be serialized with msgpack.
                 Typically includes:
                 {
                     "route": "pairEPR/add",
                     "payload": {...}
                 }

    This function replaces the old HTTP-based sender while keeping
    the same signature for compatibility. It is extremely fast because:
        - No HTTP
        - No Flask
        - No reconnections
        - Binary serialization (msgpack)
    """
    try:
        sock = get_zmq_socket(url)
        sock.send(msgpack.packb(payload))  # Send binary-encoded message
        print(f"[SENDER] Sent via ZeroMQ to {url}")
    except Exception as e:
        print(f"[SENDER] ZeroMQ send error: {e}")


#def send_info(url, payload):
 #   """Send payload to a node's HTTP endpoint using a persistent session."""
  #  try:
   #     r = session.post(url, json=payload, timeout=2)
    #    print(f"[SENDER] Sent info to {url}, status={r.status_code}")
    #except Exception as e:
     #   print(f"[SENDER] Error sending info to {url}: {e}")


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
    msg = {"comand": "recalculate", "id": epr_id, "info": result_recv}
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

with conn_lock:

    def generar_epr(emisor, receptor, conn, emisor_port, receptor_port,
                    pgen, epr_id, node_info):

        print(f"[SENDER] {emisor} attempting EPR with {receptor} (pgen={pgen})")

        neighbors = [n["id"] for n in node_info.get("neighbors", [])]
        if receptor not in neighbors:
            send_info(
                f"tcp://localhost:{emisor_port+1000}",
                {
                    "route": "pairEPR/add",
                    "payload": {
                        "id": epr_id,
                        "neighbor": receptor,
                        "t_gen": "0",
                        "w_gen": "0"
                    }
                }
            )
            return


        if random.random() > pgen:
            for port, neighbor in [(emisor_port, receptor), (receptor_port, emisor)]:
                send_info(
                    f"tcp://localhost:{port+1000}",
                    {
                        "route": "pairEPR/add",
                        "payload": {
                            "id": epr_id,
                            "neighbor": neighbor,
                            "t_gen": "0",
                            "w_gen": "0"
                        }
                    }
                )
            return


        # --------------------------------------------------
        # 1) Total EPR generation timing
        # --------------------------------------------------
        t_total_start = timestamp_precise()

        try:
            print("\n================ SIMULAQRON DEBUG ================")
            print("[DEBUG] Attempting createEPR")
            print("[DEBUG] Local node:", conn.name)
            print("[DEBUG] Target node (raw):", repr(receptor))
            print("==================================================\n")

            # --------------------------------------------------
            # 2) Backend createEPR timing
            # --------------------------------------------------
            t_start = timestamp_precise()
            q = conn.createEPR(receptor)
            t_end = timestamp_precise()
            t_diff_create = diff_precise(t_start, t_end)

            log_timestamp("CreateEPR_backend",epr_id,t_start=t_start,t_end=t_end,t_diff=f"{t_diff_create:.6f}")

            epr_store[epr_id] = {"q": q, "w_out": 1.0, "other_port": receptor_port}

        except Exception as e:
            print(f"[SENDER] Unexpected error: {e}")
            return

        # --------------------------------------------------
        # 3) Generate t_gen timestamp
        # --------------------------------------------------
        t_gen = time.strftime("%M:%S.") + f"{int((time.time() % 1)*1000):03d}"

        # --------------------------------------------------
        # 4) Classical notification timing
        # --------------------------------------------------
        t_notify_start = timestamp_precise()

        for port, neighbor in [(emisor_port, receptor), (receptor_port, emisor)]:
            send_info(
                f"tcp://localhost:{port+1000}",
                {
                    "route": "pairEPR/add",
                    "payload": {
                        "id": epr_id,
                        "neighbor": neighbor,
                        "t_gen": t_gen,
                        "w_gen": 1.0
                    }
                }
            )


        t_notify_end = timestamp_precise()
        t_diff_notify = diff_precise(t_notify_start, t_notify_end)

        log_timestamp("CreateEPR_notify",epr_id,t_start=t_notify_start,t_end=t_notify_end,t_diff=f"{t_diff_notify:.6f}")

        # --------------------------------------------------
        # 5) Total EPR generation latency
        # --------------------------------------------------
        t_total_end = timestamp_precise()
        t_diff_total = diff_precise(t_total_start, t_total_end)

        log_timestamp("CreateEPR_total",epr_id,t_start=t_total_start,t_end=t_total_end,t_diff=f"{t_diff_total:.6f}")


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
        for epr in node_info["pairEPR"]:
            if epr["id"] == epr_id and epr["state"] == "active":
                epr["state"] = order
                epr["medicion"] = m

        del epr_store[epr_id]
        result_measure = {"id": epr_id, "medicion": m, "state": order}

        try:
            if my_port:
                requests.post(f"http://localhost:{my_port}/pairEPR/recv", json=result_measure, timeout=2)
            if other_port:
                requests.post(f"http://localhost:{other_port}/pairEPR/recv", json=result_measure, timeout=2)
        except Exception as e:
            print(f"[ORDER] Error notifying endpoints of a measure with ports: {my_port}, {other_port} with this msg: {result_measure} and error: {e}")

        return result_measure

    return None
def recibir_epr(payload, node_info, conn, my_port, emisor_port, listener_port):

    epr_id = payload.get("id", 0)
    state = payload.get("state", "fallo")
    # --- TIMESTAMP: antes de recvEPR ---
    t_start = timestamp_precise()
    # --- TIMESTAMP: entrada a la función ---
    log_timestamp("RECV_ENTER", epr_id, t=timestamp_precise())

    resultado_recv = {
        "id": epr_id,
        "neighbor": payload.get("neighbor"),
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
            log_timestamp("RECV_EPR_START", epr_id, t_start=t_start)
            with conn_lock:
                q = conn.recvEPR()

            # --- TIMESTAMP: después de recvEPR ---
            t_end = timestamp_precise()
            t_diff_recv = diff_precise(t_start, t_end)
            log_timestamp(
                "ReceiveEPR",
                epr_id,
                t_start=t_start,
                t_end=t_end,
                t_diff=f"{t_diff_recv:.6f}"
            )

            # Store qubit
            epr_store[epr_id] = {
                "q": q,
                "other_port": emisor_port
            }

            w_in = float(payload.get("w_gen", 1.0))

            # Precise t_recv
            t_gen_str = payload.get("t_gen", "0")
            t_recv_str = time.strftime("%M:%S.") + f"{int((time.time() % 1)*1000):03d}"

            tdif = calculate_tdiff(t_gen_str, t_recv_str)

            dist_km = float(node_info.get("distkm", 0.0))
            tcoh = float(node_info.get("tcoh", 10.0))
            tesp = dist_km / (2.0/3.0 * C)

            w_out = w_in * math.exp(-(tdif + tesp) / tcoh)

            resultado_recv["w_out"] = w_out
            resultado_recv["t_recv"] = t_recv_str
            resultado_recv["t_diff"] = tdif
            resultado_recv["state"] = "active"

            neighbor = payload["neighbor"]
            resultado_recv["distancia_nodos"] = next(
                v["distanceKm"] for v in node_info["neighbors"] if v["id"] == neighbor
            )

            resultado_recv["listener_port"] = listener_port

            # --- TIMESTAMP: antes de start_monitor ---
            log_timestamp("RECV_BEFORE_MONITOR", epr_id, t=timestamp_precise())

            start_monitor(
                epr_id,
                resultado_recv,
                conn,
                node_info,
                role="receiver",
                my_port=my_port,
                other_port=emisor_port
            )

        except Exception as e:
            print(f"[RECEIVER] Error : {e}")
            resultado_recv["state"] = "error"

    else:
        print("[RECEIVER] EPR not received")
        resultado_recv["state"] = "EPR not received"

    # --- TIMESTAMP: antes de actualizar memoria ---
    log_timestamp("RECV_BEFORE_UPDATE", epr_id, t=timestamp_precise())

    # Update local memory
    pares = node_info.get("pairEPR", [])
    updated = False
    for i, epr in enumerate(pares):
        if epr.get("id") == epr_id:
            pares[i] = resultado_recv
            updated = True
            break
    if not updated:
        pares.append(resultado_recv)
    node_info["pairEPR"] = pares

    # --- TIMESTAMP: antes de notificar ---
    log_timestamp("RECV_BEFORE_NOTIFY", epr_id, t=timestamp_precise())

    try:
        print("[RECEIVER] Success on receiving the EPR, sending update states to sender and master")

        # --- Send to my_port (the receiver node) ---
        if my_port:
            send_info(
                f"tcp://localhost:{my_port + 1000}",
                {
                    "route": "pairEPR/recv",
                    "payload": resultado_recv
                }
            )

        # --- Send to emisor_port (the sender node) ---
        if emisor_port:
            resultado_recv_sender = dict(resultado_recv)
            resultado_recv_sender["neighbor"] = node_info["id"]

            send_info(
                f"tcp://localhost:{emisor_port + 1000}",
                {
                    "route": "pairEPR/recv",
                    "payload": resultado_recv_sender
                }
            )

            # Trigger Werner recalculation on sender
            listener_emiter_port = emisor_port + 4000
            starting_werner_recalculate_sender(epr_id, resultado_recv_sender, listener_emiter_port)

    except Exception as e:
        print(f"[RECEIVER] ZeroMQ error notifying endpoints: {e}")

    # --- TIMESTAMP: salida de la función ---
    t_end_recv = timestamp_precise()
    t_diff = diff_precise(t_start,t_end_recv)
    log_timestamp("RECV_TOTAL_no_plots", epr_id, t_start = t_start ,t_end_recv=t_end_recv,t_diff=t_diff)
    

    export_timestamps_to_csv()
    compute_latency_stats()
    plot_latencies()
    # --- TIMESTAMP: salida de la función ---
    t_end_recv = timestamp_precise()
    t_diff = diff_precise(t_start,t_end_recv)
    log_timestamp("RECV_TOTAL", epr_id, t_start = t_start ,t_end_recv=t_end_recv,t_diff=t_diff)
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
        par = node_info.get("pairEPR", [])
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
            if e1["neighbor"] in (dest1, dest2) and e2["neighbor"] in (dest1, dest2):
                if e1["neighbor"] != e2["neighbor"]:
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
        for epr in node_info.get("pairEPR", []):
            if epr.get("neighbor") == neighbor and epr.get("id") in candidates:
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


def do_swapping(epr1, epr2, id_swap, node_info, t_gen_swap, conn,
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

    # refresh node_info once after swap to catch latest pairEPR 
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
        "comand": "stop_monitor",
        "id": old_id_A
    }
    stop_msg_2 = {
        "comand": "stop_monitor",
        "id": old_id_B
    }
    sending_monitor(stop_msg_1, str(ports_involved[0]))
    sending_monitor(stop_msg_2, str(ports_involved[1]))


    # Derived fields
    tcoh = float(node_info.get("tcoh", 10.0))
    t_recv_str = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"
    tdiff1 = calculate_tdiff(epr1.get("t_gen"), t_recv_str)
    tdiff2 = calculate_tdiff(epr2.get("t_gen"), t_recv_str)
    tdif = calculate_tdiff(t_gen_swap, t_recv_str)
    w1 = math.exp(-tdiff1 / tcoh)
    w2 = math.exp(-tdiff2 / tcoh)

    print("w1 at t_swap: ",w1)
    print("w2 at t_swap: ",w2)

    w_gen_tuple = (w1, w2)
    w_out_new = (w_gen_tuple[0] * w_gen_tuple[1]) if all(w_gen_tuple) else None
    distancia_total = (epr1.get("distancia_nodos") or 0) + (epr2.get("distancia_nodos") or 0)

    # New swapped EPR (metadata)
    swapped_epr = {
        "id": id_swap,
        "neighbor": destinatarios,
        "state": "active",
        "medicion": None,
        "t_gen": t_gen_swap,
        "t_recv": t_recv_str,
        "t_diff": tdif,
        "w_gen": w_gen_tuple,
        "w_out": w_out_new,
        "distancia_nodos": distancia_total,
        "listener_port": None
    }
    node_info["pairEPR"].append(swapped_epr)

    # Notify endpoints
    result_swap = {
        "id": f"{str(epr1['id'])}_{str(epr2['id'])}",
        "neighbor": swapped_epr["neighbor"],
        "state": "swapper",
    }
    try:

        if destinatarios_ports and len(destinatarios_ports) == 2 and len(destinatarios) == 2:
            # Send swapped EPR metadata to each neighbor
            epr_msg1 = swapped_epr.copy()
            epr_msg1["neighbor"] = destinatarios[1]
            epr_msg1["w_gen"] = w_gen_tuple[0]
            epr_msg1["listener_port"] = ports_involved[0]
            print("Notifying", destinatarios[0], "on port", destinatarios_ports[0])
            requests.post(f"http://localhost:{destinatarios_ports[0]}/pairEPR/recv", json=epr_msg1, timeout=2)

            epr_msg2 = swapped_epr.copy()
            epr_msg2["neighbor"] = destinatarios[0]
            epr_msg2["w_gen"] = w_gen_tuple[1]
            epr_msg2["listener_port"] = ports_involved[1]
            print("Notifying", destinatarios[1], "on port", destinatarios_ports[1])
            requests.post(f"http://localhost:{destinatarios_ports[1]}/pairEPR/recv", json=epr_msg2, timeout=2)

        if my_port:
            requests.post(f"http://localhost:{my_port}/pairEPR/swap", json=result_swap, timeout=2)

        # Updating their EPR and watch over it, making one of them measured it if it reaches the threshold
        monitor_msg_A = {
            "comand": "watch_over",
            "order": "kill_if_reached",
            "id": id_swap,
            "old_id": old_id_A,
            "EPR_pair": epr_msg1,
            "my_port": int(destinatarios_ports[0]),
            "other_port": int(destinatarios_ports[1])
        }
        monitor_msg_B = {
            "comand": "watch_over",
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
        comand = payload.get("comand")

        print(f"[LISTENER] Acción recibida: {comand}")
        try: 
            node_info = requests.get(f"http://localhost:{my_port}/info", timeout=2).json() 
        except: 
            pass

        # --------------------------------------------------
        # GENERATE EPR
        # --------------------------------------------------
        if comand == "generate EPR":
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
        elif comand == "receive EPR":
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
        elif comand == "purified":
            epr_id = payload.get("id")
            result = measure_epr(epr_id, node_info, conn, my_port, "Consumed")
            conn_sock.send(json.dumps(result or {"error": "EPR not found"}).encode())

        # --------------------------------------------------
        # RECALCULATE (sender-side monitor start)
        # --------------------------------------------------
        elif comand == "recalculate":
            if payload["info"] != "active":
                 print(f"[LISTENER] Ignoring recalculate because EPR with id: {payload['id']} is not active") 
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
        elif comand == "watch_over":
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
        elif comand == "do swapping":
            t_gen_swap = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"
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
                    t_gen_swap=t_gen_swap,
                    conn=conn,
                    destinatarios=destinatarios,
                    destinatarios_ports=destinatarios_ports,
                    pswap=pswap,
                    listener_port=listener_port_in,
                    my_port=my_port_in,
                    ports_involved=ports_involved
                )
                conn_sock.send(json.dumps(result).encode())
        elif comand == "stop_monitor":
            epr_id = payload["id"]
            print(f"[LISTENER] Stop monitor for {epr_id}")
            if epr_id in epr_store:
                epr_store[epr_id]["protected"] = True
            conn_sock.send(json.dumps({"status": "stopped"}).encode())


        else:
            conn_sock.send(json.dumps({"error": f"Unknown action {comand}"}).encode())

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
