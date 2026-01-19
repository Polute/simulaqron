# 🧬 Quantum Network Simulator

## ⚡ Quick Execution (Environment Already Configured)

If you already have Python 3.10.x and the virtual environment `simulaqron_env` installed and activated, you can run the simulator immediately.

### Run the master (local full‑network simulation)
```bash
python app.py master
```
This launches the master on port **8000** and simulates the entire network locally.

### Run individual nodes
Open several terminals and run:
```bash
python nodo.py
```
Each instance will automatically bind to a different port.

### Run only the master listener (history receiver)
```bash
python app.py bob
```

---

# 🛠️ Development Environment Setup

Install dependencies:
```bash
pip install -r requirements.txt
```

If SimulaQron fails to start, rebuild the environment:
```bash
chmod +x setup_env.sh
./setup_env.sh
```

This recreates the virtual environment and installs all required packages.

---

# 🧭 Information Model of the System

The simulator organizes all node‑related data into **three categories**.  
This helps clarify what each component knows and what information is exchanged during quantum operations.

## 📌 Information Categories

### **1. Local Information**
Private data stored inside each node.  
Not shared unless required by a protocol.

Includes:
- `id` — internal node identifier  
- `name` — human‑readable label  
- `latitude`, `longitude` — geographic coordinates  
- `pswap` — swapping success probability  
- `roles` — emitter / receiver / repeater  
- `eprPairs` — local EPR memory (active, swapped, measured, failed…)  
- Qubit lifetime and internal timers  
- Any operational parameter that belongs only to the node  

### **2. Global Information**
Data required to maintain a coherent view of the network.

Includes:
- Network topology  
- Distances between nodes  
- Physical parameters (attenuation, pgen, etc.)  
- Node availability  
- Routing metadata  

Important:  
Nodes only know their **direct neighbors**.  
The **master** is the only component that knows the full topology.

### **3. Transactional Information**
Generated dynamically during protocol execution.

Includes:
- Classical signals  
- Measurement results  
- EPR generation and reception messages  
- Purification attempts  
- Swapping notifications  
- Event logs  
- Resource requests  

This information flows between:
- Nodes  
- Master  
- Neighboring nodes  
- Listener ports  

---

# 🧩 Node Attributes (Simplified Overview)

Each node maintains a set of attributes that describe its state, capabilities and relationships with the rest of the network.

- **id** (local): unique identifier  
- **name** (local): descriptive name  
- **latitude**, **longitude** (local): geographic coordinates  
- **pswap** (local): swapping success probability  
- **roles** (local): emitter / receiver / repeater  
- **neighbors** (global + transactional): list of direct neighbors with distance, pgen, and coordinates  
- **distanceKm** (global): distance to each neighbor  
- **pgen** (transactional): EPR generation success probability  
- **eprPairs** (local + transactional): list of stored EPR pairs  

---

# 🧩 EPR Message Attributes

Messages exchanged during EPR generation, reception, purification and swapping include:

### **EPR Generation**
- `id`  
- `neighbor`  
- `t_gen`  
- `w_gen`  

### **EPR Reception**
- `id`  
- `neighbor`  
- `t_gen`  
- `t_recv`  
- `t_diff`  
- `w_gen`  
- `w_out`  
- `state`  
- `measurement`  
- `distanceNodes`  
- `listener_port`  

### **Purification**
- `id`  
- `neighbor`  
- `state`  
- `t_pur`  
- `w_gen`  
- `w_out`  
- `purified_from`  

### **Entanglement Swapping**
For nodes not performing the swap:
- `id`  
- `neighbor`  
- `state`  
- `t_gen`, `t_recv`, `t_diff`  
- `w_gen`, `w_out`  
- `distanceNodes`  
- `listener_port`  

For the repeater:
- `id` (combination of the two consumed EPRs)  
- `state` = `swapper`  
- `neighbor` = list of the two remote endpoints  

---

# 🧩 Special Attribute: `listener_port`

- Port where each node listens for further commands (generation, purification, swapping, monitoring, etc.)
- Activated after the node generates or receives its first EPR
- Shared between the node, its neighbors, and the master

---

# 🖥️ Using the Simulator

Once the master is running and the nodes are deployed, they are detected automatically.  
Before running operations, the master interface requires two manual actions:

1. **Update Info** – refreshes the SimulaQron CQC network and retrieves the latest node state.  
2. **Update Nodes** – sends this updated information to all nodes so they can open their communication channels.

Nodes do not communicate with each other until the master authorizes it.

---

# 🧱 Interface Overview

## Left Panel
Displays:
- Interactive map  
- Update buttons  
- Physical and logical parameters of each node  

These parameters can be edited either:
- From the master page (then press **Update Nodes**)  
- From the node’s own page (detected when pressing **Update Info**)  

---

# 🔧 Operations Panel (Center)

Contains modular blocks representing the available operations:

### EPR Generation
1. Place the source node  
2. Add the “Generate EPR” block  
3. Place the destination node  

### Entanglement Swapping
Requires a repeater node with two active EPRs from different neighbors.

### Purification
Available when two EPRs exist between the same pair of nodes.

---

# 📤 Exporting Operations

Press **Export Orders** to send all configured operations to the corresponding nodes.  
The master handles routing and distribution.

---

# 📜 Operation History (Right Panel)

Shows:
- Real‑time logs of all executed operations  
- Results returned by each node  
- A per‑node breakdown of participation in operations  

---

# 🚧 Development Status

The simulator is under active development.  
Features and UI elements may change frequently, and some components may be temporarily unstable between releases.
