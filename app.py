import os
import subprocess
import time
from flask import Flask, render_template, jsonify, request
import random
import math
import re
import sys
import requests



app = Flask(__name__)
contador = 0
simulacion_en_curso = False

if len(sys.argv) > 1 and sys.argv[1].lower() == "bob":
    ROL = "bob"
    PUERTO = 5001
else:
    ROL = "alice"
    PUERTO = 5000

# Reiniciar SimulaQron al iniciar el servidor
print("[INIT] Reiniciando SimulaQron...")
subprocess.run(["simulaqron", "reset", "--force"])
subprocess.run(["simulaqron", "start", "--name", "default", "--force"])
print("[INIT] SimulaQron iniciado.")

resultado = subprocess.run(["simulaqron", "nodes", "list"], capture_output=True, text=True)
nodos_existentes = resultado.stdout.strip().split("\n")


"""
@app.route("/crear_nodos_simulaqron")
def crear_nodos_simulaqron():
    nodos_raw = request.args.get("nodos", "")
    nodos = nodos_raw.split(" ")

    # Establecer red activa
    print("[SIMULAQRON] Estableciendo red 'default' como activa...")
    subprocess.run(["simulaqron", "set", "network.name", "default"])

    # Obtener nodos ya existentes
    resultado = subprocess.run(["simulaqron", "nodes", "get"], capture_output=True, text=True)
    nodos_existentes = resultado.stdout.strip().split("\n")
    print(f"[SERVIDOR] Nodos existentes: {nodos_existentes}")
    nodos_creados = []
    for nodo in nodos:
        if nodo not in nodos_existentes:
            subprocess.run(["simulaqron", "nodes", "add", nodo])
            nodos_creados.append(nodo)

    return jsonify({"status": "ok", "nodos_creados": nodos_creados})
"""

def retardo(distancia_km):
    """Calcula el tiempo de transmisión en segundos según la distancia en km."""
    return (distancia_km * 1000) / (2e8)

@app.route("/actualizar_historial", methods=["POST"])
def actualizar_historial():
    if ROL != "bob":
        return jsonify({"error": "Este nodo no puede recibir historial."})

    data = request.get_json()
    resultado = data.get("resultado", "Sin resultado")
    contador = data.get("contador", 0)
    historial = data.get("historial", "Ninguna operación realizada")

    print(f"[BOB] Contador qubit entrelazado recibido: {resultado}")
    print(f"[BOB] Qubit entrelazado recibido: {resultado}")
    print(f"[BOB] Qubits entrelazado recibido hasta ahora: {historial}")
    print(f"[BOB] Historial actualizado con simulación #{contador}")

    return render_template(
        "receiver.html", 
        resultado=resultado, 
        contador=contador, 
        historial=historial,
        rol=ROL
        )

@app.route("/")
def index():
    try:
        with open("bob_resultado.txt", "r") as f:
            ultimo_resultado = f.read()
    except FileNotFoundError:
        ultimo_resultado = "Aún no se ha realizado la simulación."

    try:
        with open("historial_resultados.txt", "r") as h:
            historial = [line.strip() for line in h.readlines()]
    except FileNotFoundError:
        historial = []

    if ROL == "alice":
        return render_template(
            "index.html",
            resultado=ultimo_resultado,
            contador=contador,
            historial=historial,
            rol=ROL
        )
    elif ROL == "bob":
        return render_template(
            "receiver.html",
            resultado=ultimo_resultado,
            contador=contador,
            historial=historial,
            rol=ROL
        )
    else:
        return "Rol no reconocido", 400

@app.route("/limpiar_historial")
def limpiar_historial():
    global contador, simulacion_en_curso
    contador = 0
    simulacion_en_curso = False
    try:
        open("fidelidad_alice.txt", "w").close()
        open("fidelidad_bob.txt", "w").close()
        open("historial_resultados.txt", "w").close()
        open("bob_resultado.txt", "w").close()
        open("qubit_enviado.txt", "w").close()
        subprocess.Popen(["python3", "limpiar_qubits.py"])
        print("[SERVIDOR] Historial y qubits limpiados correctamente.")
    except Exception as e:
        print(f"[ERROR] No se pudo limpiar el historial: {e}")
    return jsonify({"status": "ok"})

