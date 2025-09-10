import socket
import threading
import json
import asyncio
import time
import slixmpp
import json as _json

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
                print(f"[TCP] {message.get('proto')} {message.get('type')} {message.get('from')} -> {message.get('to')}")
        except Exception as e:
            print(f"[TCP] Error sending to {target_host}:{target_port} -> {e}")
            raise

class XMPPBot(slixmpp.ClientXMPP):
    def __init__(self, jid, password, on_message_callback):
        super().__init__(jid, password)
        self.on_message_callback = on_message_callback

        # Handlers
        self.add_event_handler("session_start", self.start)
        self.add_event_handler("message", self.message)

    async def start(self, event):
        try:
            self.send_presence()
            await self.get_roster()
            print("[XMPP] Session started, presence sent and roster fetched")
        except Exception as e:
            print(f"[XMPP] Error in session_start: {e}")

    def message(self, msg):
        if msg['type'] in ('chat', 'normal'):
            try:
                data = _json.loads(str(msg['body']))
                self.on_message_callback(data)
            except Exception as e:
                print(f"[XMPP] Error al procesar mensaje: {e}")


class XMPPTransport:

    def __init__(self, jid, password, on_message_callback,
        server='homelab.fortiguate.com', port=16379):
        self.jid = jid
        self.password = password
        self.on_message_callback = on_message_callback
        self.server = server
        self.port = port

        self.xmpp = XMPPBot(jid, password, on_message_callback)

        self._loop_thread = None
        self._loop = None
        self._running = False

        self._has_process = hasattr(self.xmpp, 'process')

    def connect(self):
        pass

    def send(self, to_jid, message):
        try:
            msg_str = _json.dumps(message)
        except Exception as e:
            print(f"[XMPP] Error serializando mensaje: {e}")
            return

        if self._has_process:
            try:
                self.xmpp.send_message(mto=to_jid, mbody=msg_str, mtype='chat')
                print(f"[XMPP] Enviado (legacy) -> {to_jid}")
            except Exception as e:
                print(f"[XMPP] Error enviando mensaje (legacy): {e}")
            return

        if self._loop and self._running:
            def _do_send():
                try:
                    self.xmpp.send_message(mto=to_jid, mbody=msg_str, mtype='chat')
                    print(f"[XMPP] Enviado -> {to_jid}")
                except Exception as e:
                    print(f"[XMPP] Error enviando mensaje (asyncio): {e}")

            # Programar dentro del loop
            self._loop.call_soon_threadsafe(_do_send)
        else:
            print("[XMPP] No hay loop activo; ¿llamaste start_listener()?")

    def start_listener(self):
        if self._has_process:
            # ========== MODO LEGACY ==========
            def _legacy_runner():
                try:
                    # Conexión (bloquea internamente al procesar)
                    ok = self.xmpp.connect((self.server, self.port))
                    if not ok:
                        print(f"[XMPP] Legacy connect() falló contra {self.server}:{self.port}")
                        return
                    print("[XMPP] Legacy conectado; iniciando process(forever=True)")
                    self.xmpp.process(forever=True)
                except Exception as e:
                    print(f"[XMPP] Error en legacy runner: {e}")
                finally:
                    self.xmpp.disconnect()

            t = threading.Thread(target=_legacy_runner, daemon=True)
            t.start()
            return

        # ========== MODO MODERNO ==========
        if self._running:
            print("[XMPP] Listener ya estaba iniciado")
            return

        self._running = True

        def _loop_runner():
            try:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)

                # Agenda la conexión; connect() no bloquea
                self.xmpp.connect(host=self.server, port=self.port)

                # Corre hasta que se desconecte
                print(f"[XMPP] Async loop corriendo (host={self.server}, port={self.port})")
                self._loop.run_until_complete(self.xmpp.disconnected)
                print("[XMPP] Señal de desconexión recibida")
            except Exception as e:
                print(f"[XMPP] Error en loop_runner: {e}")
            finally:
                try:
                    pending = asyncio.all_tasks(loop=self._loop)
                    for task in pending:
                        task.cancel()
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                except Exception:
                    pass
                finally:
                    self._loop.stop()
                    self._loop.close()
                    self._loop = None
                    self._running = False
                    print("[XMPP] Async loop cerrado")

        self._loop_thread = threading.Thread(target=_loop_runner, daemon=True)
        self._loop_thread.start()

        time.sleep(0.1)

    def disconnect(self):
        if self._has_process:
            try:
                self.xmpp.disconnect()
                print("[XMPP] Legacy disconnect() solicitado")
            except Exception as e:
                print(f"[XMPP] Error en legacy disconnect(): {e}")
            return

        if self._loop and self._running:
            def _do_disc():
                try:
                    self.xmpp.disconnect()
                except Exception as e:
                    print(f"[XMPP] Error en disconnect(): {e}")

            self._loop.call_soon_threadsafe(_do_disc)
        else:
            print("[XMPP] No hay loop activo para desconectar")
