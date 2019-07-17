import os
import time
import unittest
from tempfile import TemporaryDirectory

import _heapprof
import heapprof


class DigestTest(unittest.TestCase):
    def testDigestion(self) -> None:
        with TemporaryDirectory() as path:
            hpxFile = os.path.join(path, 'hprof')

            # Do something to make a heap profile
            heapprof.start(hpxFile)
            list(range(100000))
            time.sleep(0.05)
            list(range(100000))
            heapprof.stop()

            # Now, make a digest with an interval of 10msec.
            heapprof.makeDigest(hpxFile, 0.01, True)

            # TODO use proper classes for this once we have them
            with open(hpxFile + '.hpc', 'rb') as hpc:
                initialTime, timeInterval, offsets = _heapprof.readDigestMetadata(hpc.fileno())
                self.assertAlmostEqual(timeInterval, 0.01)
                # Because we slept for 50 msec, we should have at least 5 snapshots.
                self.assertGreaterEqual(len(offsets), 5)

                for index, offset in enumerate(offsets):
                    _heapprof.readDigestEntry(hpc.fileno(), offset)


if __name__ == '__main__':
    unittest.main()
