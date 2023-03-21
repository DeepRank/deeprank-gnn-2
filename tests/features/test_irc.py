import numpy as np
from . import build_testgraph
from deeprankcore.domain import nodestorage as Nfeat

from deeprankcore.features.irc import add_features
from deeprankcore.utils.graph import Graph


def _run_assertions(graph: Graph):
    assert not np.any(
        [np.isnan(node.features[Nfeat.IRCTOTAL]) 
            for node in graph.nodes]
    ), 'nan found'
    assert np.any(
        [node.features[Nfeat.IRCTOTAL] > 0
            for node in graph.nodes]
    ), 'no contacts'
    
    assert np.all(
        [node.features[Nfeat.IRCTOTAL] == sum(node.features[IRCtype] for IRCtype in Nfeat.IRC_FEATURES[:-1])
            for node in graph.nodes]
    ), 'incorrect total'
    

def test_irc_residue():
    pdb_path = "tests/data/pdb/1ATN/1ATN_1w.pdb"
    graph = build_testgraph(pdb_path, 8.5, 'residue')

    add_features(pdb_path, graph)
    _run_assertions(graph)


def test_irc_atom():
    pdb_path = "tests/data/pdb/1A0Z/1A0Z.pdb"
    graph = build_testgraph(pdb_path, 4.5, 'atom')

    add_features(pdb_path, graph)
    _run_assertions(graph)
