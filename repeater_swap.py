import sys
import random
from cqc.pythonLib import CQCConnection
import time
import math

def entanglement_swap(num_ParesEPR, pswap):
    with CQCConnection("Charlie") as repeater:
        try:
            with open("qubit_enviado.txt", "r") as f:
                enviados = f.read().strip().split(",")
        except FileNotFoundError:
            enviados = []
        for i in range(num_ParesEPR):
            if enviados[i] != "ok":
                print(f"[SWAP] Qubit #{i+1} no fue enviado por Alice (fallo en pgen)")
                continue
            else:
                try: 
                    q1 = repeater.recvQubit()
                    print(f"[SWAP] Qubit #{i+1} de Alice recibido.")

                    q2 = repeater.createEPR("Bob")
                    print(f"[SWAP] EPR #{i+1} con Bob creado.")
                except Exception as e:
                    print(f"[SWAP] Error en swapping #{i+1}: {e}")

                try:
                    with open("fidelidad_alice.txt", "r") as f:
                        fidelidades = f.read().strip().split(",")
                except FileNotFoundError:
                    fidelidades = []

                w_alice = float(fidelidades[i])
                
                # Simular fidelidad del canal Charlie → Bob
                w_bob = max(0.0, min(1.0, round(random.gauss(0.9, 0.05), 3)))

                # Purificación en Charlie
                p_pur = (1+(w_alice*w_bob))/2
                print(f"[PURIFICACIÓN] Charlie tiene una probabilidad de purificación del {p_pur*100}%")
                if random.random() <= p_pur:
                    mejora = (w_alice+w_bob+4*w_alice*w_bob)/6
                    w_bob = min(w_bob + mejora, 1.0)
                    print(f"[PURIFICACIÓN] Charlie purificó el estado: mejora={mejora}, nueva w_Bob={w_bob:.3f}")
                else:
                    print("[PURIFICACIÓN] Charlie no logró purificar el estado.")

                # Simular tiempo de swapping
                inicio_swap = time.time()
                time.sleep(0.5)  # retardo interno del repetidor
                fin_swap = time.time()
                tiempo_swap = fin_swap - inicio_swap

                # Coherencia(solo temporal, puesto que es solo la temporal de la operación de swap)
                T_c = 10.0

                C_t = round(math.exp(-tiempo_swap / T_c), 3)

                if random.random() <= pswap:
                    w_swap = round(w_alice * w_bob, 3)
                    w_final = round(w_swap * C_t , 3)

                    print(f"[SWAP] Swapping exitoso:")
                    print(f"w_Alice={w_alice:.3f}, w_Bob={w_bob:.3f}, w_swap={w_swap:.3f}")
                    print(f"C_t={C_t}, w_out={w_final:.3f}")
    
                    with open("fidelidad_bob.txt", "w") as f_out:
                        f_out.write(",".join([str(w_final)]))
                    with open("qubit_enviado_rep.txt", "w") as f:
                        f.write(",".join(["ok"]))
                else:
                    print(f"[SWAP] Swapping fallido (pswap={pswap})")
                    with open("fidelidad_bob.txt", "w") as f_out:
                        f_out.write(",".join("0.0"))
                    with open("qubit_enviado.txt", "w") as f:
                        f.write(",".join(["fallo"]))
                try: 
                    q1.cnot(q2)
                    q1.H()
                    m1 = q1.measure()
                    m2 = q2.measure()
                    print(f"[SWAP] Medición Bell #{i+1}: m1={m1}, m2={m2}")
                except Exception as e:
                    print(f"[SWAP] Error en swapping #{i+1}: {e}")

if __name__ == "__main__":
    num_ParesEPR = int(sys.argv[1])
    pswap = float(sys.argv[2])
    entanglement_swap(num_ParesEPR, pswap)
