import tomllib
from pathlib import Path

import pytest
import tomlkit
from tomlkit.items import AoT, Table

from snakemakeconfigs.toml_patcher import (
    _expand_aot_element,
    apply_patch,
    expand_configs,
    extract_grids_from_doc,
    make_config_name,
)

EXAMPLES = Path(__file__).parent.parent / "examples"
GRID_SUFFIXES = ("__grid",)


# ---------------------------------------------------------------------------
# extract_grids_from_doc — plain __grid keys
# ---------------------------------------------------------------------------


def test_extract_grids_scalar():
    doc = tomlkit.parse("[model]\nlayers__grid = [128, 64, 32]\nlearning_rate = 0.01\n")
    result, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    assert set(grids) == {"model.layers"}
    assert grids["model.layers"] == [128, 64, 32]
    assert result["model"]["layers"] == 128  # first value kept


def test_extract_grids_list_values():
    doc = tomlkit.parse(
        "[test]\ntestlists__grid = [[1,2,23], [232,4654,64654]]\ntest = 101\n"
    )
    result, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    assert "test.testlists" in grids
    assert grids["test.testlists"] == [[1, 2, 23], [232, 4654, 64654]]
    assert result["test"]["testlists"] == [1, 2, 23]


def test_extract_grids_no_grid_keys():
    doc = tomlkit.parse("[model]\nlayers = [128, 64]\nlearning_rate = 0.01\n")
    _, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    assert grids == {}


# ---------------------------------------------------------------------------
# _expand_aot_element
# ---------------------------------------------------------------------------


def test_expand_aot_element_no_grids():
    elem = tomlkit.parse("test = 101\nsome_value = 1.5\n")
    variants = _expand_aot_element(elem, GRID_SUFFIXES)
    assert len(variants) == 1
    assert variants[0]["test"] == 101


def test_expand_aot_element_one_grid():
    elem = tomlkit.parse("some_values__grid = [1.2, 3.4]\ntest = 101\n")
    variants = _expand_aot_element(elem, GRID_SUFFIXES)
    assert len(variants) == 2
    assert variants[0]["some_values"] == 1.2
    assert variants[1]["some_values"] == 3.4


def test_expand_aot_element_two_grids():
    # 3 × 2 = 6 variants
    elem = tomlkit.parse(
        "some_values__grid = [1.2, 3.4, 32.1]\n"
        "testlists__grid = [[1,2,23], [232,4654,64654]]\n"
        "test = 101\n"
    )
    variants = _expand_aot_element(elem, GRID_SUFFIXES)
    assert len(variants) == 6
    some_values = [v["some_values"] for v in variants]
    assert set(some_values) == {1.2, 3.4, 32.1}


# ---------------------------------------------------------------------------
# extract_grids_from_doc — AoT
# ---------------------------------------------------------------------------


def test_extract_grids_aot_count():
    # element 0: 3×2=6, element 1: 2×2=4 → 10 total variants
    doc = tomlkit.parse(EXAMPLES.joinpath("config_with_grids_and_lists.toml").read_text())
    _, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    assert "test" in grids
    assert len(grids["test"]) == 10


def test_extract_grids_aot_result_is_table():
    doc = tomlkit.parse(EXAMPLES.joinpath("config_with_grids_and_lists.toml").read_text())
    result, _ = extract_grids_from_doc(doc, GRID_SUFFIXES)
    assert isinstance(result["test"], Table)
    assert not isinstance(result["test"], AoT)


def test_extract_grids_aot_no_grid_keys_remain():
    doc = tomlkit.parse(EXAMPLES.joinpath("config_with_grids_and_lists.toml").read_text())
    result, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    for variant in grids["test"]:
        for key in variant.keys():
            assert not key.endswith("__grid"), f"__grid key remained: {key}"


# ---------------------------------------------------------------------------
# expand_configs — full pipeline with AoT
# ---------------------------------------------------------------------------


