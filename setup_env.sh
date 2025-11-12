#!/bin/bash

# Nombre del entorno virtual
ENV_DIR="simulaqron_env"

# Archivo de requisitos
REQUIREMENTS="requirements.txt"

echo "🧹 Eliminando entorno virtual anterior si existe..."
rm -rf "$ENV_DIR"

echo "🐍 Creando nuevo entorno virtual..."
python3 -m venv "$ENV_DIR"

echo "⚙️ Activando entorno virtual..."
source "$ENV_DIR/bin/activate"

echo "📦 Instalando dependencias desde $REQUIREMENTS..."
pip install --upgrade pip
pip install -r "$REQUIREMENTS"

echo "✅ Entorno virtual listo y dependencias instaladas."
