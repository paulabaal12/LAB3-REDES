from .base import RoutingAlgorithm

class Flooding(RoutingAlgorithm):
    def __init__(self, node_id, neighbors):
        super().__init__(node_id, neighbors)
        # conjunto de mensajes ya recibidos (para evitar reenvíos duplicados)
        self.seen_messages = set()

    def compute_routes(self, topology):
        self.routing_table = {"__FLOOD__": set(topology[self.node_id].keys())}
        return self.routing_table

    def handle_message(self, msg, transport, nodes_ports):
        msg_id = msg.get("msg_id")
        
        if msg_id in self.seen_messages:
            #print(f"[{self.node_id}] Ignorado duplicado msg_id={msg_id}")
            return

        self.seen_messages.add(msg_id)

        # Mostrar el mensaje recibido
        payload = msg.get('payload', '')
        hops = msg.get('hops', 0)
        origin = msg.get('from', 'unknown')
        print(f"\n[{self.node_id}] Recibido (Flooding): '{payload}' de {origin} (hops={hops})\n> ", end="")

        if hops >= 32:
            print(f"\n[{self.node_id}] TTL excedido, no reenvío.\n> ", end="")
            return

        # Reenviar a todos los vecinos EXCEPTO:
        # - El nodo que nos envió el mensaje (last_hop)
        # - El nodo origen del mensaje (from)
        last_hop = msg.get("last_hop")
        origin_node = msg.get("from")
        
        for neigh in self.routing_table["__FLOOD__"]:
            # No reenviar al nodo que nos lo envió
            if neigh == last_hop:
                print(f"[{self.node_id}] Skip {neigh} (es last_hop)")
                continue
            
            if neigh == origin_node:
                print(f"[{self.node_id}] Skip {neigh} (es el origen)")
                continue

            # Crear copia del mensaje para reenvío
            fwd = dict(msg)
            fwd["hops"] = hops + 1
            fwd["last_hop"] = self.node_id 

            try:
                nh_port = nodes_ports[neigh]
                transport.send("127.0.0.1", nh_port, fwd)
                print(f"[{self.node_id}] Flood → {neigh} (hops={fwd['hops']})")
            except Exception as e:
                print(f"[{self.node_id}] Error reenviando a {neigh}: {e}")
