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

# Use of the Simulator

The simulator is designed so that anyone, even without extensive technical knowledge, can operate it effectively.

Once the main master program is running and the nodes have been deployed across the network, they are automatically detected. However, as a basic connectivity check, the master page requires two manual actions:

1. **Update Info** – refreshes the SimulaQron CQC network and retrieves the latest state of all nodes.  
2. **Update Nodes** – sends this updated information to every node, allowing them to open their communication channels. Nodes do not communicate with each other unless the master explicitly authorizes it.

## Interface Overview

### Left Panel
The left side of the interface displays:
- The interactive map  
- The update buttons  
- The physical and logical parameters of each node as detected by the master  

These parameters can be modified in two ways:
- From the master page, followed by **Update Nodes**, or  
- From the node’s own page, which the master detects when **Update Info** is pressed.

### Operations Panel (Center)

The central area of the interface is dedicated to operations. In future versions, a dedicated architecture‑input system will be available. For now, the simulator displays a set of modular blocks grouped into two categories:

- **Node blocks** – automatically created and updated according to the current network topology  
- **Operation blocks** – representing:
  - EPR generation  
  - Entanglement swapping  
  - Purification  

#### EPR Generation
To generate an EPR pair between two nodes:
1. Place the source node block  
2. Add the "Generate EPR" operation block  
3. Place the destination node block  

The only requirement is that the source and destination nodes must be connected in the network topology.

#### Entanglement Swapping
Swapping requires a node to act as a repeater. This node must have previously received two EPR pairs from two different emitters.

The structure is:
- Repeater node  
- Swap operation block  
- Emitter node 1  
- Emitter node 2  

#### Purification
Purification acts on an existing EPR link. To simplify the process, purification becomes available whenever two EPR pairs exist between the same emitter and receiver.

The user simply:
1. Places the purification block  
2. Selects the EPR pair to purify  

### Exporting Operations

Once all desired operations are arranged, pressing **Export Orders** sends the instructions to the appropriate nodes. The master handles all routing and distribution.

### Right Panel: Operation History

The right side of the interface displays the operation history. This log is updated dynamically based on the results sent back by each node.

Using this information, users can analyze:
- The performance of each operation  
- The impact of modifying physical parameters  
- The behavior of the network under different configurations  

An additional window shows the operations in which each individual node has participated.

### Development Status

The simulator is under active development. Functionality and visual components may change frequently, and some features may temporarily stop working between stable releases.


