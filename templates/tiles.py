import os
import requests
import time

# ------------------------------
# CONFIGURACIÓN
# ------------------------------

# Servidor de tiles legal sin API
URL_TEMPLATE = "https://tile.opentopomap.org/{z}/{x}/{y}.png"

# Zoom y área de Madrid
z = 15
x_start, x_end = 16045, 16045
y_start, y_end = 12351, 12352

# Carpeta donde se guardarán las tiles
BASE_DIR = "tiles"
# 
# ------------------------------
# DESCARGA DE TILES
# ------------------------------

def descargar_tile(z, x, y):
    url = URL_TEMPLATE.format(z=z, x=x, y=y)
    carpeta = f"{BASE_DIR}/{z}/{x}"
    archivo = f"{carpeta}/{y}.png"

    os.makedirs(carpeta, exist_ok=True)

    print(f"Descargando {url} → {archivo}")

    r = requests.get(url, timeout=10)

    if r.status_code == 200:
        with open(archivo, "wb") as f:
            f.write(r.content)
    else:
        print(f"Error {r.status_code} al descargar {url}")

def main():
    for x in range(x_start, x_end + 1):
        for y in range(y_start, y_end + 1):
            descargar_tile(z, x, y)
            time.sleep(0.5)  # medio segundo entre descargas

    print("\n✔ Descarga completada.")
    print(f"Tiles guardadas en: {BASE_DIR}/")

if __name__ == "__main__":
    main()
