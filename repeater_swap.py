import sys
import random
from cqc.pythonLib import CQCConnection

def entanglement_swap(num_qubits, pswap):
    with CQCConnection("Charlie") as repeater:
        for i in range(num_qubits):
            try:
                with open("qubit_enviado.txt", "r") as f:
                    estado = f.readline().strip()
                if estado != "ok":
                    print(f"[SWAP] Qubit #{i+1} no fue enviado por Alice (fallo en pgen)")
                    continue

                q1 = repeater.recvQubit()
                print(f"[SWAP] Qubit #{i+1} de Alice recibido.")

                q2 = repeater.createEPR("Bob")
                print(f"[SWAP] EPR #{i+1} con Bob creado.")

                with open("fidelidad_alice.txt", "r") as f:
                    w_alice = float(f.read().strip())
                w_bob = max(0.0, min(1.0, round(random.gauss(0.9, 0.05), 3)))

                if random.random() < pswap:
                    w_swap = round(w_alice * w_bob, 3)
                    print(f"[SWAP] Swapping exitoso: w_Alice={w_alice}, w_Bob={w_bob}, w_out={w_swap}")
                    with open("fidelidad_bob.txt", "w") as f_out:
                        f_out.write(str(w_swap))
                    with open("qubit_enviado.txt", "w") as f:
                        f.write("ok")
                else:
                    print(f"[SWAP] Swapping fallido (pswap={pswap})")
                    with open("fidelidad_bob.txt", "w") as f_out:
                        f_out.write("0.0")
                    with open("qubit_enviado.txt", "w") as f:
                        f.write("fallo")

                q1.cnot(q2)
                q1.H()
                m1 = q1.measure()
                m2 = q2.measure()
                print(f"[SWAP] Medición Bell #{i+1}: m1={m1}, m2={m2}")
            except Exception as e:
                print(f"[SWAP] Error en swapping #{i+1}: {e}")

if __name__ == "__main__":
    num_qubits = int(sys.argv[1])
    pswap = float(sys.argv[2])
    entanglement_swap(num_qubits, pswap)
