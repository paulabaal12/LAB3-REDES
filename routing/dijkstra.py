import heapq
from .base import RoutingAlgorithm

class Dijkstra(RoutingAlgorithm):
    def compute_routes(self, topology):
        # Asegura que todos los nodos vecinos estén como claves
        for u in list(topology.keys()):
            for v in topology[u]:
                if v not in topology:
                    topology[v] = {}
        dist = {node: float("inf") for node in topology}
        prev = {node: None for node in topology}
        dist[self.node_id] = 0

        pq = [(0, self.node_id)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, w in topology[u].items():
                alt = dist[u] + w
                if alt < dist[v]:
                    dist[v] = alt
                    prev[v] = u
                    heapq.heappush(pq, (alt, v))

        # construir tabla de enrutamiento
        table = {}
        for dest in topology:
            if dest == self.node_id:
                continue
            # encontrar el next hop
            current = dest
            while prev[current] and prev[current] != self.node_id:
                current = prev[current]
            if prev[current]:
                table[dest] = current
        self.routing_table = table
        return table
