import warnings
from os.path import join
from shutil import rmtree
from tempfile import mkdtemp
from types import ModuleType

import h5py
import pytest

from deeprank2.domain import edgestorage as Efeat
from deeprank2.domain import nodestorage as Nfeat
from deeprank2.domain.aminoacidlist import alanine, phenylalanine
from deeprank2.features import components, contact, surfacearea
from deeprank2.query import ProteinProteinInterfaceQuery, Query, QueryCollection, SingleResidueVariantQuery
from deeprank2.tools.target import compute_ppi_scores


def _querycollection_tester(
    query_type: str,
    n_queries: int = 3,
    feature_modules: ModuleType | list[ModuleType] = [components, contact],  # noqa: B006 (unsafe default value)
    cpu_count: int = 1,
    combine_output: bool = True,
) -> (QueryCollection, str, list[str]):
    """
    Generic function to test QueryCollection class.

    Args:
        query_type (str): query type to be generated. It accepts only 'ppi' (ProteinProteinInterface) or 'srv' (SingleResidueVariant).
            Defaults to 'ppi'.
        n_queries (int): number of queries to be generated.
        feature_modules: module or list of feature modules (from deeprank2.features) to be passed to process.
            Defaults to components and contact, which are the defaults for `query.process`
        cpu_count (int): number of cpus to be used during the queries processing.
        combine_output (bool): boolean for combining the hdf5 files generated by the processes.
            By default, the hdf5 files generated are combined into one, and then deleted.
    """
    if query_type == "ppi":
        queries = [
            ProteinProteinInterfaceQuery(
                pdb_path="tests/data/pdb/3C8P/3C8P.pdb",
                resolution="residue",
                chain_ids=["A", "B"],
                pssm_paths={
                    "A": "tests/data/pssm/3C8P/3C8P.A.pdb.pssm",
                    "B": "tests/data/pssm/3C8P/3C8P.B.pdb.pssm",
                },
            ),
        ] * n_queries
    elif query_type == "srv":
        queries = [
            SingleResidueVariantQuery(
                pdb_path="tests/data/pdb/101M/101M.pdb",
                resolution="residue",
                chain_ids="A",
                variant_residue_number=None,  # placeholder
                insertion_code=None,
                wildtype_amino_acid=alanine,
                variant_amino_acid=phenylalanine,
                pssm_paths={"A": "tests/data/pssm/101M/101M.A.pdb.pssm"},
            ),
        ] * n_queries
    else:
        msg = "Please insert a valid type (either ppi or srv)."
        raise ValueError(msg)

    output_directory = mkdtemp()
    prefix = join(output_directory, "test-process-queries")
    collection = QueryCollection()

    for idx in range(n_queries):
        if query_type == "srv":
            queries[idx].variant_residue_number = idx + 1
            collection.add(queries[idx])
        else:
            collection.add(queries[idx], warn_duplicate=False)

    output_paths = collection.process(
        prefix,
        feature_modules,
        cpu_count,
        combine_output,
    )
    assert len(output_paths) > 0

    graph_names = []
    for path in output_paths:
        with h5py.File(path, "r") as f5:
            graph_names += list(f5.keys())

    for query in collection.queries:
        assert query.get_query_id() in graph_names, f"missing in output: {query.get_query_id()}"

    return collection, output_directory, output_paths


def _assert_correct_modules(
    output_paths: str,
    features: str | list[str],
    absent: str,
) -> None:
    """Helper function to assert inclusion of correct features.

    Args:
        output_paths (str): output_paths as returned from _querycollection_tester
        features (str | list[str]): feature(s) that should be present
        absent (str): feature that should be absent
    """
    if isinstance(features, str):
        features = [features]

    with h5py.File(output_paths[0], "r") as f5:
        missing = []
        for feat in features:
            try:
                if feat == Efeat.DISTANCE:
                    _ = f5[next(iter(f5.keys()))][f"{Efeat.EDGE}/{feat}"]
                else:
                    _ = f5[next(iter(f5.keys()))][f"{Nfeat.NODE}/{feat}"]
            except KeyError:
                missing.append(feat)
            if missing:
                msg = f"The following feature(s) were not created: {missing}."
                raise KeyError(msg)

        with pytest.raises(KeyError):
            _ = f5[next(iter(f5.keys()))][f"{Nfeat.NODE}/{absent}"]


def test_querycollection_process() -> None:
    """Tests processing method of QueryCollection class."""
    for query_type in ["ppi", "srv"]:
        n_queries = 3
        n_queries = 3

        collection, output_directory, _ = _querycollection_tester(query_type, n_queries=n_queries)

        assert isinstance(collection.queries, list)
        assert len(collection.queries) == n_queries
        for query in collection.queries:
            assert issubclass(type(query), Query)

        rmtree(output_directory)


