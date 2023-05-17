import os
import unittest
from shutil import rmtree
from tempfile import mkdtemp

import h5py
import numpy as np
import pandas as pd
from torch_geometric.loader import DataLoader

from deeprankcore.dataset import GraphDataset, GridDataset, save_hdf5_keys
from deeprankcore.domain import edgestorage as Efeat
from deeprankcore.domain import nodestorage as Nfeat
from deeprankcore.domain import targetstorage as targets

node_feats = [Nfeat.RESTYPE, Nfeat.POLARITY, Nfeat.BSA, Nfeat.RESDEPTH, Nfeat.HSE, Nfeat.INFOCONTENT, Nfeat.PSSM]

def _cal_mean_std( # noqa: MC0001, pylint: disable=too-many-locals
                       hdf5_path: str,
                       features_transform:dict,
                       feat:str
    ):

        df_final = pd.DataFrame()

        for fname in hdf5_path:
            with h5py.File(fname, 'r') as f:
                entry_names = [entry for entry, _ in f.items()]

                df_dict = {}
                df_dict['id'] = entry_names

                transform = False
                transform = features_transform.get(feat, {}).get('transform')
                        
                df_dict[feat] = [
                    f[entry_name][Nfeat.NODE][feat][:]
                    if f[entry_name][Nfeat.NODE][feat][()].ndim == 1
                    else f[entry_name][Nfeat.NODE][feat][()] for entry_name in entry_names]
                #apply transformation
                if transform:
                    df_dict[feat]=[transform(row) for row in df_dict[feat]]
                
                df = pd.DataFrame(data=df_dict)

            df_final = pd.concat([df_final, df])

        df_final.reset_index(drop=True, inplace=True)
        df = df_final
        
        means = {col: round(np.concatenate(df[col].values).mean(), 1) if isinstance(df[col].values[0], np.ndarray) \
            else round(df[col].values.mean(), 1) \
            for col in df.columns[1:]}
        devs = {col: round(np.concatenate(df[col].values).std(), 1) if isinstance(df[col].values[0], np.ndarray) \
            else round(df[col].values.std(), 1) \
            for col in df.columns[1:]}
        
        means_devs=[means,devs]

        return means_devs

