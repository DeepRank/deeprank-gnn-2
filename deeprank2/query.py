import importlib
import logging
import os
import pickle
import pkgutil
import warnings
from dataclasses import MISSING, dataclass, field, fields
from functools import partial
from glob import glob
from multiprocessing import Pool
from random import randrange
from types import ModuleType
from typing import Dict, Iterator, List, Optional, Union

import h5py
import numpy as np
import pdb2sql

import deeprank2.features
from deeprank2.domain.aminoacidlist import convert_aa_nomenclature
from deeprank2.features import components, conservation, contact
from deeprank2.molstruct.aminoacid import AminoAcid
from deeprank2.molstruct.residue import Residue, SingleResidueVariant
from deeprank2.molstruct.structure import PDBStructure
from deeprank2.utils.buildgraph import (get_contact_atoms, get_structure,
                                        get_surrounding_residues)
from deeprank2.utils.graph import (Graph, build_atomic_graph,
                                   build_residue_graph)
from deeprank2.utils.grid import Augmentation, GridSettings, MapMethod
from deeprank2.utils.parsing.pssm import parse_pssm

_log = logging.getLogger(__name__)

VALID_RESOLUTIONS = ['atomic', 'residue']


def _check_pssm(pdb_path: str, pssm_paths: Dict[str, str], suppress: bool, verbosity: int = 0):
    #TODO: make this an internal method of DeepRankQuery?
    """Checks whether information stored in pssm file matches the corresponding pdb file.

    Args:
        pdb_path (str): Path to the PDB file.
        pssm_paths (Dict[str, str]): The paths to the PSSM files, per chain identifier.
        suppress (bool): Suppress errors and throw warnings instead.
        verbosity (int): Level of verbosity of error/warning. Defaults to 0.
            0 (low): Only state file name where error occurred;
            1 (medium): Also state number of incorrect and missing residues;
            2 (high): Also list the incorrect residues

    Raises:
        ValueError: Raised if info between pdb file and pssm file doesn't match or if no pssms were provided
    """

    if not pssm_paths:
        raise ValueError('No pssm paths provided for conservation feature module.')

    pssm_data = {}
    for chain in pssm_paths:
        with open(pssm_paths[chain], encoding='utf-8') as f:
            lines = f.readlines()[1:]
        for line in lines:
            pssm_data[chain + line.split()[0].zfill(4)] = convert_aa_nomenclature(line.split()[1], 3)

    # load ground truth from pdb file
    pdb_truth = pdb2sql.pdb2sql(pdb_path).get_residues()
    pdb_truth = {res[0] + str(res[2]).zfill(4): res[1] for res in pdb_truth if res[0] in pssm_paths}

    wrong_list = []
    missing_list = []

    for residue in pdb_truth:
        try:
            if pdb_truth[residue] != pssm_data[residue]:
                wrong_list.append(residue)
        except KeyError:
            missing_list.append(residue)

    if len(wrong_list) + len(missing_list) > 0:
        error_message = f'Amino acids in PSSM files do not match pdb file for {os.path.split(pdb_path)[1]}.'
        if verbosity:
            if len(wrong_list) > 0:
                error_message = error_message + f'\n\t{len(wrong_list)} entries are incorrect.'
                if verbosity == 2:
                    error_message = error_message[-1] + f':\n\t{missing_list}'
            if len(missing_list) > 0:
                error_message = error_message + f'\n\t{len(missing_list)} entries are missing.'
                if verbosity == 2:
                    error_message = error_message[-1] + f':\n\t{missing_list}'

        if not suppress:
            raise ValueError(error_message)

        warnings.warn(error_message)
        _log.warning(error_message)


