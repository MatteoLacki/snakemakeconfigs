# toml_patcher.py
import argparse
import difflib
import hashlib
import re

from itertools import product
from pathlib import Path

import tomlkit


# -----------------------------
# Patch / grid extraction
# -----------------------------


def apply_patch(base_doc, patch_doc, grid_suffixes):
    grid_params = {}

    def merge(target, updates, path=""):
        for key, value in updates.items():
            for suffix in grid_suffixes:
                if key.endswith(suffix):
                    actual_key = key[: -len(suffix)]
                    actual_path = f"{path}.{actual_key}" if path else actual_key

                    if not isinstance(value, list):
                        raise TypeError(f"{actual_path}{suffix} must be a list")

                    grid_params[actual_path] = value
                    target[actual_key] = value[0]
                    break
            else:
                if isinstance(value, dict):
                    if key not in target:
                        target[key] = tomlkit.table()
                    next_path = f"{path}.{key}" if path else key
                    merge(target[key], value, next_path)
                else:
                    target[key] = value

    result = tomlkit.parse(tomlkit.dumps(base_doc))
    merge(result, patch_doc)
    return result, grid_params


def extract_grids_from_doc(doc, grid_suffixes):
    grid_params = {}

    def walk(table, path=""):
        for key in list(table.keys()):
            value = table[key]

            for suffix in grid_suffixes:
                if key.endswith(suffix):
                    actual_key = key[: -len(suffix)]
                    actual_path = f"{path}.{actual_key}" if path else actual_key

                    if not isinstance(value, list):
                        raise TypeError(f"{actual_path}{suffix} must be a list")

                    grid_params[actual_path] = value
                    table[actual_key] = value[0]
                    del table[key]
                    break
            else:
                if isinstance(value, dict):
                    next_path = f"{path}.{key}" if path else key
                    walk(value, next_path)

    result = tomlkit.parse(tomlkit.dumps(doc))
    walk(result)
    return result, grid_params


# -----------------------------
# Nested helpers
# -----------------------------


def set_nested_value(doc, path, value):
    parts = path.split(".")
    current = doc
    for part in parts[:-1]:
        if part not in current:
            current[part] = tomlkit.table()
        current = current[part]
    current[parts[-1]] = value


def get_nested_value(doc, path):
    current = doc
    for part in path.split("."):
        if part not in current:
            return None
        current = current[part]
    return current


# -----------------------------
# Filename helpers
# -----------------------------


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


def diff_strings(str_a, str_b):
    tokens_a = re.findall(r"\w+", str(str_a))
    tokens_b = re.findall(r"\w+", str(str_b))

    matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b)
    new_tokens = []

    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ("insert", "replace"):
            new_tokens.extend(tokens_b[j1:j2])

    return "_".join(new_tokens)


def value_to_string(value, base_value=None):
    if (
        base_value is not None
        and isinstance(value, str)
        and isinstance(base_value, str)
    ):
        diff = diff_strings(base_value, value)
        if diff:
            return sanitize_for_filename(diff)

    if isinstance(value, float):
        return str(value).replace(".", "p").replace("-", "neg")
    if isinstance(value, bool):
        return "true" if value else "false"

    return sanitize_for_filename(str(value))


def shorten_param_name(name):
    return name.split(".")[-1]


def truncate_to_bytes(s, max_bytes):
    encoded = s.encode("utf-8")
    if len(encoded) <= max_bytes:
        return s
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def make_config_name(params, base_stem, base_values, short_names=False):
    parts = []

    for key, value in params.items():
        name = shorten_param_name(key) if short_names else key.replace(".", "_")
        base_value = base_values.get(key)
        val_str = value_to_string(value, base_value)
        parts.append(f"{name}={val_str}")

    param_str = "__".join(parts)
    base_name = f"{base_stem}__{param_str}"

    if len(base_name.encode("utf-8")) > 250:
        h = hashlib.md5(param_str.encode()).hexdigest()[:8]
        truncated = truncate_to_bytes(base_name, 241)
        base_name = f"{truncated}_{h}"

    return f"{base_name}.toml"


# -----------------------------
# Expansion logic
# -----------------------------


def expand_configs(base_doc, grid_params, output_dir, base_stem, short_names=False):
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True, parents=True)

    written_files = []

    if not grid_params:
        name = f"{base_stem}.toml"
        (output_dir / name).write_text(tomlkit.dumps(base_doc))
        written_files.append(name)
        return written_files

    base_scalar_values = {
        name: get_nested_value(base_doc, name) for name in grid_params
    }

    param_names = list(grid_params)
    param_values = [grid_params[n] for n in param_names]

    for combo in product(*param_values):
        variant = tomlkit.parse(tomlkit.dumps(base_doc))
        params = dict(zip(param_names, combo))

        for k, v in params.items():
            set_nested_value(variant, k, v)

        filename = make_config_name(
            params,
            base_stem,
            base_scalar_values,
            short_names,
        )

        (output_dir / filename).write_text(tomlkit.dumps(variant))
        written_files.append(filename)

    return written_files


# -----------------------------
# CLI entry points
# -----------------------------


def _print_filenames(names):
    print("{" + ",".join(names) + "}")


def configpatch_cli():
    parser = argparse.ArgumentParser(
        description="Apply TOML patches with grid-search support"
    )
    parser.add_argument("base", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--short-names", action="store_true")
    parser.add_argument(
        "--grid-tag",
        action="append",
        default=["__grid"],
        help="Grid suffix (repeatable). Default: __grid",
    )

    args = parser.parse_args()

    base_doc = tomlkit.parse(args.base.read_text())
    patch_doc = tomlkit.parse(args.patch.read_text())

    result_doc, grid_params = apply_patch(base_doc, patch_doc, tuple(args.grid_tag))

    names = expand_configs(
        result_doc,
        grid_params,
        args.output,
        args.base.stem,
        args.short_names,
    )

    _print_filenames(names)


def expandgrids_cli():
    parser = argparse.ArgumentParser(
        description="Expand grid parameters in a single TOML config"
    )
    parser.add_argument("base", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--short-names", action="store_true")
    parser.add_argument(
        "--grid-tag",
        action="append",
        default=["__grid"],
        help="Grid suffix (repeatable). Default: __grid",
    )

    args = parser.parse_args()

    base_doc = tomlkit.parse(args.base.read_text())

    result_doc, grid_params = extract_grids_from_doc(base_doc, tuple(args.grid_tag))

    names = expand_configs(
        result_doc,
        grid_params,
        args.output,
        args.base.stem,
        args.short_names,
    )

    _print_filenames(names)
