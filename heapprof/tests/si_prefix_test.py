import unittest

from heapprof._si_prefix import siPrefixString


class SIPrefixTest(unittest.TestCase):
    def testDecimal(self):
        self.assertEqual('1050.00', siPrefixString(1050, threshold=1.1, precision=2))
        self.assertEqual('1.05k', siPrefixString(1050, threshold=1.05, precision=2))
        self.assertEqual('1.1', siPrefixString(1.1, threshold=1.1, precision=1))
        self.assertEqual('2.0M', siPrefixString(2000000, threshold=1.1, precision=1))
        self.assertEqual('500m', siPrefixString(0.5, threshold=1.1, precision=0))
        self.assertEqual('1.1μ', siPrefixString(1.1e-6, threshold=1.1, precision=1))

    def testBinary(self):
        self.assertEqual('1050.00', siPrefixString(1050, threshold=1.1, precision=2, binary=True))
        self.assertEqual('1.1k', siPrefixString(1130, threshold=1.1, precision=1, binary=True))
        self.assertEqual('1.1', siPrefixString(1.1, threshold=1.1, precision=1, binary=True))
        self.assertEqual(
            '2.0M', siPrefixString(2 * 1024 * 1024, threshold=1.1, precision=1, binary=True)
        )
        # NB that 0.5 = 512 * (1024)^-1.
        self.assertEqual('512m', siPrefixString(0.5, threshold=1.1, precision=0, binary=True))
        self.assertEqual('1.2μ', siPrefixString(1.1e-6, threshold=1.1, precision=1, binary=True))

    def testIEC(self):
        self.assertEqual(
            '1050.00', siPrefixString(1050, threshold=1.1, precision=2, binary=True, iecFormat=True)
        )
        self.assertEqual(
            '1.1Ki', siPrefixString(1130, threshold=1.1, precision=1, binary=True, iecFormat=True)
        )
        self.assertEqual(
            '1.1', siPrefixString(1.1, threshold=1.1, precision=1, binary=True, iecFormat=True)
        )
        self.assertEqual(
            '2.0Mi',
            siPrefixString(
                2 * 1024 * 1024, threshold=1.1, precision=1, binary=True, iecFormat=True
            ),
        )
        self.assertEqual(
            '512mi', siPrefixString(0.5, threshold=1.1, precision=0, binary=True, iecFormat=True)
        )
        self.assertEqual(
            '1.2μi', siPrefixString(1.1e-6, threshold=1.1, precision=1, binary=True, iecFormat=True)
        )


if __name__ == '__main__':
    unittest.main()