class TestDataSet(unittest.TestCase):
    def setUp(self):
        self.hdf5_path = "tests/data/hdf5/1ATN_ppi.hdf5"

    def test_collates_entry_names_datasets(self):

        for dataset_name, dataset in [("GraphDataset", GraphDataset(self.hdf5_path,
                                                                    node_features=node_feats,
                                                                    edge_features=[Efeat.DISTANCE],
                                                                    target=targets.IRMSD)),
                                      ("GridDataset", GridDataset(self.hdf5_path,
                                                                  features=[Efeat.VDW],
                                                                  target=targets.IRMSD))]:

            entry_names = []
            for batch_data in DataLoader(dataset, batch_size=2, shuffle=True):
                entry_names += batch_data.entry_names

            assert set(entry_names) == set(['residue-ppi-1ATN_1w:A-B',
                                            'residue-ppi-1ATN_2w:A-B',
                                            'residue-ppi-1ATN_3w:A-B',
                                            'residue-ppi-1ATN_4w:A-B']), f"entry names of {dataset_name} were not collated correctly"

    def test_datasets(self):
        dataset_graph = GraphDataset(
            hdf5_path=self.hdf5_path,
            node_features=node_feats,
            edge_features=[Efeat.DISTANCE],
            target=targets.IRMSD,
            subset=None,
        )

        dataset_grid = GridDataset(
            hdf5_path=self.hdf5_path,
            features=[Efeat.DISTANCE, Efeat.COVALENT, Efeat.SAMECHAIN],
            target=targets.IRMSD,
            subset=None,
        )

        assert len(dataset_graph) == 4
        assert dataset_graph[0] is not None
        assert len(dataset_grid) == 4
        assert dataset_grid[0] is not None
    
    def test_regression_griddataset(self):
        dataset = GridDataset(
            hdf5_path=self.hdf5_path,
            features=[Efeat.VDW, Efeat.ELEC],
            target=targets.IRMSD
        )

        assert len(dataset) == 4

        # 1 entry, 2 features with grid box dimensions
        assert dataset[0].x.shape == (1, 2, 20, 20, 20), f"got features shape {dataset[0].x.shape}"

        # 1 entry with rmsd value
        assert dataset[0].y.shape == (1,)

    def test_classification_griddataset(self):
        dataset = GridDataset(
            hdf5_path=self.hdf5_path,
            features=[Efeat.VDW, Efeat.ELEC],
            target=targets.BINARY
        )

        assert len(dataset) == 4

        # 1 entry, 2 features with grid box dimensions
        assert dataset[0].x.shape == (1, 2, 20, 20, 20), f"got features shape {dataset[0].x.shape}"

        # 1 entry with class value
        assert dataset[0].y.shape == (1,)

    def test_filter_graphdataset(self):
        GraphDataset(
            hdf5_path=self.hdf5_path,
            node_features=node_feats,
            edge_features=[Efeat.DISTANCE],
            target=targets.IRMSD,
            subset=None,
            target_filter={targets.IRMSD: "<10"},
        )

    def test_multi_file_graphdataset(self):
        dataset = GraphDataset(
            hdf5_path=["tests/data/hdf5/train.hdf5", "tests/data/hdf5/valid.hdf5"],
            node_features=node_feats,
            edge_features=[Efeat.DISTANCE],
            target=targets.BINARY
        )

        assert dataset.len() > 0
        assert dataset.get(0) is not None

    def test_save_external_links_graphdataset(self):
        n = 2

        with h5py.File("tests/data/hdf5/test.hdf5", 'r') as hdf5:
            original_ids = list(hdf5.keys())
        
        save_hdf5_keys("tests/data/hdf5/test.hdf5", original_ids[:n], "tests/data/hdf5/test_resized.hdf5")

        with h5py.File("tests/data/hdf5/test_resized.hdf5", 'r') as hdf5:
            new_ids = list(hdf5.keys())
            assert all(isinstance(hdf5.get(key, getlink=True), h5py.ExternalLink) for key in hdf5.keys())
  
        assert len(new_ids) == n
        for new_id in new_ids:
            assert new_id in original_ids

    def test_save_hard_links_graphdataset(self):
        n = 2

        with h5py.File("tests/data/hdf5/test.hdf5", 'r') as hdf5:
            original_ids = list(hdf5.keys())
        
        save_hdf5_keys("tests/data/hdf5/test.hdf5", original_ids[:n], "tests/data/hdf5/test_resized.hdf5", hardcopy = True)

        with h5py.File("tests/data/hdf5/test_resized.hdf5", 'r') as hdf5:
            new_ids = list(hdf5.keys())
            assert all(isinstance(hdf5.get(key, getlink=True), h5py.HardLink) for key in hdf5.keys())
  
        assert len(new_ids) == n
        for new_id in new_ids:
            assert new_id in original_ids

    def test_subset_graphdataset(self):
        hdf5 = h5py.File("tests/data/hdf5/train.hdf5", 'r')  # contains 44 datapoints
        hdf5_keys = list(hdf5.keys())
        n = 10
        subset = hdf5_keys[:n]

        dataset = GraphDataset(
            hdf5_path="tests/data/hdf5/train.hdf5",
            subset=subset,
        )

        assert n == len(dataset)

        hdf5.close()

    def test_target_transform_graphdataset(self):

        dataset = GraphDataset(
            hdf5_path = "tests/data/hdf5/train.hdf5",
            target = targets.BA, # continuous values --> regression
            target_transform = True
        )

        for i in range(len(dataset)):
            assert(0 <= dataset.get(i).y <= 1)

    def test_invalid_target_transform_graphdataset(self):

        dataset = GraphDataset(
            hdf5_path = "tests/data/hdf5/train.hdf5",
            target = targets.BINARY, # --> classification
            target_transform = True # only for regression
        )

        with self.assertRaises(ValueError):
            dataset.get(0)

    def test_size_graphdataset(self):
        hdf5_paths = ["tests/data/hdf5/train.hdf5", "tests/data/hdf5/valid.hdf5", "tests/data/hdf5/test.hdf5"]
        dataset = GraphDataset(
            hdf5_path=hdf5_paths,
            node_features=node_feats,
            edge_features=[Efeat.DISTANCE],
            target=targets.BINARY
        )
        n = 0
        for hdf5 in hdf5_paths:
            with h5py.File(hdf5, 'r') as hdf5_r:
                n += len(hdf5_r.keys())      
        assert len(dataset) == n, f"total data points got was {len(dataset)}"
    
    def test_hdf5_to_pandas_graphdataset(self):

        hdf5_path = "tests/data/hdf5/train.hdf5"
        dataset = GraphDataset(
            hdf5_path = hdf5_path,
            node_features='charge',
            edge_features=['distance', 'same_chain'],
            target='binary'
        )
        dataset.hdf5_to_pandas()
        cols = list(dataset.df.columns)
        cols.sort()
        
        # assert dataset and df shapes
        assert dataset.df.shape[0] == len(dataset)
        assert dataset.df.shape[1] == 5
        assert cols == ['binary', 'charge', 'distance', 'id', 'same_chain']

        # assert dataset and df values
        with h5py.File(hdf5_path, 'r') as f5:

            # getting nodes values with get()
            tensor_idx = 0
            features_dict = {}
            for feat in dataset.node_features:
                vals = f5[list(f5.keys())[0]][f"{Nfeat.NODE}/{feat}"][()]
                if vals.ndim == 1: # features with only one channel
                    arr = []
                    for entry_idx in range(len(dataset)):
                        arr.append(dataset.get(entry_idx).x[:, tensor_idx])
                    arr = np.concatenate(arr)
                    features_dict[feat] = arr
                    tensor_idx += 1
                else:
                    for ch in range(vals.shape[1]):
                        arr = []
                        for entry_idx in range(len(dataset)):
                            arr.append(dataset.get(entry_idx).x[:, tensor_idx])
                        tensor_idx += 1
                        arr = np.concatenate(arr)
                        features_dict[feat + f'_{ch}'] = arr

            for feat, values in features_dict.items():
                assert np.allclose(values, np.concatenate(dataset.df[feat].values))

            # getting edges values with get()
            tensor_idx = 0
            features_dict = {}
            for feat in dataset.edge_features:
                vals = f5[list(f5.keys())[0]][f"{Efeat.EDGE}/{feat}"][()]
                if vals.ndim == 1: # features with only one channel
                    arr = []
                    for entry_idx in range(len(dataset)):
                        arr.append(dataset.get(entry_idx).edge_attr[:, tensor_idx])
                    arr = np.concatenate(arr)
                    features_dict[feat] = arr
                    tensor_idx += 1
                else:
                    for ch in range(vals.shape[1]):
                        arr = []
                        for entry_idx in range(len(dataset)):
                            arr.append(dataset.get(entry_idx).edge_attr[:, tensor_idx])
                        tensor_idx += 1
                        arr = np.concatenate(arr)
                        features_dict[feat + f'_{ch}'] = arr

            for feat, values in features_dict.items():
                # edge_attr contains stacked edges (doubled) so we test on mean and std
                assert np.float32(round(values.mean(), 2)) == np.float32(round(np.concatenate(dataset.df[feat].values).mean(), 2))
                assert np.float32(round(values.std(), 2)) == np.float32(round(np.concatenate(dataset.df[feat].values).std(), 2))
        
        # assert dataset and df shapes in subset case
        with h5py.File(hdf5_path, 'r') as f:
            keys = list(f.keys())

        dataset = GraphDataset(
            hdf5_path = hdf5_path,
            node_features='charge',
            edge_features=['distance', 'same_chain'],
            target='binary',
            subset=keys[2:]
        )
        dataset.hdf5_to_pandas()

        assert dataset.df.shape[0] == len(keys[2:])

    def test_save_hist_graphdataset(self):

        output_directory = mkdtemp()
        fname = os.path.join(output_directory, "test.png")
        hdf5_path = "tests/data/hdf5/test.hdf5"

        dataset = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary'
        )

        with self.assertRaises(ValueError):
            dataset.save_hist(['non existing feature'], fname = fname)

        dataset.save_hist(['charge', 'binary'], fname = fname)

        assert len(os.listdir(output_directory)) > 0

        rmtree(output_directory)
    
    def test_standardize_graphdataset(self):# noqa: MC0001, pylint: disable=too-many-locals

        hdf5_path = "tests/data/hdf5/train.hdf5"

        features_transform = {'bsa': {'standardize': True},
                        'sasa': {'standardize': True},
                        'hb_donors':{'standardize': False},
                        'hse': {'standardize': True}}
        
        dataset = GraphDataset(
            hdf5_path = "tests/data/hdf5/train.hdf5",
            target = 'binary',
            features_transform = features_transform
        )

        with h5py.File(hdf5_path, 'r') as f5:
            grp = f5[list(f5.keys())[0]]

            # getting all node features values
            tensor_idx = 0
            features_dict = {}
            for feat in dataset.node_features:
                vals = grp[f"{Nfeat.NODE}/{feat}"][()]
                if vals.ndim == 1: # features with only one channel
                    arr = []
                    for entry_idx in range(len(dataset)):
                        arr.append(dataset.get(entry_idx).x[:, tensor_idx]) 
                    arr = np.concatenate(arr)
                    features_dict[feat] = arr
                    tensor_idx += 1
                else:
                    for ch in range(vals.shape[1]):
                        arr = []
                        for entry_idx in range(len(dataset)):
                            arr.append(dataset.get(entry_idx).x[:, tensor_idx]) 
                        tensor_idx += 1
                        arr = np.concatenate(arr)
                        features_dict[feat + f'_{ch}'] = arr

            # getting all edge features values
            tensor_idx = 0
            for feat in dataset.edge_features:
                vals = grp[f"{Efeat.EDGE}/{feat}"][()]
                if vals.ndim == 1: # features with only one channel
                    arr = []
                    for entry_idx in range(len(dataset)):
                        arr.append(dataset.get(entry_idx).edge_attr[:, tensor_idx]) 
                    arr = np.concatenate(arr)
                    features_dict[feat] = arr
                    tensor_idx += 1
                else:
                    for ch in range(vals.shape[1]):
                        arr = []
                        for entry_idx in range(len(dataset)):
                            arr.append(dataset.get(entry_idx).edge_attr[:, tensor_idx]) 
                        tensor_idx += 1
                        arr = np.concatenate(arr)
                        features_dict[feat + f'_{ch}'] = arr

            for key, values in features_dict.items():
                if(key in features_transform):
                    standardization = features_transform.get(key, {}).get('standardize')
                    if standardization: #Feature contains in dictionary & standardization=True
                        mean = values.mean()
                        dev = values.std()
                        assert -0.2 < mean < 0.2
                        assert 0.8 < dev < 1.2

    def test_standardization_logic_graphdataset(self):

        hdf5_path = "tests/data/hdf5/train.hdf5"
        features_transform={'all':{'transform':None,'standardize':True}}
        features_transform_nostandardize={'all':{'transform':None,'standardize':False}}
        
        # features_transform setted only in train
        dataset_train = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary',
            features_transform=features_transform
        )

        dataset_test = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary',
            train=False,
            dataset_train=dataset_train
        )
        
        assert dataset_train.features_transform == dataset_test.features_transform
        assert dataset_train.means == dataset_test.means
        assert dataset_train.devs == dataset_test.devs

        # features_transform setted in train
        dataset_train = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary',
            features_transform=features_transform
        )
        # features_transform setted in test and should be ignore
        dataset_test = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary',
            train=False,
            dataset_train=dataset_train,
            features_transform=features_transform_nostandardize
        )
        
        assert dataset_train.features_transform == dataset_test.features_transform
        assert dataset_train.means == dataset_test.means
        assert dataset_train.devs == dataset_test.devs
        
        # without specifying features_transform in training set
        dataset_train = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary'
        )

        dataset_test = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary',
            train=False,
            dataset_train=dataset_train
        )
        # mean and devs should be None
        assert dataset_train.means == dataset_test.means
        assert dataset_train.devs == dataset_test.devs
        assert dataset_train.means == None
        assert dataset_train.devs == None

        # raise error if dataset_train is not provided
        with self.assertRaises(TypeError):
            GraphDataset(
                hdf5_path = hdf5_path,
                target='binary',
                train=False
            )

        # raise error if dataset_train is of the wrong type
        with self.assertRaises(TypeError):

            dataset_train = GridDataset(
                hdf5_path = "tests/data/hdf5/1ATN_ppi.hdf5",
                target='binary'
            )

            GraphDataset(
                hdf5_path = hdf5_path,
                target='binary',
                train=False,
                dataset_train=dataset_train
            )
            
    def test_feature_transform_mean_std(self):
        hdf5_path = "tests/data/hdf5/train.hdf5"
        features_transform={'bsa':{'transform':lambda t:np.log(t+1),'standardize':True}}
        
        dataset_test_transform = GraphDataset(
            hdf5_path = hdf5_path,
            target='binary',
            node_features = ['bsa'],
            edge_features =[],
            features_transform=features_transform
        )
        
        means_devs=_cal_mean_std(hdf5_path,features_transform,'bsa')
        
        assert means_devs[0] == dataset_test_transform.means
        assert means_devs[1] == dataset_test_transform.devs

if __name__ == "__main__":
    unittest.main()
    