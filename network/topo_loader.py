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
    def normalize_node_name(name):
        name = name.strip()
        if name.lower().startswith('nodo'):
            return name.lower()
        if name.upper().startswith('N') and name[1:].isdigit():
            return f"nodo{int(name[1:])}"
        return name

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

        n1_norm = normalize_node_name(n1)
        n2_norm = normalize_node_name(n2)

        # añadir aristas en ambas direcciones
        if n1_norm not in topology:
            topology[n1_norm] = {}
        if n2_norm not in topology:
            topology[n2_norm] = {}
        topology[n1_norm][n2_norm] = w
        topology[n2_norm][n1_norm] = w

    return topology

