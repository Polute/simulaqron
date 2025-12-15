---

# ⚡ Quick Execution (with environment already configured)

If you already have Python 3.10.x and the virtual environment `simulaqron_env` correctly installed and activated, you can run the simulator directly by downloading the ZIP file with the essential files:

1. Extract the contents into your working environment
2. Currently, the simulator can be run in two ways:

```bash
python app.py master
```
This simulates the entire network on a local machine (Port 8000).

Run each node individually:
```bash
python nodo.py 
```

Open several terminals and run this command; each instance will open on a different port.



Listen to the master only:
```bash
python app.py bob
```

This acts as a receiver node that only receives the history.

#------------------------------------------------------------

Development Environment Setup

Follow the instructions in the provided PDF to configure the development environment.
Remember to update your requirements file with:

```bash
pip install -r requirements.txt
```

If SimulaQron fails, run setup_env.sh with execution permissions:
```bash
./setup_env.sh
```

This will delete the virtual environment and recreate it with the requirements installed.
New packages will be added periodically as needed.