@app.route("/limpiar_qubits")
def limpiar_qubits():
    try:
        subprocess.Popen(["python3", "limpiar_qubits.py"])
        print("[SERVIDOR] Qubits limpiados correctamente.")
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[ERROR] No se pudo limpiar los qubits: {e}")
        return jsonify({"status": "error"})


@app.route("/simular")
def simular():
    global contador, simulacion_en_curso

    if simulacion_en_curso:
        print("[SERVIDOR] Simulación en curso. Ignorando nueva petición.")
        return jsonify({
            "resultado": "ERROR: Simulación en curso. Espera a que finalice.",
            "contador": contador,
            "historial": []
        })

    simulacion_en_curso = True
    inicio_real = time.time()
    pswap = float(request.args.get("pswap", 0.9))
    modo = request.args.get("modo", "puro")
    num_qubits = int(request.args.get("num_qubits", 2))

    # --- PGEN por nodo ---
    pgen_nodos_raw = request.args.get("pgen_nodos", "")
    pgen_por_nodo = {}
    for item in pgen_nodos_raw.split(","):
        if ":" in item:
            nombre, valor = item.split(":")
            pgen_por_nodo[nombre] = float(valor)

    # --- Distancias entre nodos ---
    distancias_raw = request.args.get("distancias", "")
    dist_por_par = {}
    for item in distancias_raw.split(","):
        partes = item.split(":")
        if len(partes) == 3:
            origen, destino, valor = partes
            clave_directa = f"{origen}-{destino}"
            clave_inversa = f"{destino}-{origen}"
            dist_por_par[clave_directa] = float(valor)
            dist_por_par[clave_inversa] = float(valor)  # acceso simétrico


    # Obtener distancias específicas
    dist_ab = dist_por_par.get("Alice-Bob", 50)
    dist_ac = dist_por_par.get("Alice-Charlie", 100)
    dist_cb = dist_por_par.get("Charlie-Bob", 50)

    # Obtener pgen específico
    pgen_alice = pgen_por_nodo.get("Alice", 0.8)

    print(f"[WEB] Iniciando simulación en modo: {modo} (p={pgen_alice}, qubits={num_qubits})")
    print(f"[WEB] Distancias: AB={dist_ab} km, AC={dist_ac} km, CB={dist_cb} km")

    try:
        # Calcular tiempo estimado según el modo
        if modo == "puro":
            tiempo_estimado = retardo(dist_ab)
        elif modo == "werner":
            tiempo_estimado = retardo(dist_ab)
        elif modo == "swap":
            tiempo_estimado = retardo(dist_cb) + retardo(dist_ac) + retardo(dist_ac)
        else:
            tiempo_estimado = 0
        # Operaciones de simulación
        if modo in ["puro", "werner", "swap"]:
            if modo == "puro":
                subprocess.run(["python3", "alice.py", modo, str(1.0), str(num_qubits)])
                time.sleep(retardo(dist_ab))  # Alice → Bob

                w_out = 1.0
                subprocess.run(["python3", "bob.py", modo, str(w_out), str(num_qubits)])

            elif modo == "werner":
                subprocess.run(["python3", "alice.py", modo, str(pgen_alice), str(num_qubits)])
                time.sleep(retardo(dist_ab))  # Alice → Repeater

                # Leer fidelidad generada por Alice
                try:
                    with open("fidelidad_alice.txt", "r") as f:
                        w_in = float(f.read().strip())
                except:
                    w_in = 0.0

                subprocess.run(["python3", "bob.py", modo, str(w_in), str(num_qubits)])
                w_out = w_in  # En este modo, fidelidad se conserva

            elif modo == "swap":
                subprocess.run(["python3", "alice.py", modo, str(pgen_alice), str(num_qubits)])
                time.sleep(retardo(dist_ac))  # Alice → Charlie

                subprocess.run(["python3", "repeater_swap.py", str(num_qubits), str(pswap)])
                time.sleep(retardo(dist_cb))  # Charlie → Bob

                # Leer fidelidad generada por Alice
                try:
                    with open("fidelidad_alice.txt", "r") as f:
                        w_in = float(f.read().strip())
                except:
                    w_in = 0.0

                subprocess.run(["python3", "bob.py", modo, str(w_in), str(num_qubits)])
                w_out = w_in  # Bob calculará el producto con su propio w

        else:
            w_out = 0.0  # Modo desconocido
            
        fin_real = time.time()
        tiempo_real = fin_real - inicio_real

        # Parámetros de coherencia
        T_c = 10.0  # tiempo de coherencia en segundos
        L_c = 100.0  # longitud de coherencia en km

        # Coherencia temporal
        coherencia_temporal = round(math.exp(-tiempo_real / T_c), 3)

        # Coherencia física (según modo)
        if modo == "puro":
            distancia_total = dist_ab
        elif modo == "werner":
            distancia_total = dist_ab
        elif modo == "swap":
            distancia_total = dist_ac + dist_cb
        else:
            distancia_total = 0.0

        coherencia_fisica = round(math.exp(-distancia_total / L_c), 3)

        try:
            # Leer resultado original
            with open("bob_resultado.txt", "r") as f:
                resultado = f.read().strip()

            # Extraer w_out original
            match = re.search(r"w_out=(\d+\.\d+)", resultado)
            if match:
                w_out_original = float(match.group(1))
                w_out_corregido = round(w_out_original * coherencia_temporal * coherencia_fisica, 3)

                # Reemplazar w_out en el texto
                resultado = re.sub(r"w_out=\d+\.\d+", f"w_out={w_out_corregido:.3f}", resultado)

                # Reescribir archivo con nuevo w_out
                with open("bob_resultado.txt", "w") as f:
                    f.write(resultado)
            else:
                w_out_corregido = 0.0  # Si no se encuentra, usar valor por defecto
            if "ERROR" in resultado.upper():
                print("[SERVIDOR] Error detectado en resultado. Deteniendo simulación.")
                simulacion_en_curso = False
                return jsonify({
                    "resultado": resultado,
                    "contador": contador,
                    "historial": []
                })

            contador += 1
            with open("historial_resultados.txt", "a") as h:
                if modo != "puro":
                    h.write(
                    f"{contador}: {resultado} (modo={modo}, qubits={num_qubits}, "
                    f"estimado={tiempo_estimado:.6f}s, real={tiempo_real:.6f}s), "
                    f"C_t={coherencia_temporal}, C_d={coherencia_fisica}\n"
                )
                else:
                    h.write(
                    f"{contador}: {resultado} (modo={modo}, qubits={num_qubits}, "
                    f"estimado={tiempo_estimado:.6f}s, real={tiempo_real:.6f}s)\n"
                )


        except FileNotFoundError:
            resultado = "ERROR: No se pudo leer el resultado."

        try:
            with open("historial_resultados.txt", "r") as h:
                historial = [line.strip() for line in h.readlines()]
        except FileNotFoundError:
            historial = []

        simulacion_en_curso = False
        if ROL == "alice":
            try:
                requests.post("http://localhost:5001/actualizar_historial", json={
                    "resultado": resultado,
                    "contador": contador,
                    "historial": historial
                })
                print("[ALICE] Historial enviado a Bob.")
            except Exception as e:
                print(f"[ALICE] No se pudo enviar historial a Bob: {e}")

        return jsonify({
            "resultado": resultado,
            "contador": contador,
            "historial": historial
        })

    except Exception as e:
        simulacion_en_curso = False
        print(f"[ERROR] Fallo en la simulación: {e}")
        return jsonify({
            "resultado": "ERROR: Fallo interno en la simulación.",
            "contador": contador,
            "historial": []
        })

if __name__ == "__main__":
    print(f"[SERVIDOR] Iniciando servidor en el puerto {PUERTO} con rol {ROL}...")
    app.run(host="0.0.0.0", port=PUERTO)
