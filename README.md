# netnav.py

Calculate Net NAV for EulerSwap pools (matching website display values).

## Installation

```bash
pip install requests
```

## Usage

### Current NAV
```bash
$ python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1

Net NAV: $2,112,619.47

Positions:
  USDC: -3,864,058.79 @ $0.999816
  USDT: 5,976,060.73 @ $0.999984
```

### Pool Lifetime Return
```bash
$ python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1 --lifespan

Lifespan: Block 23120299 → 23132801
Historical Return Analysis
========================================
Period: Block 23120299 → 23132801
Duration: 1.75 days

Start NAV: $2,111,464.39
End NAV:   $2,112,619.35

Return:    $1,154.96 (+0.05%)
Annualized: 12.11%
```

### Historical Return
```bash
$ python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1 \
  --from-block 23120299 --to-block 23132700

Historical Return Analysis
========================================
Period: Block 23120299 → 23132700
Duration: 1.73 days

Start NAV: $2,111,464.39
End NAV:   $2,112,617.51

Return:    $1,153.12 (+0.05%)
Annualized: 12.19%
```

## What is Net NAV?

Net NAV = Vault assets - Vault borrowed

This represents the actual economic position after accounting for leverage, matching what euler.finance displays as the position NAV.

---

# findpool.py

Find EulerSwap pools by token pair, including uninstalled pools.

## Usage

```bash
# Find all pools for a token pair
python findpool.py --token0 0x66a1e37c9b0eaddca17d3662d6c05f4decf3e110 --token1 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 --chain 1
```

Finds pools containing the specified tokens, shows active/inactive status and last activity.

---

# poolinfo.py

Get detailed deployment parameters and configuration for a pool.

## Usage

```bash
# Get pool information
python poolinfo.py --pool 0x29bE2d4b843DA604665C2c5C46D596890303E8a8 --chain 1
```

Shows deployment parameters, fees, concentration, vaults, reserves, volume, and APY.