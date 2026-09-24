import sys
import unittest
from pathlib import Path
from fastapi import HTTPException

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app/backend'))
from river_links import _pair


class RiverLinkTests(unittest.TestCase):
    def test_pair_canonicalizes_adjacent_cells(self):
        self.assertEqual(_pair({'q1':2,'r1':3,'q2':1,'r2':3}),(1,3,2,3))

    def test_pair_rejects_nonadjacent_cells(self):
        with self.assertRaises(HTTPException):
            _pair({'q1':2,'r1':3,'q2':5,'r2':3})


if __name__=='__main__':unittest.main()
