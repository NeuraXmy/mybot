import aiohttp
from typing import List

class IntegerSequence(object):
    def __init__(self, blk):
        self.id = None
        self.name = None
        self.formula = None
        self.sequence = []
        self.comments = ''

        for line in blk:
            data_type = line[1]
            sequence_name = line[3:10]
            data = line[10:].strip()

            if data_type == 'I':
                self.id = sequence_name
            elif data_type == 'S':
                if data[-1] == ',':
                    data = data[:-1]
                self.sequence = [int(num) for num in data.split(',')]
            elif data_type == 'N':
                self.name = data
            elif data_type == 'C':
                self.comments += (data + '\n')
            elif data_type == 'F':
                self.formula = data


class OEISError(Exception):
    def __init__(self, message):
        Exception.__init__(self, message)


async def raw_query(sequence, n=1):
    payload = {}
    payload['q'] = sequence
    payload['n'] = str(n)
    payload['fmt'] = 'text'
    async with aiohttp.ClientSession() as session:
        async with session.get('http://oeis.org/search', params=payload) as response:
            if response.status != 200:
                raise OEISError('Invalid HTTP response from the OEIS')
            return await response.text()


def split_blocks(content):
    blocks = content.split('\n\n')
    return [block for block in blocks if _valid_block(block)]


def _valid_block(block):
    return len(block) > 0 and block[0] == '%'


async def oeis_query(sequence, n=1) -> List[IntegerSequence]:
    content = await raw_query(sequence, n)
    blocks = split_blocks(content)
    return [IntegerSequence(block.split('\n')) for block in blocks]