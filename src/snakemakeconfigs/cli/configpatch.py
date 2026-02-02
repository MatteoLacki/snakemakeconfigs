# toml_patcher.py
import argparse
import tomlkit

from itertools import product
from pathlib import Path


def apply_patch(base_doc, patch_doc):
    grid_params = {}

    def merge(target, updates, path=""):
        for key, value in updates.items():
            current_path = f"{path}.{key}" if path else key

            if key.endswith("_grid"):
                actual_key = key[:-5]
                actual_path = f"{path}.{actual_key}" if path else actual_key
                grid_params[actual_path] = value
                target[actual_key] = value[0]
                continue

            match value:
                case dict():
                    if key not in target:
                        target[key] = tomlkit.table()
                    merge(target[key], value, current_path)
                case [first, *_] if isinstance(first, list):
                    grid_params[current_path] = value
                    target[key] = value[0]
                case list():
                    target[key] = value
                case _:
                    target[key] = value

    result = tomlkit.parse(tomlkit.dumps(base_doc))
    merge(result, patch_doc)
    return result, grid_params


def set_nested_value(doc, path, value):
    parts = path.split(".")
    current = doc
    for part in parts[:-1]:
        if part not in current:
            current[part] = tomlkit.table()
        current = current[part]
    current[parts[-1]] = value


def generate_configs(base_path, patch_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    with open(base_path, "r") as f:
        base_doc = tomlkit.parse(f.read())

    with open(patch_path, "r") as f:
        patch_doc = tomlkit.parse(f.read())

    result_doc, grid_params = apply_patch(base_doc, patch_doc)

    if not grid_params:
        with open(output_dir / "config.toml", "w") as f:
            f.write(tomlkit.dumps(result_doc))
    else:
        param_names = list(grid_params.keys())
        param_values = [grid_params[name] for name in param_names]

        for i, combination in enumerate(product(*param_values)):
            variant = tomlkit.parse(tomlkit.dumps(result_doc))

            for param_name, value in zip(param_names, combination):
                set_nested_value(variant, param_name, value)

            with open(output_dir / f"config_{i:03d}.toml", "w") as f:
                f.write(tomlkit.dumps(variant))


def main():
    parser = argparse.ArgumentParser(
        description="Apply TOML patches with grid search support"
    )
    parser.add_argument("base", type=Path, help="Base TOML file")
    parser.add_argument("patch", type=Path, help="Patch TOML file")
    parser.add_argument(
        "-o", "--output", type=Path, required=True, help="Output directory"
    )
    args = parser.parse_args()

    if not args.base.exists():
        parser.error(f"Base file not found: {args.base}")
    if not args.patch.exists():
        parser.error(f"Patch file not found: {args.patch}")

    generate_configs(args.base, args.patch, args.output)


if __name__ == "__main__":
    main()
