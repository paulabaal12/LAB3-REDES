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
                print(f"[TCP] {message['proto']} {message['type']} {message['from']} -> {message['to']}")

        except Exception as e:
            print(f"[TCP] Error sending to {target_host}:{target_port} -> {e}")
            raise


import slixmpp
import json as _json

print("DEBUG: slixmpp.ClientXMPP =", slixmpp.ClientXMPP)
print("DEBUG: hasattr(ClientXMPP, 'process') =", hasattr(slixmpp.ClientXMPP, 'process'))

class XMPPBot(slixmpp.ClientXMPP):
    def __init__(self, jid, password, on_message_callback):
        super().__init__(jid, password)
        self.on_message_callback = on_message_callback
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.message)

    async def start(self, event):
        self.send_presence()
        await self.get_roster()

    def message(self, msg):
        if msg['type'] in ('chat', 'normal'):
            try:
                data = _json.loads(str(msg['body']))
                self.on_message_callback(data)
            except Exception as e:
                print(f"[XMPP] Error al procesar mensaje: {e}")

class XMPPTransport:
    def __init__(self, jid, password, on_message_callback, server='homelab.fortiguate.com', port=16379):
        self.jid = jid
        self.password = password
        self.on_message_callback = on_message_callback
        self.server = server
        self.port = port
        self.xmpp = XMPPBot(jid, password, on_message_callback)

    def connect(self):
        self.xmpp.connect((self.server, self.port))

    def send(self, to_jid, message):
        try:
            msg_str = _json.dumps(message)
            self.xmpp.send_message(mto=to_jid, mbody=msg_str, mtype='chat')
        except Exception as e:
            print(f"[XMPP] Error enviando mensaje: {e}")

    def start_listener(self):
        print("DEBUG: type(self.xmpp) =", type(self.xmpp))
        # Forzar uso de process si existe
        if hasattr(self.xmpp, 'process'):
            self.xmpp.process(forever=True)
        elif hasattr(self.xmpp, 'client') and hasattr(self.xmpp.client, 'process'):
            self.xmpp.client.process(forever=True)
        else:
            raise AttributeError(f'No se encontró el método process en XMPPBot ({type(self.xmpp)}) ni en su cliente interno')

    def disconnect(self):
        self.xmpp.disconnect()