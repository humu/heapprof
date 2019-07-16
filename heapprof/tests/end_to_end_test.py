import os
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
            self.assertFalse(heapprof.isProfiling())
            hpxFile = os.path.join(path, 'hprof')

            heapprof.start(hpxFile)
            self.assertTrue(heapprof.isProfiling())
            list(range(10000))
            heapprof.stop()

            self.assertFalse(heapprof.isProfiling())

            profile = heapprof.HeapProfile(hpxFile)

            # We can't check for absolute equality of the dicts, since the sampling rate stored in
            # the files is uint32-quantized.
            self.assertListEqual(
                sorted(list(heapprof.DEFAULT_SAMPLING_RATE.keys())),
                sorted(list(profile.samplingRate.keys())),
            )
            for key in profile.samplingRate:
                self.assertAlmostEqual(
                    heapprof.DEFAULT_SAMPLING_RATE[key], profile.samplingRate[key]
                )

            # Not really sure how to test the exact contents of this, but let's at least make sure
            # we can iterate the file without crashing.
            self.assertGreater(len(list(profile)), 0)

            history = heapprof.HeapHistory.make(profile)
            self.assertGreaterEqual(len(history.history), 1)


if __name__ == '__main__':
    unittest.main()
