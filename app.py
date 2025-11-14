import os
import subprocess
import time
from flask import Flask, render_template, jsonify, request
import random
import math
import re
import sys
import requests
from multiprocessing import Process, Manager
from alice import run_alice
from bob import run_bob
from datetime import datetime
import json
import importlib.resources



app = Flask(__name__)
contador = 0
simulacion_en_curso = False

if len(sys.argv) > 1 and sys.argv[1].lower() == "bob":
    ROL = "bob"
    PUERTO = 5001
else:
    ROL = "alice"
    PUERTO = 5000
app = Flask(__name__)


# Reiniciar SimulaQron al iniciar el servidor
print("[INIT] Reiniciando SimulaQron...")
subprocess.run(["simulaqron", "reset", "--force"])
subprocess.run(["simulaqron", "start", "--name", "default", "--force", "-n", "Alice,Bob,Charlie"])
print("[INIT] Inicializando SimulaQron...")


@app.route("/crear_nodos_simulaqron")
def crear_nodos_simulaqron():
    limpiar_historial()
    nodos_raw = request.args.get("nodos", "")
    nodos = [n for n in nodos_raw.split(" ") if n]  # evita strings vacíos

    log_file = "simulaqron_log.txt"

    def log(msg):
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(msg + "\n")

    # Obtener nodos ya existentes
    nodos_creados = []
    resultado = subprocess.run(["simulaqron", "nodes", "get"],
                            capture_output=True, text=True)
    nodos_existentes = resultado.stdout.strip().split()  # ahora es lista correcta
    log(f"[SERVIDOR] Nodos existentes: {nodos_existentes}")

    for nodo in nodos:
        if nodo not in nodos_existentes:
            print(nodo)
            res_add = subprocess.run(["simulaqron", "nodes", "add", nodo, "--force"],
                                    capture_output=True, text=True)
            nodos_creados.append(nodo)
            log(f"[SERVIDOR] Nodo creado: {nodo} -> {res_add.stdout.strip()} {res_add.stderr.strip()}")

    log(f"[SERVIDOR] Nodos creados en esta petición: {nodos_creados}")
    log("--------------------------------------------------")
    resultado_fin= subprocess.run(["simulaqron", "nodes", "get"],
                            capture_output=True, text=True)
    nodos_existentes_fin = resultado_fin.stdout.strip().split()
    log(f"[SERVIDOR] Nodos existentes tras operacion: {nodos_existentes_fin}")

    return jsonify({"status": "ok", "nodos_creados": nodos_creados})

@app.route("/modificar_links", methods=["POST"])
def mod_links():
    data = request.get_json()
    links = data.get("links", [])

    conexiones = []
    for link in links:
        origen = link["source"]
        destino = link["target"]

        # Actualizar vecinos de origen
        subprocess.run(
            ["simulaqron", "nodes", "add", origen, "--force", "--neighbors", destino],
            capture_output=True, text=True
        )
        # Actualizar vecinos de destino
        subprocess.run(
            ["simulaqron", "nodes", "add", destino, "--force", "--neighbors", origen],
            capture_output=True, text=True
        )

        conexiones.append((origen, destino))

    return jsonify({"status": "ok", "conexiones": conexiones})



def buscar_network_json(base_dir):
    """
    Busca el archivo network.json dentro de cualquier subcarpeta de base_dir.
    Devuelve la primera ruta encontrada o None.
    """
    for root, dirs, files in os.walk(base_dir):
        if "network.json" in files and root.endswith("simulaqron/config"):
            print(os.path.join(root, "network.json"))
            return os.path.join(root, "network.json")
    return None

