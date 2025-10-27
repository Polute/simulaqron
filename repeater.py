import sys
from cqc.pythonLib import CQCConnection

def run_repeater(num_qubits):
    with CQCConnection("Charlie") as repeater:
        for i in range(num_qubits):
            q = repeater.recvQubit()
            print(f"[REPEATER] Qubit #{i+1} recibido de Alice.")
            repeater.sendQubit(q, "Bob")
            print(f"[REPEATER] Qubit #{i+1} reenviado a Bob.")

if __name__ == "__main__":
    num_qubits = int(sys.argv[1])
    run_repeater(num_qubits)
