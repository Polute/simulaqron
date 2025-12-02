import sys
import random
import json
import requests
import time
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError

def send_info(url, payload):
    """Send payload to a node's /parEPR/add endpoint."""
    try:
        r = requests.post(url, json=payload)
        print(f"[SENDER] Sent info to {url}, status={r.status_code}")
    except Exception as e:
        print(f"[SENDER] Error sending info to {url}: {e}")

def generar_epr(emisor, receptor, emisor_port, receptor_port, pgen, epr_id, node_info):
    print(f"[SENDER] {emisor} attempting EPR with {receptor} (pgen={pgen})")

    # comprobar si receptor está en la lista de vecinos de node_info
    vecinos = [n["id"] for n in node_info["neighbors"]]
    if receptor not in vecinos:
        print(f"[SENDER] Error: {receptor} no es vecino de {emisor} según node_info")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor, 
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        return

    # Probabilistic check
    if random.random() > pgen:
        print(f"[SENDER] Probabilistic failure, no EPR created")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor,  # el otro extremo
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload_receptor = {
            "id": epr_id,
            "vecino": emisor,    # el otro extremo
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)
        return

    try:
        with CQCConnection(emisor) as conn:
            print("[DEBUG] Conexión abierta correctamente con", emisor)
            q = conn.createEPR(receptor)
    except CQCNoQubitError:
        print(f"[SENDER] Error: no quantum memory available")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload_receptor = {
            "id": epr_id,
            "vecino": emisor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)
        return
    except Exception as e:
        print(f"[SENDER] Unexpected error: {e}")
        payload_emisor = {
            "id": epr_id,
            "vecino": receptor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload_receptor = {
            "id": epr_id,
            "vecino": emisor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)
        return

    # Success payload
    t_gen = time.strftime("%M:%S.") + f"{int((time.time() % 1)*1000):03d}"
    payload_emisor = {
        "id": epr_id,
        "vecino": receptor,  # el otro extremo
        "t_gen": t_gen,
        "w_gen": 1.0
    }
    payload_receptor = {
        "id": epr_id,
        "vecino": emisor,    # el otro extremo
        "t_gen": t_gen,
        "w_gen": 1.0
    }

    send_info(f"http://localhost:{emisor_port}/parEPR/add", payload_emisor)
    send_info(f"http://localhost:{receptor_port}/parEPR/add", payload_receptor)


if __name__ == "__main__":
    emisor = sys.argv[1]       
    receptor = sys.argv[2]      
    emisor_port = int(sys.argv[3])
    receptor_port = int(sys.argv[4])
    pgen = float(sys.argv[5])   # probability of generation
    epr_id = sys.argv[6]
    node_info = json.loads(sys.argv[7])
    print("en sender.py")
    generar_epr(emisor, receptor, emisor_port, receptor_port, pgen, epr_id, node_info)
