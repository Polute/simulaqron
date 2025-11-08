from cqc.pythonLib import CQCConnection
import subprocess

def nodo_activo(nombre):
    try:
        resultado = subprocess.run(["simulaqron", "getnodes"], capture_output=True, text=True)
        nodos = resultado.stdout.strip().split("\n")
        return nombre in nodos
    except Exception as e:
        print(f"[ERROR] No se pudo verificar el nodo {nombre}: {e}")
        return False

def limpiar_nodo(nombre):
    if not nodo_activo(nombre):
        print(f"[LIMPIAR] Nodo {nombre} no está activo. Se omite.")
        return

    try:
        with CQCConnection(nombre) as nodo:
            for _ in range(10):  # máximo 10 intentos
                try:
                    q = nodo.recvQubit()
                    q.release()
                    print(f"[{nombre}] Qubit residual liberado.")
                except:
                    break
    except Exception as e:
        print(f"[ERROR] No se pudo conectar con {nombre}: {e}")

if __name__ == "__main__":
    for nombre in ["Alice", "Bob", "Charlie"]:
        limpiar_nodo(nombre)
