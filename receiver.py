import sys
import math
import time
import json
import requests
import socket
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCTimeoutError

C = 3e5  # km/s

# Memoria local de qubits
epr_store = {}
nodo_info = {"parEPR": []}
import threading, time, math

def monitor_coherence(epr, node_info, conn, my_port, interval=0.01, threshold=1/3):
    """
    Periodically recomputes w_out for an EPR until it falls below the threshold.
    When w_out <= threshold, the EPR is automatically measured.
    """
    w_in = float(epr.get("w_gen", 1.0))
    t_gen_str = epr.get("t_gen", "0")
    dist_km = float(epr.get("distancia_nodos", 0.0))
    tcoh = float(node_info.get("tcoh", 10.0))

    while True:
        # Current timestamp
        t_recv_str = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"
        t_gen_val, t_recv_val, tdif = calculate_tdiff(t_gen_str, t_recv_str)
        tesp = dist_km / (2.0/3.0 * C)

        w_out = w_in * math.exp(-(tdif + tesp) / tcoh)
        epr["w_out"] = w_out  # update internally

        if w_out <= threshold:
            print(f"[COHERENCE] EPR {epr['id']} reached w={w_out:.3f} in {t_recv_str}, measuring...")
            measure_epr(epr["id"], node_info, conn, my_port, order="measure")
            break

        time.sleep(interval)

def start_monitor(epr, node_info, conn, my_port):
    """
    Launches the coherence monitor in the background for a given EPR.
    """
    threading.Thread(
        target=monitor_coherence,
        args=(epr, node_info, conn, my_port),
        daemon=True
    ).start()

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
    return val1, val2, diff

def starting_werner_recalculate_sender(epr_id, result_recv,listener_emiter_port):
    msg = {"accion": "recalculate", "id": epr_id, "info": result_recv}
    print("Sending recalculating")
    print(listener_emiter_port)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", listener_emiter_port))
    s.send(json.dumps(msg).encode())
    resp = s.recv(4096).decode()
    s.close()
    return json.loads(resp)

def recibir_epr(payload, node_info, conn, my_port, emisor_port, listener_port):
    epr_id = payload.get("id", 0)
    estado = payload.get("estado", "fallo")
    resultado_recv = {
        "id": epr_id,
        "vecino": payload.get("vecino"),
        "t_gen": payload.get("t_gen"),
        "t_recv": None,
        "t_diff": None,
        "w_gen": payload.get("w_gen"),
        "w_out": None,
        "estado": estado,
        "medicion": None,
        "distancia_nodos": None,
        "listener_port": None
    }

    if estado == "ok":
        try:
            q = conn.recvEPR()
            # Guardar qubit en memoria interna
            epr_store[epr_id] = {
                "q": q,
                "emisor_port": emisor_port
            }

            w_in = float(payload.get("w_gen", 1.0))
            # Calcular tiempos
            t_gen_str = payload.get("t_gen", "0")
            t_recv_str = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"

            t_gen_val, t_recv_val, tdif = calculate_tdiff(t_gen_str, t_recv_str)

            dist_km = float(node_info.get("distkm", 0.0))
            tcoh = float(node_info.get("tcoh", 1.0))
            tesp = dist_km / (2.0/3.0 * C)

            w_out = w_in * math.exp(-(tdif + tesp) / tcoh)

            resultado_recv["w_out"] = w_out
            resultado_recv["t_recv"] = t_recv_str
            resultado_recv["t_diff"] = tdif
            resultado_recv["estado"] = "active"
            vecino = payload["vecino"]

            resultado_recv["distancia_nodos"] = next(v["distanceKm"] for v in node_info["neighbors"] if v["id"] == vecino)

            resultado_recv["listener_port"] = listener_port
            # Start the background coherence monitor here
            start_monitor(resultado_recv, node_info, conn, my_port)
        except CQCTimeoutError:
            resultado_recv["estado"] = "timeout"
        except Exception as e:
            print(f"[RECEIVER] Error : {e}")
            resultado_recv["estado"] = "error"
    else:
        resultado_recv["estado"] = "EPR not received"

    # Actualizar memoria local
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

    # Notificar endpoints
    try:
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=resultado_recv, timeout=2)
        if emisor_port:
            resultado_recv["vecino"] = node_info["id"]
            requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=resultado_recv, timeout=2)
            print(time.time())
            listener_emiter_port = emisor_port + 5000
            starting_werner_recalculate_sender(epr_id, resultado_recv, listener_emiter_port)

    except Exception as e:
        print(f"[RECEIVER] Error notificando endpoints: {e}")

    return resultado_recv

