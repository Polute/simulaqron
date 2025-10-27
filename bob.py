import sys
import random
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCTimeoutError

def run_bob(modo, p, num_qubits):
    with CQCConnection("Bob") as bob:
        resultados = []
        for i in range(num_qubits):
            try:
                if modo == "puro":
                    q = bob.recvEPR()
                elif modo == "werner":
                    q = bob.recvQubit()
                    if random.random() > p:
                        resultados.append("ruido")
                        continue
                elif modo == "swap":
                    q = bob.recvEPR()
                m = q.measure()
                resultados.append(m)
                print(f"[BOB] Medición #{i+1}: {m}")
            except CQCTimeoutError:
                print(f"[BOB] Timeout al recibir qubit #{i+1}")
                resultados.append("timeout")

        with open("bob_resultado.txt", "w") as f:
            f.write(", ".join(map(str, resultados)))

if __name__ == "__main__":
    modo = sys.argv[1]
    p = float(sys.argv[2])
    num_qubits = int(sys.argv[3])
    run_bob(modo, p, num_qubits)
