import json, sys, random, time, socket, requests


import time

def pedir_medicion(epr_id, listener_port):
    msg = {"accion": "measure", "id": epr_id}
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(("localhost", listener_port))
    s.send(json.dumps(msg).encode())
    resp = s.recv(4096).decode()
    s.close()
    return json.loads(resp)

def pick_pair_same_edge(node_info, timeout=7.0, interval=0.2):
    """
    Wait up to `timeout` seconds for two EPRs 'active' on the same edge.
    Returns (epr1, epr2, status):
      status = "valid"    -> two 'active'
      status = "fallback" -> two 'EPR not received' OR one 'active' + one 'EPR not received'
      status = "none"     -> no usable pair
    """
    local_id = node_info["id"]
    start = time.time()

    while time.time() - start < timeout:
        pairs = node_info.get("parEPR", [])
        groups = {}
        for e in pairs:
            v = e.get("vecino") or "None"
            # Saltar si vecino es una lista (caso swapped)
            if isinstance(v, list):
                continue
            key = "-".join(sorted([local_id, v]))
            groups.setdefault(key, []).append(e)

        for key, lst in groups.items():
            if len(lst) < 2:
                continue

            # Case 1: two 'active' EPRs
            active = [e for e in lst if e.get("state") == "active"]
            if len(active) >= 2:
                return active[-2], active[-1], "valid"

            # Case 2: last two are 'EPR not received'
            if lst[-2].get("state") == "EPR not received" and lst[-1].get("state") == "EPR not received":
                return lst[-2], lst[-1], "fallback"

            # Case 3: one 'active' and one 'EPR not received'
            states = {lst[-2].get("state"), lst[-1].get("state")}
            if "active" in states and "EPR not received" in states:
                return lst[-2], lst[-1], "fallback"
            try:
                # refrescar node_info desde el endpoint /info
                resp = requests.get(f"http://localhost:{my_port}/info", timeout=2)
                node_info = resp.json()
            except Exception as e:
                print("[DEBUG] Error refreshing node_info:", e)
        print("P...")
        # Wait before retrying
        time.sleep(interval)

    # Timeout reached without finding a valid pair
    return None, None, "none"


def send_epr_pu_failed(node_info, master_id, my_port, emitter_port, reason, epr1=None, epr2=None):
    neighbor = None
    if epr2 and "vecino" in epr2:
        neighbor = epr2["vecino"]
    elif epr1 and "vecino" in epr1:
        neighbor = epr1["vecino"]

    link = "-".join(sorted([node_info["id"], neighbor])) if neighbor else None
    purified_from = []
    if epr1 and "id" in epr1:
        purified_from.append(epr1["id"])
    if epr2 and "id" in epr2:
        purified_from.append(epr2["id"])

    new_epr = {
        "id": master_id,
        "state": "failed pur" if reason == "No 2 active EPR" else "failed p_pur",
        "vecino": neighbor,
        "enlace": link,
        "purificado_de": purified_from
    }

    node_info.setdefault("parEPR", []).append(new_epr)

    try:
        time.sleep(0.5)
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/failed_pur", json=new_epr, timeout=2)
        if emitter_port:
            requests.post(f"http://localhost:{emitter_port}/parEPR/failed_pur", json=new_epr, timeout=2)
    except Exception as e:
        print(f"[PURIFY] Error notifying endpoints: {e}")

    print("[PURIFY] Purification failed; failed EPR registered:", json.dumps(new_epr, indent=2))


def purify(node_info, master_id, my_port=None, emitter_port=None):
    epr1, epr2, status = pick_pair_same_edge(node_info)

    if status != "valid":
        reason = "No 2 active EPR"
        send_epr_pu_failed(node_info, master_id, my_port, emitter_port, reason, epr1, epr2)
        print("[PURIFY] No valid pair of active EPRs on the same edge")
        return

    # Actual purification logic when two valid actives are found
    print("[PURIFY] Purification with EPRs:", epr1["id"], epr2["id"])

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

    epr1["state"], epr1["medicion"] = "medido", res1.get("medicion")
    epr2["state"], epr2["medicion"] = "medido", res2.get("medicion")

    w1, w2 = epr1.get("w_out"), epr2.get("w_out")
    if w1 is None or w2 is None:
        print("[PURIFY] Faltan w_out para calcular p_pur")
        return

    p_pur = (1 + (w1 * w2)) / 2
    if random.random() <= p_pur:
        mejora = (w1 + w2 + 4 * w1 * w2) / (6*p_pur)
        w_final = mejora

        nuevo_epr = {
            "id": master_id,
            "vecino": epr2["vecino"],
            "state": "purificado",
            "medicion": epr2.get("medicion"),
            "distancia_nodos": epr2.get("distancia_nodos"),
            "t_gen": epr2.get("t_gen"),
            "t_recv": epr2.get("t_recv"),
            "t_diff": epr2.get("t_diff"),
            "t_pur": time.strftime("%M:%S", time.localtime()) + f".{int((time.time() % 1)*1000):03d}",
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

