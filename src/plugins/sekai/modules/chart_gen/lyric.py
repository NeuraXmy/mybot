import dataclasses
import re


@dataclasses.dataclass
class Word:
    bar: float
    text: str


def load_lyric(lines):
    words: list[Word] = []

    for line in lines:
        line = line.strip()
        if match := re.match(r'^(\d+): (.*)$', line):
            bar = int(match.group(1))
            texts = match.group(2).split('/')
            for i, text in enumerate(texts):
                if text:
                    words.append(Word(
                        bar=bar + i / len(texts),
                        text=text
                    ))

    return words
