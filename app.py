import os
import subprocess
import time
from flask import Flask, render_template, jsonify, request
import random


app = Flask(__name__)
contador = 0
simulacion_en_curso = False

def retardo(distancia_km):
    """Calcula el tiempo de transmisión en segundos según la distancia en km."""
    return (distancia_km * 1000) / (2e8)

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

    return render_template("index.html", resultado=ultimo_resultado, contador=contador, historial=historial)

@app.route("/limpiar_historial")
def limpiar_historial():
    global contador, simulacion_en_curso
    contador = 0
    simulacion_en_curso = False
    try:
        open("historial_resultados.txt", "w").close()
        open("bob_resultado.txt", "w").close()
        subprocess.run(["python3", "limpiar_qubits.py"])
        print("[SERVIDOR] Historial y qubits limpiados correctamente.")
    except Exception as e:
        print(f"[ERROR] No se pudo limpiar el historial: {e}")
    return jsonify({"status": "ok"})

@app.route("/limpiar_qubits")
def limpiar_qubits():
    try:
        subprocess.run(["python3", "limpiar_qubits.py"])
        print("[SERVIDOR] Qubits limpiados correctamente.")
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[ERROR] No se pudo limpiar los qubits: {e}")
        return jsonify({"status": "error"})


@app.route("/simular")
def simular():
    global contador, simulacion_en_curso
    pgen = float(request.args.get("pgen", 0.8))
    pswap = float(request.args.get("pswap", 0.9))

    if simulacion_en_curso:
        print("[SERVIDOR] Simulación en curso. Ignorando nueva petición.")
        return jsonify({
            "resultado": "ERROR: Simulación en curso. Espera a que finalice.",
            "contador": contador,
            "historial": []
        })

    simulacion_en_curso = True
    inicio_real = time.time()
    pgen = float(request.args.get("pgen", 0.8))
    pswap = float(request.args.get("pswap", 0.9))
    modo = request.args.get("modo", "puro")
    num_qubits = int(request.args.get("num_qubits", 2))

    # Distancias físicas recibidas desde el HTML
    dist_ab = float(request.args.get("dist_ab", 50))  # Alice ↔ Bob
    dist_ac = float(request.args.get("dist_ac", 100)) # Alice ↔ Charlie
    dist_cb = float(request.args.get("dist_cb", 50))  # Charlie ↔ Bob

    print(f"[WEB] Iniciando simulación en modo: {modo} (p={pgen}, qubits={num_qubits})")
    print(f"[WEB] Distancias: AB={dist_ab} km, AC={dist_ac} km, CB={dist_cb} km")

    try:
        # Calcular tiempo estimado según el modo
        if modo == "puro":
            tiempo_estimado = retardo(dist_ab)
        elif modo == "werner":
            tiempo_estimado = retardo(dist_cb) + retardo(dist_ac) + retardo(dist_ac)
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
                subprocess.run(["python3", "alice.py", modo, str(pgen), str(num_qubits)])
                time.sleep(retardo(dist_ac))  # Alice → Repeater

                subprocess.run(["python3", "repeater.py", str(num_qubits)])
                time.sleep(retardo(dist_cb))  # Charlie → Bob

                # Leer fidelidad generada por Alice
                try:
                    with open("fidelidad_alice.txt", "r") as f:
                        w_in = float(f.read().strip())
                except:
                    w_in = 0.0

                subprocess.run(["python3", "bob.py", modo, str(w_in), str(num_qubits)])
                w_out = w_in  # En este modo, fidelidad se conserva

            elif modo == "swap":
                subprocess.run(["python3", "alice.py", modo, str(pgen), str(num_qubits)])
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
        try:
            with open("bob_resultado.txt", "r") as f:
                resultado = f.read().strip()

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
                h.write(f"{contador}: {resultado} (modo={modo}, qubits={num_qubits},estimado={tiempo_estimado:.6f}s, real={tiempo_real:.6f}s)\n")

        except FileNotFoundError:
            resultado = "ERROR: No se pudo leer el resultado."

        try:
            with open("historial_resultados.txt", "r") as h:
                historial = [line.strip() for line in h.readlines()]
        except FileNotFoundError:
            historial = []

        simulacion_en_curso = False

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
    app.run(debug=True)
