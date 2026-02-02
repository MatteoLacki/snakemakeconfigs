# toml_patcher.py
import argparse
import tomlkit

from itertools import product
from pathlib import Path


def apply_patch(base_doc, patch_doc):
    """
    Apply patch to base, preserving order and formatting.
    Convention: keys ending in '_grid' are grid search parameters.
    Returns: (modified_doc, grid_params_dict)
    """
    grid_params = {}

    def merge(target, updates, path=""):
        """Recursively merge updates into target"""
        for key, value in updates.items():
            current_path = f"{path}.{key}" if path else key

            # Check for grid search marker
            if key.endswith("_grid"):
                # Grid search parameter
                actual_key = key[:-5]  # Remove '_grid' suffix
                grid_params[f"{path}.{actual_key}" if path else actual_key] = value
                target[actual_key] = value[0]  # Use first value as default
                continue

            match value:
                case dict():
                    # Nested table
                    if key not in target:
                        target[key] = tomlkit.table()
                    merge(target[key], value, current_path)

                case [first, *_] if isinstance(first, list):
                    # List of lists - treat as grid search
                    grid_params[current_path] = value
                    target[key] = value[0]

                case list():
                    # Simple list - single value
                    target[key] = value

                case _:
                    # Single value - just update
                    target[key] = value

    # Create a working copy
    result = tomlkit.parse(tomlkit.dumps(base_doc))
    merge(result, patch_doc)

    return result, grid_params


def set_nested_value(doc, path, value):
    """Set value at path in tomlkit document"""
    parts = path.split(".")
    current = doc

    for part in parts[:-1]:
        current = current[part]

    current[parts[-1]] = value


def generate_configs(base_path, patch_path, output_dir, prefix="config", dry_run=False):
    """Generate all config combinations"""
    output_dir = Path(output_dir)

    if not dry_run:
        output_dir.mkdir(exist_ok=True, parents=True)

    # Load with tomlkit to preserve formatting
    with open(base_path, "r") as f:
        base_doc = tomlkit.parse(f.read())

    with open(patch_path, "r") as f:
        patch_doc = tomlkit.parse(f.read())

    # Apply patch and extract grid parameters
    result_doc, grid_params = apply_patch(base_doc, patch_doc)

    match grid_params:
        case {}:
            # No grid search - single output
            filename = f"{prefix}.toml"
            if not dry_run:
                with open(output_dir / filename, "w") as f:
                    f.write(tomlkit.dumps(result_doc))
            print(f"Generated 1 config: {filename}")
            return

        case _:
            # Grid search - multiple outputs
            param_names = list(grid_params.keys())
            param_values = [grid_params[name] for name in param_names]

            print(f"Grid search parameters:")
            for name, values in grid_params.items():
                print(f"  {name}: {len(values)} values")
            print()

            configs_generated = []
            for i, combination in enumerate(product(*param_values)):
                # Start with base result
                variant = tomlkit.parse(tomlkit.dumps(result_doc))

                # Apply this combination
                for param_name, value in zip(param_names, combination):
                    set_nested_value(variant, param_name, value)

                # Write output
                filename = f"{prefix}_{i:03d}.toml"
                if not dry_run:
                    with open(output_dir / filename, "w") as f:
                        f.write(tomlkit.dumps(variant))

                configs_generated.append(
                    (filename, dict(zip(param_names, combination)))
                )

            # Print summary
            print(f"Generated {len(configs_generated)} configs:")
            match len(configs_generated):
                case n if n <= 10 or dry_run:
                    # Show all if <= 10, or if dry run
                    for filename, params in configs_generated:
                        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
                        print(f"  {filename}: {params_str}")

                case _:
                    # Show first 5 and last 5
                    for filename, params in configs_generated[:5]:
                        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
                        print(f"  {filename}: {params_str}")
                    print(f"  ... ({len(configs_generated) - 10} more) ...")
                    for filename, params in configs_generated[-5:]:
                        params_str = ", ".join(f"{k}={v}" for k, v in params.items())
                        print(f"  {filename}: {params_str}")


def main():
    parser = argparse.ArgumentParser(
        description="Apply TOML patches with grid search support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate configs from base and patch
  %(prog)s base.toml patch.toml -o output/
  
  # Dry run to see what would be generated
  %(prog)s base.toml patch.toml -o output/ --dry-run
  
  # Custom prefix for output files
  %(prog)s base.toml patch.toml -o output/ --prefix experiment
  
Grid Search Convention:
  Use '_grid' suffix in patch.toml for parameters to search over:
  
    [model]
    learning_rate_grid = [0.001, 0.01, 0.1]  # Grid search
    dropout = 0.3                             # Single value
        """,
    )

    parser.add_argument("base", type=Path, help="Base TOML configuration file")

    parser.add_argument(
        "patch", type=Path, help="Patch TOML file with overrides and grid parameters"
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output directory for generated configs",
    )

    parser.add_argument(
        "--prefix",
        type=str,
        default="config",
        help="Prefix for output filenames (default: config)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be generated without writing files",
    )

    args = parser.parse_args()

    # Validate inputs
    match (args.base.exists(), args.patch.exists()):
        case (False, _):
            parser.error(f"Base file not found: {args.base}")
        case (_, False):
            parser.error(f"Patch file not found: {args.patch}")
        case (True, True):
            # All good, proceed
            generate_configs(
                args.base,
                args.patch,
                args.output,
                prefix=args.prefix,
                dry_run=args.dry_run,
            )


if __name__ == "__main__":
    main()
