import os
import time
import unittest
from tempfile import TemporaryDirectory

import heapprof


class EndToEndTest(unittest.TestCase):
    def testGatherStats(self) -> None:
        # Basically a smoke test -- make sure it runs.
        heapprof.gatherStats()
        self.assertTrue(heapprof.isProfiling())
        list(range(10000))
        heapprof.stop()

    def testHeapProfiler(self) -> None:
        with TemporaryDirectory() as path:
            hpxFile = os.path.join(path, "hprof")

            # Do something to make a heap profile
            heapprof.start(hpxFile)
            list(range(100000))
            time.sleep(0.05)
            list(range(100000))
            heapprof.stop()

            reader = heapprof.Reader(hpxFile)
            # No digest yet, so we can't check elapsed time.
            with self.assertRaises(AssertionError):
                reader.elapsedTime()

            # Make a digest with 10-millisecond intervals and no rounding.
            reader.makeDigest(timeInterval=0.01, precision=0)

            self.assertGreaterEqual(reader.elapsedTime(), 0.05)
            self.assertAlmostEqual(reader.snapshotInterval(), 0.01)
            for index, snapshot in enumerate(reader.snapshots()):
                self.assertAlmostEqual(
                    index * reader.snapshotInterval(), snapshot.relativeTime
                )
                # It would be nice to do some more sophisticated testing here.
                self.assertGreater(len(snapshot.usage), 0)


if __name__ == "__main__":
    unittest.main()