def test_querycollection_process_single_feature_module() -> None:
    """Test processing for generating from a single feature module.

    Tested for following input types: ModuleType, list[ModuleType] str, list[str]
    """
    for query_type in ["ppi", "srv"]:
        for testcase in [surfacearea, [surfacearea], "surfacearea", ["surfacearea"]]:
            _, output_directory, output_paths = _querycollection_tester(query_type, feature_modules=testcase)
            _assert_correct_modules(output_paths, Nfeat.BSA, Nfeat.HSE)
            rmtree(output_directory)


def test_querycollection_process_all_features_modules() -> None:
    """Tests processing for generating all features."""
    one_feature_from_each_module = [
        Nfeat.RESTYPE,
        Nfeat.PSSM,
        Efeat.DISTANCE,
        Nfeat.HSE,
        Nfeat.SECSTRUCT,
        Nfeat.BSA,
        Nfeat.IRCTOTAL,
    ]

    _, output_directory, output_paths = _querycollection_tester("ppi", feature_modules="all")
    _assert_correct_modules(output_paths, one_feature_from_each_module, "dummy_feature")
    rmtree(output_directory)

    _, output_directory, output_paths = _querycollection_tester("srv", feature_modules="all")
    _assert_correct_modules(
        output_paths,
        one_feature_from_each_module[:-1],
        Nfeat.IRCTOTAL,
    )

    rmtree(output_directory)


def test_querycollection_process_default_features_modules() -> None:
    """Tests processing for generating all features."""
    for query_type in ["ppi", "srv"]:
        _, output_directory, output_paths = _querycollection_tester(query_type)
        _assert_correct_modules(
            output_paths,
            [Nfeat.RESTYPE, Efeat.DISTANCE],
            Nfeat.HSE,
        )

        rmtree(output_directory)


def test_querycollection_process_combine_output_true() -> None:
    """Tests processing for combining hdf5 files into one."""
    for query_type in ["ppi", "srv"]:
        modules = [surfacearea, components]
        _, output_directory_t, output_paths_t = _querycollection_tester(query_type, feature_modules=modules)
        _, output_directory_f, output_paths_f = _querycollection_tester(query_type, feature_modules=modules, combine_output=False, cpu_count=2)
        assert len(output_paths_t) == 1

        keys_t = {}
        with h5py.File(output_paths_t[0], "r") as file_t:
            for key, value in file_t.items():
                keys_t[key] = value
        keys_f = {}
        for output_path in output_paths_f:
            with h5py.File(output_path, "r") as file_f:
                for key, value in file_f.items():
                    keys_f[key] = value
        assert keys_t == keys_f

        rmtree(output_directory_t)
        rmtree(output_directory_f)


def test_querycollection_process_combine_output_false() -> None:
    """Tests processing for keeping all generated hdf5 files ."""
    for query_type in ["ppi", "srv"]:
        cpu_count = 2
        combine_output = False
        modules = [surfacearea, components]
        _, output_directory, output_paths = _querycollection_tester(
            query_type,
            feature_modules=modules,
            cpu_count=cpu_count,
            combine_output=combine_output,
        )
        assert len(output_paths) == cpu_count

        rmtree(output_directory)


def test_querycollection_duplicates_add() -> None:
    """Tests add method of QueryCollection class."""
    ref_path = "tests/data/ref/1ATN/1ATN.pdb"
    pssm_path1 = "tests/data/pssm/1ATN/1ATN.A.pdb.pssm"
    pssm_path2 = "tests/data/pssm/1ATN/1ATN.B.pdb.pssm"
    chain_id1 = "A"
    chain_id2 = "B"
    pdb_paths = [
        "tests/data/pdb/1ATN/1ATN_1w.pdb",
        "tests/data/pdb/1ATN/1ATN_1w.pdb",
        "tests/data/pdb/1ATN/1ATN_1w.pdb",
        "tests/data/pdb/1ATN/1ATN_2w.pdb",
        "tests/data/pdb/1ATN/1ATN_2w.pdb",
        "tests/data/pdb/1ATN/1ATN_3w.pdb",
    ]

    queries = QueryCollection()

    with warnings.catch_warnings(record=UserWarning):
        for pdb_path in pdb_paths:
            # Append data points
            targets = compute_ppi_scores(pdb_path, ref_path)
            queries.add(
                ProteinProteinInterfaceQuery(
                    pdb_path=pdb_path,
                    resolution="residue",
                    chain_ids=[chain_id1, chain_id2],
                    targets=targets,
                    pssm_paths={chain_id1: pssm_path1, chain_id2: pssm_path2},
                ),
            )

    # check id naming for all pdb files
    model_ids = [query.model_id for query in queries.queries]
    model_ids.sort()

    assert model_ids == [
        "1ATN_1w",
        "1ATN_1w_2",
        "1ATN_1w_3",
        "1ATN_2w",
        "1ATN_2w_2",
        "1ATN_3w",
    ]
    assert queries._ids_count["residue-ppi:A-B:1ATN_1w"] == 3  # noqa: SLF001 (private member accessed)
    assert queries._ids_count["residue-ppi:A-B:1ATN_2w"] == 2  # noqa: SLF001 (private member accessed)
    assert queries._ids_count["residue-ppi:A-B:1ATN_3w"] == 1  # noqa: SLF001 (private member accessed)
