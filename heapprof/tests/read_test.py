import io
import unittest

from heapprof._read import readVarint


class ReadTest(unittest.TestCase):
    def testReadVarint(self):
        self.assertEqual(0x15, readVarint(io.BytesIO(b'\x15')))
        self.assertEqual(196, readVarint(io.BytesIO(b'\xc4\x01')))


if __name__ == '__main__':
    unittest.main()
