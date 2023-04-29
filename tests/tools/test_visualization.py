import unittest
import warnings

import h5py
import numpy as np

from deeprankcore.tools.visualization.embedding import manifold_embedding
from deeprankcore.tools.visualization.plotting import (hdf5_to_networkx,
                                                       plotly_2d, plotly_3d)


class TestGraph(unittest.TestCase):
    def setUp(self):
        with h5py.File("tests/data/hdf5/1ATN_ppi.hdf5", "r") as f5:
            self.networkx_graph = hdf5_to_networkx(f5["residue-ppi-1ATN_1w:A-B"])

        self.pdb_path = "tests/data/pdb/1ATN/1ATN_1w.pdb"
        self.reference_path = "tests/data/pdb/1ATN/1ATN_2w.pdb"

    def test_plot_2d(self):
        with warnings.catch_warnings(record=FutureWarning):
            plotly_2d(self.networkx_graph, "1ATN", disable_plot=True)

    def test_plot_3d(self):
        plotly_3d(self.networkx_graph, "1ATN", disable_plot=True)

    def test_embedding(self):
        pos = np.random.rand(110, 3)
        for method in ["tsne", "spectral", "mds"]:
            with warnings.catch_warnings(record=FutureWarning):
                _ = manifold_embedding(pos, method=method)


if __name__ == "__main__":
    unittest.main()
