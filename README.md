# Mining Dashboard

A local web dashboard for monitoring and controlling hobby Bitcoin miners.

Supports **Bitaxe** (AxeOS) and **Avalon Nano 3S** miners, with optional **Bitcoin Core node** integration for solo mining stats.

![dashboard preview](https://raw.githubusercontent.com/WhiteFireOne/mining-dashboard/main/preview.png)

## Features

- Live hashrate, temperature, fan speed, power draw and efficiency per miner
- Fan and OC tune controls for Bitaxe (BM1370)
- Work mode and fan controls for Avalon Nano 3S
- Bitcoin network stats via mempool.space (block value, fees, difficulty retarget)
- Solo mining odds panel if you run a Bitcoin Core node
- Auto-refresh every 30 seconds

## Requirements

- Python 3.7+
- Miners and your computer on the same local network

## Setup

**1. Clone the repo**

```bash
git clone https://github.com/WhiteFireOne/mining-dashboard.git
cd mining-dashboard
```

**2. Run the server — it will prompt you for your setup on first launch**

```bash
python3 server.py
```

You will be asked for:
- Each miner's IP address, name, and type (`bitaxe` or `avalon`)
- Whether you have a Bitcoin Core node (optional)
  - If yes: node IP:port, RPC username, and RPC password

Your answers are saved to `config.json` (excluded from git).

**3. Open the dashboard**

```
http://localhost:8080/mining-dashboard.html
```

## Reconfiguring

Delete `config.json` and restart `server.py` to run the setup wizard again, or edit `config.json` directly using `config.example.json` as a reference.

## Supported Miner Types

| Type | Protocol | Notes |
|------|----------|-------|
| `bitaxe` | HTTP (AxeOS API) | Bitaxe Gamma, Ultra, Supra, etc. |
| `avalon` | CGMiner TCP (port 4028) | Avalon Nano 3S and similar |

## Bitcoin Node (optional)

If you run Bitcoin Core with `server=1` and `rpcallowip` set for your local network, the dashboard shows:

- Current block height and network difficulty
- Network hashrate
- Solo mining probability (24h / 1 week / 1 month / 1 year)

Add to your `bitcoin.conf`:

```
server=1
rpcuser=bitcoin
rpcpassword=your-password
rpcallowip=192.168.1.0/24
```