def test_expand_configs_aot_file_count(tmp_path):
    doc = tomlkit.parse(EXAMPLES.joinpath("config_with_grids_and_lists.toml").read_text())
    result, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    files = expand_configs(result, grids, tmp_path, "config", short_names=True)
    assert len(files) == 30


def test_expand_configs_aot_all_valid_toml(tmp_path):
    doc = tomlkit.parse(EXAMPLES.joinpath("config_with_grids_and_lists.toml").read_text())
    result, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    expand_configs(result, grids, tmp_path, "config", short_names=True)
    for f in tmp_path.glob("*.toml"):
        tomllib.load(open(f, "rb"))  # raises on invalid TOML


def test_expand_configs_aot_test_is_plain_table(tmp_path):
    doc = tomlkit.parse(EXAMPLES.joinpath("config_with_grids_and_lists.toml").read_text())
    result, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    expand_configs(result, grids, tmp_path, "config", short_names=True)
    for f in tmp_path.glob("*.toml"):
        out = tomlkit.parse(f.read_text())
        assert isinstance(out["test"], Table)
        assert not isinstance(out["test"], AoT)


def test_expand_configs_aot_filenames_encode_index(tmp_path):
    doc = tomlkit.parse(EXAMPLES.joinpath("config_with_grids_and_lists.toml").read_text())
    result, grids = extract_grids_from_doc(doc, GRID_SUFFIXES)
    files = expand_configs(result, grids, tmp_path, "config", short_names=True, equal_sign="+")
    # All 10 test indices (0-9) must appear across the 30 files
    indices = {int(f.split("test+")[1].split("__")[0].replace(".toml", "")) for f in files}
    assert indices == set(range(10))


# ---------------------------------------------------------------------------
# apply_patch — AoT in patch
# ---------------------------------------------------------------------------


def test_apply_patch_aot(tmp_path):
    base = tomlkit.parse("[model]\nlayers = 128\nlearning_rate = 0.01\n")
    patch_text = (
        "[[test]]\nsome_values__grid = [1.2, 3.4]\ntest = 1\n\n"
        "[[test]]\nsome_values__grid = [10.0]\ntest = 2\n"
    )
    patch = tomlkit.parse(patch_text)
    result, grids = apply_patch(base, patch, GRID_SUFFIXES)
    # element 0: 2 variants, element 1: 1 variant → 3 total
    assert "test" in grids
    assert len(grids["test"]) == 3
    assert isinstance(result["test"], Table)


def test_apply_patch_aot_expand_files(tmp_path):
    base = tomlkit.parse("[model]\nlayers = 64\nlearning_rate = 0.01\n")
    # patch adds both an AoT grid dimension and a scalar grid dimension
    patch_text = (
        "layers__grid = [64, 128]\n\n"
        "[[test]]\nsome_values__grid = [1.2, 3.4]\ntest = 1\n\n"
        "[[test]]\nsome_values__grid = [10.0]\ntest = 2\n"
    )
    patch = tomlkit.parse(patch_text)
    result, grids = apply_patch(base, patch, GRID_SUFFIXES)
    # 2 layers × 3 test variants = 6 files
    files = expand_configs(result, grids, tmp_path, "config", short_names=True)
    assert len(files) == 6


# ---------------------------------------------------------------------------
# make_config_name — grid_indices for table values
# ---------------------------------------------------------------------------


def test_make_config_name_grid_indices():
    t0 = tomlkit.parse("a = 1\n")
    t1 = tomlkit.parse("a = 2\n")
    grid_indices = {"test": {id(t0): 0, id(t1): 1}}
    name = make_config_name(
        {"test": t0}, "base", {}, short_names=True, equal_sign="+", grid_indices=grid_indices
    )
    assert name == "base__test+0.toml"
    name = make_config_name(
        {"test": t1}, "base", {}, short_names=True, equal_sign="+", grid_indices=grid_indices
    )
    assert name == "base__test+1.toml"
