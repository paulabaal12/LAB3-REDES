import json

def load_topology_json(file_path):
    with open(file_path) as f:
        data = json.load(f)
    return data["config"]

def load_names(file_path):
    with open(file_path) as f:
        data = json.load(f)
    return data["config"]

# network/topo_loader.py
def load_topology(file_path):
    """
    Carga una topología desde un archivo con formato:
    N1-N2:20, N1-N3:14, N1-N5:17, ...
    
    Retorna un diccionario:
    {
      "N1": {"N2": 20, "N3": 14, "N5": 17},
      "N2": {"N1": 20},
      ...
    }
    """
    topology = {}
    with open(file_path) as f:
        raw = f.read().strip()

    # separar por coma
    entries = [e.strip() for e in raw.split(",") if e.strip()]
    for entry in entries:
        # ejemplo: N1-N2:20
        nodes, weight = entry.split(":")
        n1, n2 = nodes.split("-")
        w = int(weight)

        # añadir aristas en ambas direcciones
        if n1 not in topology:
            topology[n1] = {}
        if n2 not in topology:
            topology[n2] = {}
        topology[n1][n2] = w
        topology[n2][n1] = w

    return topology

