import sys, json, time
from PyQt6.QtWidgets import *
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from wallet import Wallet
from blockchain import Blockchain
from network import NetworkNode
import hashlib

class AutoMiner(QThread):
    block_mined = pyqtSignal(dict)
    def __init__(self, bc, addr):
        super().__init__(); self.bc, self.addr, self.running = bc, addr, True
    def run(self):
        while self.running:
            last = self.bc.get_last_block()
            if not last: continue
            prev, idx, nonce = last[5], last[0]+1, 0
            diff = self.bc.get_current_difficulty()
            txs = [{"sender":"SYSTEM","inputs":[],"outputs":[{"address":self.addr,"amount":2.5}],"ts":time.time()}] + list(self.bc.pending_transactions)
            tx_data = json.dumps(txs)
            while self.running:
                if self.bc.calculate_hash(idx, prev, time.time(), tx_data, nonce).startswith("0"*diff):
                    block = self.bc.create_block(nonce, prev); block['transactions'] = txs
                    if self.bc.save_block(block): self.block_mined.emit(block)
                    break
                nonce += 1
                if nonce % 20000 == 0:
                    l = self.bc.get_last_block()
                    if l and l[0] >= idx: break
                    time.sleep(0.001)

class App(QMainWindow):
    def __init__(self):
        super().__init__()
        self.wallet, self.blockchain, self.net = Wallet(), Blockchain(), NetworkNode()
        self.initUI()
        
        self.net.start_server(self.handle_net)
        self.miner = AutoMiner(self.blockchain, self.wallet.get_address())
        self.miner.block_mined.connect(lambda b: self.log_msg(f" Mined Block #{b['idx']}", "#f1c40f"))
        self.miner.start()
        
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(2000)

    def initUI(self):
        self.setWindowTitle("Wezel")
        self.setMinimumSize(1000, 700)
        self.setStyleSheet("""
            QMainWindow { background-color: #0b0e11; }
            QWidget { color: #eaecef; font-family: 'Segoe UI', sans-serif; font-size: 13px; }
            QFrame#Card { background-color: #181a20; border-radius: 8px; border: 1px solid #2b2f36; }
            QLineEdit, QDoubleSpinBox { background: #2b2f36; border: 1px solid #3b3e46; padding: 8px; border-radius: 4px; color: white; }
            QPushButton { background-color: #f0b90b; color: #000; font-weight: bold; border-radius: 4px; padding: 10px; }
            QPushButton:hover { background-color: #ffe259; }
            QPushButton#AltBtn { background-color: #2b2f36; color: white; border: 1px solid #484d58; }
            QLabel#Header { font-size: 18px; font-weight: bold; color: #f0b90b; }
            QTextEdit { background-color: #0b0e11; border: none; font-family: 'Consolas'; font-size: 12px; }
        """)

        main_widget = QWidget(); main_layout = QHBoxLayout(main_widget)
        self.setCentralWidget(main_widget)

        # LEWA KOLUMNA
        left_panel = QVBoxLayout()
        
        wallet_card = QFrame(); wallet_card.setObjectName("Card")
        wallet_lay = QVBoxLayout(wallet_card)
        
        self.bal_lbl = QLabel("0.00 HutekCoin")
        self.bal_lbl.setStyleSheet("font-size: 32px; font-weight: bold; color: #02c076;")
        wallet_lay.addWidget(QLabel("AVAILABLE BALANCE"))
        wallet_lay.addWidget(self.bal_lbl)
        
        self.addr_in = QLineEdit(self.wallet.get_address()); self.addr_in.setReadOnly(True)
        wallet_lay.addWidget(QLabel("Your Public Address:"))
        wallet_lay.addWidget(self.addr_in)
        
        wallet_lay.addWidget(QLabel("Import Wallet:"))
        self.priv_in = QLineEdit(); self.priv_in.setPlaceholderText("Paste Private Key (Hex)")
        btn_import_hex = QPushButton("Import from Hex")
        btn_import_hex.clicked.connect(self.import_hex)
        
        btn_import_file = QPushButton("Import .dat File")
        btn_import_file.setObjectName("AltBtn")
        btn_import_file.clicked.connect(self.import_file_dialog)
        
        wallet_lay.addWidget(self.priv_in)
        wallet_lay.addWidget(btn_import_hex)
        wallet_lay.addWidget(btn_import_file)
        left_panel.addWidget(wallet_card)

        # Transakcje
        tx_card = QFrame(); tx_card.setObjectName("Card")
        tx_lay = QVBoxLayout(tx_card)
        tx_lay.addWidget(QLabel("SEND TRANSACTION"))
        self.dest = QLineEdit(); self.dest.setPlaceholderText("Recipient Address")
        self.amt = QDoubleSpinBox(); self.amt.setRange(0, 999999)
        btn_send = QPushButton("Transfer Coins")
        btn_send.clicked.connect(self.send_tx)
        tx_lay.addWidget(self.dest); tx_lay.addWidget(self.amt); tx_lay.addWidget(btn_send)
        left_panel.addWidget(tx_card)

        # Sieć
        net_card = QFrame(); net_card.setObjectName("Card")
        net_lay = QVBoxLayout(net_card)
        net_lay.addWidget(QLabel("NETWORK STATUS"))
        self.node_url = QLineEdit("Searching for public IP..."); self.node_url.setReadOnly(True)
        self.p_in = QLineEdit(); self.p_in.setPlaceholderText("Peer URL (e.g. 1.2.3.4)")
        btn_conn = QPushButton("Connect to Peer")
        btn_conn.clicked.connect(lambda: self.net.connect_to_peer(self.p_in.text()))
        net_lay.addWidget(self.node_url); net_lay.addWidget(self.p_in); net_lay.addWidget(btn_conn)
        left_panel.addWidget(net_card)

        # PRAWA KOLUMNA
        right_panel = QVBoxLayout()
        log_card = QFrame(); log_card.setObjectName("Card")
        log_lay = QVBoxLayout(log_card)
        self.log = QTextEdit(); self.log.setReadOnly(True)
        log_lay.addWidget(QLabel("NODE LIVE LOGS"))
        log_lay.addWidget(self.log)
        right_panel.addWidget(log_card)

        main_layout.addLayout(left_panel, 1); main_layout.addLayout(right_panel, 2)

    def log_msg(self, text, color="#eaecef"):
        ts = time.strftime("%H:%M:%S")
        self.log.append(f'<span style="color:#707a8a">[{ts}]</span> <span style="color:{color}">{text}</span>')

    def import_hex(self):
        if self.wallet.import_wallet(self.priv_in.text().strip()):
            self.update_wallet_ui()
            self.log_msg(" Wallet imported from Hex!", "#02c076")
        else: self.log_msg(" Invalid Hex Key.", "#cf304a")

    def import_file_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Wallet File", "", "Data Files (*.dat);;All Files (*)")
        if file_path:
            if self.wallet.import_from_file(file_path):
                self.update_wallet_ui()
                self.log_msg(f" Wallet imported from {file_path.split('/')[-1]}", "#02c076")
            else:
                self.log_msg(" Error: Invalid wallet file (must be 32 bytes).", "#cf304a")

    def update_wallet_ui(self):
        addr = self.wallet.get_address()
        self.addr_in.setText(addr)
        self.miner.addr = addr
        self.refresh()

    def refresh(self):
        balance = self.blockchain.get_balance(self.wallet.get_address())
        self.bal_lbl.setText(f"{balance:.2f} HutekCoin")
        if self.net.public_url: self.node_url.setText(f"Online: {self.net.public_url}")

    def send_tx(self):
        if self.blockchain.add_transaction(self.wallet.get_address(), self.dest.text(), self.amt.value()):
            self.net.broadcast({"type":"TX","data":self.blockchain.pending_transactions[-1]})
            self.log_msg(f" Sent {self.amt.value()} COIN", "#3498db")
        else: self.log_msg(" Insufficient funds!", "#cf304a")

    def handle_net(self, msg, node):
        if msg['type'] == "BLOCK":
            if self.blockchain.save_block(msg['data']): self.log_msg(f" Synced Block #{msg['data']['idx']}", "#3498db")
        elif msg['type'] == "TX":
            self.blockchain.pending_transactions.append(msg['data'])
        elif msg['type'] == "CHAIN_DATA":
            if self.blockchain.replace_chain(msg['chain']): self.log_msg(" Blockchain synchronized!", "#9b59b6")

if __name__ == "__main__":
    a = QApplication(sys.argv); w = App(); w.show(); sys.exit(a.exec())
