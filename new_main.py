import argparse
import json
import asyncio
from topology import load_topology, get_neighbors
from transport import AsyncRedisTransport
from colorama import Fore, Style, init
from routing.dijkstra import Dijkstra

# Inicializar colorama
init(autoreset=True)

TOPOLOGY = {}
NODE_ID = None
TRANSPORT = None
LOCK = asyncio.Lock()


def make_hello(from_node, to_node, weight):
    return {"type": "hello", "from": from_node, "to": to_node, "hops": weight}


def make_message(from_node, to_node, weight):
    return {"type": "message", "from": from_node, "to": to_node, "hops": weight}


SEEN_MESSAGES = set()

async def on_message(msg):
    """Callback ejecutado al recibir mensajes"""
    global TOPOLOGY, NODE_ID, SEEN_MESSAGES
    msg_type = msg.get("type")
    from_node = msg.get("from")
    to_node = msg.get("to")
    hops = msg.get("hops")

    if not (msg_type and from_node and to_node and hops is not None):
        print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} Mensaje inválido")
        return

    # Identificador único para cada enlace aprendido
    msg_id = f"{from_node}-{to_node}-{hops}"

    async with LOCK:
        if msg_type == "hello":
            if from_node in TOPOLOGY.get(NODE_ID, {}):
                TOPOLOGY[NODE_ID][from_node]["time"] = 5
                TOPOLOGY[from_node][NODE_ID]["time"] = 5
                print(f"{Fore.MAGENTA}[HELLO]{Style.RESET_ALL} Refrescada conexión {NODE_ID} <-> {from_node}")
            else:
                print(f"{Fore.MAGENTA}[HELLO]{Style.RESET_ALL} Ignorado hello de no-vecino {from_node}")

        elif msg_type == "message":
            if msg_id in SEEN_MESSAGES:
                # Ya procesado
                return
            SEEN_MESSAGES.add(msg_id)

            # Aprender la conexión
            if from_node not in TOPOLOGY:
                TOPOLOGY[from_node] = {}
            if to_node not in TOPOLOGY:
                TOPOLOGY[to_node] = {}

            if to_node not in TOPOLOGY[from_node]:
                TOPOLOGY[from_node][to_node] = {"weight": hops, "time": 15}
                TOPOLOGY[to_node][from_node] = {"weight": hops, "time": 15}
                print(f"{Fore.BLUE}[MSG]{Style.RESET_ALL} Aprendida nueva conexión {from_node} <-> {to_node}")
            else:
                TOPOLOGY[from_node][to_node]["time"] = 15
                TOPOLOGY[to_node][from_node]["time"] = 15
                print(f"{Fore.BLUE}[MSG]{Style.RESET_ALL} Refrescada conexión {from_node} <-> {to_node}")

            # Flooding: reenviar a todos los vecinos excepto quien lo envió
            for nbr in TOPOLOGY[NODE_ID].keys():
                if nbr != msg.get("from"):
                    await TRANSPORT.send(nbr, msg)
                    print(f"{Fore.CYAN}[FLOOD]{Style.RESET_ALL} Reenviado {from_node} <-> {to_node} a {nbr}")



async def decrement_topology():
    while True:
        await asyncio.sleep(1)
        async with LOCK:
            to_remove = []
            for node, neighbors in list(TOPOLOGY.items()):
                for nbr, data in list(neighbors.items()):
                    data["time"] -= 1
                    if data["time"] <= 0:
                        print(f"{Fore.RED}[DELETED]{Style.RESET_ALL} Eliminando conexión {node} <-> {nbr}")
                        to_remove.append((node, nbr))
            for node, nbr in to_remove:
                if nbr in TOPOLOGY.get(node, {}):
                    del TOPOLOGY[node][nbr]
                if node in TOPOLOGY.get(nbr, {}):
                    del TOPOLOGY[nbr][node]


async def send_hellos(neighbors):
    global TRANSPORT, NODE_ID
    while True:
        await asyncio.sleep(3)
        async with LOCK:
            for nbr, data in neighbors.items():
                msg = make_hello(NODE_ID, nbr, data["weight"])
                await TRANSPORT.send(nbr, msg)
                print(f"{Fore.GREEN}[ADDED]{Style.RESET_ALL} Enviando Hello a {nbr}")


async def send_messages():
    global TRANSPORT, NODE_ID, TOPOLOGY
    while True:
        await asyncio.sleep(10)
        async with LOCK:
            for node, neighbors in TOPOLOGY.items():
                for nbr, data in neighbors.items():
                    if node == NODE_ID:
                        for my_nbr in TOPOLOGY[NODE_ID].keys():
                            msg = make_message(node, nbr, data["weight"])
                            await TRANSPORT.send(my_nbr, msg)
                            print(f"{Fore.YELLOW}[UPDATE]{Style.RESET_ALL} Difundiendo conexión {node} <-> {nbr} a {my_nbr}")


async def menu_loop():
    global TOPOLOGY
    while True:
        print("\n=== MENÚ ===")
        print("1. Mostrar topología actual")
        print("2. Ejecutar Dijkstra (pendiente)")
        print("3. Salir del nodo")
        opcion = await asyncio.to_thread(input, "Selecciona una opción: ")

        if opcion.strip() == "1":
            async with LOCK:
                print("\n[TOPOLOGÍA ACTUAL]")
                print(json.dumps(TOPOLOGY, indent=2))
        elif opcion.strip() == "2":

            # obtener vecinos desde la topología aprendida
            neighbors = list(TOPOLOGY[NODE_ID].keys())

            # inicializar Dijkstra
            dijkstra = Dijkstra(NODE_ID, neighbors)

            # calcular rutas
            dijkstra.compute_routes(TOPOLOGY)

            # imprimir tabla
            dijkstra.printTable()
            print("[TODO] Implementar Dijkstra")
        elif opcion.strip() == "3":
            print("[MAIN] Nodo detenido por usuario")
            await TRANSPORT.disconnect()
            raise SystemExit
        else:
            print("[WARN] Opción inválida")


async def main():
    global TOPOLOGY, NODE_ID, TRANSPORT

    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True)
    parser.add_argument("--topo", required=True)
    parser.add_argument("--ids", required=True)
    parser.add_argument("--transport", required=True, choices=["redis"])
    args = parser.parse_args()

    NODE_ID = args.id
    full_topology = load_topology(args.topo, args.ids)
    neighbors = get_neighbors(NODE_ID, full_topology)

    TOPOLOGY[NODE_ID] = {}
    for nbr, data in neighbors.items():
        TOPOLOGY[NODE_ID][nbr] = {"weight": data["weight"], "time": 5}
        if nbr not in TOPOLOGY:
            TOPOLOGY[nbr] = {}
        TOPOLOGY[nbr][NODE_ID] = {"weight": data["weight"], "time": 5}

    print("[INIT] Topología inicial:")
    print(json.dumps(TOPOLOGY, indent=2))

    if args.transport == "redis":
        TRANSPORT = AsyncRedisTransport(
            node_id=NODE_ID,
            on_message=on_message,
            neighbor_ids=list(neighbors.keys())
        )
        await TRANSPORT.start_server()

    # Correr todas las tareas en paralelo
    await asyncio.gather(
        decrement_topology(),
        send_hellos(neighbors),
        send_messages(),
        menu_loop()
    )


if __name__ == "__main__":
    asyncio.run(main())