def mostrar_topologia():
    # Busca desde el directorio actual del proyecto
    ruta = buscar_network_json(os.getcwd())
    if ruta is None:
        # Si no lo encuentra, busca en el entorno de site-packages
        ruta = buscar_network_json(os.path.dirname(__file__))

    if ruta is None:
        print("[ERROR] No se encontró simulaqron/config/network.json")
        return {}

    with open(ruta) as f:
        data = json.load(f)
    print("[DEBUG] JSON completo:", data)

    try:
        topology = data["default"]["topology"]
        node_names = list(data["default"]["nodes"].keys())
    except KeyError:
        print("[ERROR] El archivo no contiene 'default' o 'topology'")
        return {}

    # Si la topología es null, crear pseudo-topología completa
    if topology is None:
        pseudo_topology = {}
        for nodo in node_names:
            pseudo_topology[nodo] = [n for n in node_names if n != nodo]
        return pseudo_topology

    resultado = {}
    for nodo, vecinos in topology.items():
        resultado[nodo] = vecinos
        print(f"Nodo {nodo} conectado con: {{{', '.join(vecinos)}}}")

    return resultado

@app.route("/topologia", methods=["GET"])
def topologia():
    return jsonify(mostrar_topologia())


def retardo(distancia_km):
    """Calcula el tiempo de transmisión en segundos según la distancia en km."""
    return (distancia_km * 1000) / (2e8) #(2/3)c

def parse_timestamp(ts):
    return datetime.strptime(ts, "%M:%S.%f")

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
        open("tiempo_creacion.txt", "w").close()
        open("tiempo_recepcion.txt", "w").close()
        open("qubit_enviado_rep.txt", "w").close()
        open("simulaqron_log.txt","w").close()
        # subprocess.Popen(["python3", "limpiar_qubits.py"]) Preparado para imprevistos de memoria cuantica
        print("[SERVIDOR] Historial y qubits limpiados correctamente.")
    except Exception as e:
        print(f"[ERROR] No se pudo limpiar el historial: {e}")
    return jsonify({"status": "ok"})

