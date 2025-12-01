# swap.py
import sys
import json
import socket
from cqc.pythonLib import CQCConnection

def realizar_swap(node_info, conn, helper_id):
    """Busca los dos últimos EPRs recibidos por el helper y hace entanglement swapping."""
    recibidos = [e for e in node_info["parEPR"] if e["receptor"] == helper_id and e["estado"] == "activo"]

    if len(recibidos) < 2:
        print("[SWAP] No hay suficientes EPRs recibidos para hacer swapping.")
        return None

    # Tomar los dos últimos
    epr1, epr2 = recibidos[-2], recibidos[-1]
    emisor1, emisor2 = epr1["emisor"], epr2["emisor"]

    # Consumir los antiguos
    epr1["estado"] = "consumed"
    epr2["estado"] = "consumed"

    # Crear nuevo EPR
    nuevo_epr = {
        "id": f"swap_{emisor1}_{emisor2}_{helper_id}",
        "emisor": emisor1,
        "receptor": emisor2,
        "helper": helper_id,
        "estado": "activo",
        "medicion": None
    }
    node_info["parEPR"].append(nuevo_epr)

    print(f"[SWAP] {helper_id} ha hecho entanglement swapping entre {emisor1} y {emisor2}.")
    return nuevo_epr


def swap_listener(node_info, conn, helper_id, port=9100, timeout=5):
    """Listener que espera orden de swap y si no llega, mide automáticamente tras timeout."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("localhost", port))
    server.listen(5)
    server.settimeout(timeout)
    print(f"[SWAP] Escuchando órdenes de swap en puerto {port}...")

    while True:
        try:
            conn_sock, addr = server.accept()
            data = conn_sock.recv(4096).decode()
            if not data:
                conn_sock.close()
                continue
            payload = json.loads(data)
            if payload.get("accion") == "swap":
                nuevo = realizar_swap(node_info, conn, helper_id)
                if nuevo:
                    conn_sock.send(json.dumps(nuevo).encode())
                else:
                    conn_sock.send(json.dumps({"error": "No hay suficientes EPRs"}).encode())
            conn_sock.close()

        except socket.timeout:
            # Si no se recibió nada en timeout, medir automáticamente
            print(f"[SWAP] Timeout de {timeout}s: midiendo EPRs activos por cuenta propia...")
            activos = [e for e in node_info["parEPR"] if e["estado"] == "activo"]
            if not activos:
                print("[SWAP] No quedan EPRs activos, cerrando listener.")
                break
            for epr in activos:
                epr["estado"] = "medido"
                epr["medicion"] = 0  # ejemplo de resultado
                print(f"[SWAP] Medido automáticamente EPR {epr['id']}: {epr['medicion']}")
            break


if __name__ == "__main__":
    node_info = json.loads(sys.argv[1])
    helper_id = sys.argv[2]
    my_port = int(sys.argv[3])

    with CQCConnection(node_info["id"]) as conn:
        swap_listener(node_info, conn, helper_id, port=my_port)
