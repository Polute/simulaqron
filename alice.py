import sys
import random
from concurrent.futures import ThreadPoolExecutor
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError

def generar_epr(i, modo, pgen):
    # Simular fallo probabilístico en generación
    if random.random() > pgen:
        print(f"[ALICE] Fallo probabilístico en generación de EPR #{i+1} (pgen={pgen})")
        with open("qubit_enviado.txt", "w") as f:
            f.write("fallo")
        return

    try:
        with CQCConnection("Alice") as alice:
            if modo == "puro":
                q = alice.createEPR("Bob")
                print(f"[ALICE] EPR #{i+1} creado con Bob.")
                w_alice = 1.00
            elif modo == "werner":
                q = alice.createEPR("Bob")
                print(f"[ALICE] EPR #{i+1} creado con Bob.")
                w_alice = 0.90
            elif modo == "swap":
                q = alice.createEPR("Charlie")
                print(f"[ALICE] EPR #{i+1} creado con Charlie.")
                alice.sendQubit(q, "Charlie")
                w_alice = 0.90
            else:
                print(f"[ALICE] Modo desconocido: {modo}")
                return

            with open("fidelidad_alice.txt", "w") as f:
                f.write(str(w_alice))
            with open("qubit_enviado.txt", "w") as f:
                f.write("ok")

    except CQCNoQubitError:
        print(f"[ALICE] Fallo por falta de memoria cuántica al generar EPR #{i+1}")
        with open("bob_resultado.txt", "w") as f:
            f.write("ERROR: Memoria cuántica llena. Limpia el historial.")

def run_alice(modo, pgen, num_qubits, modo_tiempo):
    if modo_tiempo == "simultaneo":
        with ThreadPoolExecutor() as executor:
            for i in range(num_qubits):
                executor.submit(generar_epr, i, modo, pgen)
    else:  # modo_tiempo == "secuencial" o cualquier otro valor
        for i in range(num_qubits):
            generar_epr(i, modo, pgen)

if __name__ == "__main__":
    modo = sys.argv[1]              # "puro", "werner" o "swap"
    pgen = float(sys.argv[2])       # probabilidad de generación
    num_qubits = int(sys.argv[3])   # cantidad de pares EPR
    modo_tiempo = sys.argv[4]       # "secuencial" o "simultaneo"
    w_alice_list = []
    run_alice(modo, pgen, num_qubits, modo_tiempo)
