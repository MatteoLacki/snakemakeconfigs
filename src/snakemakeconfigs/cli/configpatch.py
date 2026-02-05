import argparse
import hashlib
import tomlkit

from itertools import product
from pathlib import Path
from tomlkit.items import String


def expand_dotted_tables(doc):
    """
    Convert dotted tables like [a.b.c] into nested tables
    so merge() can recurse properly.
    """
    for raw_key in list(doc.keys()):
        key = str(raw_key)
        if "." not in key:
            continue

        value = doc[raw_key]
        del doc[raw_key]

        parts = key.split(".")
        current = doc
        for part in parts[:-1]:
            if part not in current:
                current[part] = tomlkit.table()
            current = current[part]

        current[parts[-1]] = value


def apply_patch(base_doc, patch_doc):
    grid_params = {}

    def merge(target, updates, path=""):
        for raw_key, value in updates.items():
            key = str(raw_key)
            current_path = f"{path}.{key}" if path else key

            if key.endswith(":grid"):
                actual_key = key[:-5]
                actual_path = f"{path}.{actual_key}" if path else actual_key
                grid_params[actual_path] = value
                target[actual_key] = value[0]
                continue

            match value:
                case dict():
                    if raw_key not in target:
                        target[raw_key] = tomlkit.table()
                    merge(target[raw_key], value, current_path)

                case [first, *_] if isinstance(first, list):
                    grid_params[current_path] = value
                    target[raw_key] = value[0]

                case list():
                    target[raw_key] = value

                case _:
                    target[raw_key] = value

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


def sanitize_for_filename(s):
    s = str(s)
    replacements = {
        "[": "",
        "]": "",
        " ": "",
        ",": "-",
        ".": "p",
        "/": "_",
        "\\": "_",
        ":": "_",
        "*": "star",
        "?": "",
        '"': "",
        "<": "",
        ">": "",
        "|": "_",
    }
    for old, new in replacements.items():
        s = s.replace(old, new)
    return s


def value_to_string(value):
    if isinstance(value, list):
        return sanitize_for_filename(str(value))
    elif isinstance(value, float):
        return str(value).replace(".", "p").replace("-", "neg")
    elif isinstance(value, bool):
        return "true" if value else "false"
    else:
        return sanitize_for_filename(str(value))


def truncate_to_bytes(s, max_bytes):
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def make_config_name(params_dict, index):
    parts = []
    for key, value in params_dict.items():
        key_str = key.replace(".", "_")
        val_str = value_to_string(value)
        parts.append(f"{key_str}={val_str}")

    param_str = "__".join(parts)
    base_name = f"config_{index:03d}__{param_str}"

    max_length = 250
    if len(base_name.encode("utf-8")) > max_length:
        param_hash = hashlib.md5(param_str.encode()).hexdigest()[:8]
        truncated = truncate_to_bytes(base_name, max_length - 9)
        base_name = f"{truncated}_{param_hash}"

    return f"{base_name}.toml"


def generate_configs(base_path, patch_path, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    with open(base_path, "r") as f:
        base_doc = tomlkit.parse(f.read())

    with open(patch_path, "r") as f:
        patch_doc = tomlkit.parse(f.read())

    # 🔑 critical fix
    expand_dotted_tables(patch_doc)

    result_doc, grid_params = apply_patch(base_doc, patch_doc)

    if not grid_params:
        with open(output_dir / "config.toml", "w") as f:
            f.write(tomlkit.dumps(result_doc))
    else:
        param_names = list(grid_params.keys())
        param_values = [grid_params[name] for name in param_names]

        for i, combination in enumerate(product(*param_values)):
            variant = tomlkit.parse(tomlkit.dumps(result_doc))
            params = dict(zip(param_names, combination))

            for param_name, value in params.items():
                set_nested_value(variant, param_name, value)

            filename = make_config_name(params, i)
            with open(output_dir / filename, "w") as f:
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
