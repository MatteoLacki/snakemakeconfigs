# snakemakeconfigs

A compact tool for applying patches to TOML configuration files with built-in support for grid search parameter exploration.

## Features

- **Structure-preserving patches** - Maintains original TOML formatting, comments, and key ordering using `tomlkit`
- **Grid search support** - Generate multiple configurations from parameter combinations
- **Explicit tracking** - Config filenames encode all parameter values for easy identification
- **Simple syntax** - Patches are just TOML files that mirror the target structure
- **Minimal dependencies** - Only `tomlkit` (pure Python)

## Installation

```bash
python -m pip install git+https://github.com/MatteoLacki/snakemakeconfigs.git
```

or 

```bash
python -m pip install git+ssh://git@github.com:MatteoLacki/snakemakeconfigs.git
```

Then place `toml_patcher.py` in your project or PATH.

## Quick Start

### Basic Usage

**base.toml:**
```toml
[model]
layers = [128, 64, 32]
learning_rate = 0.01
```

**patch.toml:**
```toml
[model]
dropout = 0.3
learning_rate = 0.001
```

**Apply patch:**
```bash
python toml_patcher.py base.toml patch.toml -o output/
```

**Result:** `output/config.toml` with `dropout` added and `learning_rate` updated.

### Grid Search

Use the `_grid` suffix to specify multiple values for a parameter:

**patch.toml:**
```toml
[model]
learning_rate_grid = [0.001, 0.01, 0.1]
optimizer_grid = ["adam", "sgd"]
dropout = 0.3
```

**Apply patch:**
```bash
python toml_patcher.py base.toml patch.toml -o experiments/
```

**Result:** 6 configuration files (3 learning rates × 2 optimizers):
```
experiments/
├── config_000__model_learning_rate=0p001__model_optimizer=adam.toml
├── config_001__model_learning_rate=0p001__model_optimizer=sgd.toml
├── config_002__model_learning_rate=0p01__model_optimizer=adam.toml
├── config_003__model_learning_rate=0p01__model_optimizer=sgd.toml
├── config_004__model_learning_rate=0p1__model_optimizer=adam.toml
└── config_005__model_learning_rate=0p1__model_optimizer=sgd.toml
```

## Usage

```bash
python toml_patcher.py <base.toml> <patch.toml> -o <output_dir>
```

**Arguments:**
- `base` - Base TOML configuration file
- `patch` - Patch TOML file with overrides and grid parameters
- `-o, --output` - Output directory for generated configs (required)

## Grid Search Convention

Any key ending in `_grid` is treated as a grid search parameter:

```toml
# Single value - applied to all configs
[section]
param = "value"

# Grid search - generates multiple configs
[section]
param_grid = ["value1", "value2", "value3"]

# Works with nested values too
[section]
layers_grid = [
    [128, 64, 32],
    [256, 128, 64],
    [512, 256, 128]
]
```

The `_grid` suffix is removed in the final configs - `learning_rate_grid` becomes `learning_rate`.

## Filename Encoding

Generated config filenames explicitly encode all grid parameters:

- **Index:** `config_000`, `config_001`, etc. for ordering
- **Parameters:** Full parameter paths and values
- **Separators:** `__` between parameters, `=` between key and value
- **Value formatting:**
  - Floats: `.` → `p` (e.g., `0.001` → `0p001`)
  - Lists: `[1, 2, 3]` → `1-2-3`
  - Negatives: `-` → `neg`

**Length protection:** Filenames are automatically truncated at 250 bytes (Linux limit is 255). Truncated names include an 8-character hash suffix for uniqueness.

## Examples

### Machine Learning Hyperparameter Search

**base.toml:**
```toml
[model]
name = "classifier"
layers = [64, 32]

[training]
batch_size = 32
epochs = 100
```

**patch.toml:**
```toml
[model]
layers_grid = [
    [128, 64, 32],
    [256, 128, 64]
]

[training]
batch_size_grid = [16, 32, 64]
learning_rate_grid = [0.001, 0.01]
```

Generates 12 configs (2 layer configs × 3 batch sizes × 2 learning rates).

### Nested Configuration Updates

**patch.toml:**
```toml
[database.connection]
host = "new-host.com"
timeout_grid = [30, 60, 120]

[database.pool]
max_size = 100
```

Works with deeply nested structures - just mirror the structure in your patch file.

## Design Philosophy

This tool follows these principles:

1. **TOML mirrors TOML** - Patch files use the same structure as target files
2. **Preserve formatting** - Comments and ordering maintained via `tomlkit`
3. **Explicit is better** - Filenames show exactly what changed
4. **Single responsibility** - apply patches with grid search

## Technical Details

- **Python 3.10+** required (uses `match` statements)
- **Dependencies:** `tomlkit` only
- **File size:** ~150 lines of code
- **Format preservation:** Uses `tomlkit` for lossless TOML round-trips
- **Grid expansion:** Uses `itertools.product` for Cartesian product of parameters

## Limitations

- Requires Python 3.10+ for pattern matching
- Very long filenames (>250 bytes) are truncated with hash suffix
- Grid parameters must be specified with `_grid` suffix (convention over configuration)
- No deletion support - patches can only add or modify, not remove keys

## License
MIT, see LICENSE.
