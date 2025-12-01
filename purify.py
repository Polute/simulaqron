import json, sys, random, time, uuid, socket, requests

def pedir_medicion(epr_id, listener_port):
    msg = {"accion": "measure", "id": epr_id}
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", listener_port))
    s.send(json.dumps(msg).encode())
    resp = s.recv(4096).decode()
    print("[DEBUG PUR] Recibido:", repr(resp)) 
    s.close()
    return json.loads(resp)
def purify(node_info, listener_port, master_id, my_port=None, emisor_port=None):
    pares = node_info.get("parEPR", [])
    time.sleep(1)
    if len(pares) < 2:
        print("[PURIFY] No hay suficientes EPRs para purificar")
        return

    # Tomar los dos últimos
    epr1, epr2 = pares[-2], pares[-1]

    # Medirlos vía listener
    print("[PUR] Su listener Port es:")
    res1 = pedir_medicion(epr1["id"], listener_port-2)
    res2 = pedir_medicion(epr2["id"], listener_port-1)
    epr1["estado"], epr1["medicion"] = "medido", res1.get("medicion")
    epr2["estado"], epr2["medicion"] = "medido", res2.get("medicion")

    w1, w2 = epr1["w_out"], epr2["w_out"]
    p_pur = (1 + (w1 * w2)) / 2

    if random.random() <= p_pur:
        mejora = (w1 + w2 + 4*w1*w2) / 6
        w_final = min(w2 + mejora, 1.0)

        nuevo_epr = {
            "id": master_id,   # usar el id de la orden
            "vecino": epr2["vecino"],
            "estado": "purificado",
            "medicion": epr2["medicion"],
            "distancia_nodos": epr2.get("distancia_nodos"),
            "t_gen": epr2.get("t_gen"),
            "t_recv": epr2.get("t_recv"),
            "t_diff": epr2.get("t_diff"),
            "t_pur": time.strftime("%H:%M.%S", time.localtime()),
            "w_gen": epr2.get("w_gen"),
            "w_out": w_final,
            "purificado_de": [epr1["id"], epr2["id"]]
        }

        node_info["parEPR"].append(nuevo_epr)
        try:
            if my_port:
                requests.post(f"http://localhost:{my_port}/parEPR/recv", json=nuevo_epr, timeout=2)
            if emisor_port:
                requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=nuevo_epr, timeout=2)
        except Exception as e:
            print(f"[PURIFY] Error notificando endpoints: {e}")

        print("[PURIFY] Nuevo EPR purificado creado:", json.dumps(nuevo_epr, indent=2))


if __name__ == "__main__":
    node_info = json.loads(sys.argv[1])
    listener_port = int(sys.argv[2])
    master_id = sys.argv[3]
    my_port = int(sys.argv[4])
    emisor_port = int(sys.argv[5])
    purify(node_info, listener_port, master_id, my_port, emisor_port)
