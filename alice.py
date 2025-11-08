import sys
import random
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCNoQubitError

def run_alice(modo, pgen, num_qubits):
    with CQCConnection("Alice") as alice:
        for i in range(num_qubits):
            # Simular fallo probabilístico en generación
            if random.random() > pgen:
                print(f"[ALICE] Fallo probabilístico en generación de EPR #{i+1} (pgen={pgen})")
                with open("qubit_enviado.txt", "w") as f:
                    f.write("fallo")
                continue

            try:
                if modo == "puro":
                    q = alice.createEPR("Bob")
                    print(f"[ALICE] EPR #{i+1} creado con Bob.")
                elif modo == "werner":
                    q = alice.createEPR("Bob")
                    print(f"[ALICE] EPR #{i+1} creado con Bob.")
                elif modo == "swap":
                    q = alice.createEPR("Charlie")
                    print(f"[ALICE] EPR #{i+1} creado con Charlie.")
                    alice.sendQubit(q, "Charlie")
                w_alice = 0.90 #Fidelidad fija para Alice
                with open("fidelidad_alice.txt", "w") as f:
                    f.write(str(w_alice))
                with open("qubit_enviado.txt", "w") as f:
                    f.write("ok")

            except CQCNoQubitError:
                print(f"[ALICE] Fallo por falta de memoria cuántica al generar EPR #{i+1}")
                with open("bob_resultado.txt", "w") as f:
                    f.write("ERROR: Memoria cuántica llena. Limpia el historial.")
                return

if __name__ == "__main__":
    modo = sys.argv[1]
    pgen = float(sys.argv[2])
    num_qubits = int(sys.argv[3])
    run_alice(modo, pgen, num_qubits)
