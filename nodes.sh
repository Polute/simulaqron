#!/bin/bash
# nodes.sh
# Usage: ./nodes.sh N   (where N is the number of terminals to open)

if [ -z "$1" ]; then
  echo "Usage: $0 <number_of_terminals>"
  exit 1
fi

NUM=$1

for i in $(seq 1 $NUM); do
  gnome-terminal -- bash -c "source simulaqron_env/bin/activate; python nodo.py; exec bash"
done