# TODO: consider whether we want to use the built-in repr and eq, or define it ourselves
# if built-in: consider which arguments to include in either.
@dataclass(repr=False, kw_only=True)
class DeepRankQuery:
    """Represents one entity of interest, like a single residue variant or a protein-protein interface.

    :class:`DeepRankQuery` objects are used to generate graphs from structures, and they should be created before any model is loaded.
    They can have target values associated with them, which will be stored with the resulting graph.

    Args:
        model_id (str): The ID of the model to load, usually a .PDB accession code.
        targets (Optional[Dict[str, Union[float, int]]], optional): Target values associated with the query. Defaults to None.
        suppress_pssm_errors (bool, optional): Suppress error raised if .pssm files do not match .pdb files and throw warning instead.
            Defaults to False.
    """

    pdb_path: str
    resolution: str
    chain_ids: List[str] | str
    pssm_paths: Dict[str, str] = field(default_factory=dict)
    distance_cutoff: float = None
    targets: Dict[str, float] = field(default_factory=dict)
    suppress_pssm_errors: bool = False

    def __post_init__(self):
        self._model_id = os.path.splitext(os.path.basename(self.pdb_path))[0]

        if self.resolution not in VALID_RESOLUTIONS:
            raise ValueError(f"Invalid resolution given ({self.resolution}). Must be one of {VALID_RESOLUTIONS}")

        if not isinstance(self.chain_ids, list):
            self.chain_ids = [self.chain_ids]

        # convert None to empty type (e.g. list, dict) for arguments where this is expected
        for f in fields(self):
            value = getattr(self, f.name)
            if value is None and f.default_factory is not MISSING:
                setattr(self, f.name, f.default_factory())

    def _set_graph_targets(self, graph: Graph):
        """Copy target data from query to graph."""
        for target_name, target_data in self.targets.items():
            graph.targets[target_name] = target_data

    def _load_structure(self, pssm_required: bool) -> PDBStructure:
        """Build PDBStructure objects from pdb and pssm data."""
        pdb = pdb2sql.pdb2sql(self.pdb_path)
        try:
            structure = get_structure(pdb, self.model_id)
        finally:
            pdb._close() # pylint: disable=protected-access
        # read the pssm
        if pssm_required:
            self._load_pssm_data(structure)

        return structure

    def _load_pssm_data(self, structure: PDBStructure):
        self._check_pssm()
        for chain in structure.chains:
            if chain.id in self.pssm_paths:
                pssm_path = self.pssm_paths[chain.id]
                with open(pssm_path, "rt", encoding="utf-8") as f:
                    chain.pssm = parse_pssm(f, chain)

    @property
    def model_id(self) -> str:
        """The ID of the model, usually a .PDB accession code."""
        return self._model_id
    @model_id.setter
    def model_id(self, value: str):
        self._model_id = value

    def __repr__(self) -> str:
        return f"{type(self)}({self.get_query_id()})"

    def build(self, feature_modules: List[ModuleType]) -> Graph:
        raise NotImplementedError("Must be defined in child classes.")
    def get_query_id(self) -> str:
        raise NotImplementedError("Must be defined in child classes.")


