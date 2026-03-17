# toml_patcher.py
import argparse
import difflib
import hashlib
import os
import re

from itertools import product
from pathlib import Path

import copy

import tomlkit
from tomlkit.items import AoT


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

                    if isinstance(value, AoT):
                        all_variants = []
                        for elem in value:
                            all_variants.extend(_expand_aot_element(elem, grid_suffixes))
                        grid_params[actual_path] = all_variants
                        target[actual_key] = all_variants[0]
                    elif isinstance(value, list):
                        grid_params[actual_path] = value
                        target[actual_key] = value[0]
                    else:
                        raise TypeError(f"{actual_path}{suffix} must be a list or array of tables")
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


def _aot_elem_to_plain_table(elem):
    """Recursively convert an AoT element Table to a plain tomlkit table.

    deepcopy alone preserves is_aot_element=True, which causes the table to
    serialize as [[key]] instead of [key] when placed back in a document.
    This function builds a fresh tomlkit.table() free of that flag.
    """
    t = tomlkit.table()
    for k, v in elem.items():
        t[k] = _aot_elem_to_plain_table(v) if isinstance(v, dict) else copy.deepcopy(v)
    return t


def _expand_aot_element(elem_table, grid_suffixes):
    """Expand __grid params within a single AoT element.
    Returns a list of tomlkit Table objects (one per combo)."""
    local_grids = {}

    def walk_elem(tbl, path=""):
        for key in list(tbl.keys()):
            value = tbl[key]
            for suffix in grid_suffixes:
                if key.endswith(suffix):
                    actual_key = key[: -len(suffix)]
                    actual_path = f"{path}.{actual_key}" if path else actual_key
                    if not isinstance(value, list):
                        raise TypeError(f"{actual_path}{suffix} must be a list")
                    local_grids[actual_path] = value
                    tbl[actual_key] = value[0]
                    del tbl[key]
                    break
            else:
                if isinstance(value, dict):
                    walk_elem(value, f"{path}.{key}" if path else key)

    base = _aot_elem_to_plain_table(elem_table)

    explicit_label = None
    if "__label" in base:
        explicit_label = str(base["__label"])
        del base["__label"]

    walk_elem(base)

    if not local_grids:
        results = [base]
    else:
        names = list(local_grids)
        values = [local_grids[n] for n in names]
        results = []
        for combo in product(*values):
            variant = _aot_elem_to_plain_table(base)
            for k, v in zip(names, combo):
                set_nested_value(variant, k, v)
            results.append(variant)

    if explicit_label is not None:
        for variant in results:
            variant["__label"] = explicit_label
    return results


def extract_grids_from_doc(doc, grid_suffixes):
    grid_params = {}

    def walk(table, path=""):
        for key in list(table.keys()):
            value = table[key]

            for suffix in grid_suffixes:
                if key.endswith(suffix):
                    actual_key = key[: -len(suffix)]
                    actual_path = f"{path}.{actual_key}" if path else actual_key

                    if isinstance(value, AoT):
                        all_variants = []
                        for elem in value:
                            all_variants.extend(_expand_aot_element(elem, grid_suffixes))
                        grid_params[actual_path] = all_variants
                        table[actual_key] = all_variants[0]
                        del table[key]
                    elif isinstance(value, list):
                        grid_params[actual_path] = value
                        table[actual_key] = value[0]
                        del table[key]
                    else:
                        raise TypeError(f"{actual_path}{suffix} must be a list or array of tables")
                    break
            else:
                if isinstance(value, dict):
                    next_path = f"{path}.{key}" if path else key
                    walk(value, next_path)
                # plain AoT without suffix: not a grid dimension, leave as-is

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


def _strip_common_affixes(labels):
    """Strip character-level common prefix and suffix from a list of label strings.

    Falls back gracefully: if stripping would fully consume any label, tries
    prefix-only, then suffix-only, then returns labels unchanged.
    Dangling leading/trailing underscores are removed from the result.
    """
    prefix = os.path.commonprefix(labels)
    suffix = os.path.commonprefix([s[::-1] for s in labels])[::-1]
    p, s = len(prefix), len(suffix)
    if p + s == 0:
        return labels
    if any(p + s >= len(lab) for lab in labels):
        s = 0  # drop suffix, try prefix only
        if any(p >= len(lab) for lab in labels):
            return labels
    stripped = [lab[p : len(lab) - s if s else None].strip("_") or lab for lab in labels]
    return stripped


def _find_auto_label(vals):
    """Return {id(v): label_str} if all dict variants share a top-level string
    key with distinct values; otherwise None."""
    common_keys = set(vals[0].keys())
    for v in vals[1:]:
        common_keys &= set(v.keys())
    for key in sorted(common_keys):  # deterministic order
        values = [v[key] for v in vals]
        if all(isinstance(val, str) for val in values) and len(set(values)) == len(vals):
            return {id(v): sanitize_for_filename(v[key]) for v in vals}
    return None


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


