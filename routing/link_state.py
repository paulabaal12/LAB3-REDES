
import heapq
import time
from .base import RoutingAlgorithm

import threading

class LinkState(RoutingAlgorithm):
	def __init__(self, node_id, neighbors):
		super().__init__(node_id, neighbors)
		# LSDB: { node_id: { neighbor: cost, ... }, ... }
		self.lsdb = {node_id: dict(neighbors)}
		self.seen_lsas = set()  # (origin, seq)
		self.seq = 0
		self._periodic_flooding_started = False

	def start_periodic_flooding(self, transport, nodes_ports, interval=2.0, duration=8.0):
		"""Reenvía LSAs cada 'interval' segundos durante 'duration' segundos tras el arranque."""
		if self._periodic_flooding_started:
			return
		self._periodic_flooding_started = True
		def flood_loop():
			import time
			start = time.time()
			while time.time() - start < duration:
				self.flood_lsa(transport, nodes_ports, initial_delay=0)
				time.sleep(interval)
		threading.Thread(target=flood_loop, daemon=True).start()

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
				# print(f"[LSR] Error reenviando LSA a {neigh}: {e}")
				pass

	def flood_lsa(self, transport, nodes_ports, initial_delay=1.5):
		import time
		if initial_delay > 0:
			#print(f"[LSR][{self.node_id}] Esperando {initial_delay} segundos antes de floodear LSA...")
			time.sleep(initial_delay)
		lsa = self.create_lsa()
		print(f"[LSR][{self.node_id}] Flooding LSA a vecinos: {list(self.neighbors.keys())}")
		for neigh in self.neighbors:
			nh_port = nodes_ports[neigh]
			fwd = dict(lsa)
			fwd["last_hop"] = self.node_id
			try:
				print(f"[LSR][{self.node_id}] Enviando LSA a {neigh} (puerto {nh_port})")
				transport.send("127.0.0.1", nh_port, fwd)
			except Exception as e:
				# print(f"[LSR] Error enviando LSA a {neigh}: {e}")
				pass

	def compute_routes(self, topology):
		# Asegura que la LSDB tenga entradas para todos los nodos
		all_nodes = set(topology.keys())
		for node in all_nodes:
			if node not in self.lsdb:
				self.lsdb[node] = {}
		# Ejecuta Dijkstra sobre la LSDB
		dist = {node: float("inf") for node in self.lsdb}
		prev = {node: None for node in self.lsdb}
		dist[self.node_id] = 0
		pq = [(0, self.node_id)]
		while pq:
			d, u = heapq.heappop(pq)
			if d > dist[u]:
				continue
			for v, w in self.lsdb.get(u, {}).items():
				if v not in dist:
					dist[v] = float("inf")
					prev[v] = None
				alt = dist[u] + w
				if alt < dist[v]:
					dist[v] = alt
					prev[v] = u
					heapq.heappush(pq, (alt, v))
		table = {}
		for dest in self.lsdb:
			if dest == self.node_id:
				continue
			current = dest
			while prev[current] and prev[current] != self.node_id:
				current = prev[current]
			if prev[current]:
				table[dest] = current
		self.routing_table = table
		print(f"[LSR][{self.node_id}] Tabla de enrutamiento actualizada: {self.routing_table}")
		return table
