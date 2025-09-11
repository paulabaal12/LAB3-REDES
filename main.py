import json
import argparse
import uuid
import time
from network.transport import TCPTransport, XMPPTransport, RedisTransport
from network.protocol import make_message
from network.topo_loader import load_topology, load_names
from routing.dijkstra import Dijkstra
from routing.flooding import Flooding
from routing.link_state import LinkState
from routing.dvr import DistanceVector


# Cargar grupos globalmente para que esté disponible en on_message
with open("groups.json") as f:
    groups = json.load(f)

nodes_ports = load_names("names-ports.json")
print(nodes_ports)

node_id = None
algo = None
transport = None


def on_message(msg):
    # Print genérico para cualquier mensaje recibido
    print(f"[RECEIVED][{node_id}] Mensaje recibido: {msg}")
    global groups
    print(f"Tipo antes: {type(msg)}")
    print(msg)
    try:
        msg = json.loads(msg)
    except Exception as e:
        print(f"Error decodificando JSON: {e}")
        return  
    if hasattr(msg, 'get'):
        msg["ttl"] = int(msg.get("hops", 0))
    print(f"Tipo después: {type(msg)}")
    
    print(f"Mensaje recibido es variable de tipo {type(msg)}")

    if hasattr(msg, 'get'):
        if msg.get("type") == "MESSAGE":
            print(f"\n[{node_id}] Recibido mensaje: '{msg.get('payload')}' de {msg.get('from')} (ttl={msg.get('ttl')})\n> ", end="")
            return

        if msg.get("type") == "HELLO" or msg.get("type") == "hello":
            print(f"[HELLO] Recibido HELLO de {msg.get('from')} (hops={msg.get('hops')})")
            # Responder con PING si quieres medir latencia
            if msg.get("payload") == "HELLO":
                reply = dict(msg)
                reply["type"] = "PING"
                reply["from"] = node_id
                reply["to"] = msg["from"]
                reply["payload"] = "PING"
                reply["timestamp_reply"] = time.time()
                if transport.__class__.__name__ == "RedisTransport":
                    group = groups.get(msg["from"], 9)
                    transport.send(msg["from"], reply, group=group)
                else:
                    nh_port = nodes_ports.get(msg["from"], None)
                    if nh_port:
                        transport.send("127.0.0.1", nh_port, reply)
            return
        if msg.get("type") == "PING":
            #print(f"[PING] Recibido PING de {msg.get('from')} (timestamp={msg.get('timestamp_reply')})")
            return
        if msg.get("type") == "TABLE":
            #print(f"[INFO] Recibida tabla de ruteo de {msg.get('from')}: {msg.get('table')}")
            return
    if isinstance(algo, Flooding):
        algo.handle_message(msg, transport, nodes_ports)
        return
    if isinstance(algo, LinkState):
        if hasattr(msg, 'get'):
            # Procesar mensajes LSA
            if msg.get("type") == "LSA":
                algo.handle_message(msg, transport, nodes_ports)
        else:
            print("Mensaje recibido sin método 'get':")
        return
    if isinstance(algo, DistanceVector):
        if hasattr(msg, 'get'):

            if msg.get("type") == "DV_UPDATE":
                algo.handle_message(msg, transport, nodes_ports)
        else:
            print("Mensaje recibido sin método 'get':")
        return