class QueryCollection:
    """
    Represents the collection of data queries.
        Queries can be saved as a dictionary to easily navigate through their data.

    """

    def __init__(self):

        self._queries = []
        self.cpu_count = None
        self.ids_count = {}

    def add(self, query: DeepRankQuery, verbose: bool = False, warn_duplicate: bool = True):
        """
        Adds a new query to the collection.

        Args:
            query(:class:`DeepRankQuery`): Must be a :class:`DeepRankQuery` object, either :class:`ProteinProteinInterfaceResidueQuery` or
                :class:`SingleResidueVariantAtomicQuery`.
            verbose(bool, optional): For logging query IDs added, defaults to False.
            warn_duplicate (bool): Log a warning before renaming if a duplicate query is identified.

        """
        query_id = query.get_query_id()

        if verbose:
            _log.info(f'Adding query with ID {query_id}.')

        if query_id not in self.ids_count:
            self.ids_count[query_id] = 1
        else:
            self.ids_count[query_id] += 1
            new_id = query.model_id + "_" + str(self.ids_count[query_id])
            query.model_id = new_id

            if warn_duplicate:
                _log.warning(f'DeepRankQuery with ID {query_id} has already been added to the collection. Renaming it as {query.get_query_id()}')

        self._queries.append(query)

    def export_dict(self, dataset_path: str):
        """Exports the colection of all queries to a dictionary file.

        Args:
            dataset_path (str): The path where to save the list of queries.
        """
        with open(dataset_path, "wb") as pkl_file:
            pickle.dump(self, pkl_file)

    @property
    def queries(self) -> List[DeepRankQuery]:
        """The list of queries added to the collection."""
        return self._queries

    def __contains__(self, query: DeepRankQuery) -> bool:
        return query in self._queries

    def __iter__(self) -> Iterator[DeepRankQuery]:
        return iter(self._queries)

    def __len__(self) -> int:
        return len(self._queries)

    def _process_one_query(  # pylint: disable=too-many-arguments
        self,
        prefix: str,
        feature_names: List[str],
        grid_settings: Optional[GridSettings],
        grid_map_method: Optional[MapMethod],
        grid_augmentation_count: int,
        query: DeepRankQuery
    ):

        try:
            # because only one process may access an hdf5 file at a time:
            output_path = f"{prefix}-{os.getpid()}.hdf5"

            feature_modules = [
                importlib.import_module('deeprank2.features.' + name) for name in feature_names]

            graph = query.build(feature_modules)
            graph.write_to_hdf5(output_path)

            if grid_settings is not None and grid_map_method is not None:
                graph.write_as_grid_to_hdf5(output_path, grid_settings, grid_map_method)

                for _ in range(grid_augmentation_count):
                    # repeat with random augmentation
                    axis, angle = pdb2sql.transform.get_rot_axis_angle(randrange(100))
                    augmentation = Augmentation(axis, angle)
                    graph.write_as_grid_to_hdf5(output_path, grid_settings, grid_map_method, augmentation)

            return None

        except (ValueError, AttributeError, KeyError, TimeoutError) as e:
            _log.warning(f'\nGraph/DeepRankQuery with ID {query.get_query_id()} ran into an Exception ({e.__class__.__name__}: {e}),'
            ' and it has not been written to the hdf5 file. More details below:')
            _log.exception(e)
            return None

    def process( # pylint: disable=too-many-arguments, too-many-locals, dangerous-default-value
        self,
        prefix: Optional[str] = None,
        feature_modules: Union[ModuleType, List[ModuleType], str, List[str]] = [components, contact],
        cpu_count: Optional[int] = None,
        combine_output: bool = True,
        grid_settings: Optional[GridSettings] = None,
        grid_map_method: Optional[MapMethod] = None,
        grid_augmentation_count: int = 0
    ) -> List[str]:
        """
        Args:
            prefix (Optional[str], optional): Prefix for the output files. Defaults to None, which sets ./processed-queries- prefix.
            feature_modules (Union[ModuleType, List[ModuleType], str, List[str]], optional): Features' module or list of features' modules
                used to generate features (given as string or as an imported module). Each module must implement the :py:func:`add_features` function,
                and features' modules can be found (or should be placed in case of a custom made feature) in `deeprank2.features` folder.
                If set to 'all', all available modules in `deeprank2.features` are used to generate the features.
                Defaults to only the basic feature modules `deeprank2.features.components` and `deeprank2.features.contact`.
            cpu_count (Optional[int], optional): How many processes to be run simultaneously. Defaults to None, which takes all available cpu cores.
            combine_output (bool, optional): For combining the HDF5 files generated by the processes. Defaults to True.
            grid_settings (Optional[:class:`GridSettings`], optional): If valid together with `grid_map_method`, the grid data will be stored as well.
                Defaults to None.
            grid_map_method (Optional[:class:`MapMethod`], optional): If valid together with `grid_settings`, the grid data will be stored as well.
                Defaults to None.
            grid_augmentation_count (int, optional): Number of grid data augmentations. May not be negative be zero or a positive number.
                Defaults to 0.

        Returns:
            List[str]: The list of paths of the generated HDF5 files.
        """

        # set defaults
        if prefix is None:
            prefix = "processed-queries"
        elif prefix.endswith('.hdf5'):
            prefix = prefix[:-5]
        if cpu_count is None:
            cpu_count = os.cpu_count()  # returns the number of CPUs in the system
        else:
            cpu_count_system = os.cpu_count()
            if cpu_count > cpu_count_system:
                _log.warning(f'\nTried to set {cpu_count} CPUs, but only {cpu_count_system} are present in the system.')
                cpu_count = cpu_count_system
        self.cpu_count = cpu_count
        _log.info(f'\nNumber of CPUs for processing the queries set to: {self.cpu_count}.')


        if feature_modules == 'all':
            feature_names = [modname for _, modname, _ in pkgutil.iter_modules(deeprank2.features.__path__)]
        elif isinstance(feature_modules, list):
            feature_names = [os.path.basename(m.__file__)[:-3] if isinstance(m,ModuleType)
                             else m.replace('.py','') for m in feature_modules]
        elif isinstance(feature_modules, ModuleType):
            feature_names = [os.path.basename(feature_modules.__file__)[:-3]]
        elif isinstance(feature_modules, str):
            feature_names = [feature_modules.replace('.py','')]
        else:
            raise ValueError(f'Feature_modules has received an invalid input type: {type(feature_modules)}.')
        _log.info(f'\nSelected feature modules: {feature_names}.')

        _log.info(f'Creating pool function to process {len(self.queries)} queries...')
        pool_function = partial(self._process_one_query, prefix,
                                feature_names,
                                grid_settings, grid_map_method, grid_augmentation_count)

        with Pool(self.cpu_count) as pool:
            _log.info('Starting pooling...\n')
            pool.map(pool_function, self.queries)

        output_paths = glob(f"{prefix}-*.hdf5")

        if combine_output:
            for output_path in output_paths:
                with h5py.File(f"{prefix}.hdf5",'a') as f_dest, h5py.File(output_path,'r') as f_src:
                    for key, value in f_src.items():
                        _log.debug(f"copy {key} from {output_path} to {prefix}.hdf5")
                        f_src.copy(value, f_dest)
                os.remove(output_path)
            return glob(f"{prefix}.hdf5")

        return output_paths

