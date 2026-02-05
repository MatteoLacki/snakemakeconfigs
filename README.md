# snakemakeconfigs

Apply patches to TOML configs with grid search support. Generate multiple configuration variants from parameter combinations.

## Installation

```bash
pip install git+https://github.com/MatteoLacki/snakemakeconfigs.git
```

## Usage

```bash
configpatch <base.toml> <patch.toml> -o <output_dir> [--short-names]
```

## Example

**base.toml:**
```toml
[model]
layers = [128, 64, 32]
learning_rate = 0.01
```

**patch.toml:**
```toml
[model]
# Grid parameters use :grid suffix
learning_rate:grid = [0.001, 0.01, 0.1]
layers:grid = [
    [128, 64, 32],
    [256, 128, 64],
]

# Single override (applied to all configs)
dropout = 0.3
```

**Run:**
```bash
configpatch base.toml patch.toml -o output/
```

**Output:** 6 configs (3 learning rates x 2 layer configs):
```
output/
├── config__model_layers=128-64-32__model_learning_rate=0p001.toml
├── config__model_layers=128-64-32__model_learning_rate=0p01.toml
├── config__model_layers=128-64-32__model_learning_rate=0p1.toml
├── config__model_layers=256-128-64__model_learning_rate=0p001.toml
├── config__model_layers=256-128-64__model_learning_rate=0p01.toml
└── config__model_layers=256-128-64__model_learning_rate=0p1.toml
```

Each generated config has the grid values applied:
```toml
[model]
layers = [128, 64, 32]
learning_rate = 0.001
dropout = 0.3
```

## Grid Search Detection

Use the `:grid` suffix to specify grid parameters:
```toml
param:grid = [val1, val2, val3]
layers:grid = [[128, 64], [256, 128]]
```

The `:grid` suffix is stripped in output files. Multiple grid params produce a Cartesian product of all combinations.

## Filename Encoding

Parameters are encoded in filenames:
- Floats: `.` → `p`, `-` → `neg`
- Lists: `[1, 2, 3]` → `1-2-3`
- Use `--short-names` for shorter filenames (last key component only)

## Requirements

- Python 3.10+
- `tomlkit`

## License

MIT
