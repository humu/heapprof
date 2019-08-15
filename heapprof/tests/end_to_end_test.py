import os
import sys
import time
import unittest
from tempfile import TemporaryDirectory

import heapprof


def hexdump(filename: str) -> None:
    print(filename)
    offset = 0
    with open(filename, 'rb') as input:
        data = input.read(16)
        sys.stdout.write(f'{offset:04x}')
        for pos, char in enumerate(data):
            if pos % 8 == 0:
                sys.stdout.write(' ')
            sys.stdout.write(f' {char:02x}')
        sys.stdout.write('\n')


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
            list(range(100_000))
            time.sleep(0.05)
            list(range(100_000))
            heapprof.stop()

            reader = heapprof.Reader(hpxFile)
            # No digest yet, so we can't check elapsed time.
            with self.assertRaises(AssertionError):
                reader.elapsedTime()

            hexdump(hpxFile + '.hpm')

            # Make a digest with 10-millisecond intervals and no rounding.
            reader.makeDigest(timeInterval=0.01, precision=0)

            self.assertGreaterEqual(reader.elapsedTime(), 0.05)
            self.assertAlmostEqual(reader.snapshotInterval(), 0.01)
            for index, snapshot in enumerate(reader.snapshots()):
                self.assertAlmostEqual(index * reader.snapshotInterval(), snapshot.relativeTime)
                # It would be nice to do some more sophisticated testing here.
                self.assertGreater(len(snapshot.usage), 0)


if __name__ == "__main__":
    unittest.main()