@dataclass(kw_only=True)
class SingleResidueVariantQuery(DeepRankQuery):
    """A query that builds a single residue variant graph."""

    variant_residue_number: int
    insertion_code: str | None
    wildtype_amino_acid: AminoAcid
    variant_amino_acid: AminoAcid
    radius: float = 10.0

    def __post_init__(self):
        super().__post_init__()  # calls __post_init__ of parents

        if len(self.chain_ids) != 1:
            # TODO: Consider throwing a warning instead of error and taking the first entry of the list anyway.
            raise ValueError(f"SingleResidueVariantQuery must contain exactly 1 chain_id, but {len(self.chain_ids)} were given.")
        self.variant_chain_id = self.chain_ids[0]

        if not self.distance_cutoff:
            self.distance_cutoff = 4.5

    @property
    def residue_id(self) -> str:
        """String representation of the residue number and insertion code."""
        if self.insertion_code is not None:
            return f"{self.variant_residue_number}{self.insertion_code}"
        return str(self.variant_residue_number)

    def get_query_id(self) -> str:
        """Returns the string representing the complete query ID."""
        return (f"{self.resolution}-srv:"
                + f"{self.variant_chain_id}:{self.residue_id}:"
                + f"{self.wildtype_amino_acid.name}->{self.variant_amino_acid.name}:{self.model_id}"
                )

    def build(
        self,
        feature_modules: List[ModuleType] | ModuleType,
    ) -> Graph:
        #TODO: check how much of this is common with PPI and move it to parent class
        """Builds the graph from the .PDB structure.

        Args:
            feature_modules (List[ModuleType]): Each must implement the :py:func:`add_features` function.

        Returns:
            :class:`Graph`: The resulting :class:`Graph` object with all the features and targets.
        """

        # load .PDB structure
        if isinstance(feature_modules, List):
            pssm_required = conservation in feature_modules
        else:
            pssm_required = conservation == feature_modules
            feature_modules = [feature_modules]
        structure: PDBStructure = self._load_structure(pssm_required)

        # find the variant residue and its surroundings
        variant_residue = None
        for residue in structure.get_chain(self.variant_chain_id).residues:
            residue: Residue
            if (
                residue.number == self.variant_residue_number
                and residue.insertion_code == self.insertion_code
            ):
                variant_residue = residue
                break
        if variant_residue is None:
            raise ValueError(
                f"Residue not found in {self.pdb_path}: {self.variant_chain_id} {self.residue_id}"
            )
        variant = SingleResidueVariant(variant_residue, self.variant_amino_acid)
        residues = get_surrounding_residues(structure, variant_residue, self.radius)

        # build the graph
        if self.resolution == 'residue':
            graph = build_residue_graph(residues, self.get_query_id(), self.distance_cutoff)
        elif self.resolution == 'atomic':
            residues.append(variant_residue)
            atoms = set([])
            for residue in residues:
                if residue.amino_acid is not None:
                    for atom in residue.atoms:
                        atoms.add(atom)
            atoms = list(atoms)
            #TODO: why was this a set at first? I think each atom is unique anyway, given that it has a Residue property

            graph = build_atomic_graph(atoms, self.get_query_id(), self.distance_cutoff)
            #TODO: check if this works with a set instead of a list


        else:
            raise NotImplementedError(f"No function exists to build graphs with resolution of {self.resolution}.")
        graph.center = variant_residue.get_center()

        # add data to the graph
        self._set_graph_targets(graph)
        for feature_module in feature_modules:
            feature_module.add_features(self.pdb_path, graph, variant)

        return graph


