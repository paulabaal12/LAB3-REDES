from .base import RoutingAlgorithm
import threading
import time
import copy

class DistanceVector(RoutingAlgorithm):
	def __init__(self, node_id, neighbors):
		super().__init__(node_id, neighbors)
		# Tabla de distancias: { destino: (costo, next_hop) }
		self.dv_table = {n: (w, n) for n, w in neighbors.items()}
		self.dv_table[node_id] = (0, node_id)
		self.neighbor_tables = {}  # { vecino: {destino: (costo, next_hop)} }
		self.lock = threading.Lock()

	def create_update_msg(self):
		return {
			"proto": "dvr",
			"type": "DV_UPDATE",
			"from": self.node_id,
			"table": copy.deepcopy(self.dv_table),
			"timestamp": time.time(),
		}

	def handle_message(self, msg, transport, nodes_ports):
		if msg.get("type") != "DV_UPDATE":
			return
		origin = msg["from"]
		table = msg["table"]
		with self.lock:
			self.neighbor_tables[origin] = table
			changed = self.update_routes()
		if changed:
			self.flood_update(transport, nodes_ports)

	def flood_update(self, transport, nodes_ports):
		msg = self.create_update_msg()
		for neigh in self.neighbors:
			nh_port = nodes_ports[neigh]
			try:
				transport.send("127.0.0.1", nh_port, msg)
			except Exception:
				pass

	def update_routes(self):
		changed = False
		new_table = {self.node_id: (0, self.node_id)}
		for dest in self.dv_table:
			new_table[dest] = self.dv_table[dest]
		# Bellman-Ford: para cada destino, ver si hay mejor ruta vía vecinos
		for neigh, neigh_table in self.neighbor_tables.items():
			cost_to_neigh = self.neighbors[neigh]
			for dest, (cost_via_neigh, _) in neigh_table.items():
				if dest == self.node_id:
					continue
				total_cost = cost_to_neigh + cost_via_neigh
				if dest not in new_table or total_cost < new_table[dest][0]:
					new_table[dest] = (total_cost, neigh)
					changed = True
		if changed:
			self.dv_table = new_table
			# Actualiza la tabla de enrutamiento para el framework
			self.routing_table = {dest: nh for dest, (c, nh) in self.dv_table.items() if dest != self.node_id}
			print(f"[DVR][{self.node_id}] Tabla de ruteo actualizada: {self.routing_table}")
		return changed

	def compute_routes(self, topology=None):
		# Para compatibilidad con el framework
		self.routing_table = {dest: nh for dest, (c, nh) in self.dv_table.items() if dest != self.node_id}
		return self.routing_table
