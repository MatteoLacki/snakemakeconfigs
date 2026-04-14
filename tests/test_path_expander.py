import io

from pathlib import Path

import pytest

from snakemakeconfigs.path_expander import (
    COLOR_BRACE,
    COLOR_LITERAL,
    COLOR_NAME,
    COLOR_RESET,
    COLOR_WILDCARD,
    pathfill_cli,
)


def write_paths_file(tmp_path: Path):
    path = tmp_path / "paths.py"
    path.write_text(
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n\n"
        "def get_paths():\n"
        "    return SimpleNamespace(\n"
        "        tdf='data/{dataset}.d',\n"
        "        mgf='temp/{dataset}/{cfg}/mgf.mgf',\n"
        "        static='configs/mgf/default.toml',\n"
        "    )\n\n"
        "def get_paths2():\n"
        "    return SimpleNamespace(\n"
        "        mzml=Path('temp') / '{dataset}' / '{cfg}' / 'mzml.mzML',\n"
        "    )\n"
    )
    return path


def make_input(values, prompts):
    iterator = iter(values)

    def fake_input(prompt):
        prompts.append(prompt)
        return next(iterator)

    return fake_input


class FakeTty(io.StringIO):
    def isatty(self):
        return True


def test_single_entry_one_wildcard(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)
    prompts = []

    pathfill_cli(
        ["--paths-file", str(paths_file), "tdf"],
        input_func=make_input(["dataset_a"], prompts),
    )

    assert prompts == ["dataset: "]
    assert capsys.readouterr().out == "tdf=data/dataset_a.d\n"


def test_no_entries_lists_namespace_keys(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)

    pathfill_cli(["--paths-file", str(paths_file)], input_func=make_input([], []))

    assert capsys.readouterr().out == (
        "tdf=data/{dataset}.d\n"
        "mgf=temp/{dataset}/{cfg}/mgf.mgf\n"
        "static=configs/mgf/default.toml\n"
    )


def test_no_entries_lists_selected_function_keys(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)

    pathfill_cli(
        ["--paths-file", str(paths_file), "--paths-fn", "get_paths2"],
        input_func=make_input([], []),
    )

    assert capsys.readouterr().out == "mzml=temp/{dataset}/{cfg}/mzml.mzML\n"


def test_multiple_entries_shared_wildcard_prompted_once(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)
    prompts = []

    pathfill_cli(
        ["--paths-file", str(paths_file), "tdf", "mgf"],
        input_func=make_input(["dataset_a", "cfg_b"], prompts),
    )

    assert prompts == ["dataset: ", "cfg: "]
    assert capsys.readouterr().out == (
        "tdf=data/dataset_a.d\n"
        "mgf=temp/dataset_a/cfg_b/mgf.mgf\n"
    )


def test_entry_without_wildcards_printed_unchanged(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)

    pathfill_cli(["--paths-file", str(paths_file), "static"], input_func=make_input([], []))

    assert capsys.readouterr().out == "static=configs/mgf/default.toml\n"


def test_get_paths2_mode_supports_path_objects(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)
    prompts = []

    pathfill_cli(
        ["--paths-file", str(paths_file), "--paths-fn", "get_paths2", "mzml"],
        input_func=make_input(["dataset_a", "cfg_b"], prompts),
    )

    assert prompts == ["dataset: ", "cfg: "]
    assert capsys.readouterr().out == "mzml=temp/dataset_a/cfg_b/mzml.mzML\n"


def test_unknown_entry_exits_with_error(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        pathfill_cli(["--paths-file", str(paths_file), "missing"], input_func=make_input([], []))

    assert excinfo.value.code == 2
    assert capsys.readouterr().err == "error: unknown path entries: missing\n"


def test_invalid_paths_fn_exits_with_error(tmp_path, capsys):
    paths_file = write_paths_file(tmp_path)

    with pytest.raises(SystemExit) as excinfo:
        pathfill_cli(
            ["--paths-file", str(paths_file), "--paths-fn", "missing_fn", "tdf"],
            input_func=make_input([], []),
        )

    assert excinfo.value.code == 2
    assert capsys.readouterr().err == f"error: 'missing_fn' is not defined in {paths_file}\n"


def test_missing_paths_file_exits_with_error(capsys, tmp_path):
    missing = tmp_path / "missing_paths.py"

    with pytest.raises(SystemExit) as excinfo:
        pathfill_cli(["--paths-file", str(missing), "tdf"], input_func=make_input([], []))

    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert err.startswith(f"error: failed to load paths from {missing}: ")


def test_listing_uses_colors_on_tty_output(tmp_path):
    paths_file = write_paths_file(tmp_path)
    stdout = FakeTty()

    pathfill_cli(["--paths-file", str(paths_file)], input_func=make_input([], []), stdout=stdout)

    assert stdout.getvalue() == (
        f"{COLOR_NAME}tdf{COLOR_RESET}="
        f"{COLOR_LITERAL}data/{COLOR_RESET}"
        f"{COLOR_BRACE}{{{COLOR_RESET}"
        f"{COLOR_WILDCARD}dataset{COLOR_RESET}"
        f"{COLOR_BRACE}}}{COLOR_RESET}"
        f"{COLOR_LITERAL}.d{COLOR_RESET}\n"
        f"{COLOR_NAME}mgf{COLOR_RESET}="
        f"{COLOR_LITERAL}temp/{COLOR_RESET}"
        f"{COLOR_BRACE}{{{COLOR_RESET}"
        f"{COLOR_WILDCARD}dataset{COLOR_RESET}"
        f"{COLOR_BRACE}}}{COLOR_RESET}"
        f"{COLOR_LITERAL}/{COLOR_RESET}"
        f"{COLOR_BRACE}{{{COLOR_RESET}"
        f"{COLOR_WILDCARD}cfg{COLOR_RESET}"
        f"{COLOR_BRACE}}}{COLOR_RESET}"
        f"{COLOR_LITERAL}/mgf.mgf{COLOR_RESET}\n"
        f"{COLOR_NAME}static{COLOR_RESET}="
        f"{COLOR_LITERAL}configs/mgf/default.toml{COLOR_RESET}\n"
    )


def test_no_color_flag_disables_tty_colors(tmp_path):
    paths_file = write_paths_file(tmp_path)
    stdout = FakeTty()

    pathfill_cli(
        ["--paths-file", str(paths_file), "--no-color"],
        input_func=make_input([], []),
        stdout=stdout,
    )

    assert stdout.getvalue() == (
        "tdf=data/{dataset}.d\n"
        "mgf=temp/{dataset}/{cfg}/mgf.mgf\n"
        "static=configs/mgf/default.toml\n"
    )
