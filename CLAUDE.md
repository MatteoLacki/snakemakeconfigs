# CLAUDE.md

## Project Overview

**snakemakeconfigs** is a Python CLI tool for applying patches to TOML configuration files with grid search support. It generates multiple config variants from parameter combinations (Cartesian product).

## Key Files

- `src/snakemakeconfigs/cli/configpatch.py` - All core logic (~237 lines)
- `pyproject.toml` - Package config, entry point: `configpatch`
- `examples/` - Base config, patch file, and generated outputs

## Architecture

Single-module design with these key functions:
- `apply_patch(base_doc, patch_doc)` - Applies patches, identifies grid parameters
- `generate_configs(base_path, patch_path, output_dir, short_names)` - Main orchestrator
- `make_config_name(params, base_stem, base_values, short_names)` - Generates filenames with encoded params
- `main()` - CLI entry point via argparse

## Dependencies

- **Runtime:** `tomlkit` only (preserves TOML formatting/comments)
- **Python:** 3.10+ (uses `match` statements)

## Commands

```bash
# Install locally for development
pip install -e .

# Run the tool
configpatch <base.toml> <patch.toml> -o <output_dir> [--short-names]

# Test with examples
configpatch examples/config.toml examples/patch.toml -o examples/test/

# Upload to PyPI
make upload_pypi
make upload_test_pypi
```

## Grid Search Detection

Use the `:grid` suffix on any key to make it a grid parameter:
```toml
learning_rate:grid = [0.001, 0.01, 0.1]
layers:grid = [[128, 64], [256, 128]]
```
The `:grid` suffix is stripped in output (becomes `learning_rate`, `layers`).

Multiple grid params produce Cartesian product of all combinations.

## Filename Encoding

Output files encode all grid params: `{base_stem}__{param=value__...}.toml`
- Floats: `.` → `p`, `-` → `neg` (e.g., `-0.001` → `neg0p001`)
- Lists: `[1, 2, 3]` → `1-2-3`
- Booleans: `true` / `false`
- Strings: diff against base value when possible
- Long names (>250 bytes) truncated with MD5 hash suffix
- Use `--short-names` to use only last key component

## Code Patterns

- Uses `tomlkit` (not `tomllib`) to preserve formatting
- `itertools.product` for grid expansion
- Pattern matching (`match/case`) for type dispatch in `apply_patch`
- Recursive descent for nested TOML structures via `merge()` inner function
