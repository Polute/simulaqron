import sys
from cqc.pythonLib import CQCConnection

from cqc.pythonLib.util import CQCNoQubitError

def run_alice(modo, p, num_qubits):
    with CQCConnection("Alice") as alice:
        for i in range(num_qubits):
            try:
                if modo == "puro":
                    q = alice.createEPR("Bob")
                    print(f"[ALICE] EPR #{i+1} creado con Bob.")
                elif modo == "werner":
                    q = alice.createEPR("Charlie")
                    print(f"[ALICE] EPR #{i+1} creado con Repeater.")
                    alice.sendQubit(q, "Charlie")
                elif modo == "swap":
                    q = alice.createEPR("Charlie")
                    print(f"[ALICE] EPR #{i+1} creado con Charlie.")
                    alice.sendQubit(q, "Charlie")
            except CQCNoQubitError:
                print("[ALICE] No hay espacio de memoria cuántica disponible.")
                with open("bob_resultado.txt", "w") as f:
                    f.write("ERROR: Memoria cuántica llena. Limpia el historial.")
                return

if __name__ == "__main__":
    modo = sys.argv[1]
    p = float(sys.argv[2])
    num_qubits = int(sys.argv[3])
    run_alice(modo, p, num_qubits)