def make_config_name(params, base_stem, base_values, short_names=False, equal_sign="=", grid_indices=None, value_only_keys=None):
    parts = []

    for key, value in params.items():
        name = shorten_param_name(key) if short_names else key.replace(".", "_")
        if grid_indices and key in grid_indices:
            val_str = str(grid_indices[key][id(value)])
        else:
            base_value = base_values.get(key)
            val_str = value_to_string(value, base_value)
        if value_only_keys and key in value_only_keys:
            parts.append(val_str)
        else:
            parts.append(f"{name}{equal_sign}{val_str}")

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


def _build_grid_indices(grid_params):
    result = {}
    for name, vals in grid_params.items():
        if not (vals and isinstance(vals[0], dict)):
            continue
        # Explicit __label takes priority
        if any("__label" in v for v in vals):
            result[name] = {id(v): sanitize_for_filename(str(v["__label"]))
                            for v in vals if "__label" in v}
            # fill any missing (shouldn't happen if user is consistent)
            for i, v in enumerate(vals):
                if id(v) not in result[name]:
                    result[name][id(v)] = str(i)
        else:
            auto = _find_auto_label(vals)
            result[name] = auto if auto is not None else {id(v): str(i) for i, v in enumerate(vals)}
    return result


def _compute_value_only_keys(grid_params, grid_indices, base_scalar_values, short_names):
    """Return set of param names whose key prefix can be omitted in filenames.

    Eligible when short_names=True and the dim uses human-readable string labels
    (not bare numeric indices) that are unambiguous across all other eligible dims.
    Covers both AoT dims (labels from grid_indices) and scalar string dims.
    """
    if not short_names:
        return set()

    # Collect candidate label-sets per dim
    candidate_label_sets = {}
    for name, vals in grid_params.items():
        if name in grid_indices:
            labels = set(grid_indices[name].values())
            # Only treat as string-labeled if not purely numeric indices
            if not all(s.isdigit() for s in labels):
                candidate_label_sets[name] = labels
        elif vals and all(isinstance(v, str) for v in vals):
            base_val = base_scalar_values.get(name)
            candidate_label_sets[name] = {value_to_string(v, base_val) for v in vals}

    # A dim is value-only if its labels don't overlap with any other candidate's labels
    value_only = set()
    for name, label_set in candidate_label_sets.items():
        other_values = set()
        for other_name, other_set in candidate_label_sets.items():
            if other_name != name:
                other_values |= other_set
        if not (label_set & other_values):
            value_only.add(name)
    return value_only


def expand_configs(base_doc, grid_params, output_dir, base_stem, **kwargs):
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

    grid_indices = _build_grid_indices(grid_params)

    short_names = kwargs.get("short_names", False)
    value_only_keys = _compute_value_only_keys(
        grid_params, grid_indices, base_scalar_values, short_names
    )

    # Strip __label from all AoT variants so it doesn't appear in output TOML
    for vals in grid_params.values():
        for v in vals:
            if isinstance(v, dict) and "__label" in v:
                del v["__label"]

    param_names = list(grid_params)
    param_values = [grid_params[n] for n in param_names]

    for combo in product(*param_values):
        variant = tomlkit.parse(tomlkit.dumps(base_doc))
        params = dict(zip(param_names, combo))

        for k, v in params.items():
            set_nested_value(variant, k, v)

        filename = make_config_name(
            params, base_stem, base_scalar_values,
            grid_indices=grid_indices, value_only_keys=value_only_keys, **kwargs
        )

        (output_dir / filename).write_text(tomlkit.dumps(variant))
        written_files.append(filename)

    return written_files


# -----------------------------
# CLI entry points
# -----------------------------


def _print_filenames(names):
    print("{" + ",".join((n.replace(".toml", "") for n in names)) + "}")


def configpatch_cli():
    parser = argparse.ArgumentParser(
        description="Apply TOML patches with grid-search support",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("base", type=Path)
    parser.add_argument("patch", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--long-names", action="store_true")
    parser.add_argument(
        "--grid-tag",
        action="append",
        default=["__grid"],
        help="Grid suffix/suffixes (e.g. `--grid-tag __grid --grid-tag __span`).",
    )
    parser.add_argument(
        "--equal-sign",
        default="+",
        help="Equal sign used in names of configs.",
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
        short_names=not args.long_names,
        equal_sign=args.equal_sign,
    )

    _print_filenames(names)


def expandgrids_cli():
    parser = argparse.ArgumentParser(
        description="Expand grid parameters in a single TOML config",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("base", type=Path)
    parser.add_argument("-o", "--output", type=Path, required=True)
    parser.add_argument("--long-names", action="store_true")
    parser.add_argument(
        "--grid-tag",
        action="append",
        default=["__grid"],
        help="Grid suffix/suffixes (e.g. `--grid-tag __grid --grid-tag __span`).",
    )
    parser.add_argument(
        "--equal-sign",
        default="+",
        help="Equal sign used in names of configs.",
    )
    args = parser.parse_args()

    base_doc = tomlkit.parse(args.base.read_text())

    result_doc, grid_params = extract_grids_from_doc(base_doc, tuple(args.grid_tag))

    names = expand_configs(
        result_doc,
        grid_params,
        args.output,
        args.base.stem,
        short_names=not args.long_names,
        equal_sign=args.equal_sign,
    )

    _print_filenames(names)
