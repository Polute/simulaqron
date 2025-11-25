import sys
import random
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCTimeoutError
from multiprocessing import Manager
import time
import os
from datetime import datetime

# Bloqueo global para escritura segura en archivos compartidos
lock = Lock()

def recogerEPR(modo, w_in, i, modo_tiempo, enviados, fidelidades):
    """
    Recibe un qubit EPR y guarda la medición y fidelidad en archivos compartidos.
    """

    # Determinar fidelidad de entrada
    if modo_tiempo == "simultaneo":
        w_in_i = w_in
    else:
        try:
            w_in_i = float(fidelidades[i]) if i < len(fidelidades) and fidelidades[i].strip() not in ["None", ""] else 0.0
        except ValueError:
            print(f"[BOB] Error al convertir fidelidad Alice #{i}: '{fidelidades[i]}'")
            w_in_i = 0.0

    estado = enviados[i] if i < len(enviados) else "fallo"
    medicion = "no recibido"
    fidelidad_bob = "None"

    with CQCConnection("Bob") as bob:
        if estado != "ok":
            print(f"[BOB] Qubit #{i} no recibido (fallo en pgen o pswap)")
        else:
            try:
                ahora = datetime.now()
                timestamp = ahora.strftime("%M:%S.%f")[:-3]  # recorta a milésimas
                print(f"[TIEMPO REC] {timestamp}")
                #  Recibir qubit y calcular fidelidad
                q = bob.recvEPR()
                print(f"[TIEMPO REC FINAL] {timestamp}")
                if modo == "puro":
                    w_out = 1.0
                elif modo == "werner":
                    w_out = w_in_i
                elif modo == "swap":
                    w_bob = max(0.0, min(1.0, round(random.gauss(0.9, 0.05), 3)))
                    w_out = round(w_in_i * w_bob, 3)
                    print(f"[BOB] Swap fidelidades: w_Alice={w_in_i:.3f}, w_Bob={w_bob:.3f}, w_out={w_out:.3f}")
                else:
                    print(f"[BOB] Modo inválido: {modo}")
                    return

                #  Medir qubit
                m = q.measure()

                t_recepcion = datetime.now().strftime("%M:%S.%f")[:-3]

                # Guardar tiempo en archivo indexado
                with lock:
                    try:
                        with open("pre_docs/tiempo_recepcion.txt", "r") as f:
                            tiempos = f.read().strip().split(",")
                    except FileNotFoundError:
                        tiempos = []

                    while len(tiempos) <= i:
                        tiempos.append("None")

                    tiempos[i] = t_recepcion

                    with open("pre_docs/tiempo_recepcion.txt", "w") as f:
                        f.write(",".join(tiempos))

                medicion = str(m)
                fidelidad_bob = f"{w_out:.3f}"
                print(f"[BOB] Medición #{i}: {m} con fidelidad w_out={w_out:.3f}")

            except CQCTimeoutError:
                print(f"[BOB] Timeout al recibir qubit #{i}")
                medicion = "timeout"

    #  Guardar resultados
    with lock:
        try:
            with open("pre_docs/bob_resultado.txt", "r") as f:
                mediciones = f.read().strip().split(",")
        except FileNotFoundError:
            mediciones = []

        try:
            with open("pre_docs/fidelidad_bob.txt", "r") as f:
                fidelidades_bob = f.read().strip().split(",")
        except FileNotFoundError:
            fidelidades_bob = []

        while len(mediciones) <= i:
            mediciones.append("pendiente")
        while len(fidelidades_bob) <= i:
            fidelidades_bob.append("None")

        mediciones[i] = medicion
        fidelidades_bob[i] = fidelidad_bob

        with open("pre_docs/bob_resultado.txt", "w") as f:
            f.write(",".join(mediciones))
        with open("pre_docs/fidelidad_bob.txt", "w") as f:
            f.write(",".join(fidelidades_bob))

        print(f"[BOB] Resultado #{i} guardado: medición={medicion}, fidelidad={fidelidad_bob}")


def run_bob(modo, w_in, num_ParesEPR, modo_tiempo, semaforos):
    """
    Ejecuta la recepción de múltiples qubits EPR, en paralelo o secuencialmente.
    """
    with lock:
        try:
            with open("pre_docs/qubit_enviado.txt", "r") as f:
                enviados = f.read().strip().split(",")
        except FileNotFoundError:
            enviados = []

        try:
            with open("pre_docs/fidelidad_alice.txt", "r") as f:
                fidelidades = f.read().strip().split(",")
        except FileNotFoundError:
            fidelidades = []

    if modo_tiempo == "simultaneo":
        with ThreadPoolExecutor() as executor:
            for i in range(num_ParesEPR):
                if(enviados[i] == "ok"):
                    print(f"[BOB] Esperando semáforo para qubit #{i}")
                    semaforos[i].acquire()
                    time.sleep(0.01)
                    executor.submit(recogerEPR, modo, w_in, i, modo_tiempo, enviados, fidelidades)
                    time.sleep(0.01)
    else:
        for i in range(num_ParesEPR):
            recogerEPR(modo, w_in, i, modo_tiempo, enviados, fidelidades)



# Punto de entrada si se ejecuta como script externo
if __name__ == "__main__":
    # Leer argumentos desde línea de comandos
    modo = sys.argv[1]              # "puro", "werner" o "swap"
    w_in = float(sys.argv[2])       # Fidelidad promedio si simultáneo
    num_ParesEPR = int(sys.argv[3]) # Número de pares EPR
    modo_tiempo = sys.argv[4]       # "secuencial" o "simultaneo"
    semaforos_raw = sys.argv[5]     # "no_semaforos" o marcador

    semaforos = None

    # Ejecutar Bob
    run_bob(modo, w_in, num_ParesEPR, modo_tiempo, semaforos)
