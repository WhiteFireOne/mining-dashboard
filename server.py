#!/usr/bin/env python3
"""
Mining Dashboard proxy server.
- Serves mining-dashboard.html as a local web app.
- /proxy?url=...   : HTTP proxy for Bitaxe miners (GET, POST, PATCH).
- /avalon?ip=...   : TCP CGMiner API client for Avalon Nano 3S (port 4028).

Usage:  python3 server.py
Then open: http://localhost:8080/mining-dashboard.html
"""

import http.server
import urllib.request
import urllib.parse
import json
import os
import socket
import re
import base64

PORT = 8080
ROOT = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(ROOT, 'config.json')


def run_setup():
    print('\n=== Mining Dashboard — First-run Setup ===')
    print("config.json not found. Let's build one.\n")

    miners = []
    while True:
        idx = len(miners) + 1
        ip = input(f'Miner #{idx} IP address (leave blank to finish): ').strip()
        if not ip:
            break
        name  = input(f'  Name [Miner {idx}]: ').strip() or f'Miner {idx}'
        mtype = ''
        while mtype not in ('bitaxe', 'avalon'):
            mtype = input('  Type (bitaxe / avalon): ').strip().lower()
        miners.append({'ip': ip, 'name': name, 'type': mtype})

    node = None
    if input('\nDo you have a Bitcoin node? (y/n): ').strip().lower() == 'y':
        addr = input('  Node host:port (e.g. 192.168.1.10:8332): ').strip()
        user = input('  RPC username [bitcoin]: ').strip() or 'bitcoin'
        pwd  = input('  RPC password: ').strip()
        node = {'url': f'http://{addr}/', 'user': user, 'password': pwd}

    cfg = {'miners': miners}
    if node:
        cfg['node'] = node

    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)
    print(f'\nConfig saved to {CONFIG_FILE}\n')


def load_config():
    if not os.path.exists(CONFIG_FILE):
        run_setup()
    with open(CONFIG_FILE) as f:
        return json.load(f)


config      = load_config()
ALLOWED_IPS = {m['ip'] for m in config['miners']}
NODE_RPC    = config.get('node')  # None if no node configured


# ── Bitcoin Core RPC ─────────────────────────────────────────────────────────

