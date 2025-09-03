import argparse
import uuid
from network.transport import TCPTransport
from network.protocol import make_message
from network.topo_loader import load_topology, load_names
from routing.dijkstra import Dijkstra
from routing.flooding import Flooding
from routing.link_state import LinkState

nodes_ports = load_names("names-ports.json")

node_id = None
algo = None
transport = None


def on_message(msg):
    msg["hops"] = int(msg.get("hops", 0))

    if isinstance(algo, Flooding):
        algo.handle_message(msg, transport, nodes_ports)
        return

    if isinstance(algo, LinkState):
        # Procesar mensajes LSA
        if msg.get("type") == "LSA":
            algo.handle_message(msg, transport, nodes_ports)
            return

    dest = msg.get("to")
    if dest == node_id:
        print(f"\n[DELIVERED to {node_id}] {msg.get('payload')}\n> ", end="")
        return

    if dest not in algo.routing_table:
        print(f"\n[{node_id}] No hay ruta hacia {dest}. Descarto.\n> ", end="")
        return

    if msg["hops"] >= 32:  # TTL
        print(f"\n[{node_id}] TTL excedido hacia {dest}.\n> ", end="")
        return

    next_hop = algo.routing_table[dest]
    msg["hops"] += 1
    try:
        nh_port = nodes_ports[next_hop]
        transport.send("127.0.0.1", nh_port, msg)
        print(f"\n[{node_id}] Forward → {next_hop} (dest {dest}, hops={msg['hops']})\n> ", end="")
    except Exception as e:
        print(f"\n[{node_id}] Error reenviando a {next_hop}: {e}\n> ", end="")


def main():
    global node_id, algo, transport

    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Node ID (ej. A)")
    parser.add_argument("--algo", required=True, choices=["dijkstra", "flooding", "linkstate"],
                        help="Algoritmo de enrutamiento a usar")
    parser.add_argument("--topo", required=True, help="Archivo de topología")
    parser.add_argument("--names", required=True, help="Archivo de nombres")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    node_id = args.id
    topology = load_topology(args.topo)
    names = load_names(args.names)
    neighbors = topology[node_id]

    if args.algo == "dijkstra":
        algo = Dijkstra(node_id, neighbors)
    elif args.algo == "flooding":
        algo = Flooding(node_id, neighbors)
    elif args.algo == "linkstate":
        algo = LinkState(node_id, neighbors)

    print(f"[INFO] Nodo {node_id} usando algoritmo: {args.algo}")

    print("[INFO] Calculando tabla de enrutamiento...")
    if args.algo == "linkstate":
        table = algo.compute_routes(algo.lsdb)
    else:
        table = algo.compute_routes(topology)
    print("[ROUTING TABLE]", table)

    transport = TCPTransport(args.host, nodes_ports[args.id], on_message)
    transport.start_server()

    print(f"\nNodo {node_id} conectado en {args.host}:{nodes_ports[args.id]}\n")

    # Flood inicial de LSA para LinkState
    if args.algo == "linkstate":
        algo.flood_lsa(transport, nodes_ports)

    while True:
        print("\n========== MENU ==========")
        print("1. Enviar paquete")
        print("2. Escuchar mensajes (continuo)")
        print("3. Salir")
        choice = input("> ")

        if choice == "1":
            payload = input("Mensaje: ").strip()
            headers = {"msg_id": str(uuid.uuid4())}
            msg = make_message("DATA", node_id, None, payload, headers=headers, hops=0)

            if isinstance(algo, Flooding):
                for neigh in algo.routing_table["__FLOOD__"]:
                    fwd = dict(msg)
                    fwd["last_hop"] = node_id  # el origen se marca como último salto
                    try:
                        nh_port = nodes_ports[neigh]
                        transport.send("127.0.0.1", nh_port, fwd)
                        print(f"[{node_id}] Flood inicial → {neigh}")
                    except Exception as e:
                        print("Error enviando:", e)
            elif isinstance(algo, LinkState):
                dest = input("Destino (ej. E): ").strip()
                if dest not in algo.routing_table:
                    print(f"No hay ruta hacia {dest}")
                    continue
                msg["to"] = dest
                next_hop = algo.routing_table[dest]
                try:
                    nh_port = nodes_ports[next_hop]
                    transport.send("127.0.0.1", nh_port, msg)
                    print(f"[{node_id}] Enviado a {dest} via next hop {next_hop}")
                except Exception as e:
                    print("Error enviando:", e)
            else:
                dest = input("Destino (ej. E): ").strip()
                if dest not in algo.routing_table:
                    print(f"No hay ruta hacia {dest}")
                    continue
                msg["to"] = dest
                next_hop = algo.routing_table[dest]
                try:
                    nh_port = nodes_ports[next_hop]
                    transport.send("127.0.0.1", nh_port, msg)
                    print(f"[{node_id}] Enviado a {dest} via next hop {next_hop}")
                except Exception as e:
                    print("Error enviando:", e)

        elif choice == "2":
            print("Escuchando mensajes... (ENTER para volver al menú)")
            input()

        elif choice == "3":
            print("Saliendo de la red...")
            break

        else:
            print("Opción inválida")


if __name__ == "__main__":
    main()
