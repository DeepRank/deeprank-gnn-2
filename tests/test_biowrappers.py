import unittest
from deeprankcore.tools.BioWrappers import (
    get_bio_model,
    get_depth_res,
    get_depth_contact_res,
    get_hse,
)


class TestBioWrappers(unittest.TestCase):
    def setUp(self):
        self.pdb = "tests/data/pdb/1CRN/1CRN.pdb"

    def test_hse(self):
        model = get_bio_model(self.pdb)
        _ = get_hse(model)

    def test_depth_res(self):
        model = get_bio_model(self.pdb)
        _ = get_depth_res(model)

    @unittest.expectedFailure
    def test_depth_contact_res(self):
        model = get_bio_model(self.pdb)
        _ = get_depth_contact_res(model, [("A", "1")])


if __name__ == "__main__":
    unittest.main()
