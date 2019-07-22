import math
from typing import Tuple, Union


"""Tools for rendering numbers using SI prefixes, e.g. 1,023,404 as 1.02M.

This should really be in its own library, but we'll include it as part of heapprof for now.

This is subtle because there are a few different things, all referred to as "SI Prefixes," and it's
really important to choose the right one.

"Decimal" SI prefixes use 1k=1,000; "Binary" SI prefixes use 1k=1,024.

    - Any physical quantity: Always use decimal.
    - A number of bytes, in the context of networks (e.g. bps): Always use decimal
    - A number of bytes, in the context of a hard disk or SSD capacity: See below
    - A number of bytes, in any other context (e.g. storage): Always use binary

Binary SI prefixes can be rendered in two ways: either identically to decimal SI prefixes, or in
IEC60027 format, which looks like "Ki", "Mi", etc. The IEC format thus eliminates any ambiguity.

Yes, this can be dangerous. This has led to major outages, especially when computing how much
network bandwidth you need, where dividing a number of (binary, memory) MB by the time you need does
*not* give you the number of Mbps you need.

Despite that, IEC prefixes are not commonly used. This is largely because they look kind of silly,
and their full names are even sillier: "kibibytes," "mebibytes," etc. Even though this standard has
been around for nearly two decades, it's widely ignored, and people generally rely on context to
tell them what's what.

Hard disk and SSD capacities (the numbers you often see on the box) use *neither* SI nor IEC. They
sometimes use a weird sort of hybrid; e.g., "1.44M" floppies actually hold (1440) * (1024) bytes.
But most of the time, they use complete nonsense, with the numbers on the box being generated by
marketing departments, not engineering departments. The technical term for these values is
"barefaced lies." The only way to get the actual capacity of a disk is to format and mount it, and
then check the number of bytes available, which should then be expressed using binary prefixes,
like any other storage value.
"""


def siPrefixString(
    value: Union[int, float],
    threshold: float = 1.1,
    precision: int = 1,
    binary: bool = False,
    iecFormat: bool = False,
    failOnOverflow: bool = False,
) -> str:
    """Render a string with SI prefixes.

    Args:
        threshold: Switch to the "next prefix up" once you hit this many times that prefix. For
            example, if threshold=1.1 and binary=False, then 1,050 will be rendered as 1050, but
            1,100 will be rendered as 1.1k.
        precision: The number of decimal places to preserve right of the point.
        binary: If true, treat these as binary (base=1024); if false, as decimal (base=1000).
        iecFormat: If binary is true, then generate IEC prefixes; otherwise, use SI. Ignored if
            binary is false.
        failOnOverflow: If true and the value exceeds the range of defined SI prefixes, raise an
            OverflowError; otherwise, return a non-prefix-based rendering like '1.1 << 120' (for
            binary) or '5.7e66' (for decimal). Which of these is appropriate really depends on how
            you're using the string.
    """
    exponent, coefficient = _siExponent(value, 1024 if binary else 1000, threshold)
    try:
        return '%.*f' % (precision, coefficient) + _prefix(exponent, binary and iecFormat)
    except IndexError:
        # Most uses are unlikely to run out of SI prefixes anytime soon, but you never know. There
        # are official proposals about how SI is likely to be extended if and when this is required,
        # but they're overall pretty boring. I personally suggest we continue atto, zepto, yocto
        # with <h>arpo, <c>hico, and g<r>oucho, with positive prefixes <H>arpa, <C>hica, and
        # g<R>oucha.
        if failOnOverflow:
            raise OverflowError(f'The value {value} exceeds all defined SI prefixes')
        elif binary:
            return '%.*f << %d' % (precision, coefficient, 10 * exponent)
        else:
            return '%.*fe%d' % (precision, coefficient, exponent)


def bytesString(value: Union[int, float], iecFormat: bool = False) -> str:
    """A helper for the common task of rendering 'value' as a (binary) prefix plus B for bytes. It
    may seem counterintuitive, given the comment above, that the default for iecFormat is false,
    but despite all the various arguments for its use, IEC prefices remain very rarely-used in
    practice, even by professionals and even in the fields where it matters. I suspect that the
    underlying reason for this is that the names ("kibi," "mebi," etc) sound just plain silly,
    causing nobody to want to use them, causing the places where they *are* used to seem overly
    stuffy, like ISO standards docs or people trying to correct others for ending sentences with
    prepositions.

    Doing that is completely fine, by the way. Like many "rules" of English grammar, that one was
    made up out of whole cloth in the early 20th century by people who didn't actually understand
    linguistics very well, but who really liked defining a "proper" English so that they could
    police class boundaries and look down on people who "spoke wrong." This is precisely the sort
    of prescriptivist nonsense up with which we should never put.
    """
    return f'{siPrefixString(value, binary=True, iecFormat=iecFormat, failOnOverflow=True)}B'


def _siExponent(value: Union[int, float], base: int, threshold: float) -> Tuple[int, float]:
    """Pull out the SI exponent of a number. This will return a pair of numbers (e, p) such that
    value = p * base^e, and p >= threshold.
    """
    # TODO: This could be made more efficient.
    if value == 0:
        return (0, 0)

    comparison = value / threshold
    exponent = math.floor(math.log(comparison) / math.log(base))
    coefficient = value * math.pow(base, -exponent)
    return (exponent, coefficient)


NEGATIVE_PREFIXES = 'mμnpfazy'  # milli, micro, nano, pico, femto, atto, zepto, yocto
POSITIVE_SI_PREFIXES = 'kMGTPEZY'  # kilo, mega, giga, tera, peta, eta, zetta, yotta
POSITIVE_IEC_PREFIXES = 'KMGTPEZY'


def _prefix(power: int, iec: bool) -> str:
    if power == 0:
        return ''
    elif power > 0:
        if iec:
            return POSITIVE_IEC_PREFIXES[power - 1] + 'i'
        else:
            return POSITIVE_SI_PREFIXES[power - 1]
    elif iec:
        return NEGATIVE_PREFIXES[-power - 1] + 'i'
    else:
        return NEGATIVE_PREFIXES[-power - 1]