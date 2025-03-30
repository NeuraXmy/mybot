import dataclasses
import functools
import re
import typing


@dataclasses.dataclass
class Note:
    bar: float
    lane: int
    width: int
    type: int

    def __hash__(self) -> int:
        return hash(str(self))


@dataclasses.dataclass
class Tap(Note):

    def __hash__(self) -> int:
        return hash(str(self))


@dataclasses.dataclass
class Directional(Note):
    tap: typing.Optional[Note] = dataclasses.field(default=None, repr=False)

    def __hash__(self) -> int:
        return hash(str(self))


@dataclasses.dataclass
class Slide(Note):
    channel: int = 0

    tap: typing.Optional[Note] = dataclasses.field(default=None, repr=False)
    directional: typing.Optional[Note] = dataclasses.field(default=None, repr=False)
    next: typing.Optional['Note'] = dataclasses.field(default=None, repr=False)
    head: typing.Optional[Note] = dataclasses.field(default=None, repr=False)

    def __hash__(self) -> int:
        return hash(str(self))

    def is_path_note(self):
        if self.type == 0:
            return False

        if self.type != 3:
            return True

        if self.directional:
            return True

        if self.tap is None and self.directional is None:
            return True

        return False

    def is_among_note(self):
        if self.type == 3:
            return True

        return False


@dataclasses.dataclass
class Event:
    bar: float
    bpm: typing.Optional[float] = None
    bar_length: typing.Optional[int] = None
    sentence_length: int = None
    section: str = None
    text: str = None

    def __or__(self, other):
        assert self.bar <= other.bar
        return Event(
            bar=other.bar,
            bpm=other.bpm or self.bpm,
            bar_length=other.bar_length or self.bar_length,
            sentence_length=other.sentence_length or self.sentence_length,
            section=other.section or self.section,
            text=other.text or self.text,
        )


class Line:
    type: str
    header: str
    data: str

    def __init__(self, line: str):
        line = line.strip()

        if match := re.match(r'^#(\w+)\s+(.*)$', line):
            self.type = 'meta'
            self.header, self.data = match.groups()

        elif match := re.match(r'^#(\w+):\s*(.*)$', line):
            self.type = 'score'
            self.header, self.data = match.groups()

        else:
            self.type = 'comment'
            self.header, self.data = 'comment', line


