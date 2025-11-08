import sys
import random
from cqc.pythonLib import CQCConnection
from cqc.pythonLib.util import CQCTimeoutError

def run_bob(modo, w_in, num_qubits):
    with CQCConnection("Bob") as bob:
        mediciones = []
        w_out = 0.0  # Valor por defecto

        for i in range(num_qubits):
            try:
                with open("qubit_enviado.txt", "r") as f:
                    estado = f.readline().strip()
                if estado != "ok":
                    print(f"[BOB] Qubit #{i+1} no recibido (fallo en pgen o pswap)")
                    mediciones.append("no recibido")
                    continue

                if modo == "puro":
                    q = bob.recvEPR()
                    w_out = 1.0
                elif modo == "werner":
                    q = bob.recvEPR()
                    w_out = w_in
                elif modo == "swap":
                    q = bob.recvEPR()
                    w_bob = max(0.0, min(1.0, round(random.gauss(0.9, 0.05), 3)))
                    w_out = round(w_in * w_bob, 3)
                    print(f"[BOB] Swap fidelidades: w_Alice={w_in:.3f}, w_Bob={w_bob:.3f}, w_out={w_out:.3f}")
                else:
                    mediciones.append("modo inválido")
                    continue

                m = q.measure()
                mediciones.append(int(m))
                print(f"[BOB] Medición #{i+1}: {m} con fidelidad w_out={w_out:.3f}")

            except CQCTimeoutError:
                print(f"[BOB] Timeout al recibir qubit #{i+1}")
                mediciones.append("timeout")

        # Guardar resultado como lista + fidelidad única
        with open("bob_resultado.txt", "w") as f:
            f.write(f"{mediciones} (w_out={w_out:.3f})")

        # También guardar fidelidad por separado si se necesita
        with open("fidelidad_bob.txt", "w") as f:
            f.write(str(w_out))

if __name__ == "__main__":
    modo = sys.argv[1]
    w_in = float(sys.argv[2])
    num_qubits = int(sys.argv[3])
    run_bob(modo, w_in, num_qubits)
