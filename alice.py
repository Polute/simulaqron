import sys
import random
import os
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError
from datetime import datetime
import time


#  Bloqueo global para escritura segura en archivos compartidos
lock = Lock()

def generar_epr(i, modo, pgen, modo_tiempo, semaforos):
    """
    Genera un par EPR con probabilidad pgen y guarda el resultado en archivos compartidos.
    """
    print(f"[ALICE] Iniciando generación de EPR #{i+1}")

    estado = "ok" if random.random() <= pgen else "fallo"
    w_alice = None

    try:
        if estado == "fallo":
            print(f"[ALICE] Fallo probabilístico en generación de EPR #{i+1} (pgen={pgen})")
        else:
            with CQCConnection("Alice") as alice:
                #Calculo el tiempo de ejecucion inicial de la generacion del par EPR
                t_creacion = datetime.now().strftime("%M:%S.%f")[:-3]
                with lock:
                    try:
                        with open("tiempo_creacion.txt", "r") as f:
                            tiempos = f.read().strip().split(",")
                    except FileNotFoundError:
                        tiempos = []

                    while len(tiempos) <= i:
                        tiempos.append("00:00.000")  # valor por defecto válido
                    if estado == "fallo":
                        t_creacion = "00:00.000"
                    tiempos[i] = t_creacion

                    with open("tiempo_creacion.txt", "w") as f:
                        f.write(",".join(tiempos))
                ahora = datetime.now()
                timestamp = ahora.strftime("%M:%S.%f")[:-3]  # recorta a milésimas
                print(f"[TIEMPO GEN] {timestamp}")
                if modo == "puro":
                    q = alice.createEPR("Bob")
                    q1_ID = q.get_entInfo().id_AB
                    ahora = datetime.now()
                    timestamp = ahora.strftime("%M:%S.%f")[:-3]  # recorta a milésimas
                    print(f"[TIEMPO] {timestamp}")
                    print(f"[ALICE] EPR generado con id:{q1_ID}")
                    w_alice = 1.00
                    print(f"[ALICE] EPR #{i+1} creado con Bob (modo puro).")
                elif modo == "werner":
                    q = alice.createEPR("Bob")
                    print(f"[TIEMPO] {timestamp}")
                    q1_ID = q.get_entInfo().id_AB
                    print(f"[ALICE] EPR generado con id:{q1_ID}")
                    w_alice = 0.90
                    print(f"[ALICE] EPR #{i+1} creado con Bob (modo werner).")
                elif modo == "swap":
                    q = alice.createEPR("Charlie")
                    alice.sendQubit(q, "Charlie")
                    print(f"[TIEMPO] {timestamp}")
                    q1_ID = q.get_entInfo().id_AB
                    print(f"[ALICE] EPR generado con id:{q1_ID}")
                    w_alice = 0.90
                    print(f"[ALICE] EPR #{i+1} creado y enviado a Charlie (modo swap).")
                else:
                    print(f"[ALICE] Modo desconocido: {modo}")
                    estado = "fallo"

                # Señal para Bob si estamos en modo simultáneo
                if modo_tiempo == "simultaneo" and semaforos:
                    semaforos[i].release()

                id1 = q.get_entInfo().id_AB
                print(f"[ALICE] ID del par EPR #{i+1}: {id1}")
    except CQCNoQubitError:
        print(f"[ALICE] Error: sin memoria cuántica para EPR #{i+1}")
        estado = "fallo"
    except Exception as e:
        print(f"[ALICE] Error inesperado en EPR #{i+1}: {e}")
        estado = "fallo"

    #  Escritura segura en archivos compartidos
    with lock:
        try:
            with open("qubit_enviado.txt", "r") as f:
                enviados = f.read().strip().split(",")
        except FileNotFoundError:
            enviados = []

        try:
            with open("fidelidad_alice.txt", "r") as f:
                fidelidades = f.read().strip().split(",")
        except FileNotFoundError:
            fidelidades = []

        # Asegurar longitud suficiente
        while len(enviados) <= i:
            enviados.append("pendiente")
        while len(fidelidades) <= i:
            fidelidades.append("None")

        # Guardar resultados
        enviados[i] = estado
        fidelidades[i] = f"{w_alice:.3f}" if isinstance(w_alice, float) else "None"

        with open("qubit_enviado.txt", "w") as f:
            f.write(",".join(enviados))
        with open("fidelidad_alice.txt", "w") as f:
            f.write(",".join(fidelidades))

        print(f"[ALICE] Resultado #{i+1} guardado: estado={estado}, fidelidad={fidelidades[i]}")


def run_alice(modo, pgen, num_ParesEPR, modo_tiempo, semaforos):
    """
    Ejecuta la generación de múltiples pares EPR, en paralelo o secuencialmente.
    """

    if modo_tiempo == "simultaneo":
        with ThreadPoolExecutor() as executor:
            for i in range(num_ParesEPR):
                time.sleep(0.01)
                executor.submit(generar_epr, i, modo, pgen, modo_tiempo, semaforos)
                time.sleep(0.01)
    else:
        for i in range(num_ParesEPR):
            generar_epr(i, modo, pgen, modo_tiempo, semaforos)



# Punto de entrada si se ejecuta como script externo
if __name__ == "__main__":
    # Leer argumentos desde línea de comandos
    modo = sys.argv[1]              # "puro", "werner" o "swap"
    pgen = float(sys.argv[2])       # Probabilidad de generación
    num_ParesEPR = int(sys.argv[3]) # Número de pares EPR
    modo_tiempo = sys.argv[4]       # "secuencial" o "simultaneo"
    semaforos_raw = sys.argv[5]     # "no_semaforos" o marcador

    # Ejecutar Alice
    run_alice(modo, pgen, num_ParesEPR, modo_tiempo, semaforos_raw)