@app.route("/limpieza_docs")
def limpiar_txt():
    try:
        open("fidelidad_alice.txt", "w").close()
        open("fidelidad_bob.txt", "w").close()
        open("bob_resultado.txt", "w").close()
        open("qubit_enviado.txt", "w").close()
        open("tiempo_creacion.txt", "w").close()
        open("tiempo_recepcion.txt", "w").close()
        open("qubit_enviado_rep.txt", "w").close()
        open("simulaqron_log.txt","w").close()
        # subprocess.Popen(["python3", "limpiar_qubits.py"]) Preparado para imprevistos de memoria cuantica
        print("[SERVIDOR] Trazas de los qubits y qubits limpiados correctamente.")
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
    num_ParesEPR = int(request.args.get("num_ParesEPR", 2))
    modo_tiempo = request.args.get("modo_tiempo", "secuencial")
    print(f"[WEB] Modo de tiempo seleccionado: {modo_tiempo}")

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

    print(f"[WEB] Iniciando simulación en modo: {modo} (p={pgen_alice}, qubits={num_ParesEPR})")
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
            if modo_tiempo == "simultaneo":
                manager = Manager()
                semaforos = [manager.Semaphore(0) for _ in range(num_ParesEPR)]
                if modo == "puro":
                    # Ejecutar Alice
                    proceso_alice = Process(target=run_alice, args=(modo, 1.0, num_ParesEPR, modo_tiempo, semaforos))
                    proceso_alice.start()
                    time.sleep(retardo(dist_ab))  # Alice → Bob
                    inicio_bob = manager.Event()

                    # En Alice, al final de run_alice:
                    inicio_bob.set()

                    # En Bob, al inicio de run_bob:
                    inicio_bob.wait()

                    # Ejecutar Bob
                    w_in = 1.0
                    proceso_bob = Process(target=run_bob, args=(modo, w_in, num_ParesEPR, modo_tiempo, semaforos))
                    proceso_bob.start()

                    proceso_alice.join()
                    proceso_bob.join()

                elif modo == "werner":
                    proceso_alice = Process(target=run_alice, args=(modo, pgen_alice, num_ParesEPR, modo_tiempo, semaforos))
                    proceso_alice.start()
                    time.sleep(retardo(dist_ab))  # Alice → Repeater

                    proceso_alice.join()

                    # Leer fidelidad generada por Alice
                    with open("fidelidad_alice.txt", "r") as f:
                        fidelidades = f.read().strip().split(",")
                        valores = [float(w) for w in fidelidades if w != "None"]
                        w_in = round(sum(valores) / len(valores), 3) if valores else 0.0

                    proceso_bob = Process(target=run_bob, args=(modo, w_in, num_ParesEPR, modo_tiempo, semaforos))
                    proceso_bob.start()
                    proceso_bob.join()
                    w_out = w_in  # En este modo, fidelidad se conserva

                elif modo == "swap":
                    proceso_alice = Process(target=run_alice, args=(modo, pgen_alice, num_ParesEPR, modo_tiempo, semaforos))
                    proceso_alice.start()
                    time.sleep(retardo(dist_ac))  # Alice → Charlie

                    proceso_alice.join()

                    subprocess.run(["python3", "repeater_swap.py", str(num_ParesEPR), str(pswap)])
                    time.sleep(retardo(dist_cb))  # Charlie → Bob

                    with open("fidelidad_alice.txt", "r") as f:
                        fidelidades = f.read().strip().split(",")
                        valores = [float(w) for w in fidelidades if w != "None"]
                        w_in = round(sum(valores) / len(valores), 3) if valores else 0.0

                    proceso_bob = Process(target=run_bob, args=(modo, w_in, num_ParesEPR, modo_tiempo, semaforos))
                    proceso_bob.start()
                    proceso_bob.join()
                    w_out = w_in  # Bob calculará el producto con su propio w
            else:
                if modo in ["puro", "werner", "swap"]:
                    if modo == "puro":
                        print(f"[ALICE] Aver que pasa antes de ejecutar")
                        subprocess.run(["python3", "alice.py", modo, str(1.0), str(num_ParesEPR), modo_tiempo, "no_semaforos"])
                        time.sleep(retardo(dist_ab))  # Alice → Bob
                        w_out = 1.0
                        subprocess.run(["python3", "bob.py", modo, str(w_out), str(num_ParesEPR), modo_tiempo, "no_semaforos"])

                    elif modo == "werner":
                        subprocess.run(["python3", "alice.py", modo, str(pgen_alice), str(num_ParesEPR), modo_tiempo, "no_semaforos"])
                        time.sleep(retardo(dist_ab))  # Alice → Repeater

                        # Leer fidelidad generada por Alice
                        with open("fidelidad_alice.txt", "r") as f:
                            fidelidades = f.read().strip().split(",")
                            valores = [float(w) for w in fidelidades if w != "None"]
                            w_in = round(sum(valores) / len(valores), 3) if valores else 0.0

                        subprocess.run(["python3", "bob.py", modo, str(w_in), str(num_ParesEPR), modo_tiempo,"no_semaforos"])
                        w_out = w_in  # En este modo, fidelidad se conserva

                    elif modo == "swap":
                        subprocess.run(["python3", "alice.py", modo, str(pgen_alice), str(num_ParesEPR), modo_tiempo, "no_semaforos"])
                        time.sleep(retardo(dist_ac))  # Alice → Charlie

                        subprocess.run(["python3", "repeater_swap.py", str(num_ParesEPR), str(pswap)])
                        time.sleep(retardo(dist_cb))  # Charlie → Bob

                        # Leer fidelidad generada por Alice
                        with open("fidelidad_alice.txt", "r") as f:
                            fidelidades = f.read().strip().split(",")
                            valores = [float(w) for w in fidelidades if w != "None"]
                            w_in = round(sum(valores) / len(valores), 3) if valores else 0.0

                        subprocess.run(["python3", "bob.py", modo, str(w_in), str(num_ParesEPR), modo_tiempo,"no_semaforos"])
                        w_out = w_in  # Bob calculará el producto con su propio w

        else:
            w_out = 0.0  # Modo desconocido
            
        fin_real = time.time()
        tiempo_real = fin_real - inicio_real

        # Parámetros de coherencia
        T_c = 10.0  # tiempo de coherencia en segundos
        L_c = 100.0  # longitud de coherencia en km


        with open("tiempo_creacion.txt", "r") as f:
            t_creacion = f.read().strip().split(",")

        with open("tiempo_recepcion.txt", "r") as f:
            t_recepcion = f.read().strip().split(",")

        coherencias_temporales = []

        for i in range(len(t_creacion)):
            if t_creacion[i] != "None" and t_recepcion[i] != "None":
                t1 = parse_timestamp(t_creacion[i])
                t2 = parse_timestamp(t_recepcion[i])
                delta = (t2 - t1).total_seconds()
                ct = round(math.exp(-delta / T_c), 3)
                print(f"[DECOHERENCIA TEMPORAL] Par EPR #{i}: {ct}")
            else:
                ct = 1.0
            coherencias_temporales.append(ct)




        # Recibir canal cuántico desde la petición
        canal_cuantico = request.args.get("canal_cuantico", "1.0")

        try:
            # Caso 1: el usuario ha introducido un número (0–1)
            canal_cuantico = float(canal_cuantico)
            coherencia_fisica = round(canal_cuantico, 3)

        except ValueError:
            # Caso 2: el usuario ha introducido una matriz 4x4 en formato JSON
            canal_cuantico = json.loads(canal_cuantico)  # lista de listas 4x4

            # Ejemplo de operación: usar la traza como medida de coherencia
            traza = sum(canal_cuantico[i][i] for i in range(4))
            coherencia_fisica = round(traza, 3)

        print("Canal cuántico recibido:", canal_cuantico)
        print("Coherencia física calculada:", coherencia_fisica)


        try:
            # Leer mediciones y fidelidades originales
            with open("bob_resultado.txt", "r") as f:
                mediciones = f.read().strip().split(",")

            with open("fidelidad_bob.txt", "r") as f:
                fidelidades = f.read().strip().split(",")
            # Aplicar corrección de fidelidad si no es modo puro
            fidelidades_corregidas = []
            for idx, w in enumerate(fidelidades):
                if w != "None":
                    w_out_original = float(w)
                    ct = coherencias_temporales[idx] if idx < len(coherencias_temporales) else 1.0
                    print(ct)
                    if modo != "puro":
                        w_out_corregido = round(w_out_original * ct * coherencia_fisica, 3)
                    else:
                        w_out_corregido = 1.0
                    fidelidades_corregidas.append(f"w{idx+1}={w_out_corregido:.3f}")
                else:
                    fidelidades_corregidas.append(f"w{idx+1}=None")

            # Construir resultado compacto
            resultado = (
                f"[{','.join(mediciones)}]"
                f"({','.join(fidelidades_corregidas)})"
                f"(modo={modo},num_ParesEPR={num_ParesEPR})"
            )

            # Verificar si hubo error
            if "ERROR" in resultado.upper():
                print("[SERVIDOR] Error detectado en resultado. Deteniendo simulación.")
                simulacion_en_curso = False
                return jsonify({
                    "resultado": resultado,
                    "contador": contador,
                    "historial": []
                })

            # Actualizar historial
            contador += 1
            with open("historial_resultados.txt", "a") as h:
                h.write(
                    f"{contador}: {resultado} "
                    f"(estimado={tiempo_estimado:.6f}s, real={tiempo_real:.6f}s"
                )
                if modo != "puro":
                    h.write(f", Se le aplica coherencia temporal y la del canal cuántico asociado")
                h.write(")\n")

        except FileNotFoundError:
            resultado = "ERROR: No se pudo leer el resultado."

        # Leer historial completo
        try:
            with open("historial_resultados.txt", "r") as h:
                historial = [line.strip() for line in h.readlines()]
        except FileNotFoundError:
            historial = []

        # Finalizar simulación
        simulacion_en_curso = False

        # Enviar historial a Bob si el rol es Alice
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

        # Devolver todo junto en un único mensaje
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
    app.run(host="0.0.0.0", port=PUERTO, debug=True) #Quitar debug=True si no estoy en produccion

