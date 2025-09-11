# main.py
import argparse
import uuid
import time
import threading
import json
from network.protocol import make_hello_message, make_info_message
from network.transport import RedisTransport   # **usar solo Redis**
from network.topo_loader import load_topology, load_names



with open("groups.json") as f:
    groups = json.load(f)

nodes_ports = load_names("names-ports.json")
print(nodes_ports)


# ---------- Dijkstra local (devuelve next-hop y distancias + full path) ----------
import heapq
def dijkstra_full(topology, src):
    """
    topology: { node: { neighbor: weight, ... }, ... }
    returns: dist, prev
    """
    dist = {n: float("inf") for n in topology}
    prev = {n: None for n in topology}
    if src not in topology:
        return {}, {}
    dist[src] = 0
    pq = [(0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in topology.get(u, {}).items():
            alt = dist[u] + w
            if alt < dist.get(v, float("inf")):
                dist[v] = alt
                prev[v] = u
                heapq.heappush(pq, (alt, v))
    # build next-hop table
    next_hop = {}
    for dest in topology:
        if dest == src: continue
        if dist.get(dest, float("inf")) == float("inf"):
            continue
        # walk back to get next hop
        cur = dest
        while prev[cur] and prev[cur] != src:
            cur = prev[cur]
        if prev[cur] or cur == src:
            # if prev[cur] is src OR cur==src (direct)
            # next hop is cur if cur != src else dest
            nh = cur if cur != src else dest
            next_hop[dest] = nh
    return dist, next_hop, prev

# ---------- Programa principal ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", required=True, help="Node ID (ej. N1)")
    parser.add_argument("--topo", required=True, help="Archivo de topología (formato N1-N2:20,...)")
    parser.add_argument("--names", required=True, help="Archivo names-ports o names-jids (para mapping)")
    parser.add_argument("--transport", default="redis", choices=["redis"], help="Usar redis")
    parser.add_argument("--proto", default="linkstate", help="Proto label to set in messages (dijkstra|linkstate|etc.)")
    parser.add_argument("--hello-interval", type=int, default=3, help="Segs entre HELLOs")
    parser.add_argument("--msg-interval", type=int, default=15, help="Segs entre MESSAGEs")
    parser.add_argument("--timer-initial", type=int, default=5, help="Timer inicial en segundos para vecinos")
    args = parser.parse_args()

    node_id = args.id
    topology_file = args.topo
    names_file = args.names
    proto_name = args.proto

    # carga topología estática (weights) para conocer pesos iniciales de vecinos
    static_topo = load_topology(topology_file)   # formato {N1: {N2: w, ...}, ...}
    nodes_ports = load_names(names_file)         # mapping por si lo necesitas
    print(static_topo)
    # neighbors (directos a partir del archivo)
    direct_neighbors = static_topo.get(node_id, {})

    # ---------- Estructura de topología dinámica ----------
    # topology_local: { node: { neighbor: {"weight": w, "timer": t}, ...}, ... }
    topology_local = {}
    topo_lock = threading.Lock()

    # inicializa con nuestro nodo y vecinos directos
    with topo_lock:
        topology_local[node_id] = {}
        for n, w in direct_neighbors.items():
            topology_local[node_id][n] = {"weight": w, "timer": args.timer_initial}

    # estado de auto envío
    auto_message_enabled = True
    stop_threads = False

    # ---------- Callback cuando llega mensaje ----------
    def on_message(msg):
        nonlocal topology_local
        try:
            # debug print raw
            print(f"\n[RECV raw] {msg}")
            mtype = msg.get("type")
            sender = msg.get("from")
            if mtype == "hello":
                hops = msg.get("hops", 1)
                # reinicia o añade la entrada: topology_local[self][sender]
                with topo_lock:
                    if node_id not in topology_local:
                        topology_local[node_id] = {}
                    topology_local[node_id][sender] = {"weight": hops, "timer": args.timer_initial}
                print(f"[HELLO] Updated neighbor {sender} weight={hops} timer={args.timer_initial}")

            elif mtype == "message":
                edges = msg.get("edges", [])
                # edges is list of triples (u,v,w) or dicts; accept both
                added = 0
                with topo_lock:
                    for e in edges:
                        if isinstance(e, (list, tuple)) and len(e) >= 3:
                            u, v, w = e[0], e[1], e[2]
                        elif isinstance(e, dict):
                            # dict like {"u": "N6", "v":"N11", "w":5}
                            u = e.get("u"); v = e.get("v"); w = e.get("w")
                        else:
                            continue
                        # ensure entries
                        if u not in topology_local:
                            topology_local[u] = {}
                        topology_local[u][v] = {"weight": w, "timer": args.timer_initial}
                        added += 1
                if added:
                    print(f"[MESSAGE] Added/updated {added} edge(s) from payload by {sender}")
            else:
                print(f"[WARN] Unknown message type: {mtype}")
        except Exception as e:
            print(f"[on_message] Error processing msg: {e}")

    # ---------- Inicializar RedisTransport ----------
    # Build neighbor_groups / my_group placeholders if you use grouped channels.
    # For simplicity here we won't use per-group channels: assume transport.publish(target_node)
    transport = RedisTransport(node_id, on_message)

    # start listening (suscribe to own channel by default inside transport)
    # Optionally subscribe to neighbors if your RedisTransport supports it via start_server(subscribe_list=...)
    try:
        transport.start_server(subscribe_list=list(direct_neighbors.keys()))
    except TypeError:
        # backward compatibility if start_server doesn't accept subscribe_list
        transport.start_server()

    print(f"[INFO] Node {node_id} started. Direct neighbors from topo file: {list(direct_neighbors.keys())}")

    # ---------- helper to send robustly (tries multiple call styles) ----------
    def send_to(target_node, message):
        # try simple form first
        try:
            transport.send(target_node, message)
            return
        except TypeError:
            pass
        except Exception as e:
            print(f"[Send] Exception (first try): {e}")
        # try host,port,message if we have port mapping
        try:
            if target_node in nodes_ports:
                port = nodes_ports[target_node]
                transport.send("127.0.0.1", port, message)
                return
        except Exception as e:
            print(f"[Send] Exception (second try): {e}")
        # fallback: try publish with asyncio via transport.redis if available
        try:
            if hasattr(transport, "redis"):
                ch = f"sec30.grupo0.{target_node}"
                s = json.dumps(message)
                # blocking publish
                import asyncio
                asyncio.run(transport.redis.publish(ch, s))
                return
        except Exception as e:
            print(f"[Send] Exception (fallback): {e}")
        print(f"[Send] Could not send to {target_node}")

    # ---------- periodic: decrement timers each second ----------
    def timer_loop():
        nonlocal stop_threads
        while not stop_threads:
            time.sleep(1)
            removed = []
            with topo_lock:
                for node, nbrs in list(topology_local.items()):
                    for neigh, info in list(nbrs.items()):
                        info["timer"] -= 1
                        if info["timer"] <= 0:
                            del topology_local[node][neigh]
                            removed.append((node, neigh))
                    # if a node has no neighbors, we may keep empty dict
            if removed:
                for n, m in removed:
                    print(f"[TIMER] Removed entry {n} -> {m} due to timeout")

    t_timer = threading.Thread(target=timer_loop, daemon=True)
    t_timer.start()

    # ---------- periodic: send HELLO every hello_interval seconds ----------
    def hello_loop():
        nonlocal stop_threads
        while not stop_threads:
            # build list of current neighbors to send hello to (keys taken from static topo or dynamic neighbor list)
            with topo_lock:
                # prefer direct neighbors from static file for sending hello; fallback to dynamic known neighbors
                targets = list(direct_neighbors.keys()) if direct_neighbors else list(topology_local.get(node_id, {}).keys())
                # use weight from static if available else from topology_local
                targets_info = [(t, direct_neighbors.get(t) or topology_local.get(node_id, {}).get(t, {}).get("weight", 1)) for t in targets]
            for (t, w) in targets_info:
                hello = make_hello_message(proto_name, node_id, t, w)
                send_to(t, hello)
                # on send we don't modify timers; receiving side will reset
            # sleep the full interval
            for _ in range(args.hello_interval):
                if stop_threads: break
                time.sleep(1)

    t_hello = threading.Thread(target=hello_loop, daemon=True)
    t_hello.start()

    # ---------- periodic: send MESSAGE every msg_interval seconds ----------
    def message_loop():
        nonlocal stop_threads, auto_message_enabled
        while not stop_threads:
            if auto_message_enabled:
                # Prepare edges payload: collect our local view flattened to triples
                with topo_lock:
                    edges = []
                    # send all adjacency known in topology_local (as u,v,w)
                    for u, nbrs in topology_local.items():
                        for v, info in nbrs.items():
                            edges.append((u, v, info.get("weight", 1)))
                    # optionally reduce duplicate/reverse edges if you want
                # send to each direct neighbor (use static direct list if available)
                send_targets = list(direct_neighbors.keys()) if direct_neighbors else list(topology_local.get(node_id, {}).keys())
                for t in send_targets:
                    msg = make_info_message(proto_name, node_id, t, edges)
                    send_to(t, msg)
                    # slight delay between sends
                    time.sleep(0.05)
            # sleep the full interval
            for _ in range(args.msg_interval):
                if stop_threads: break
                time.sleep(1)

    t_msg = threading.Thread(target=message_loop, daemon=True)
    t_msg.start()

    # ---------- Interactive menu ----------
    try:
        while True:
            print("\n========== MENU ==========")
            print("1. Ver topología (dinámica)")
            print("2. Ver vecinos directos (del fichero)")
            print("3. Calcular tabla de enrutamiento (Dijkstra)")
            print("4. Toggle envío automático de MESSAGE (actualmente {})".format("ON" if auto_message_enabled else "OFF"))
            print("5. Enviar MESSAGE manualmente ahora")
            print("6. Salir")
            choice = input("> ").strip()
            if choice == "1":
                with topo_lock:
                    print(json.dumps(topology_local, indent=2))
            elif choice == "2":
                print("Direct neighbors (from topo file):", list(direct_neighbors.keys()))
                with topo_lock:
                    print("Neighbors seen in dynamic topology for this node:", list(topology_local.get(node_id, {}).keys()))
            elif choice == "3":
                # Build weight-only topology for dijkstra
                with topo_lock:
                    graph = {}
                    for u, nbrs in topology_local.items():
                        graph[u] = {v: info["weight"] for v, info in nbrs.items()}
                dist, next_hop, prev = dijkstra_full(graph, node_id)
                print("Distances:")
                for k, d in dist.items():
                    print(f"  {k}: {d}")
                print("Next-hop table:")
                print(json.dumps(next_hop, indent=2))
            elif choice == "4":
                auto_message_enabled = not auto_message_enabled
                print("Auto MESSAGE is now", "ON" if auto_message_enabled else "OFF")
            elif choice == "5":
                # manual send one MESSAGE to each direct neighbor
                with topo_lock:
                    edges = []
                    for u, nbrs in topology_local.items():
                        for v, info in nbrs.items():
                            edges.append((u, v, info.get("weight", 1)))
                    targets = list(direct_neighbors.keys()) if direct_neighbors else list(topology_local.get(node_id, {}).keys())
                for t in targets:
                    msg = make_info_message(proto_name, node_id, t, edges)
                    send_to(t, msg)
                    print(f"[MANUAL] Sent MESSAGE to {t}")
            elif choice == "6":
                print("Shutting down...")
                break
            else:
                print("Opción inválida")
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        stop_threads = True
        transport.disconnect()
        print("Bye")

if __name__ == "__main__":
    main()
