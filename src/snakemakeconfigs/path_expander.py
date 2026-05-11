import argparse
import importlib.util
import string
import sys

from pathlib import Path


DEFAULT_PATHS_FILE = Path("workflow/paths.py")
COLOR_RESET = "\033[0m"
COLOR_NAME = "\033[1;36m"
COLOR_LITERAL = "\033[0;37m"
COLOR_WILDCARD = "\033[1;33m"
COLOR_BRACE = "\033[1;34m"


def _load_module(module_path: Path):
    spec = importlib.util.spec_from_file_location(
        "snakemake_pipeline_paths", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not import module from {module_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_paths_namespace(paths_file: Path, paths_fn: str):
    module = _load_module(paths_file)
    try:
        factory = getattr(module, paths_fn)
    except AttributeError as exc:
        raise ValueError(f"{paths_fn!r} is not defined in {paths_file}") from exc
    return factory()


def namespace_to_templates(namespace):
    return {name: str(value) for name, value in vars(namespace).items()}


def colorize_template(template: str, use_color: bool) -> str:
    if not use_color:
        return template

    parts = []
    formatter = string.Formatter()
    for literal_text, field_name, format_spec, conversion in formatter.parse(template):
        if literal_text:
            parts.append(f"{COLOR_LITERAL}{literal_text}{COLOR_RESET}")
        if field_name is None:
            continue
        parts.append(f"{COLOR_BRACE}{{{COLOR_RESET}")
        parts.append(f"{COLOR_WILDCARD}{field_name}{COLOR_RESET}")
        suffix = ""
        if conversion:
            suffix += f"!{conversion}"
        if format_spec:
            suffix += f":{format_spec}"
        if suffix:
            parts.append(f"{COLOR_LITERAL}{suffix}{COLOR_RESET}")
        parts.append(f"{COLOR_BRACE}}}{COLOR_RESET}")
    return "".join(parts)


def format_assignment(name: str, value: str, use_color: bool) -> str:
    if not use_color:
        return f"{name}={value}"
    return f"{COLOR_NAME}{name}{COLOR_RESET}={colorize_template(value, use_color=True)}"


def extract_wildcards(template: str) -> list[str]:
    formatter = string.Formatter()
    wildcards = []
    seen = set()

    for _, field_name, _, _ in formatter.parse(template):
        if not field_name:
            continue
        if field_name not in seen:
            seen.add(field_name)
            wildcards.append(field_name)

    return wildcards


def collect_wildcard_values(wildcards, input_func=input):
    values = {}
    for wildcard in wildcards:
        values[wildcard] = input_func(f"{wildcard}: ")
    return values


def resolve_entries(entries, templates, wildcard_values):
    resolved = []
    for entry in entries:
        if entry not in templates:
            raise KeyError(entry)
        resolved.append((entry, templates[entry].format(**wildcard_values)))
    return resolved


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Fill wildcarded path templates from workflow/paths.py by prompting "
            "for each required wildcard value."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "entries",
        nargs="*",
        help="One or more attribute names from the selected paths namespace.",
    )
    parser.add_argument(
        "--paths-file",
        type=Path,
        default=DEFAULT_PATHS_FILE,
        help="Python file containing the paths namespace factory.",
    )
    parser.add_argument(
        "--paths-fn",
        default="get_paths",
        help="Factory function to call inside --paths-file.",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable ANSI colors in output.",
    )
    return parser


def pathfill_cli(argv=None, input_func=input, stdout=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    stdout = stdout or sys.stdout
    use_color = not args.no_color and getattr(stdout, "isatty", lambda: False)()

    try:
        namespace = load_paths_namespace(args.paths_file, args.paths_fn)
    except (OSError, RuntimeError) as exc:
        parser.exit(2, f"error: failed to load paths from {args.paths_file}: {exc}\n")
    except ValueError as exc:
        parser.exit(2, f"error: {exc}\n")

    templates = namespace_to_templates(namespace)

    if not args.entries:
        for entry, template in templates.items():
            print(format_assignment(entry, template, use_color), file=stdout)
        return

    missing_entries = [entry for entry in args.entries if entry not in templates]
    if missing_entries:
        parser.exit(2, f"error: unknown path entries: {', '.join(missing_entries)}\n")

    wildcards = []
    seen = set()
    for entry in args.entries:
        for wildcard in extract_wildcards(templates[entry]):
            if wildcard not in seen:
                seen.add(wildcard)
                wildcards.append(wildcard)

    values = collect_wildcard_values(wildcards, input_func=input_func)
    for entry, path in resolve_entries(args.entries, templates, values):
        print(format_assignment(entry, path, use_color), file=stdout)
