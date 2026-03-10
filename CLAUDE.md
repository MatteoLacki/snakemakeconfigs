# CLAUDE.md

## Project Overview

**snakemakeconfigs** is a Python CLI tool for applying patches to TOML configuration files with grid search support. It generates multiple config variants from parameter combinations (Cartesian product).

## Key Files

- `src/snakemakeconfigs/toml_patcher.py` - All core logic (~314 lines)
- `pyproject.toml` - Package config, entry point: `configpatch`
- `examples/` - Base config, patch file, and generated outputs

## Architecture

Single-module design with these key functions:
- `apply_patch(base_doc, patch_doc, grid_suffixes)` - Applies patch, identifies grid parameters
- `extract_grids_from_doc(doc, grid_suffixes)` - Extracts grids from a single doc (for `expandgrids`)
- `expand_configs(base_doc, grid_params, output_dir, base_stem, **kwargs)` - Main expansion orchestrator
- `make_config_name(params, base_stem, base_values, short_names, equal_sign)` - Generates filenames
- `configpatch_cli()` - CLI entry point for `configpatch` (base + patch → outputs)
- `expandgrids_cli()` - CLI entry point for `expandgrids` (single config with grid tags → outputs)

## Dependencies

- **Runtime:** `tomlkit` only (preserves TOML formatting/comments)
- **Python:** 3.10+ (uses `match` statements)

## Commands

```bash
# Install locally for development
pip install -e .

# Apply patch with grid expansion
configpatch <base.toml> <patch.toml> -o <output_dir> [--long-names] [--grid-tag TAG] [--equal-sign CHAR]

# Expand grid parameters in a single config (no patch)
expandgrids <config.toml> -o <output_dir> [--long-names] [--grid-tag TAG] [--equal-sign CHAR]

# Test with examples
configpatch examples/config.toml examples/patch.toml -o examples/test/
expandgrids examples/config_with_grids.toml -o examples/test/

# Upload to PyPI
make upload_pypi
make upload_test_pypi
```

## Grid Search Detection

Use the `__grid` suffix (double underscore, default; configurable via `--grid-tag`) on any key to make it a grid parameter:
```toml
learning_rate__grid = [0.001, 0.01, 0.1]
layers__grid = [[128, 64], [256, 128]]
```
The `__grid` suffix is stripped in output (becomes `learning_rate`, `layers`).

Multiple grid params produce Cartesian product of all combinations.

Multiple `--grid-tag` values are supported: `--grid-tag __grid --grid-tag __span`

## Filename Encoding

Output files encode all grid params: `{base_stem}__{param+value__...}.toml`
- Default equal sign is `+` (configurable via `--equal-sign`)
- Floats: `.` → `p`, `-` → `neg` (e.g., `-0.001` → `neg0p001`)
- Lists: `[1, 2, 3]` → `1-2-3`
- Booleans: `true` / `false`
- Strings: diff against base value when possible
- Long names (>250 bytes) truncated with MD5 hash suffix
- Short names (last key component only) are the default; use `--long-names` for full dotted paths

## Code Patterns

- Uses `tomlkit` (not `tomllib`) to preserve formatting
- `itertools.product` for grid expansion
- Pattern matching (`match/case`) for type dispatch in `apply_patch`
- Recursive descent for nested TOML structures via `merge()` inner function
