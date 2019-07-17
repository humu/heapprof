from struct import unpack
from typing import BinaryIO


def readFixed32(src: BinaryIO) -> int:
    data = src.read(4)
    if len(data) != 4:
        raise EOFError()
    return unpack('>L', data)[0]


def readFixed64(src: BinaryIO) -> int:
    data = src.read(8)
    if len(data) != 8:
        raise EOFError()
    return unpack('>Q', data)[0]


# Max bytes to hold a uint64 in a varint
VARINT_BUFFER_SIZE = 10


def readVarint(src: BinaryIO) -> int:
    result = 0
    bitshift = 0
    while True:
        try:
            value = src.read(1)[0]
        except IndexError:
            raise EOFError()
        result |= (value & 0x7F) << bitshift
        if value & 0x80:
            bitshift += 7
        else:
            return result
