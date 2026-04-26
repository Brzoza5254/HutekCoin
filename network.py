import socket, threading, json, subprocess, re, time

class NetworkNode:
    def __init__(self, port=5000):
        self.port, self.peers, self.public_url = port, set(), None
        self.start_tunnel()

    def start_tunnel(self):
        def run():
            # Tunelowanie przez localhost.run - mapuje lokalny port na publiczny port 80
            p = subprocess.Popen(["ssh","-o","StrictHostKeyChecking=accept-new","-R",f"80:localhost:{self.port}","nokey@localhost.run"], stdout=subprocess.PIPE, text=True)
            for line in p.stdout:
                m = re.search(r'([\w-]+\.lhr\.life)', line)
                if m: 
                    self.public_url = m.group(1)
                    print(f"[*] Public URL: {self.public_url}")
                    break
        threading.Thread(target=run, daemon=True).start()

    def connect_to_peer(self, addr):
        # Usuwamy ewentualne http:// lub porty, by mieć czysty host
        clean_addr = addr.replace("http://", "").split(":")[0].strip()
        if clean_addr and clean_addr != self.public_url and clean_addr not in self.peers:
            self.peers.add(clean_addr)
            # 1. Przywitaj się i podaj swoich znajomych
            self.send_to_one(clean_addr, {
                "type": "GOSSIP_HELLO",
                "my_url": self.public_url,
                "known_peers": list(self.peers)
            })
            # 2. Poproś o łańcuch do synchronizacji
            self.send_to_one(clean_addr, {"type": "GET_CHAIN", "my_url": self.public_url})

    def start_server(self, cb):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', self.port))
        s.listen(5)
        def run():
            while True:
                try:
                    c, _ = s.accept()
                    d = c.recv(1024*1024)
                    if d:
                        msg = json.loads(d.decode())
                        # REAKCJA NA GOSSIP: Jeśli poznałeś nowych, połącz się z nimi
                        if msg['type'] == "GOSSIP_HELLO":
                            new_found = False
                            for p in msg.get('known_peers', []):
                                if p != self.public_url and p not in self.peers:
                                    self.peers.add(p)
                                    new_found = True
                                    # Automatyczne łączenie z nowo odkrytymi (REAKCJA ŁAŃCUCHOWA)
                                    threading.Thread(target=self.connect_to_peer, args=(p,)).start()
                            
                            if msg['my_url'] not in self.peers and msg['my_url'] != self.public_url:
                                self.peers.add(msg['my_url'])
                                # Odpowiedz nowemu peerowi, by on też o Tobie wiedział
                                self.send_to_one(msg['my_url'], {
                                    "type": "GOSSIP_HELLO", 
                                    "my_url": self.public_url, 
                                    "known_peers": list(self.peers)
                                })
                        
                        cb(msg, self)
                    c.close()
                except: pass
        threading.Thread(target=run, daemon=True).start()

    def send_to_one(self, host, data):
        def _send():
            try:
                # Wymuszamy port 80, bo localhost.run tam odbiera ruch
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                s.connect((host.strip(), 80)) 
                s.send(json.dumps(data).encode())
                s.close()
            except: pass
        # Wysyłamy w osobnym wątku, by nie blokować GUI/Minera
        threading.Thread(target=_send).start()

    def broadcast(self, data):
        for p in list(self.peers): 
            self.send_to_one(p, data)