class Score:

    def __init__(self, lines: list[Line] = None, events: list[Event] = None, notes: list[Note] = None) -> None:
        self.bpm_map = {}
        self.events: list[Event] = []
        self.notes: list[Note] = []

        if lines:
            for line in lines:
                for object in self.parse_line(line):
                    if isinstance(object, Event):
                        self.events.append(object)
                    elif isinstance(object, Note):
                        self.notes.append(object)

        if events:
            self.events += events

        if notes:
            self.notes += notes

        self.notes = sorted(set(self.notes), key=lambda note: note.bar)
        self.notes, self.note_events = self.parse_notes(self.notes, add_slide_intervals=True)

        self.events = sorted(self.events + self.note_events, key=lambda event: event.bar)
        self.events = self.parse_events(self.events)

    def parse_line(self, line: Line):
        if match := re.match(r'^(\d\d\d)02$', line.header):
            yield Event(bar=int(match.group(1)) + 0.0, bar_length=float(line.data))

        elif match := re.match(r'^BPM(..)$', line.header):
            self.bpm_map[match.group(1)] = float(line.data)

        elif match := re.match(r'^(\d\d\d)08$', line.header):
            for beat, data in self.parse_data(line.data):
                yield Event(bar=int(match.group(1)) + beat, bpm=self.bpm_map[data])

        elif match := re.match(r'^(\d\d\d)1(.)$', line.header):
            for beat, data in self.parse_data(line.data):
                yield Tap(bar=int(match.group(1)) + beat, lane=int(match.group(2), 36), width=int(data[1], 36), type=int(data[0], 36))

        elif match := re.match(r'^(\d\d\d)3(.)(.)$', line.header):
            for beat, data in self.parse_data(line.data):
                yield Slide(bar=int(match.group(1)) + beat, lane=int(match.group(2), 36), width=int(data[1], 36), type=int(data[0], 36), channel=int(match.group(3), 36))

        elif match := re.match(r'^(\d\d\d)5(.)$', line.header):
            for beat, data in self.parse_data(line.data):
                yield Directional(bar=int(match.group(1)) + beat, lane=int(match.group(2), 36), width=int(data[1], 36), type=int(data[0], 36))

    @functools.lru_cache()
    def get_time_event(self, bar):
        t = 0.0
        event = Event(bar=0.0, bpm=120.0, bar_length=4.0, sentence_length=4)

        for i in range(len(self.events)):
            event = event | self.events[i]
            if i+1 == len(self.events) or self.events[i+1].bar > bar + 1e-6:
                t += event.bar_length * 60 / event.bpm * (bar - event.bar)
                break
            else:
                t += event.bar_length * 60 / event.bpm * (self.events[i+1].bar - event.bar)

        return t, event

    def get_time(self, bar):
        return self.get_time_event(bar)[0]

    def get_event(self, bar):
        return self.get_time_event(bar)[1]

    def get_time_delta(self, bar_from, bar_to):
        return self.get_time(bar_to) - self.get_time(bar_from)

    @functools.lru_cache()
    def get_bar_event(self, time):
        t = 0.0
        event = Event(bar=0.0, bpm=120.0, bar_length=4.0, sentence_length=4)

        for i in range(len(self.events)):
            event = event | self.events[i]
            if i+1 == len(self.events) or t + event.bar_length * 60 / event.bpm * (self.events[i+1].bar - event.bar) > time:
                break
            else:
                t += event.bar_length * 60 / event.bpm * (self.events[i+1].bar - event.bar)

        bar = event.bar + (time - t) / (event.bar_length * 60 / event.bpm)

        return bar, event

    def get_bar(self, time):
        return self.get_bar_event(time)[0]

    @staticmethod
    def parse_events(sorted_events: list[Event]):
        events: list[Event] = []

        for event in sorted_events:
            if len(events) and '%e' % event.bar == '%e' % events[-1].bar:
                events[-1] |= event
            else:
                events.append(event)

        return events

    @staticmethod
    def parse_notes(sorted_notes: list[Note], add_slide_intervals=False):
        notes: list[Note] = list(sorted_notes)
        note_events: list[Event] = []

        note_dict: dict[float, list[Note]] = {}
        for note in sorted_notes:
            if note.bar not in note_dict:
                note_dict[note.bar] = []
            note_dict[note.bar].append(note)

        for i, note in enumerate(sorted_notes):
            if not 0 <= note.lane - 2 < 12:
                notes.remove(note)
                note_events.append(Event(
                    bar=note.bar,
                    text='SKILL' if note.lane == 0 else 'FEVER CHANCE!' if note.type == 1 else 'SUPER FEVER!!',
                ))

        for i, note in enumerate(sorted_notes):
            if isinstance(note, Directional):
                directional = note

                for note in note_dict[directional.bar]:
                    if isinstance(note, Tap):
                        tap = note
                        if tap.bar == directional.bar and tap.lane == directional.lane and tap.width == directional.width:
                            notes.remove(tap)
                            note_dict[directional.bar].remove(tap)
                            directional.tap = tap
                            break

        for i, note in enumerate(sorted_notes):
            if isinstance(note, Slide):
                slide = note
                if slide.head is None:
                    slide.head = slide

                for note in note_dict[slide.bar]:
                    if isinstance(note, Tap):
                        tap = note
                        if tap.bar == slide.bar and tap.lane == slide.lane and tap.width == slide.width:
                            notes.remove(tap)
                            note_dict[slide.bar].remove(tap)
                            slide.tap = tap
                            break

                for note in note_dict[slide.bar]:
                    if isinstance(note, Directional):
                        directional = note
                        if directional.bar == slide.bar and directional.lane == slide.lane and directional.width == slide.width:
                            notes.remove(directional)
                            note_dict[slide.bar].remove(directional)
                            slide.directional = directional
                            if directional.tap is not None:
                                slide.tap = directional.tap
                            break

                if slide.type != 2:
                    for note in sorted_notes[i+1:]:
                        if isinstance(note, Slide):
                            if note.channel == slide.channel:
                                head = slide.head

                                interval = slide
                                if add_slide_intervals:
                                    bar = slide.bar + 1/8
                                    while bar + 1e-3 < note.bar:
                                        interval_next = Slide(bar, slide.lane, slide.width, 0, slide.channel, head=head)
                                        notes.append(interval_next)
                                        interval.next = interval_next
                                        interval = interval_next
                                        bar += 1/8

                                interval.next = note
                                note.head = slide.head
                                break

        return sorted(notes, key=lambda note: note.bar), note_events

    @staticmethod
    def parse_data(data: str):
        for i in range(0, len(data), 2):
            if data[i: i+2] != '00':
                yield i / (len(data)), data[i: i+2]

    def rebase(self, events: list[Event], offset=0.0) -> 'Score':
        score = Score(events=events)

        for note_0 in self.notes:
            if isinstance(note_0, Tap):
                score.notes.append(dataclasses.replace(
                    note_0,
                    bar=score.get_bar(self.get_time(note_0.bar) - offset),
                ))
            elif isinstance(note_0, Directional):
                score.notes.append(dataclasses.replace(
                    note_0,
                    bar=score.get_bar(self.get_time(note_0.bar) - offset),
                    tap=None,
                ))
                if note_0.tap:
                    score.notes.append(dataclasses.replace(
                        note_0.tap,
                        bar=score.get_bar(self.get_time(note_0.tap.bar) - offset),
                    ))
            elif isinstance(note_0, Slide):
                score.notes.append(dataclasses.replace(
                    note_0,
                    bar=score.get_bar(self.get_time(note_0.bar) - offset),
                    tap=None,
                    directional=None,
                    next=None,
                    head=None,
                ))
                if note_0.tap:
                    score.notes.append(dataclasses.replace(
                        note_0.tap,
                        bar=score.get_bar(self.get_time(note_0.tap.bar) - offset),
                    ))
                if note_0.directional:
                    score.notes.append(dataclasses.replace(
                        note_0.directional,
                        bar=score.get_bar(self.get_time(note_0.directional.bar) - offset),
                        tap=None,
                    ))
                    if note_0.directional.tap and note_0.directional.tap is not note_0.tap:
                        score.notes.append(dataclasses.replace(
                            note_0.directional.tap,
                            bar=score.get_bar(self.get_time(note_0.directional.tap.bar) - offset),
                        ))

        score.notes.sort(key=lambda note: note.bar)
        score.notes, _ = score.parse_notes(score.notes)

        for note_event in self.note_events:
            score.note_events.append(
                dataclasses.replace(
                    note_event,
                    bar=score.get_bar(self.get_time(note_event.bar) - offset),
                )
            )

        score.events = sorted(score.events + score.note_events, key=lambda event: event.bar)
        score.events = score.parse_events(score.events)

        return score

    @functools.lru_cache()
    def note_hands(self, single_hand_max_combo=16):
        @dataclasses.dataclass
        class DPState:
            hard: float

            i: typing.Optional[int] = None
            hand: typing.Optional[int] = None
            j: typing.Optional[int] = None

            def __lt__(self, other):
                return self.hard < other.hard

            def __gt__(self, other):
                return self.hard > other.hard

            def __le__(self, other):
                return self.hard <= other.hard

            def __ge__(self, other):
                return self.hard >= other.hard

            def __eq__(self, other):
                return self.hard == other.hard

        inf = float('inf')

        def hard(note: Note, last: Note, hand: int):
            if last is None:
                return 0.0

            ans = 0

            # interval
            interval = abs(self.get_time(note.bar) - self.get_time(last.bar)) + 1e-3
            if isinstance(last, Directional):
                interval *= 0.95
            if isinstance(last, Slide) and last.type not in (1, 2):
                if last.next is note:
                    interval = interval * 6 + 1
                else:
                    interval *= 0.5
            if isinstance(last, Slide) and last.type == 2:
                interval *= 2

            try:
                if isinstance(note, Slide) and note.type not in (1, 2):
                    ans += max(0, 1 / interval - 1)
                else:
                    ans += max(0, 1 / interval ** 2 - 1)
            except ZeroDivisionError:
                ans += inf

            # lane move
            lane_move = max(
                0,
                abs((note.lane - 2 + note.width / 2) - (last.lane - 2 + last.width / 2)) - 4
            )
            ans = ans * (1 + 0.35 * lane_move / interval ** 0.5)  # + 3 * lane_move / interval ** 0.5

            # hand move
            hand_move = max(
                0,
                hand == 0 and (note.lane - 2 + note.width * 0.25) - 6,
                hand == 1 and 6 - (note.lane - 2 + note.width * 0.75),
            )
            ans = ans * (1 + 0.1 * hand_move ** 2) + 1 * hand_move ** 2

            # reverse slice
            if isinstance(note, Directional):
                reverse_slide = max(
                    0,
                    hand == 0 and note.type == 4,
                    hand == 1 and note.type == 3,
                )
                ans = ans * (1 + 0.02 * reverse_slide) + 6 * reverse_slide

            # right hand
            if hand == 1:
                ans -= 0.000001

            return ans

        dp = [
            [
                [
                    DPState(0.0) if i == 0 and j == 0 else
                    DPState(inf)
                    for j in range(len(self.notes) + 1)
                ] for hand in range(2)
            ] for i in range(len(self.notes))
        ]

        for i, note in enumerate(self.notes):
            for hand in [0, 1]:
                if i == 0:
                    pass

                else:
                    for j in range(max(-1, i - single_hand_max_combo), i):
                        options = [
                            # use the same hand if the last note is the same hand
                            DPState(
                                dp[i-1][hand][j+1].hard + hard(
                                    self.notes[i],
                                    self.notes[i-1] if i-1 != -1 else None,
                                    hand=hand,
                                ),
                                i-1, hand, j,
                            )
                        ] if j+1 != i else [
                            # use the opposite hand
                            *([
                                DPState(
                                    dp[i-1][1-hand][k+1].hard + hard(
                                        self.notes[i],
                                        self.notes[k] if k != -1 else None,
                                        hand=hand,
                                    ),
                                    i-1, 1-hand, k,
                                )
                                for k in range(max(-1, j - single_hand_max_combo), i-1)
                            ])
                        ]

                        dp[i][hand][j+1] = min(options)

        note_hands = [None for _ in range(len(self.notes))]

        ans = DPState(inf)
        index = None
        for hand in [0, 1]:
            for j in range(len(self.notes)+1):
                if ans >= dp[len(self.notes) - 1][hand][j]:
                    ans = dp[len(self.notes) - 1][hand][j]
                    index = hand, j-1

        ans = DPState(ans.hard, len(self.notes) - 1, *index)
        while True:
            for i in range(ans.i, ans.j, -1):
                note_hands[i] = ans.hand

            try:
                ans = dp[ans.i][ans.hand][ans.j+1]
                assert ans.i is not None
            except:
                break

        return note_hands
