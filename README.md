---

## ⚡ Ejecución rápida (con entorno ya configurado)

Si ya tienes Python 3.10.x y el entorno virtual `simulaqron_env` correctamente instalado y activado, puedes ejecutar el simulador directamente descargando el archivo ZIP con los archivos esenciales:

1. Extrae el contenido en tu entorno de trabajo
2. Actualmente, el simulador se ejecuta de dos formas:

```bash
python app.py master
```
La cual simula la red completa en una máquina local(Puerto 8000)

Para ejecutar individualmente cada nodo, con info que contienen local, ejecuta:

```bash
python app.py 
```

Realizalo en varias terminales, las cuales se abriran en puertos distintos cada vez que lo ejecutes


Y para simplemente escuchar lo que hace master, ejecuta:

```bash
python app.py bob
```

El cual sirve como nodo receiver donde únicamente recibe el qubit y el historial, también lo puede borrar.


Para configurar el entorno de desarrollo, siga las intrucciones del pdf.
Recuerde actualizar su requirements txt con:

```bash
pip install -r requirements.txt
```

Si te falla simulaqron, ejecuta setup_env.sh, con permisos de ejecución.
Este borrara el entorno virtual y se te creará de nuevo con los requirements instalados


Ya que se agregarán nuevos paquetes periodicamente y según hagan falta.

Falta logica, agregar nodos a simulaqron, más detalle del pgen y pswap y que cada nodo actue como emisor. 