from pathlib import Path
from typing import Optional
from typing import Tuple
from typing import Union
from pdb2sql import pdb2sql
from deeprank2.molstruct.aminoacid import AminoAcid
from deeprank2.molstruct.residue import Residue
from deeprank2.molstruct.residue import SingleResidueVariant
from deeprank2.molstruct.structure import Chain
from deeprank2.molstruct.structure import PDBStructure
from deeprank2.utils.buildgraph import get_residue_contact_pairs
from deeprank2.utils.buildgraph import get_structure
from deeprank2.utils.buildgraph import get_surrounding_residues
from deeprank2.utils.graph import Graph
from deeprank2.utils.graph import build_atomic_graph
from deeprank2.utils.graph import build_residue_graph
from deeprank2.utils.parsing.pssm import parse_pssm


def _get_residue(chain: Chain, number: int) -> Residue:
    """Get the Residue from its Chain and number."""
    for residue in chain.residues:
        if residue.number == number:
            return residue
    raise ValueError(f"Not found: {number}")


def build_testgraph(  # pylint: disable=too-many-locals, too-many-arguments # noqa:MC0001
    pdb_path: str,
    cutoff: float,
    detail: str,
    central_res: Optional[int] = None,
    variant: Optional[AminoAcid] = None,
    chain_ids: Optional[Union[str, Tuple[str, str]]] = None,
) -> Union[Graph, Tuple[Graph, SingleResidueVariant]]:
    """Creates a Graph object for feature tests.

    Args:
        pdb_path (str): Path of pdb file.
        cutoff (float): Cutoff distance of the graph (also used as radius for single-chain graphs).
        detail (str): Level of detail. Accepted values are: 'residue' or 'atom'.
        central_res (Optional[int], optional): Residue to center a single-chain graph around.
            Use None to create a 2-chain graph, or any value for a single-chain graph
            Defaults to None.
        variant (Optional[AminoAcid], optional): Amino acid to use as a variant amino acid.
            Defaults to None.
        chain_ids (Optional[Union[str, Tuple[str, str]]], optional): Explicitly specify which chain(s) to use.
            Defaults to None, which will use the first (two) chain(s) from the structure.

    Raises:
        TypeError: if detail is set to anything other than 'residue' or 'atom'

    Returns:
        Graph: As generated by build_residue_graph or build_atomic_graph
        SingleResidueVariant: Only resturned if central_res is not None
    """
    pdb = pdb2sql(pdb_path)
    try:
        structure: PDBStructure = get_structure(pdb, Path(pdb_path).stem)
    finally:
        pdb._close()  # pylint: disable=protected-access

    if not central_res:  # pylint: disable=no-else-raise
        nodes = set([])
        if not chain_ids:
            chains = (structure.chains[0].id, structure.chains[1].id)
        else:
            chains = [structure.get_chain(chain_id) for chain_id in chain_ids]
        for residue1, residue2 in get_residue_contact_pairs(pdb_path, structure, chains[0], chains[1], cutoff):
            if detail == "residue":
                nodes.add(residue1)
                nodes.add(residue2)

            elif detail == "atom":
                for atom in residue1.atoms:
                    nodes.add(atom)
                for atom in residue2.atoms:
                    nodes.add(atom)

        if detail == "residue":
            return build_residue_graph(list(nodes), structure.id, cutoff)
        if detail == "atom":
            return build_atomic_graph(list(nodes), structure.id, cutoff)
        raise TypeError('detail must be "atom" or "residue"')

    else:
        if not chain_ids:
            chain: Chain = structure.chains[0]
        else:
            chain = structure.get_chain(chain_ids)
        residue = _get_residue(chain, central_res)
        surrounding_residues = list(get_surrounding_residues(structure, residue, cutoff))

        try:
            with open(f"tests/data/pssm/{structure.id}/{structure.id}.{chain.id}.pdb.pssm", "rt", encoding="utf-8") as f:
                chain.pssm = parse_pssm(f, chain)
        except FileNotFoundError:
            pass

        if detail == "residue":
            return build_residue_graph(surrounding_residues, structure.id, cutoff), SingleResidueVariant(residue, variant)
        if detail == "atom":
            atoms = set(atom for residue in surrounding_residues for atom in residue.atoms)
            return build_atomic_graph(list(atoms), structure.id, cutoff), SingleResidueVariant(residue, variant)
        raise TypeError('detail must be "atom" or "residue"')
