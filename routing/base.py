class RoutingAlgorithm:
    def __init__(self, node_id, neighbors):
        self.node_id = node_id
        self.neighbors = neighbors
        self.routing_table = {}

    def compute_routes(self, topology):
        raise NotImplementedError("Must be implemented by subclasses")
