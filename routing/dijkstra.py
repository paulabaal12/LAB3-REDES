import heapq
from .base import RoutingAlgorithm

class Dijkstra(RoutingAlgorithm):
    def compute_routes(self, topology):
        """
        topology: dict con formato:
        {
            "nodo1": {
                "nodo2": {"weight": 8, "time": 4},
                "nodo3": {"weight": 10, "time": 5}
            },
            ...
        }
        """
        # asegurar que todos los nodos estén en el grafo
        for u in list(topology.keys()):
            for v in topology[u]:
                if v not in topology:
                    topology[v] = {}

        # inicialización
        dist = {node: float("inf") for node in topology}
        prev = {node: None for node in topology}
        dist[self.node_id] = 0

        pq = [(0, self.node_id)]
        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            for v, edge in topology[u].items():
                w = edge["weight"]  # 👈 tomar el peso real
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
            current = dest
            while prev[current] and prev[current] != self.node_id:
                current = prev[current]
            if prev[current]:
                table[dest] = current

        self.routing_table = (table, dist)  # guardamos también los costos
        return table

    def printTable(self):
        """Imprime la tabla de enrutamiento ordenada por destino en un archivo"""
        with open('output/single_table.txt', 'w') as f:
            if not self.routing_table:
                f.write(f"[{self.node_id}] Tabla vacía\n")
                return

            table, dist = self.routing_table
            f.write(f"\nTabla de ruteo para nodo {self.node_id}:\n")
            f.write("-" * 60 + "\n")
            f.write(f"{'Destino':25s} {'Next Hop':20s} {'Costo':5s}\n")
            f.write("-" * 60 + "\n")
            for dest in sorted(table.keys()):
                nh = table[dest]
                cost = dist[dest] if dest in dist else "∞"
                f.write(f"{dest:25s} {nh:20s} {cost}\n")
            f.write("-" * 60 + "\n")

    def fill_csv(self):
        """Llena un csv con sus respectivos tiempos"""
        import csv
        import os

        # Lista de todos los nodos posibles (nodo1 a nodo11)
        nodes = [f"sec30.grupo{i}.nodo{i}" for i in range(1, 12)]
        
        # Asegurar que la carpeta output exista
        os.makedirs('output', exist_ok=True)
        
        # Ruta del archivo CSV
        csv_file = 'output/table.csv'
        
        # Obtener la tabla de enrutamiento
        table, dist = self.routing_table if self.routing_table else ({}, {})
        
        # Crear la fila para este nodo
        row = {node: "" for node in nodes}  # Inicializar con valores vacíos
        row['source'] = self.node_id  # Establecer el nodo fuente
        
        # Llenar los tiempos para los destinos alcanzables
        for dest in table:
            if dest in nodes:
                cost = dist.get(dest, "inf")
                row[dest] = str(cost)  # Convertir a string, incluyendo "∞" si no hay camino
        
        # Leer el contenido existente del CSV (si existe)
        existing_rows = []
        try:
            with open(csv_file, 'r', newline='') as f:
                reader = csv.DictReader(f)
                existing_rows = [r for r in reader if r['source'] != self.node_id]
        except FileNotFoundError:
            pass  # El archivo no existe, se creará uno nuevo
        
        # Agregar la nueva fila
        existing_rows.append(row)
        
        # Escribir el CSV
        with open(csv_file, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['source'] + nodes)
            writer.writeheader()
            writer.writerows(existing_rows)