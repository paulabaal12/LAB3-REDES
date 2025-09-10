import time
import threading
from .base import RoutingAlgorithm
from .dijkstra import Dijkstra

class LinkState(RoutingAlgorithm):
	def __init__(self, node_id, neighbors):
		super().__init__(node_id, neighbors)
		# Topología: { nodo: { vecino: costo, ... }, ... }
		self.topology = {node_id: dict(neighbors)}
		self.seen_lsa = {}  # { nodo: seq }
		self.seq_local = 0
		self.dijkstra = Dijkstra(node_id, neighbors)
		self._periodic_flooding_started = False

	def _neighbor_costs_local(self):
		# Permite flexibilidad de tipos de datos
		costs = {}
		for nbr, w in self.neighbors.items():
			try:
				costs[nbr] = float(w)
			except Exception:
				costs[nbr] = 1.0
		return costs

	def _apply_lsa(self, origin, neighbors):
		# Actualiza la topología de forma bidireccional
		self.topology.setdefault(origin, {})
		self.topology[origin] = {}
		for v, w in neighbors.items():
			try:
				w = float(w)
			except Exception:
				continue
			if w <= 0:
				continue
			self.topology[origin][v] = w
			self.topology.setdefault(v, {})
			if origin not in self.topology[v] or w < self.topology[v][origin]:
				self.topology[v][origin] = w

	def create_lsa(self):
		self.seq_local += 1
		return {
			"proto": "lsr",
			"type": "LSA",
			"origin": self.node_id,
			"seq": self.seq_local,
			"neighbors": self._neighbor_costs_local(),
			"timestamp": time.time(),
		}

	def handle_message(self, msg, transport, nodes_ports):
		# Solo procesar LSAs
		if msg.get("type") != "LSA":
			return
		origin = msg.get("origin") or msg.get("from")
		seq = msg.get("seq", -1)
		neighbors = msg.get("neighbors", {})
		if origin is None or not isinstance(neighbors, dict):
			print(f"[LSR] LSA mal formado: {msg}")
			return
		if seq <= self.seen_lsa.get(origin, -1):
			return
		self.seen_lsa[origin] = seq
		self._apply_lsa(origin, neighbors)
		self.compute_routes(self.topology)
		# Flood a todos los vecinos excepto el que lo envió
		last_hop = msg.get("last_hop")
		for neigh in self.neighbors:
			if neigh == last_hop:
				continue
			fwd = dict(msg)
			fwd["last_hop"] = self.node_id
			try:
				if hasattr(transport, 'send'):
					# RedisTransport: canal = nombre del nodo
					transport.send(neigh, fwd)
				else:
					# TCPTransport
					nh_port = nodes_ports[neigh]
					transport.send("127.0.0.1", nh_port, fwd)
			except Exception as e:
				print(f"[LSR] Error reenviando LSA a {neigh}: {e}")

	def flood_lsa(self, transport, nodes_ports, initial_delay=1.5):
		if initial_delay > 0:
			time.sleep(initial_delay)
		lsa = self.create_lsa()
		print(f"[LSR][{self.node_id}] Flooding LSA a vecinos: {list(self.neighbors.keys())}")
		for neigh in self.neighbors:
			fwd = dict(lsa)
			fwd["last_hop"] = self.node_id
			try:
				if hasattr(transport, 'send'):
					print(f"[LSR][{self.node_id}] Enviando LSA a {neigh} (canal Redis)")
					transport.send(neigh, fwd)
				else:
					nh_port = nodes_ports[neigh]
					print(f"[LSR][{self.node_id}] Enviando LSA a {neigh} (puerto {nh_port})")
					transport.send("127.0.0.1", nh_port, fwd)
			except Exception as e:
				print(f"[LSR] Error enviando LSA a {neigh}: {e}")

	def start_periodic_flooding(self, transport, nodes_ports, interval=2.0, duration=8.0):
		if self._periodic_flooding_started:
			return
		self._periodic_flooding_started = True
		def flood_loop():
			start = time.time()
			while time.time() - start < duration:
				self.flood_lsa(transport, nodes_ports, initial_delay=0)
				time.sleep(interval)
		threading.Thread(target=flood_loop, daemon=True).start()

	def compute_routes(self, topology):
		# Ejecuta Dijkstra sobre la topología
		table = self.dijkstra.compute_routes(topology)
		self.routing_table = table
		print(f"[LSR][{self.node_id}] Tabla de enrutamiento actualizada: {self.routing_table}")
		return table
