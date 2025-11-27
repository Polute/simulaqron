import sys
import math
import time
import json
import requests
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCTimeoutError

C = 3e5  # km/s

def recibir_epr(payload, node_info, my_port, emisor_port):
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
        "medicion": None
    }

    if estado == "ok":
        try:
            with CQCConnection(node_info["id"]) as conn:
                q = conn.recvEPR()
                w_in = float(payload.get("w_gen", 1.0))
                # Parsear t_gen en formato MM:SS.mmm
                t_gen_str = payload.get("t_gen", "0")
                try:
                    minutos, resto = t_gen_str.split(":")
                    segundos, milesimas = resto.split(".")
                    t_gen_val = int(minutos)*60 + int(segundos) + int(milesimas)/1000.0
                except Exception:
                    t_gen_val = 0.0

                t_local = time.time()
                # Convertir t_local a mismo formato (segundos desde inicio de minuto)
                t_local_val = (int(time.strftime("%M"))*60 +
                               int(time.strftime("%S")) +
                               (int((t_local % 1)*1000))/1000.0)

                tdif = t_local_val - t_gen_val

                dist_km = float(node_info.get("distkm", 0.0))
                tcoh = float(node_info.get("tcoh", 1.0))

                tesp = dist_km / (2.0/3.0 * C)

                # calcular w_out
                w_out = w_in * math.exp(-(tdif + tesp) / tcoh)

                m = q.measure()

                resultado["medicion"] = m
                resultado["w_out"] = w_out
                resultado["t_recv"] = t_local
                resultado["t_diff"] = tdif

                print("[DEBUG] my_port =", my_port)
                print("[DEBUG] emisor_port =", emisor_port)
                print(f"[RECEIVER] Medición #{idx}: {m}, w_out={w_out:.4f}")

        except CQCTimeoutError:
            print(f"[RECEIVER] Timeout al recibir qubit #{idx}")
            resultado["estado"] = "timeout"
        except Exception as e:
            print(f"[RECEIVER] Error inesperado: {e}")
            resultado["estado"] = "error"
    else:
        print(f"[RECEIVER] Qubit #{idx} marcado como fallo")
        resultado["estado"] = "EPR no encontrado"

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

    # Enviar resultado al propio nodo (/parEPR/recv) y al emisor (/parEPR/recv)
    try:
        if my_port:
            requests.post(f"http://localhost:{my_port}/parEPR/recv", json=resultado, timeout=2)
        if emisor_port:
            requests.post(f"http://localhost:{emisor_port}/parEPR/recv", json=resultado, timeout=2)
    except Exception as e:
        print(f"[RECEIVER] Error notificando endpoints: {e}")

    return resultado


if __name__ == "__main__":
    payload = json.loads(sys.argv[1])
    node_info = json.loads(sys.argv[2])
    my_port = int(sys.argv[3])
    emisor_port = int(sys.argv[4])

    resultado = recibir_epr(payload, node_info, my_port, emisor_port)
    print(f"[RECEIVER] Resultado final sincronizado: {resultado}")
