import socket
import threading
import json

class TCPTransport:
    def __init__(self, host, port, on_message):
        self.host = host
        self.port = port
        self.on_message = on_message
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start_server(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen()
        print(f"[TCP] Node listening on {self.host}:{self.port}")

        def accept_loop():
            while True:
                conn, addr = self.sock.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()

        threading.Thread(target=accept_loop, daemon=True).start()

    def _handle_client(self, conn):
        with conn:
            data = conn.recv(4096)
            if not data:
                return
            try:
                msg = json.loads(data.decode())
                self.on_message(msg)
            except Exception as e:
                print("[TCP] Error parsing message:", e)

    def send(self, target_host, target_port, message):
        try:
            with socket.create_connection((target_host, target_port), timeout=2) as s:
                s.sendall(json.dumps(message).encode())
        except Exception as e:
            # print(f"[TCP] Error sending to {target_host}:{target_port} -> {e}")
            pass
