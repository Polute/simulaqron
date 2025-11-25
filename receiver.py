import sys
import math
import time
import json
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCTimeoutError

C = 3e5  # km/s

def recibir_epr(payload, node_info):
    idx = payload.get("id", 0)
    estado = payload.get("estado", "fallo")

    resultado = {
        "id": idx,
        "vecino": payload.get("vecino"),
        "t_gen": payload.get("t_gen"),
        "w_gen": payload.get("w_gen"),
        "estado": estado,
        "medicion": None,
        "fidelidad": None
    }

    if estado == "ok":
        try:
            with CQCConnection(node_info["id"]) as conn:
                q = conn.recvEPR()
                w_in = float(payload.get("w_gen", 1.0))
                t_gen = float(payload.get("t_gen", 0.0))

                dist_km = float(node_info.get("distkm", 0.0))
                tcoh = float(node_info.get("tcoh", 1.0))

                t_local = time.time()
                tdif = t_local - t_gen
                tesp = dist_km / (2.0/3.0 * C)

                w_out = w_in * math.exp(-(tdif + tesp) / tcoh)
                m = q.measure()

                resultado["medicion"] = m
                resultado["fidelidad"] = w_out
                resultado["w_gen"] = w_out
                print(f"[RECEIVER] Medición #{idx}: {m}, fidelidad={w_out:.4f}")

        except CQCTimeoutError:
            print(f"[RECEIVER] Timeout al recibir qubit #{idx}")
            resultado["estado"] = "timeout"
        except Exception as e:
            print(f"[RECEIVER] Error inesperado: {e}")
            resultado["estado"] = "error"
    else:
        print(f"[RECEIVER] Qubit #{idx} marcado como fallo")

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

    return resultado


if __name__ == "__main__":
    payload = json.loads(sys.argv[1])
    node_info = json.loads(sys.argv[2])
    resultado = recibir_epr(payload, node_info)
    print(f"[RECEIVER] Resultado final sincronizado: {resultado}")
