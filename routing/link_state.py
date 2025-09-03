
import heapq
import time
from .base import RoutingAlgorithm

class LinkState(RoutingAlgorithm):
	def __init__(self, node_id, neighbors):
		super().__init__(node_id, neighbors)
		# LSDB: { node_id: { neighbor: cost, ... }, ... }
		self.lsdb = {node_id: dict(neighbors)}
		self.seen_lsas = set()  # (origin, seq)
		self.seq = 0

	def create_lsa(self):
		self.seq += 1
		return {
			"proto": "lsr",
			"type": "LSA",
			"from": self.node_id,
			"seq": self.seq,
			"neighbors": dict(self.neighbors),
			"timestamp": time.time(),
		}

	def handle_message(self, msg, transport, nodes_ports):
		# Solo procesar LSAs
		if msg.get("type") != "LSA":
			return
		origin = msg["from"]
		seq = msg["seq"]
		key = (origin, seq)
		if key in self.seen_lsas:
			return
		self.seen_lsas.add(key)
		# Actualizar LSDB
		self.lsdb[origin] = dict(msg["neighbors"])
		# Recalcular rutas
		self.compute_routes(self.lsdb)
		# Flood a todos los vecinos excepto el que lo envió
		last_hop = msg.get("last_hop")
		for neigh in self.neighbors:
			if neigh == last_hop:
				continue
			nh_port = nodes_ports[neigh]
			fwd = dict(msg)
			fwd["last_hop"] = self.node_id
			try:
				transport.send("127.0.0.1", nh_port, fwd)
			except Exception as e:
				print(f"[LSR] Error reenviando LSA a {neigh}: {e}")

	def flood_lsa(self, transport, nodes_ports):
		lsa = self.create_lsa()
		for neigh in self.neighbors:
			nh_port = nodes_ports[neigh]
			fwd = dict(lsa)
			fwd["last_hop"] = self.node_id
			try:
				transport.send("127.0.0.1", nh_port, fwd)
			except Exception as e:
				print(f"[LSR] Error enviando LSA a {neigh}: {e}")

	def compute_routes(self, topology):
		# Ejecuta Dijkstra sobre la LSDB
		dist = {node: float("inf") for node in topology}
		prev = {node: None for node in topology}
		dist[self.node_id] = 0
		pq = [(0, self.node_id)]
		while pq:
			d, u = heapq.heappop(pq)
			if d > dist[u]:
				continue
			for v, w in topology.get(u, {}).items():
				alt = dist[u] + w
				if alt < dist[v]:
					dist[v] = alt
					prev[v] = u
					heapq.heappush(pq, (alt, v))
		table = {}
		for dest in topology:
			if dest == self.node_id:
				continue
			current = dest
			while prev[current] and prev[current] != self.node_id:
				current = prev[current]
			if prev[current]:
				table[dest] = current
		self.routing_table = table
		return table
