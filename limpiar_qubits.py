from cqc.pythonLib import CQCConnection
import time
def limpiar_nodo(nombre):
    with CQCConnection(nombre) as nodo:
        while True:
            try:
                q = nodo.recvQubit()
                q.release()  # o q.measure()
                print(f"[{nombre}] Qubit residual liberado.")
            except:
                break

if __name__ == "__main__":
    for nombre in ["Alice", "Bob", "Charlie"]:
        limpiar_nodo(nombre)
        time.sleep(0.5)
