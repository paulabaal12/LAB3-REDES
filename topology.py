import json

def load_topology(txt_file, ids_file):
    with open(ids_file, "r") as f:
        ids_data = json.load(f)["config"]

    topology = {mapped: {} for mapped in ids_data.values()}

    with open(txt_file, "r") as f:
        content = f.read().strip()

    edges = [edge.strip() for edge in content.split(",")]

    for edge in edges:
        if not edge:
            continue
        nodes, weight = edge.split(":")
        n1, n2 = nodes.split("-")
        weight = int(weight)

        node1 = ids_data[n1]
        node2 = ids_data[n2]

        # Agregar en ambos sentidos
        topology[node1][node2] = {"weight": weight, "time": 0}
        topology[node2][node1] = {"weight": weight, "time": 0}

    return topology


def get_neighbors(node_id, topology):
    if node_id not in topology:
        raise ValueError(f"El nodo {node_id} no existe en la topología")
    
    # Reducir la salida solo a "weight"
    neighbors = {
        neighbor: {"weight": data["weight"]}
        for neighbor, data in topology[node_id].items()
    }
    return neighbors

if __name__ == "__main__":
    topo = load_topology("topology.txt", "nodes_ids.json")

    neighbors = get_neighbors("sec30.grupo1.nodo1", topo)
    print(neighbors)