def rpc_call(method, params=None):
    if not NODE_RPC:
        raise RuntimeError('No Bitcoin node configured')
    creds = base64.b64encode(f"{NODE_RPC['user']}:{NODE_RPC['password']}".encode()).decode()
    body  = json.dumps({'jsonrpc': '1.0', 'id': 'dashboard', 'method': method, 'params': params or []}).encode()
    req   = urllib.request.Request(
        NODE_RPC['url'],
        data=body,
        headers={'Authorization': f'Basic {creds}', 'Content-Type': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read())['result']


# ── CGMiner TCP client ────────────────────────────────────────────────────────

def cgminer_query(ip, command, parameter=None, port=4028, timeout=7):
    """Send a CGMiner RPC command via TCP and return the parsed JSON response."""
    payload = {'command': command}
    if parameter is not None:
        payload['parameter'] = parameter
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        sock.connect((ip, port))
        sock.sendall(json.dumps(payload).encode())
        chunks = []
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
    raw = b''.join(chunks).rstrip(b'\x00')
    return json.loads(raw)


# ── HTTP handler ──────────────────────────────────────────────────────────────

class Handler(http.server.SimpleHTTPRequestHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/proxy':
            self._proxy(parsed.query)
        elif parsed.path == '/avalon':
            self._avalon(parsed.query)
        elif parsed.path == '/node':
            self._node()
        elif parsed.path == '/config':
            self._serve_config()
        else:
            super().do_GET()

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/proxy':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            self._proxy_write('PATCH', parsed.query, body)
        else:
            self._error(404, 'Not found')

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        if parsed.path == '/proxy':
            self._proxy_write('POST', parsed.query, body)
        elif parsed.path == '/avalon-set':
            self._avalon_set(body)
        else:
            self._error(404, 'Not found')

    # ── /proxy?url=http://IP/path ─────────────────────────────────────────────

    def _proxy(self, query):
        params = urllib.parse.parse_qs(query)
        target = params.get('url', [None])[0]
        if not target:
            self._error(400, 'Missing url parameter')
            return
        host = urllib.parse.urlparse(target).hostname
        if host not in ALLOWED_IPS:
            self._error(403, f'IP {host} not in allowlist')
            return
        try:
            req = urllib.request.Request(target, headers={'User-Agent': 'MiningDashboard/1.0'})
            with urllib.request.urlopen(req, timeout=7) as resp:
                self._send(200, resp.read())
        except Exception as exc:
            self._error(502, str(exc))

    def _proxy_write(self, method, query, body):
        params = urllib.parse.parse_qs(query)
        target = params.get('url', [None])[0]
        if not target:
            self._error(400, 'Missing url parameter')
            return
        host = urllib.parse.urlparse(target).hostname
        if host not in ALLOWED_IPS:
            self._error(403, f'IP {host} not in allowlist')
            return
        try:
            req = urllib.request.Request(
                target,
                data=body,
                method=method,
                headers={
                    'User-Agent': 'MiningDashboard/1.0',
                    'Content-Type': 'application/json',
                },
            )
            with urllib.request.urlopen(req, timeout=7) as resp:
                self._send(200, resp.read())
        except Exception as exc:
            self._error(502, str(exc))

    # ── /config ───────────────────────────────────────────────────────────────

    def _serve_config(self):
        data = {'miners': config['miners'], 'hasNode': bool(NODE_RPC)}
        self._send(200, json.dumps(data).encode())

    # ── /node ─────────────────────────────────────────────────────────────────

    def _node(self):
        try:
            mining = rpc_call('getmininginfo')
            chain  = rpc_call('getblockchaininfo')
            result = {
                'blocks':       mining.get('blocks'),
                'difficulty':   mining.get('difficulty'),
                'networkhashps': mining.get('networkhashps'),
                'synced':       chain.get('verificationprogress', 0) > 0.9999,
                'headers':      chain.get('headers'),
            }
            self._send(200, json.dumps(result).encode())
        except Exception as exc:
            self._error(502, str(exc))

    # ── /avalon-set  POST {"ip":..., "parameter":...} ────────────────────────

    def _avalon_set(self, body):
        try:
            data = json.loads(body)
        except Exception:
            self._error(400, 'Invalid JSON')
            return
        ip        = data.get('ip')
        parameter = data.get('parameter')
        if not ip or ip not in ALLOWED_IPS:
            self._error(403, f'IP {ip!r} not in allowlist')
            return
        if not parameter:
            self._error(400, 'Missing parameter')
            return
        try:
            result = cgminer_query(ip, 'ascset', parameter)
            self._send(200, json.dumps(result).encode())
        except Exception as exc:
            self._error(502, str(exc))

    # ── /avalon?ip=IP ─────────────────────────────────────────────────────────

    def _avalon(self, query):
        params = urllib.parse.parse_qs(query)
        ip = params.get('ip', [None])[0]
        if not ip:
            self._error(400, 'Missing ip parameter')
            return
        if ip not in ALLOWED_IPS:
            self._error(403, f'IP {ip} not in allowlist')
            return

        result = {}
        for cmd in ('summary', 'litestats', 'estats', 'pools'):
            try:
                result[cmd] = cgminer_query(ip, cmd)
            except Exception as exc:
                result[cmd] = {'error': str(exc)}

        self._send(200, json.dumps(result).encode())

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send(self, code, body):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _error(self, code, msg):
        self._send(code, json.dumps({'error': msg}).encode())

    def log_message(self, fmt, *args):
        if args and isinstance(args[0], str) and ('/proxy?' in args[0] or '/avalon?' in args[0]):
            print(f'  {args[0]}  {args[1]}')


if __name__ == '__main__':
    print(f'Mining Dashboard  →  http://localhost:{PORT}/mining-dashboard.html')
    print('Press Ctrl+C to stop.\n')
    with http.server.HTTPServer(('', PORT), Handler) as httpd:
        httpd.serve_forever()
