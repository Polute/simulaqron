import json, sys, random, time, socket, requests

def pedir_medicion(epr_id, listener_port):
    msg = {"accion": "measure", "id": epr_id}
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", listener_port))
    s.send(json.dumps(msg).encode())
    resp = s.recv(4096).decode()
    s.close()
    return json.loads(resp)

def pick_active_pair_same_edge(node_info):
    local_id = node_info["id"]
    activos = [e for e in node_info.get("parEPR", []) if e.get("estado") == "activo"]
    print("[PURIFY2]",node_info)
    print("[PURIFY2]",activos)

    grupos = {}
    for e in activos:
        v = e.get("vecino")
        key = "-".join(sorted([local_id, v]))
        grupos.setdefault(key, []).append(e)

    for key, lista in grupos.items():
        if len(lista) >= 2:
            return lista[-2], lista[-1]
    return None, None
def send_epr_pu_failed(node_info, master_id, my_port, emisor_port, reason, epr1=None, epr2=None):
    if reason == "No 2 active EPR":
        nuevo_epr = {
            "id": master_id,
            "estado": "failed pur",
            "vecino": epr2["vecino"] if epr2 else None
        }
    else:
        nuevo_epr = {
            "id": master_id,
            "estado": "failed p_pur",
            "vecino": epr2["vecino"] if epr2 else None,
            "enlace": "-".join(sorted([node_info["id"], epr2["vecino"]])) if epr2 else None,
            "purificado_de": [epr1["id"], epr2["id"]] if epr1 and epr2 else []
        }
    node_info["parEPR"].append(nuevo_epr)
    try:
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=nuevo_epr, timeout=2)
        if emisor_port:
            requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=nuevo_epr, timeout=2)
    except Exception as e:
        print(f"[PURIFY] Error notificando endpoints: {e}")
    print("[PURIFY] Purificación fallida; se registra EPR fallido:", json.dumps(nuevo_epr, indent=2))

def purify(node_info, master_id, my_port=None, emisor_port=None):
    # Seleccionar dos EPR activos en la misma arista
    epr1, epr2 = pick_active_pair_same_edge(node_info)
    if not epr1 or not epr2:
        reason = "No 2 active EPR"
        send_epr_pu_failed(node_info, master_id ,my_port, emisor_port, reason, epr1, epr2)
        print("[PURIFY] No hay dos EPR activos en la misma arista")
        return

    # Medir usando el listener_port guardado en cada EPR
    lp1 = epr1.get("listener_port")
    lp2 = epr2.get("listener_port")
    if not lp1 or not lp2:
        print("[PURIFY] Faltan listener_port en los EPR seleccionados")
        return

    try:
        res1 = pedir_medicion(epr1["id"], lp1)
        res2 = pedir_medicion(epr2["id"], lp2)
    except ConnectionRefusedError:
        print("[PURIFY] No se pudo conectar a uno de los listener ports")
        return

    epr1["estado"], epr1["medicion"] = "medido", res1.get("medicion")
    epr2["estado"], epr2["medicion"] = "medido", res2.get("medicion")

    w1, w2 = epr1.get("w_out"), epr2.get("w_out")
    if w1 is None or w2 is None:
        print("[PURIFY] Faltan w_out para calcular p_pur")
        return

    p_pur = (1 + (w1 * w2)) / 2
    if random.random() <= p_pur:
        mejora = (w1 + w2 + 4 * w1 * w2) / 6
        w_final = min((w2 or 0) + mejora, 1.0)

        nuevo_epr = {
            "id": master_id,
            "vecino": epr2["vecino"],
            "estado": "purificado",
            "medicion": epr2.get("medicion"),
            "distancia_nodos": epr2.get("distancia_nodos"),
            "t_gen": epr2.get("t_gen"),
            "t_recv": epr2.get("t_recv"),
            "t_diff": epr2.get("t_diff"),
            "t_pur": time.strftime("%H:%M.%S", time.localtime()),
            "w_gen": epr2.get("w_gen"),
            "w_out": w_final,
            "purificado_de": [epr1["id"], epr2["id"]],
            # opcional: no tiene listener_port porque ya está medido
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
    else:
        reason="Ppur failed"
        print(f"[PURIFY] Ppur: {p_pur}")
        send_epr_pu_failed(node_info, master_id, my_port, emisor_port, reason, epr1, epr2)
        



if __name__ == "__main__":
    node_info = json.loads(sys.argv[1])
    master_id = sys.argv[2]
    my_port = int(sys.argv[3])
    emisor_port = int(sys.argv[4])
    purify(node_info, master_id, my_port, emisor_port)

