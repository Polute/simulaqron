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

def recibir_epr(payload, node_info, conn, my_port, emisor_port, listener_port):
    idx = payload.get("id", 0)
    estado = payload.get("estado", "fallo")

    resultado = {
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
            q = conn.recvEPR()
            # Guardar qubit en memoria interna
            epr_store[idx] = q

            w_in = float(payload.get("w_gen", 1.0))
            # Calcular tiempos
            t_gen_str = payload.get("t_gen", "0")
            try:
                minutos, resto = t_gen_str.split(":")
                segundos, milesimas = resto.split(".")
                t_gen_val = int(minutos)*60 + int(segundos) + int(milesimas)/1000.0
            except Exception:
                t_gen_val = 0.0

            t_local = time.time()
            t_local_val = (int(time.strftime("%M"))*60 +
                           int(time.strftime("%S")) +
                           (int((t_local % 1)*1000))/1000.0)
            t_recv_str = time.strftime("%M:%S", time.localtime(t_local)) + f".{int((t_local % 1)*1000):03d}"
            tdif = t_local_val - t_gen_val

            dist_km = float(node_info.get("distkm", 0.0))
            tcoh = float(node_info.get("tcoh", 1.0))
            tesp = dist_km / (2.0/3.0 * C)

            w_out = w_in * math.exp(-(tdif + tesp) / tcoh)

            resultado["w_out"] = w_out
            resultado["t_recv"] = t_recv_str
            resultado["t_diff"] = tdif
            resultado["estado"] = "active"
            vecino = payload["vecino"]

            resultado["distancia_nodos"] = next(v["distanceKm"] for v in node_info["neighbors"] if v["id"] == vecino)

            resultado["listener_port"] = listener_port
        except CQCTimeoutError:
            resultado["estado"] = "timeout"
        except Exception as e:
            resultado["estado"] = "error"
    else:
        resultado["estado"] = "EPR not received"

    # Actualizar memoria local
    pares = node_info.get("parEPR", [])
    updated = False
    for i, epr in enumerate(pares):
        if epr.get("id") == idx:
            pares[i] = resultado
            updated = True
            break
    if not updated:
        pares.append(resultado)
    node_info["parEPR"] = pares

    # Notificar endpoints
    try:
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=resultado, timeout=2)
        if emisor_port:
            resultado["vecino"] = node_info["id"]
            requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=resultado, timeout=2)
    except Exception as e:
        print(f"[RECEIVER] Error notificando endpoints: {e}")

    return resultado

def medir_epr(epr_id, node_info, conn, my_port=None, emisor_port=None, order=None):
    q = epr_store.get(epr_id)
    if q:
        m = q.measure()
        for epr in node_info["parEPR"]:
            if epr["id"] == epr_id:
                epr["estado"] = order
                epr["medicion"] = m
        del epr_store[epr_id]
        result = {"id": epr_id, "medicion": m, "estado": order}
        # notificar al propio nodo y al emisor
        try:
            if my_port:
                requests.post(f"http://localhost:{my_port}/parEPR/recv", json=result, timeout=2)
            if emisor_port:
                requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=result, timeout=2)
        except Exception as e:
            print(f"[RECEIVER] Error notificando endpoints: {e}")
        return result
    return None

def socket_listener(node_info, conn, port=9000, my_port=None, emisor_port=None):
    """Escucha órdenes de medida en un socket TCP y mide automáticamente tras 5s de inactividad"""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(5)
    server.settimeout(5.0)   # timeout de 5 segundos
    print(f"[RECEIVER] Escuchando órdenes en puerto {port}...")

    while True:
        try:
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
                result = medir_epr(epr_id, node_info, conn, my_port, emisor_port, order)
                if result:
                    conn_sock.send(json.dumps(result).encode())
                else:
                    conn_sock.send(json.dumps({"error": "EPR no encontrado"}).encode())
            """if payload.get("accion") == "swapping":
                epr_id = payload["id"]
                order = "Consumed"
                result = medir_epr(epr_id, node_info, conn, my_port, emisor_port, order)
                if result:
                    conn_sock.send(json.dumps(result).encode())
                else:
                    conn_sock.send(json.dumps({"error": "EPR no encontrado"}).encode())
                do_swapping(epr_id, payload["id1"], payload["id1"])  """ 
            conn_sock.close()

        except socket.timeout:
            # Si no se recibió nada en 5 segundos, medir automáticamente todos los activos
            print("[RECEIVER] Timeout de 5s: midiendo EPRs activos por cuenta propia...")
            activos = [e for e in node_info["parEPR"] if e["estado"] == "active"]
            if not activos:
                print("[RECEIVER] No quedan EPRs activos, cerrando listener.")
                break
            for epr in activos:
                order = "measure"
                result = medir_epr(epr["id"], node_info, conn, my_port, emisor_port, order)
                if result:
                    print(f"[RECEIVER] Medido automáticamente EPR {epr['id']}: {result['medicion']}")
            break

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