def measure_epr(epr_id, node_info, conn, my_port=None, order=None):
    entry = epr_store.get(epr_id)
    if entry:
        q = entry["q"]
        emisor_port = entry.get("emisor_port")

        print("ID DEL EPR:", epr_id, "y su emisor:", emisor_port)
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
            if emisor_port:
                requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=result_measure, timeout=2)    
        except Exception as e:
            print(f"[RECEIVER] Error notificando endpoints: {e}")
        return result_measure
    return None

def pick_pair_same_edge_swap(node_info, my_port,timeout=5.0, interval=0.2):
    """
    Wait up to `timeout` seconds for two 'active' EPRs on the same node,
    but each one must have a different destinatario (neighbor).
    Returns (epr1, epr2, status):
      status = "valid"    -> two 'active' with different neighbors
      status = "none"     -> no usable pair
    """
    local_id = node_info["id"]
    start = time.time()

    while time.time() - start < timeout:
        pairs = node_info.get("parEPR", [])
        # Filter only active EPRs
        active = [e for e in pairs if e.get("estado") == "active"]

        # Try to find two with different neighbors
        for i in range(len(active)):
            for j in range(i+1, len(active)):
                if active[i].get("vecino") != active[j].get("vecino"):
                    # Found two active EPRs with different destinatarios
                    return active[i], active[j], "valid"
        print("...")
        try:
            # refrescar node_info desde el endpoint /info
            resp = requests.get(f"http://localhost:{my_port}/info", timeout=2)
            node_info = resp.json()
        except Exception as e:
            print("[DEBUG] Error refreshing node_info:", e)
        # Wait before retrying
        time.sleep(interval)

    # Timeout reached without finding a valid pair
    return None, None, "none"

