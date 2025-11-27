import sys
import random
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

def generar_epr(emisor, receptor, emisor_port, receptor_port, pgen, epr_id):
    print(f"[SENDER] {emisor} attempting EPR with {receptor} (pgen={pgen})")

    # Probabilistic check
    if random.random() > pgen:
        print(f"[SENDER] Probabilistic failure, no EPR created")
        payload1 = {
            "id": epr_id,
            "vecino": emisor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload2 = {
            "id": epr_id,
            "vecino": receptor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        # Send to receptor and own node
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload1)
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload2)
        return

    try:
        with CQCConnection(emisor) as conn:
            print("[DEBUG] Conexión abierta correctamente con", emisor)
            print("[DEBUG] Objeto conexión:", conn)
            q = conn.createEPR(receptor)
    except CQCNoQubitError:
        print(f"[SENDER] Error: no quantum memory available")
        payload1 = {
            "id": epr_id,
            "vecino": emisor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload2 = {
            "id": epr_id,
            "vecino": receptor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        # Send to receptor and own node
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload1)
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload2)
        return
    except Exception as e:
        print(f"[SENDER] Unexpected error: {e}")
        payload1 = {
            "id": epr_id,
            "vecino": emisor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        payload2 = {
            "id": epr_id,
            "vecino": receptor,
            "t_gen": "0",
            "w_gen": "fallo"
        }
        # Send to receptor and own node
        send_info(f"http://localhost:{receptor_port}/parEPR/add", payload1)
        send_info(f"http://localhost:{emisor_port}/parEPR/add", payload2)
        return
    # Success payload
    # Generar timestamp con minuto, segundo y 3 decimales
    t_gen = time.strftime("%M:%S.") + f"{int((time.time() % 1)*1000):03d}"
    payload1 = {
        "id": epr_id,
        "vecino": emisor,
        "t_gen": t_gen,   # Alice marks 0 or actual time
        "w_gen": 1.0    # initial fidelity
    }
    payload2 = {
        "id": epr_id,
        "vecino": receptor,
        "t_gen": t_gen,   # Alice marks 0 or actual time
        "w_gen": 1.0    # initial fidelity
    }

    send_info(f"http://localhost:{receptor_port}/parEPR/add", payload1)
    send_info(f"http://localhost:{emisor_port}/parEPR/add", payload2)


if __name__ == "__main__":
    emisor = sys.argv[1]        # e.g. "Alice"
    receptor = sys.argv[2]      # e.g. "Bob"
    emisor_port = int(sys.argv[3])
    receptor_port = int(sys.argv[4])
    pgen = float(sys.argv[5])   # probability of generation
    epr_id = sys.argv[6]
    print("en sender.py")
    generar_epr(emisor, receptor, emisor_port, receptor_port, pgen, epr_id)