def main():
    def normalize_node_name(name):
        name = name.strip()
        if name.lower().startswith('nodo'):
            return name.lower()
        if name.upper().startswith('N') and name[1:].isdigit():
            return f"nodo{int(name[1:])}"
        return name
    # Leer grupos
    with open("groups.json") as f:
        groups = json.load(f)
    global node_id, algo, transport
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Node ID (ej. A)")
    parser.add_argument("--algo", required=True, choices=["dijkstra", "flooding", "linkstate", "dvr"], help="Algoritmo de enrutamiento a usar")
    parser.add_argument("--topo", required=True, help="Archivo de topología")
    parser.add_argument("--names", required=True, help="Archivo de nombres")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--transport", default="tcp", choices=["tcp", "xmpp", "redis"], help="Tipo de transporte: tcp o xmpp")
    parser.add_argument("--jid", help="JID para XMPP (solo si --transport=xmpp)")
    parser.add_argument("--password", help="Password para XMPP (solo si --transport=xmpp)")
    args = parser.parse_args()

    node_id = normalize_node_name(args.id)
    topology = load_topology(args.topo)
    names = load_names(args.names)
    neighbors = topology[node_id]

    # Inicialización de algoritmos: solo Dijkstra recibe la topología global
    if args.algo == "dijkstra":
        algo = Dijkstra(node_id, topology)
    elif args.algo == "flooding":
        algo = Flooding(node_id, neighbors)
    elif args.algo == "linkstate":
        algo = LinkState(node_id, neighbors)
    elif args.algo == "dvr":
        algo = DistanceVector(node_id, neighbors)
    else:
        print("Algoritmo no soportado.")
        return

    print(f"[INFO] Nodo {node_id} usando algoritmo: {args.algo}")

    print("[INFO] Calculando tabla de enrutamiento...")
    if args.algo == "linkstate":
        table = algo.compute_routes(algo.topology)
    elif args.algo == "dvr":
        table = algo.compute_routes()
    elif args.algo == "dijkstra":
        table = algo.compute_routes(topology)
    elif args.algo == "flooding":
        table = algo.compute_routes(topology)
    else:
        table = algo.compute_routes()
    print("[ROUTING TABLE]", table)

    # Inicializar transporte según argumento
    if args.transport == "tcp":
        transport = TCPTransport(args.host, nodes_ports[args.id], on_message)
        transport.start_server()
        print(f"\nNodo {node_id} conectado en {args.host}:{nodes_ports[args.id]} (TCP)\n")
    elif args.transport == "xmpp":
        if not args.jid or not args.password:
            print("Para XMPP debes especificar --jid y --password")
            return
        transport = XMPPTransport(args.jid, args.password, on_message)
        transport.connect()
        transport.start_listener()
        print(f"\nNodo {node_id} conectado como {args.jid} (XMPP)\n")
    elif args.transport == "redis":
        # Diccionario vecino:grupo para suscripción y envío
        neighbor_groups = {nbr: groups.get(nbr, 9) for nbr in neighbors.keys()}
        my_group = groups.get(node_id, 9)
        transport = RedisTransport(node_id, on_message, neighbor_groups=neighbor_groups, my_group=my_group)
        transport.start_server()
        print(f"\nNodo {node_id} conectado a Redis como sec30.grupo{my_group}.{node_id}\n (suscrito a vecinos: {neighbor_groups})\n")

    # Flood inicial de LSA para LinkState
    if args.algo == "linkstate":
        algo.flood_lsa(transport, nodes_ports)
    if args.algo == "dvr":
        algo.flood_update(transport, nodes_ports)

    while True:
        print("\n========== MENU ==========")
        print("1. Enviar paquete")
        print("2. Escuchar mensajes (continuo)")
        print("3. Salir")
        print("4. Enviar HELLO a vecino")
        print("5. Enviar mi tabla de ruteo a vecino (TABLE/INFO)")
        choice = input("> ")

        if choice == "1":
            payload = input("Mensaje: ").strip()

            if isinstance(algo, Flooding):
                msg = make_message(
                    proto=args.algo,
                    mtype="message",
                    src=node_id,
                    dst=None,
                    payload=payload,
                    headers={"msg_id": str(uuid.uuid4())},
                    ttl=32
                )
                for neigh in algo.routing_table["__FLOOD__"]:
                    neigh_norm = normalize_node_name(neigh)
                    fwd = dict(msg)
                    fwd["last_hop"] = node_id
                    try:
                        nh_port = nodes_ports[neigh_norm]
                        transport.send("127.0.0.1", nh_port, fwd)
                        print(f"[{node_id}] Flood inicial → {neigh_norm}")
                    except Exception as e:
                        print("Error enviando:", e)

            else:
                dest = input("Destino (ej. E): ").strip()
                dest_norm = normalize_node_name(dest)
                if dest_norm not in algo.routing_table:
                    print(f"No hay ruta hacia {dest}")
                    continue

                msg = make_message(
                    proto=args.algo,
                    mtype="message",
                    src=node_id,
                    dst=dest_norm,
                    payload=payload,
                    headers={"msg_id": str(uuid.uuid4())},
                    ttl=32
                )

                next_hop = algo.routing_table[dest_norm]
                next_hop_norm = normalize_node_name(next_hop)
                try:
                    # Detecta si es RedisTransport
                    if transport.__class__.__name__ == "RedisTransport":
                        # Usa el grupo correcto para el next_hop
                        group = groups.get(next_hop_norm, 9)
                        transport.send(next_hop_norm, msg, group=group)
                    else:
                        nh_port = nodes_ports[next_hop_norm]
                        if transport.__class__.__name__ == "RedisTransport":
                            group = groups.get(next_hop_norm, 9)
                            transport.send(next_hop_norm, msg, group=group)
                        else:
                            transport.send("127.0.0.1", nh_port, msg)
                    print(f"[{node_id}] Enviado a {dest_norm} via next hop {next_hop_norm}")
                except Exception as e:
                    print("Error enviando:", e)


        elif choice == "2":
            print("Escuchando mensajes... (ENTER para volver al menú)")
            input()

        elif choice == "3":
            print("Saliendo de la red...")
            break
        elif choice == "4":
            dest = input("Vecino destino (ej. B): ").strip()
            dest_norm = normalize_node_name(dest)
            if dest_norm not in neighbors:
                print("No es vecino directo.")
                continue
            hello_msg = {
                "proto": "hello",
                "type": "HELLO",
                "from": node_id,
                "to": dest_norm,
                "payload": "HELLO",
                "timestamp": time.time(),
            }
            if transport.__class__.__name__ == "RedisTransport":
                group = groups.get(dest_norm, 9)
                transport.send(dest_norm, hello_msg, group=group)
            else:
                nh_port = nodes_ports[dest_norm]
                transport.send("127.0.0.1", nh_port, hello_msg)
            print(f"[HELLO] Enviado HELLO a {dest_norm}")
        elif choice == "5":
            dest = input("Vecino destino (ej. B): ").strip()
            dest_norm = normalize_node_name(dest)
            if dest_norm not in neighbors:
                print("No es vecino directo.")
                continue
            table_msg = {
                "proto": "table",
                "type": "TABLE",
                "from": node_id,
                "to": dest_norm,
                "payload": "TABLE",
                "table": getattr(algo, 'routing_table', {}),
                "timestamp": time.time(),
            }
            try:
                if transport.__class__.__name__ == "RedisTransport":
                    group = groups.get(dest_norm, 9)
                    transport.send(dest_norm, table_msg, group=group)
                else:
                    nh_port = nodes_ports[dest_norm]
                    transport.send("127.0.0.1", nh_port, table_msg)
                print(f"[INFO] Enviada tabla de ruteo a {dest_norm}")
            except Exception as e:
                print(f"Error enviando tabla: {e}")
        else:
            print("Opción inválida")


if __name__ == "__main__":
    main()