def sending_monitor(msg, listener_port):
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

    # Recuperar qubits
    entry1 = epr_store.get(epr1["id"])
    entry2 = epr_store.get(epr2["id"])
    if not entry1 or not entry2:
        return {"error": "One or both EPRs not found"}
    
    # Extraer qubits
    q1 = entry1["q"]
    q2 = entry2["q"]

    # Bell measurement: CNOT + Hadamard
    q1.cnot(q2)
    q1.H()

    # Guardar el resultado del swap con su metadata
    epr_store[id_swap] = {"q": q1, "emisor_port": None}  

    order = "Consumed"

    result_measure1 = measure_epr(epr1["id"], node_info, conn, my_port, order)
    m1 = result_measure1["medicion"]
    result_measure2 = measure_epr(epr2["id"], node_info, conn, my_port, order)
    m2 = result_measure2["medicion"]
    print(f"[SWAP] Bell measurement results: {m1}, {m2}")
    print("Destinatarios: ", destinatarios)

    # Calcular campos derivados
    t_gen_str = epr1.get("t_gen")
    t_recv_str = time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}"
    t_gen_val, t_recv_val, tdif = calculate_tdiff(t_gen_str, t_recv_str)
    w_gen_tuple = (epr1.get("w_out"), epr2.get("w_out"))
    w_out_new = (w_gen_tuple[0] * w_gen_tuple[1]) if all(w_gen_tuple) else None
    distancia_total = (epr1.get("distancia_nodos") or 0) + (epr2.get("distancia_nodos") or 0)

    # Nuevo EPR swapped
    swapped_epr = {
        "id": id_swap,
        "vecino": destinatarios,
        "estado": "active",
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

    # Notificar endpoints
    result_swap = {
        "id": f"{epr1['id']}_{epr2['id']}",
        "vecino": swapped_epr["vecino"],
        "estado": "swapped",
        "medicion": [m1,m2]
    }
    try:
        # Después de hacer el swap y notificar a los vecinos
        monitor_msg = {
            "accion": "watch_over",
            "id": id_swap,        # id del nuevo EPR creado
            "my_port": destinatarios_ports[0],   # puerto del primer vecino
            "other_port": destinatarios_ports[1], # puerto del segundo vecino
            "EPR_pair": None,
            "id_before": None
        }

    
        if destinatarios_ports and len(destinatarios_ports) == 2 and len(destinatarios) == 2:
            # Send to each neighbor with 'vecino' set to the other one
            # Example: Alice receives vecino=Charlie, Charlie receives vecino=Alice
            epr_msg1 = swapped_epr.copy()
            epr_msg1["vecino"] = destinatarios[1]   # Alice sees Charlie
            epr_msg1["w_gen"] = w_gen_tuple[0]
            epr_msg1["listener_port"] = ports_involved[0]
            print("Notifying", destinatarios[0], "on port", destinatarios_ports[0])
            requests.post(f"http://localhost:{destinatarios_ports[0]}/parEPR/recv", json=epr_msg1, timeout=2)
            monitor_msg["EPR_pair"] = epr_msg1
            monitor_msg["id_before"] = epr1['id']

            epr_msg2 = swapped_epr.copy()
            epr_msg2["vecino"] = destinatarios[0]   # Charlie sees Alice
            epr_msg2["w_gen"] = w_gen_tuple[1]
            epr_msg2["listener_port"] = ports_involved[1]
            print("Notifying", destinatarios[1], "on port", destinatarios_ports[1])
            requests.post(f"http://localhost:{destinatarios_ports[1]}/parEPR/recv", json=epr_msg2, timeout=2)
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/swap", json=result_swap, timeout=2)

        #sending_monitor(monitor_msg, ports_involved[0])

    except Exception as e:
        print(f"[SWAP] Error notificando endpoints: {e}")

    print(f"[SWAP] Swapping complete, new EPR {swapped_epr['id']} registered")
    return {"status": "ok", "swapped_epr": result_swap}


def socket_listener(node_info, conn, port, my_port=None, emisor_port=None):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(5)
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
            if payload.get("accion") == "recibe EPR":
                epr_obj       = payload.get("epr_obj")
                nodo_info_in  = payload.get("nodo_info", node_info)
                my_port_in    = payload.get("my_port", my_port)
                emisor_port_in = payload.get("emisor_port", emisor_port)
                listener_port_in = payload.get("listener_port", port)
                resultado = recibir_epr(epr_obj,
                                        nodo_info_in,
                                        conn,
                                        my_port_in,
                                        emisor_port_in,
                                        listener_port_in)
                print("[RECEIVER] Initial sync result:", resultado)

            elif payload.get("accion") == "measure":
                epr_id = payload["id"]
                order = "Consumed"
                result = measure_epr(epr_id, node_info, conn, my_port, order)
                conn_sock.send(json.dumps(result or {"error": "EPR no encontrado"}).encode())

            elif payload.get("accion") == "do swapping":
                id_swap             = payload.get("id", 0)
                node_info_in        = payload.get("node_info", node_info)
                destinatarios       = payload.get("destinatarios", [])
                destinatarios_ports = payload.get("destinatarios_ports", [])
                pswap               = float(payload.get("pswap", 1.0))
                listener_port_in    = payload.get("listener_port", port)
                my_port_in          = payload.get("my_port", my_port)
                ports_involved      = payload.get("ports_involved", [])
                # Use pick_pair_same_edge to filter two active EPRs with different destinatarios
                epr1, epr2, status = pick_pair_same_edge_swap(node_info_in, my_port_in)

                if status != "valid":
                    print("[RECEIVER] No valid pair of active EPRs for swapping")
                    conn_sock.send(json.dumps({"error": "No valid pair"}).encode())
                else:
                    print(f"[RECEIVER] Performing swapping for EPRs {epr1['id']} and {epr2['id']} at node {node_info_in['id']}")
                    print(f"[RECEIVER] Destinatarios: {destinatarios} ports={destinatarios_ports} pswap={pswap}")
                    # Call do_swapping with the two IDs
                    result = do_swapping(
                        epr1=epr1,
                        epr2=epr2,
                        id_swap = id_swap, 
                        node_info=node_info_in,
                        conn=conn,
                        destinatarios=destinatarios,
                        destinatarios_ports=destinatarios_ports,
                        pswap=pswap,
                        listener_port=listener_port_in,
                        my_port=my_port_in,
                        ports_involved = ports_involved
                    )
                    conn_sock.send(json.dumps(result).encode())
                    print("[RECEIVER] Swapping result:", result)

            conn_sock.close()

    except KeyboardInterrupt:
        print("[RECEIVER] Listener interrumpido manualmente, cerrando...")
    finally:
        server.close()


if __name__ == "__main__":
    payload = json.loads(sys.argv[1])
    nodo_info = json.loads(sys.argv[2])
    my_port = int(sys.argv[3])
    emisor_port = int(sys.argv[4])
    listener_port = int(sys.argv[5])

    # Mantener la conexión abierta mientras corre el listener
    with CQCConnection(nodo_info["id"]) as conn:
        resultado = recibir_epr(payload, nodo_info, conn, my_port, emisor_port, listener_port)
        print(f"[RECEIVER] Resultado inicial sincronizado: {resultado}")

        socket_listener(nodo_info, conn, port=listener_port, my_port=my_port, emisor_port=emisor_port)
