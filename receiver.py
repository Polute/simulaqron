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

def recibir_epr(payload, node_info, conn, my_port, emisor_port, listener_port):
    idx = payload.get("id", 0)
    estado = payload.get("estado", "fallo")
    resultado_recv = {
        "id": idx,
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
            time.sleep(0.5)
            q = conn.recvEPR()
            # Guardar qubit en memoria interna
            epr_store[idx] = q

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
        if epr.get("id") == idx:
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
    except Exception as e:
        print(f"[RECEIVER] Error notificando endpoints: {e}")

    return resultado_recv

def medir_epr(epr_id, node_info, conn, my_port=None, emisor_port=None, order=None):
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
            if emisor_port:
                requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=result_measure, timeout=2)    
        except Exception as e:
            print(f"[RECEIVER] Error notificando endpoints: {e}")
        return result_measure
    return None

def pick_pair_same_edge_swap(node_info, timeout=5.0, interval=0.2):
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

        # Wait before retrying
        time.sleep(interval)

    # Timeout reached without finding a valid pair
    return None, None, "none"
def do_swapping(epr1, epr2, id_swap, node_info, conn,
                destinatarios=None, destinatarios_ports=None,
                pswap=1.0, listener_port=None,
                my_port=None):
    """
    Perform entanglement swapping between two EPRs.
    """
    print(f"[SWAP] Starting swapping for EPRs {epr1['id']},{epr2['id']} at node {node_info['id']}")

    # Recuperar qubits
    q1 = epr_store.get(epr1["id"])
    q2 = epr_store.get(epr2["id"])
    if not q1 or not q2:
        return {"error": "One or both EPRs not found"}

    # Bell measurement: CNOT + Hadamard
    q1.cnot(q2)
    q1.H()
    epr_store[id_swap] = q1

    order = "Consumed"

    result_measure1 = medir_epr(epr1["id"], node_info, conn, my_port, destinatarios_ports[0], order)
    m1 = result_measure1["medicion"]
    result_measure2 = medir_epr(epr2["id"], node_info, conn, my_port, destinatarios_ports[1], order)
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
        "listener_port": listener_port
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
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/swap", json=result_swap, timeout=2)
        if destinatarios_ports and len(destinatarios_ports) == 2 and len(destinatarios) == 2:
            # Send to each neighbor with 'vecino' set to the other one
            # Example: Alice receives vecino=Charlie, Charlie receives vecino=Alice
            epr_msg1 = swapped_epr.copy()
            epr_msg1["vecino"] = destinatarios[1]   # Alice sees Charlie
            epr_msg1["w_gen"] = w_gen_tuple[0]
            print("Notifying", destinatarios[0], "on port", destinatarios_ports[0])
            requests.post(f"http://localhost:{destinatarios_ports[0]}/parEPR/recv", json=epr_msg1, timeout=2)

            epr_msg2 = swapped_epr.copy()
            epr_msg2["vecino"] = destinatarios[0]   # Charlie sees Alice
            epr_msg2["w_gen"] = w_gen_tuple[1]
            print("Notifying", destinatarios[1], "on port", destinatarios_ports[1])
            requests.post(f"http://localhost:{destinatarios_ports[1]}/parEPR/recv", json=epr_msg2, timeout=2)

    except Exception as e:
        print(f"[SWAP] Error notificando endpoints: {e}")

    print(f"[SWAP] Swapping complete, new EPR {swapped_epr['id']} registered")
    return {"status": "ok", "swapped_epr": result_swap}


def socket_listener(node_info, conn, port=9000, my_port=None, emisor_port=None):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(5)
    server.settimeout(5.0)   # timeout de 5 segundos
    print(f"[RECEIVER] Escuchando órdenes en puerto {port}...")

    try:
        while True:
            try:
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
                    result = medir_epr(epr_id, node_info, conn, my_port, emisor_port, order)
                    conn_sock.send(json.dumps(result or {"error": "EPR no encontrado"}).encode())

                elif payload.get("accion") == "do swapping":
                    id_swap             = payload.get("id", 0)
                    node_info_in        = payload.get("node_info", node_info)
                    destinatarios       = payload.get("destinatarios", [])
                    destinatarios_ports = payload.get("destinatarios_ports", [])
                    pswap               = float(payload.get("pswap", 1.0))
                    listener_port_in    = payload.get("listener_port", port)
                    my_port_in          = payload.get("my_port", my_port)

                    # Use pick_pair_same_edge to filter two active EPRs with different destinatarios
                    epr1, epr2, status = pick_pair_same_edge_swap(node_info_in)

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
                            my_port=my_port_in
                        )

                        conn_sock.send(json.dumps(result).encode())
                        print("[RECEIVER] Swapping result:", result)



                conn_sock.close()

            except socket.timeout:
                # Si no se recibió nada en 5 segundos, medir automáticamente todos los activos
                print("[RECEIVER] Timeout de 5s: midiendo EPRs activos por cuenta propia...")
                activos = [e for e in node_info.get("parEPR", []) if e.get("estado") == "active"]
                if not activos:
                    print("[RECEIVER] No quedan EPRs activos, pero el listener sigue abierto.")
                for epr in activos:
                    order = "measure"
                    result_measure = medir_epr(epr["id"], node_info, conn, my_port, emisor_port, order)
                    if result_measure:
                        print(f"[RECEIVER] Medido automáticamente EPR {epr['id']}: {result_measure['medicion']}")
                # importante: no cerrar ni romper, el bucle continúa

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
