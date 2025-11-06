import sys
from cqc.pythonLib import CQCConnection

def run_repeater(num_qubits):
    with CQCConnection("Charlie") as repeater:
        for i in range(num_qubits):
            try:
                with open("qubit_enviado.txt", "r") as f:
                    estado = f.readline().strip()
                if estado != "ok":
                    print(f"[REPEATER] Qubit #{i+1} no fue enviado por Alice (fallo en pgen)")
                    continue

                q = repeater.recvQubit()
                print(f"[REPEATER] Qubit #{i+1} recibido de Alice.")
                repeater.sendQubit(q, "Bob")
                print(f"[REPEATER] Qubit #{i+1} reenviado a Bob.")

                with open("fidelidad_alice.txt", "r") as f:
                    w_alice = f.read().strip()
                with open("fidelidad_bob.txt", "w") as f_out:
                    f_out.write(w_alice)
            except Exception as e:
                print(f"[REPEATER] Error al recibir qubit #{i+1}: {e}")

if __name__ == "__main__":
    num_qubits = int(sys.argv[1])
    run_repeater(num_qubits)
