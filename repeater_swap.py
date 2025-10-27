import sys
from cqc.pythonLib import CQCConnection

def entanglement_swap(num_qubits):
    with CQCConnection("Charlie") as repeater:
        for i in range(num_qubits):
            q1 = repeater.recvQubit()
            print(f"[SWAP] Qubit #{i+1} de Alice recibido.")

            q2 = repeater.createEPR("Bob")
            print(f"[SWAP] EPR #{i+1} con Bob creado.")

            q1.cnot(q2)
            q1.H()
            m1 = q1.measure()
            m2 = q2.measure()
            print(f"[SWAP] Medición Bell #{i+1}: m1={m1}, m2={m2}")

if __name__ == "__main__":
    num_qubits = int(sys.argv[1])
    entanglement_swap(num_qubits)
