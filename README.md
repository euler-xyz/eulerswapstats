# netnav.py

Calculate Net NAV for EulerSwap pools (matching website display values).

## Installation

```bash
pip install requests
```

## Usage

```bash
# Current NAV
python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1

# Pool lifetime return
python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1 --lifespan

# Historical return between blocks
python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1 \
  --from-block 23120299 --to-block 23132700

# JSON output
python netnav.py --pool 0xD585c8Baa6c0099d2cc59a5a089B8366Cb3ea8A8 --chain 1 --format json
```

## Example Output

```
Net NAV: $2,112,619.47

Positions:
  USDC: -3,864,058.79 @ $0.999816
  USDT: 5,976,060.73 @ $0.999984
```

## What is Net NAV?

Net NAV = Vault assets - Vault borrowed

This represents the actual economic position after accounting for leverage, matching what euler.finance displays as the position NAV.