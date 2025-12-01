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
import socket
from flask_cors import CORS

import socket

def puerto_activo(host, port):
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False



def puerto_disponible(puerto: int) -> bool:
    """Devuelve True si el puerto está libre en localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", puerto)) != 0

def seleccionar_puerto(inicio=5000, fin=5010, excluir=None):
    """
    Recorre los puertos en el rango [inicio, fin].
    Devuelve el primer puerto libre que no esté en 'excluir'.
    """
    excluir = excluir or []
    for puerto in range(inicio, fin + 1):
        if puerto in excluir:
            continue
        if puerto_disponible(puerto):
            print(f"[INFO] Puerto libre encontrado: {puerto}")
            return puerto
    return None



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

    with open(ruta, encoding="utf-8") as f:
        data = json.load(f)
    print("[DEBUG] JSON completo:", data)

    try:
        topology = data["default"].get("topology")
        node_ids = list(data["default"]["nodes"].keys())
    except KeyError:
        print("[ERROR] El archivo no contiene 'default' o 'topology'")
        return {}

    # Si la topología es null, crear pseudo-topología completa
    if topology is None:
        pseudo_topology = {}
        for nodo in node_ids:
            pseudo_topology[nodo] = [n for n in node_ids if n != nodo]
        return pseudo_topology

    # Normalizar topología: solo vecinos válidos y distintos del propio nodo
    resultado = {}
    for nodo, vecinos in topology.items():
        vecinos_filtrados = [
            v for v in vecinos
            if v in node_ids and v != nodo
        ]
        resultado[nodo] = vecinos_filtrados
        print(f"Nodo {nodo} conectado con: {{{', '.join(vecinos_filtrados)}}}")

    return resultado

    
def retardo(distancia_km):
    """Calcula el tiempo de transmisión en segundos según la distancia en km."""
    return (distancia_km * 1000) / (2e8) #(2/3)c

def parse_timestamp(ts):
    return datetime.strptime(ts, "%M:%S.%f")
def construir_links_desde_nodos(nodos):
    """
    A partir de la lista de nodos (cada uno con 'neighbors'),
    devuelve una lista de enlaces con source, target y distanciaKm.
    """
    links = []
    for nodo in nodos:
        source = nodo.get("id") or nodo.get("name")  # usa id si existe, si no name
        for vecino in nodo.get("neighbors", []):
            target = vecino.get("id") or vecino.get("name")
            distancia = vecino.get("distanceKm", 0)

            # Evitar duplicados (Alice->Bob y Bob->Alice)
            existe = any(
                (l["source"] == source and l["target"] == target) or
                (l["source"] == target and l["target"] == source)
                for l in links
            )
            if not existe:
                links.append({
                    "source": source,
                    "target": target,
                    "distanciaKm": distancia
                })
    return links
# Nodos predefinidos (con IDs distintos para no colisionar)
PREDEFINED_NODES = [
    {
        "id": "node_alice_pre",
        "name": "Alice_pre",
        "x": 100,
        "y": 100,
        "pgen": 0.8,
        "roles": ["emisor", "receptor"],
        "neighbors": [],   # Alice no tiene vecinos iniciales
        "parEPR": []
    },
    {
        "id": "node_bob_pre",
        "name": "Bob_pre",
        "x": 300,
        "y": 100,
        "pgen": 0.7,
        "roles": ["receptor", "repeater"],
        "neighbors": [
            {"id": "node_alice_pre", "distanceKm": 50}
        ],
        "parEPR": []
    },
    {
        "id": "node_charlie_pre",
        "name": "Charlie_pre",
        "x": 200,
        "y": 250,
        "pgen": 0.9,
        "roles": ["emisor", "repeater"],
        "neighbors": [
            {"id": "node_alice_pre", "distanceKm": 70},
            {"id": "node_bob_pre", "distanceKm": 40}
        ],
        "parEPR": []
    }
]
# Reiniciar SimulaQron al iniciar el servidor
print("[INIT] Reiniciando SimulaQron...")
subprocess.run(["simulaqron", "reset", "--force"])
subprocess.run(["simulaqron", "start", "--name", "default", "--force", "-n", "node_alice_pre,node_bob_pre,node_charlie_pre"])
print("[INIT] Inicializando SimulaQron...")


contador = 0
simulacion_en_curso = False
def app_open(ROL, PUERTO):
    # Diccionario que mapea puertos a nodos completos
    PORT_NODE_MAP = {
        5000: {
            "id": "node_alice",
            "name": "Alice",
            "x": 100,
            "y": 100,
            "pgen": 0.8,
            "roles": ["emisor", "receptor"],
            "neighbors": []   # Alice no tiene vecinos iniciales
        },
        5002: {
            "id": "node_bob",
            "name": "Bob",
            "x": 300,
            "y": 100,
            "pgen": 0.7,
            "roles": ["receptor", "repeater"],
            "neighbors": [
                {"id": "node_alice", "distanceKm": 50}
            ]
        },
        5003: {
            "id": "node_charlie",
            "name": "Charlie",
            "x": 200,
            "y": 250,
            "pgen": 0.9,
            "roles": ["emisor", "repeater"],
            "neighbors": [
                {"id": "node_alice", "distanceKm": 70},
                {"id": "node_bob", "distanceKm": 40}
            ]
        }
    }

    

    nodo_info = PORT_NODE_MAP.get(PUERTO, {"id": "node_unknown", "name": "Desconocido", "neighbors": []})
    app = Flask(__name__)
    @app.route("/")
    def index():
        try:
            with open("pre_docs/bob_resultado.txt", "r") as f:
                ultimo_resultado = f.read()
        except FileNotFoundError:
            ultimo_resultado = "Aún no se ha realizado la simulación."

        try:
            with open("pre_docs/historial_resultados.txt", "r") as h:
                historial = [line.strip() for line in h.readlines()]
        except FileNotFoundError:
            historial = []

        if ROL == "alice":
            return render_template(
                "nodo.html",
                resultado=ultimo_resultado,
                contador=contador,
                historial=historial,
                rol=ROL,
                nodo_info=nodo_info,

            )
        elif ROL == "bob":
            return render_template(
                "receiver.html",
                resultado=ultimo_resultado,
                contador=len(historial),
                historial=historial,
                rol=ROL,
                nodo_info=nodo_info,
            )
        elif ROL == "master":
            nodos = []
            for port in range(5000, 5011):
                if port == 5001:
                    continue
                try:
                    res = requests.get(f"http://localhost:{port}/info", timeout=1)
                    nodos.append(res.json())   # cada res.json() es un nodo completo
                except Exception:
                    pass

            if not nodos:
                nodos = PREDEFINED_NODES

            # Enviar solo los nodos, sin links
            nodo_info_master = {
                "nodes": nodos
            }

            return render_template(
                "index.html",
                resultado=ultimo_resultado,
                contador=len(historial),
                historial=historial,
                rol=ROL,
                nodo_info=nodo_info_master
            )

    # Endpoint JSON del estado del nodo
    @app.route("/info")
    def info():
        return jsonify(nodo_info)

    # Endpoint para actualizar el estado del nodo
    @app.route("/update", methods=["POST"])
    def update():
        data = request.get_json()
        for key in ["id", "name", "pgen", "pswap", "roles", "neighbors", "parEPR"]:
            if key in data:
                nodo_info[key] = data[key]
        return jsonify({"status": "ok", "nodo_info": nodo_info})
    NODOS_PUERTOS = {}  # nodo_name -> puerto

    @app.route("/actualizar_mapa")
    def actualizar_mapa():
        nodos = []
        for port in range(5000, 5011):
            if port == 5001:
                continue
            try:
                res = requests.get(f"http://localhost:{port}/info", timeout=1)
                res.raise_for_status()
                nodo = res.json()
                NODOS_PUERTOS[nodo["id"]] = port
                nodos.append(nodo)
                print(f"Nodo recogido: {nodo}")
            except (requests.exceptions.RequestException, ValueError):
                pass

        if not nodos:
            nodos = PREDEFINED_NODES

        limpiar_historial()
        antes_start = time.time()
        subprocess.run(["simulaqron", "reset", "--force"], capture_output=True, text=True)

        ids_actuales = [n["id"] for n in nodos]
        todos_pre = all(n["id"].endswith("pre") for n in nodos)

        # Arrancar nodos según cantidad
        if len(ids_actuales) < 4 and todos_pre:
            # Arrancar todos los nodos juntos con sus IDs reales
            proc = subprocess.Popen(
                ["simulaqron", "start", "--name", "default", "--force", "-n", ",".join(ids_actuales)]
            )
        else:
            # Más de 4: extender como línea, también con IDs reales
            print("Con estos nodos: ", ids_actuales)
            proc = subprocess.Popen(
                ["simulaqron", "start", "--name", "default", "--force", "-n", ",".join(ids_actuales), "-t", "path"]
            )

        # Construir diccionario de vecinos simétricos
        vecinos_dict = {n["id"]: set() for n in nodos}
        for nodo in nodos:
            nodo_id = nodo["id"]
            for vecino in nodo.get("neighbors", []):
                vecino_id = vecino.get("id")
                if vecino_id and vecino_id != nodo_id:
                    if vecino_id in vecinos_dict:
                        vecinos_dict[nodo_id].add(vecino_id)
                        vecinos_dict[vecino_id].add(nodo_id)
                    else:
                        print(f"Vecino {vecino_id} ignorado: no está en nodos actuales")


        # Consolidar links
        links_dict = {}
        for nodo in nodos:
            nodo_id = nodo["id"]
            ts_nodo = nodo.get("lastUpdated", 0)
            for vecino in nodo.get("neighbors", []):
                vecino_id = vecino.get("id")
                if vecino_id in vecinos_dict[nodo_id]:
                    par = tuple(sorted([nodo_id, vecino_id]))
                    distancia = vecino.get("distanceKm", 0)
                    if par not in links_dict:
                        links_dict[par] = {"distanciaKm": distancia, "lastUpdated": ts_nodo}
                    else:
                        if ts_nodo > links_dict[par]["lastUpdated"]:
                            links_dict[par]["distanciaKm"] = distancia
                            links_dict[par]["lastUpdated"] = ts_nodo

        links = [
            {"source": par[0], "target": par[1], "distanciaKm": info["distanciaKm"]}
            for par, info in links_dict.items()
        ]
        
        return jsonify({"nodes": nodos, "links": links})

    # Endpoint para enviar órdenes a los nodos
    @app.route("/mandate", methods=["POST"])
    def send_mandates():
        data = request.get_json()  # formato esperado: { nodo_id: [ {accion:..., ...}, ... ], ... }
        if not isinstance(data, dict):
            return jsonify({"error": "Formato inválido"}), 400

        for nodo_id, instrucciones in data.items():
            print(f"{nodo_id} estará en {NODOS_PUERTOS}")

            if nodo_id not in NODOS_PUERTOS:
                print(f"No se encontró puerto para nodo {nodo_id}")
                continue

            puerto = NODOS_PUERTOS[nodo_id]
            url = f"http://localhost:{puerto}/mandate"  # apuntamos al POST en el nodo

            try:
                res = requests.post(url, json={nodo_id: instrucciones}, timeout=2)
                if res.status_code == 200:
                    print(f"Instrucciones enviadas a {nodo_id}: {instrucciones}")
                else:
                    print(f"Error enviando instrucciones a {nodo_id}: {res.status_code}")
            except Exception as e:
                print(f"Excepción enviando a {nodo_id}: {e}")

        return jsonify({"status": "ok"})
    
    MASTER_PAR_EPR = {}

    @app.route("/master/parEPR", methods=["GET", "POST"])
    def master_parEPR():
        if request.method == "POST":
            data = request.get_json()
            if not isinstance(data, dict):
                return jsonify({"error": "Formato inválido"}), 400

            for nodo_id, historial in data.items():
                for epr in historial:
                    clave = f"{nodo_id}-{epr['vecino']}"
                    if clave not in MASTER_PAR_EPR:
                        MASTER_PAR_EPR[clave] = []
                    # buscar si ya existe ese id y actualizar
                    updated = False
                    for i, existente in enumerate(MASTER_PAR_EPR[clave]):
                        if str(existente.get("id")) == str(epr.get("id")):
                            existente.update(epr)
                            MASTER_PAR_EPR[clave][i] = existente
                            updated = True
                            break
                    if not updated:
                        MASTER_PAR_EPR[clave].append(epr)
                    print(f"[MASTER] Historial actualizado para {clave}: {epr}")

        # Tanto GET como POST devuelven el estado actual
        return jsonify({"status": "ok", "MASTER_PAR_EPR": MASTER_PAR_EPR})

    
    @app.route("/master/parEPR/clear", methods=["POST"])
    def master_parEPR_clear():
        MASTER_PAR_EPR.clear()
        return jsonify({"status": "cleared"})


    @app.route("/crear_nodos_simulaqron")
    def crear_nodos_simulaqron():
        limpiar_historial()
        nodos_raw = request.args.get("nodos", "")
        nodos = [n for n in nodos_raw.split(" ") if n]  # evita strings vacíos

        log_file = "pre_docs/simulaqron_log.txt"

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

            topologia = mostrar_topologia()
            vecinos_actuales = topologia.get(origen, [])

            todos_nodos = list(topologia.keys())
            # Lista de todos menos el propio origen
            todos_menos_origen = [n for n in todos_nodos if n != origen]

            if set(vecinos_actuales) == set(todos_menos_origen):
                # Caso 1: el origen todavía tiene a TODOS como vecinos
                # → lo reducimos a solo el destino
                nuevos_vecinos = [destino]
            else:
                # Caso 2: ya no tiene a todos, solo algunos
                # → añadimos el destino a los que ya tiene
                nuevos_vecinos = list(vecinos_actuales)
                if destino not in nuevos_vecinos:
                    nuevos_vecinos.append(destino)

            # Actualizar origen con la lista corregida
            subprocess.run(
                ["simulaqron", "nodes", "add", origen, "--force", "--neighbors", ",".join(nuevos_vecinos)],
                capture_output=True, text=True
            )

            
            topologia = mostrar_topologia()
            for nodo, vecinos in topologia.items():
                if nodo != origen:
                    if nodo in nuevos_vecinos:
                        # Este nodo debe tener al origen como vecino
                        if origen not in vecinos:
                            vecinos.append(origen)
                    else:
                        # Este nodo NO debe tener al origen como vecino
                        if origen in vecinos:
                            vecinos.remove(origen)

                    # Actualizar SimulaQron con la lista corregida
                    subprocess.run(
                        ["simulaqron", "nodes", "add", nodo, "--force", "--neighbors", ",".join(vecinos)],
                        capture_output=True, text=True
                    )



            conexiones.append((origen, destino))

        return jsonify({"status": "ok", "conexiones": conexiones})

    @app.route("/renombrar_nodo", methods=["POST"])
    def renombrar_nodo():
        data = request.get_json()
        antiguo = data["old_name"]
        nuevo = data["new_name"]

        # Actualizar topología en SimulaQron
        topologia = mostrar_topologia()
        if antiguo not in topologia:
            return jsonify({"error": "Nodo no encontrado en topología"}), 404

        vecinos = topologia[antiguo]

        # Eliminar nodo antiguo
        subprocess.run(["simulaqron", "nodes", "remove", antiguo], capture_output=True)

        # Crear nodo nuevo con mismos vecinos
        subprocess.run(["simulaqron", "nodes", "add", nuevo, "--force", "--neighbors", ",".join(vecinos)], capture_output=True)

        # Actualizar vecinos que tenían al antiguo como vecino
        for nodo, lista in topologia.items():
            if nodo == antiguo:
                continue
            if antiguo in lista:
                nueva_lista = [nuevo if v == antiguo else v for v in lista]
                subprocess.run(["simulaqron", "nodes", "add", nodo, "--force", "--neighbors", ",".join(nueva_lista)], capture_output=True)

        return jsonify({"status": "ok", "renombrado": {"de": antiguo, "a": nuevo}})


    @app.route("/topologia", methods=["GET"])
    def topologia():
        return jsonify(mostrar_topologia())



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

    @app.route("/limpiar_historial")
    def limpiar_historial():
        global contador, simulacion_en_curso
        contador = 0
        simulacion_en_curso = False
        MASTER_PAR_EPR.clear()
        # Avisar a todos los nodos conectados
        for nodo_id, puerto in NODOS_PUERTOS.items():
            url = f"http://localhost:{puerto}/update"
            try:
                res = requests.post(
                    url,
                    json={
                        "id": nodo_id,
                        "parEPR": [],          # <-- vaciar historial de EPR
                        "lastUpdated": int(time.time() * 1000)
                    },
                    timeout=2
                )
                if res.status_code == 200:
                    print(f"[INFO] Historial EPR limpiado en nodo {nodo_id}")
                else:
                    print(f"[WARN] Error limpiando nodo {nodo_id}: {res.status_code}")
            except Exception as e:
                print(f"[ERROR] Excepción limpiando nodo {nodo_id}: {e}")

        try:
            open("pre_docs/fidelidad_alice.txt", "w").close()
            open("pre_docs/fidelidad_bob.txt", "w").close()
            open("pre_docs/historial_resultados.txt", "w").close()
            open("pre_docs/bob_resultado.txt", "w").close()
            open("pre_docs/qubit_enviado.txt", "w").close()
            open("pre_docs/tiempo_creacion.txt", "w").close()
            open("pre_docs/tiempo_recepcion.txt", "w").close()
            open("pre_docs/qubit_enviado_rep.txt", "w").close()
            open("pre_docs/simulaqron_log.txt","w").close()
            # subprocess.Popen(["python3", "limpiar_qubits.py"]) Preparado para imprevistos de memoria cuantica
            print("[SERVIDOR] Historial y qubits limpiados correctamente.")
        except Exception as e:
            print(f"[ERROR] No se pudo limpiar el historial: {e}")
        return jsonify({"status": "ok"})

    @app.route("/limpieza_docs")
    def limpiar_txt():
        try:
            open("pre_docs/fidelidad_alice.txt", "w").close()
            open("pre_docs/fidelidad_bob.txt", "w").close()
            open("pre_docs/bob_resultado.txt", "w").close()
            open("pre_docs/qubit_enviado.txt", "w").close()
            open("pre_docs/tiempo_creacion.txt", "w").close()
            open("pre_docs/tiempo_recepcion.txt", "w").close()
            open("pre_docs/qubit_enviado_rep.txt", "w").close()
            open("pre_docs/simulaqron_log.txt","w").close()
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
                        with open("pre_docs/fidelidad_alice.txt", "r") as f:
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

                        with open("pre_docs/fidelidad_alice.txt", "r") as f:
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
                            with open("pre_docs/fidelidad_alice.txt", "r") as f:
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
                            with open("pre_docs/fidelidad_alice.txt", "r") as f:
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


            with open("pre_docs/tiempo_creacion.txt", "r") as f:
                t_creacion = f.read().strip().split(",")

            with open("pre_docs/tiempo_recepcion.txt", "r") as f:
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
                with open("pre_docs/bob_resultado.txt", "r") as f:
                    mediciones = f.read().strip().split(",")

                with open("pre_docs/fidelidad_bob.txt", "r") as f:
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
                with open("pre_docs/historial_resultados.txt", "a") as h:
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
                with open("pre_docs/historial_resultados.txt", "r") as h:
                    historial = [line.strip() for line in h.readlines()]
            except FileNotFoundError:
                historial = []

            # Finalizar simulación
            simulacion_en_curso = False

            # Enviar historial a Bob si el rol es Alice
            if ROL == "alice" or ROL == "master":
                try:
                    requests.post("http://localhost:5001/actualizar_historial", json={
                        "resultado": resultado,
                        "contador": len(historial),
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
    print(f"[SERVIDOR] Iniciando servidor en el puerto {PUERTO} con rol {ROL}...")
    app.run(host="127.0.0.1", port=PUERTO, debug=True, use_reloader=False) #Quitar debug=True si no estoy en produccion

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1].lower() == "bob":
        ROL = "bob"
        # Bob solo en 5001
        PUERTO = 5001 if puerto_disponible(5001) else None
        if PUERTO is None:
            print("[ERROR] El puerto 5001 está ocupado. Bob no puede iniciar.")
            sys.exit(1)
    elif len(sys.argv) > 1 and sys.argv[1].lower() == "master":
        ROL = "master"
        PUERTO = 8000
    else:
        ROL = "alice"
        # Alice en cualquier puerto libre del rango, excepto 5001
        PUERTO = seleccionar_puerto(5000, 5010, excluir=[5001])
        if PUERTO is None:
            print("[ERROR] No hay puertos disponibles para Alice.")
            sys.exit(1)

    
    proceso = Process(target=app_open, args=(ROL, PUERTO))
    proceso.start()
    proceso.join()

    