@dataclass(kw_only=True)
class ProteinProteinInterfaceQuery(DeepRankQuery):
    """A query that builds a protein-protein interface graph."""

    def __post_init__(self):
        super().__post_init__()

        if len(self.chain_ids) != 2:
            # TODO: Consider throwing a warning instead of error and using the first two entries of the list anyway.
            raise ValueError(f"SingleResidueVariantQuery must contain exactly 2 chain_ids, but {len(self.chain_ids)} were given.")

        if not self.distance_cutoff:
            #TODO: check if we truly need so many different defaults
            if self.resolution == 'atomic':
                self.distance_cutoff = 5.5
            if self.resolution == 'residue':
                self.distance_cutoff = 10

    def get_query_id(self) -> str:
        """Returns the string representing the complete query ID."""
        return (
            f"{self.resolution}-ppi:"  # resolution and query type (ppi for protein protein interface)
            + f"{self.chain_ids[0]}-{self.chain_ids[1]}:{self.model_id}"
        )

    def build(
        self,
        feature_modules: List[ModuleType] | ModuleType,
    ) -> Graph:
        #TODO: check how much of this is common with SRV and move it to parent class
        """Builds the graph from the .PDB structure.

        Args:
            feature_modules (List[ModuleType]): Each must implement the :py:func:`add_features` function.

        Returns:
            :class:`Graph`: The resulting :class:`Graph` object with all the features and targets.
        """

        contact_atoms = get_contact_atoms(self.pdb_path, self.chain_ids, self.distance_cutoff)
        if len(contact_atoms) == 0:
            raise ValueError("no contact atoms found")

        # build the graph
        if self.resolution == 'atomic':
            graph = build_atomic_graph(contact_atoms, self.get_query_id(), self.distance_cutoff)
        elif self.resolution == 'residue':
            residues_selected = {atom.residue for atom in contact_atoms}
            graph = build_residue_graph(list(residues_selected), self.get_query_id(), self.distance_cutoff)
            #TODO: check whether this works with a set instead of a list
        else:
            raise NotImplementedError(f"No function exists to build graphs with resolution of {self.resolution}.")
        graph.center = np.mean([atom.position for atom in contact_atoms], axis=0)

        # add data to the graph
        self._set_graph_targets(graph)

        # read the pssm
        #TODO: unify with the way pssms are read for srv queries
        structure = contact_atoms[0].residue.chain.model

        if not isinstance(feature_modules, List):
            feature_modules = [feature_modules]
        if conservation in feature_modules:
            self._load_pssm_data(structure)

        # add the features
        for feature_module in feature_modules:
            feature_module.add_features(self.pdb_path, graph)

        graph.center = np.mean([atom.position for atom in contact_atoms], axis=0)
        return graph
