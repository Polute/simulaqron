---

## ⚡ Ejecución rápida (con entorno ya configurado)

Si ya tienes Python 3.10.x y el entorno virtual `simulaqron_env` correctamente instalado y activado, puedes ejecutar el simulador directamente descargando el archivo ZIP con los archivos esenciales:



1. Descarga el archivo `simulador.zip` desde la rama `main` del repositorio
2. Extrae el contenido en tu entorno de trabajo
3. Actualmente, el simulador se ejecuta de dos formas:

```bash
python app.py
```
La cual simula la red completa en una máquina local(Puerto 5000)


```bash
python app.py bob
```

El cual sirve como nodo receiver donde únicamente recibe el qubit y el historial, también lo puede borrar.


Para configurar el entorno de desarrollo, siga las intrucciones del pdf.
Recuerde actualizar su requirements txt con:

```bash
pip install -r requirements.txt
```

Ya que se agregarán nuevos paquetes periodicamente y según hagan falta.

Falta logica, agregar nodos a simulaqron, más detalle del pgen y pswap y que cada nodo actue como emisor. 