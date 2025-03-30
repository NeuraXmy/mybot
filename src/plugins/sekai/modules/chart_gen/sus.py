import math
import json

import svgwrite
import svgwrite.text
import svgwrite.image
import svgwrite.path
import svgwrite.shapes

from .score import *
from .lyric import *


def get_denominator(x: float):
    ans, remainder = 1000, 1000

    for y in [
        1, 2, 4, 8, 16, 32, 64,
        3, 6, 12, 24, 48, 96,
        5, 10, 20, 40, 80,
    ]:
        r = min((x * y) % 1, (-x * y) % 1)
        if r < remainder:
            ans, remainder = y, r
        if r < remainder + 1e-3 and y < ans:
            ans, remainder = y, r

    return ans


@dataclasses.dataclass
class Meta:
    title: typing.Optional[str] = None
    subttile: typing.Optional[str] = None
    artist: typing.Optional[str] = None
    genre: typing.Optional[str] = None
    designer: typing.Optional[str] = None
    difficulty: typing.Optional[str] = None
    playlevel: typing.Optional[str] = None
    songid: typing.Optional[str] = None
    wave: typing.Optional[str] = None
    waveoffset: typing.Optional[str] = None
    jacket: typing.Optional[str] = None
    background: typing.Optional[str] = None
    movie: typing.Optional[str] = None
    movieoffset: typing.Optional[float] = None
    basebpm: typing.Optional[float] = None
    requests: list = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class CoverObject:
    bar_from: typing.Optional[float] = None
    css_class: typing.Optional[str] = None


@dataclasses.dataclass
class CoverRect(CoverObject):
    bar_to: typing.Optional[float] = None


@dataclasses.dataclass
class CoverText(CoverObject):
    text: typing.Optional[str] = None


class SUS:
    pixel_per_second = 240
    lane_size = 12

    note_width = 8
    note_height = 16

    flick_width = 24
    flick_height = 16

    n_lanes = 12
    padding = 36
    padding_slides = -1

    meta_size = 120

    def __init__(
            self,
            lines: list[str],
            note_size=1.0,
            note_host='https://asset3.pjsekai.moe/notes',
            **kwargs,
    ) -> None:
        if kwargs['playlevel'] == '?':
            self.pixel_per_second = 340
        elif 30 < kwargs['playlevel'] <= 33:
            self.pixel_per_second += (kwargs['playlevel'] - 30) * 25
        elif kwargs['playlevel'] > 33:
            self.pixel_per_second = 340

        self.meta_lines: list[Line] = []
        self.score_lines: list[Line] = []

        for line in lines:
            line = Line(line)
            if line.type == 'meta':
                self.meta_lines.append(line)
            elif line.type == 'score':
                self.score_lines.append(line)

        self.score = Score(self.score_lines)
        self.meta = Meta()

        for meta_line in self.meta_lines:
            header = meta_line.header.lower()
            try:
                data = eval(meta_line.data)
            except:
                data = meta_line.data
            if hasattr(self.meta, header):
                setattr(self.meta, header, data)

        for header, data in kwargs.items():
            if hasattr(self.meta, header):
                setattr(self.meta, header, data)

        self.note_size = note_size
        self.note_host = note_host

        self.words: list[Word] = []

        self.special_cover_objects: list[CoverObject] = []
        self.music_meta = kwargs['meta']

    def __getitem__(self, key: slice) -> svgwrite.Drawing:
        bar_from = key.start or 0
        bar_to = key.stop or int(self.score.notes[-1].bar + 1)

        slide_paths = []
        among_images = []

        def add_slide_path(note: Slide):
            next: Slide = note.next
            while not next.is_path_note():
                next = next.next

            ease_in = note.directional and note.directional.type in (2,)
            ease_out = note.directional and note.directional.type in (5, 6)

            y = self.pixel_per_second * self.score.get_time_delta(note.bar, bar_to) + self.padding
            y_next = self.pixel_per_second * self.score.get_time_delta(next.bar, bar_to) + self.padding

            # Bézier curve:
            # left: from l[0], controlled by l[1] and l[2], to l[3]
            # right: from r[0], controlled by r[1] and r[2], to r[3]

            l = [(
                self.lane_size * (note.lane - 2) + self.padding - self.padding_slides,
                y,
            ), (
                self.lane_size * (note.lane - 2) + self.padding - self.padding_slides,
                (y + y_next) / 2 if ease_in else y,
            ), (
                self.lane_size * (next.lane - 2) + self.padding - self.padding_slides,
                (y + y_next) / 2 if ease_out else y_next,
            ), (
                self.lane_size * (next.lane - 2) + self.padding - self.padding_slides,
                y_next,
            )]
            r = [(
                self.lane_size * (note.lane - 2 + note.width) + self.padding + self.padding_slides,
                y,
            ), (
                self.lane_size * (note.lane - 2 + note.width) + self.padding + self.padding_slides,
                (y + y_next) / 2 if ease_in else y,
            ), (
                self.lane_size * (next.lane - 2 + next.width) + self.padding + self.padding_slides,
                (y + y_next) / 2 if ease_out else y_next,
            ), (
                self.lane_size * (next.lane - 2 + next.width) + self.padding + self.padding_slides,
                y_next,
            )]

            slide_paths.append(svgwrite.path.Path(
                d=[
                    ('M', list(map(round, [*l[0]]))),
                    ('C', list(map(round, [*l[1], *l[2], *l[3]]))),
                    ('L', list(map(round, [*r[3]]))),
                    ('C', list(map(round, [*r[2], *r[1], *r[0]]))),
                    ('z'),
                ],
                class_='slide' if not note.head.tap or note.head.tap.type == 1 else 'slide-critical'),
            )

            def binary_solution_for_x(y, curve: list[tuple], s: slice = None, e=0.1):
                if s is None:
                    s = slice(0, 1)

                t = (s.start + s.stop) / 2
                p = [(
                        curve[0][k] * (1 - t) ** 3 * t ** 0 * 1 +
                        curve[1][k] * (1 - t) ** 2 * t ** 1 * 3 +
                        curve[2][k] * (1 - t) ** 1 * t ** 2 * 3 +
                        curve[3][k] * (1 - t) ** 0 * t ** 3 * 1
                ) for k in range(2)]

                # print(y, s, p)

                if y - e < p[1] < y + e:
                    return p[0]
                elif p[1] > y:
                    return binary_solution_for_x(y, curve, slice(t, s.stop))
                elif p[1] < y:
                    return binary_solution_for_x(y, curve, slice(s.start, t))
                else:
                    raise NotImplementedError

            among: Slide = note.next
            while True:
                if not among or among.type == 2 or among.bar > next.bar:
                    break

                if among.is_among_note():
                    y = self.pixel_per_second * self.score.get_time_delta(among.bar, bar_to) + self.padding
                    x_l = binary_solution_for_x(y, l)
                    x_r = binary_solution_for_x(y, r)
                    x = (x_l + x_r) / 2

                    among_images.append(svgwrite.image.Image(
                        href='%s/notes_long_among%s.png' % (
                            self.note_host,
                            '' if not note.head.tap or note.head.tap.type == 1 else '_crtcl',
                        ),
                        insert=(
                            round(x - self.lane_size / 2),
                            round(y - self.lane_size / 2),
                        ),
                        size=(
                            round(self.lane_size),
                            round(self.lane_size),
                        ),
                    ))

                among = among.next

        tap_images = []

        def add_tap_images(tap: Tap, type=None):
            src = '%s/notes_%s_%s.png'
            y = self.pixel_per_second * self.score.get_time_delta(tap.bar, bar_to) + self.padding

            if type is None:
                if tap.type == 2:
                    type = 'crtcl'
                else:
                    type = 'normal'

            note_width = self.note_width * self.note_size
            note_height = self.note_height * self.note_size

            l = self.lane_size * (tap.lane - 2) + self.padding
            r = self.lane_size * (tap.lane - 2 + tap.width) + self.padding

            tap_images.append(svgwrite.image.Image(
                src % (self.note_host, type, 'left'),
                size=(
                    round(note_width),
                    round(note_height),
                ),
                insert=(
                    round(l - note_width / 2),
                    round(y - note_height / 2),
                ),
            ))
            tap_images.append(svgwrite.image.Image(
                src % (self.note_host, type, 'right'),
                size=(
                    round(note_width),
                    round(note_height),
                ),
                insert=(
                    round(r - note_width / 2),
                    round(y - note_height / 2),
                ),
            ))
            if round(r - note_width / 2) - round(l - note_width / 2) - round(note_width) > 0:
                tap_images.append(svgwrite.image.Image(
                    src % (self.note_host, type, 'middle'),
                    size=(
                        round(r - note_width / 2) - round(l - note_width / 2) - round(note_width),
                        round(note_height),
                    ),
                    insert=(
                        round(l - note_width / 2) + round(note_width),
                        round(y - note_height / 2),
                    ),
                    preserveAspectRatio='none',
                ))

        def add_hand_text(tap, hand):
            y = self.pixel_per_second * self.score.get_time_delta(tap.bar, bar_to) + self.padding
            l = self.lane_size * (tap.lane - 2) + self.padding
            r = self.lane_size * (tap.lane - 2 + tap.width) + self.padding

            tap_images.append(svgwrite.text.Text(
                str(hand),
                insert=(
                    l, y
                )
            ))

        flick_images = []

        def add_flick_image(directional: Directional, type=None, critical=None):
            src = '%s/notes_flick_arrow%s_0%s%s.png'
            y = self.pixel_per_second * self.score.get_time_delta(directional.bar, bar_to) + self.padding

            if type is None:
                if directional.type == 3:
                    type = '_diagonal_left'
                elif directional.type == 4:
                    type = '_diagonal_right'
                else:
                    type = ''

            if critical is None:
                if directional.tap and directional.tap.type == 2:
                    critical = '_crtcl'
                else:
                    critical = ''

            width = directional.width if directional.width < 6 else 6
            flick_width = ((width + 0.5) / 3) ** 0.75 * self.flick_width * self.note_size
            flick_height = ((width + 2.5) / 3) ** 0.75 * self.flick_height * self.note_size
            bias = (
                - self.note_width * self.note_size / 2 if type == '_diagonal_left' else
                self.note_width * self.note_size / 2 if type == '_diagonal_right' else
                0
            )

            flick_images.append(svgwrite.image.Image(
                src % (self.note_host, critical, width, type),
                size=(
                    round(flick_width),
                    round(flick_height),
                ),
                insert=(
                    round(self.lane_size * (directional.lane - 2 + directional.width / 2) -
                          flick_width / 2 + bias + self.padding),
                    round(y - self.note_height * self.note_size / 2 - flick_height * 2 / 3),
                )))

        tick_texts = []

        def add_tick_text(note: Note, next: Note | None = None):
            y = self.pixel_per_second * self.score.get_time_delta(note.bar, bar_to) + self.padding

            if isinstance(note, Slide) and note.is_among_note():
                tick_texts.append(svgwrite.shapes.Line(
                    start=(
                        round(self.padding * (1 - 1 / 6)),
                        round(y),
                    ),
                    end=(
                        round(self.padding),
                        round(y),
                    ),
                    class_='tick-line',
                ))

            else:
                if (
                        next is None or
                        next is note or
                        next.bar == note.bar or
                        next.bar - note.bar > 1 or
                        next.bar - note.bar > 0.5 and int(next.bar + 1e-3) != int(note.bar + 1e-3)
                ):
                    interval = math.floor(note.bar + 1 + 1e-3) - note.bar
                else:
                    interval = next.bar - note.bar

                interval *= self.score.get_event(note.bar + 1e-3).bar_length / 4
                denominator = get_denominator(interval)
                numerator = round(interval * denominator)

                text = '%g/%g' % (numerator, denominator) if numerator != 1 else '/%g' % (denominator,)

                tick_texts.append(svgwrite.shapes.Line(
                    start=(
                        round(self.padding * (1 - 1 / 2)),
                        round(y),
                    ),
                    end=(
                        round(self.padding),
                        round(y),
                    ),
                    class_='tick-line',
                ))
                tick_texts.append(svgwrite.text.Text(
                    text,
                    insert=(
                        round(self.padding - 4),
                        round(y - 2),
                    ),
                    class_='tick-text',
                ))

        def draw_cover_object(cover_object: CoverObject):
            if isinstance(cover_object, CoverText):
                cover_bar_from = cover_object.bar_from
                if cover_bar_from < bar_from - 0.2 or cover_bar_from >= bar_to - 0.1:
                    return
                drawing.add(drawing.text(
                    cover_object.text,
                    insert=(
                        self.lane_size * self.n_lanes + self.padding * 2 - 3,
                        round(self.pixel_per_second * self.score.get_time_delta(cover_bar_from, bar_to) + self.padding),
                    ),
                    transform=f'''rotate(-90, {
                    round(self.lane_size * self.n_lanes + self.padding * 2 - 3)
                    }, {
                    round(self.pixel_per_second * self.score.get_time_delta(cover_bar_from, bar_to) + self.padding)
                    })''',
                    class_=cover_object.css_class,
                ))
            elif isinstance(cover_object, CoverRect):
                cover_bar_from = max(bar_from - 0.2, cover_object.bar_from)
                cover_bar_to = min(bar_to + 0.2, cover_object.bar_to)
                if cover_bar_to <= cover_bar_from:
                    return
                drawing.add(drawing.rect(
                    insert=(
                        self.padding,
                        round(self.pixel_per_second * self.score.get_time_delta(cover_bar_to, bar_to) + self.padding),
                    ),
                    size=(
                        round(self.lane_size * self.n_lanes),
                        round(self.pixel_per_second * self.score.get_time_delta(cover_bar_from, cover_bar_to)),
                    ),
                    class_=cover_object.css_class,
                ))

        for i, note in enumerate(self.score.notes):
            if isinstance(note, Slide) and note.next:
                next: Slide = note.next
                while not next.is_path_note():
                    next = next.next

                if not bar_from - 1 <= note.bar < bar_to + 1 and not bar_from - 1 <= next.bar < bar_to + 1:
                    continue

            else:
                if not bar_from - 1 <= note.bar < bar_to + 1:
                    continue

            next: Note = note
            for next in self.score.notes[i:]:
                if isinstance(next, Slide):
                    if next.type in (1, 2) and next.bar > note.bar:
                        break
                else:
                    if next.bar > note.bar:
                        break

            if note.type != 0 and False:
                add_hand_text(note, hand=self.score.note_hands()[i])

            if isinstance(note, Tap):
                add_tap_images(note)
                add_tick_text(note, next=next)

            elif isinstance(note, Directional):
                add_flick_image(note)
                add_tap_images(note, type='crtcl' if note.tap and note.tap.type == 2 else 'flick')
                add_tick_text(note, next=next)

            elif isinstance(note, Slide):
                if note.type == 1:
                    add_slide_path(note)
                    add_tap_images(note, type=(
                        'crtcl' if note.tap and note.tap.type == 2 else
                        'long'))
                    add_tick_text(note, next=next)

                elif note.type == 2:
                    if note.directional:
                        add_flick_image(note.directional, critical=(
                            '_crtcl' if note.tap and note.tap.type == 2 else
                            '_crtcl' if note.head.tap and note.head.tap.type == 2 else
                            ''
                        ))
                    add_tap_images(note, type=(
                        'crtcl' if note.tap and note.tap.type == 2 else
                        'crtcl' if note.head.tap and note.head.tap.type == 2 else
                        'flick' if note.directional else
                        'long'
                    ))
                    add_tick_text(note, next=next)

                elif note.type == 3:
                    add_tick_text(note)
                    if note.is_path_note():
                        add_slide_path(note)

                elif note.type == 5:
                    add_slide_path(note)

        height = self.pixel_per_second * self.score.get_time_delta(bar_from, bar_to)

        drawing = svgwrite.Drawing(
            size=(
                round(self.lane_size * self.n_lanes + self.padding * 2),
                round(height + self.padding * 2),
            ),
        )

        drawing.add(drawing.rect(
            insert=(0, 0),
            size=(
                round(self.lane_size * self.n_lanes + self.padding * 2),
                round(height + self.padding * 2),
            ),
            class_='background',
        ))

        drawing.add(drawing.rect(
            insert=(self.padding, 0),
            size=(
                round(self.lane_size * self.n_lanes),
                round(height + self.padding * 2),
            ),
            class_='lane',
        ))

        # Draw special cover object under notes
        for cover_object in self.special_cover_objects:
            draw_cover_object(cover_object)

        for lane in range(0, self.n_lanes + 1, 2):
            drawing.add(drawing.line(
                start=(
                    round(self.lane_size * lane + self.padding),
                    round(0),
                ),
                end=(
                    round(self.lane_size * lane + self.padding),
                    round(height + self.padding * 2),
                ),
                class_='lane-line',
            ))

        for bar in range(bar_from, bar_to + 1):
            drawing.add(drawing.line(
                start=(
                    round(self.lane_size * 0 + self.padding),
                    round(self.pixel_per_second * self.score.get_time_delta(bar, bar_to) + self.padding),
                ),
                end=(
                    round(self.lane_size * self.n_lanes + self.padding),
                    round(self.pixel_per_second * self.score.get_time_delta(bar, bar_to) + self.padding),
                ),
                class_='bar-line',
            ))

            event = self.score.get_event(bar)
            for i in range(1, math.ceil(event.bar_length)):
                y = self.pixel_per_second * self.score.get_time_delta(bar + i / event.bar_length, bar_to) + self.padding
                drawing.add(drawing.line(
                    start=(
                        round(self.lane_size * 0 + self.padding),
                        round(y),
                    ),
                    end=(
                        round(self.lane_size * self.n_lanes + self.padding),
                        round(y),
                    ),
                    class_='beat-line',
                ))

            text = ', '.join(filter(lambda x: x, [
                '#%s' % bar,
                event.section if bar == 0 or
                                 event.section != self.score.get_event(bar - 1).section
                else None,
            ]))

            # drawing.add(drawing.line(
            #     start=(
            #         round(self.lane_size * 0),
            #         round(self.pixel_per_second * self.score.get_time_delta(bar, bar_to) + self.padding),
            #     ),
            #     end=(
            #         round(self.lane_size * 0 + self.padding),
            #         round(self.pixel_per_second * self.score.get_time_delta(bar, bar_to) + self.padding),
            #     ),
            #     class_='bar-count-line',
            # ))

            # drawing.add(drawing.text(
            #     text,
            # insert=(
            #     round(self.padding + 8),
            #     round(self.pixel_per_second * self.score.get_time_delta(bar, bar_to) + self.padding - 20),
            # ),
            # transform=f'''rotate(-90, {
            #     round(self.padding)
            # }, {
            #     round(self.pixel_per_second * self.score.get_time_delta(bar, bar_to) + self.padding)
            # })''',
            # class_='bar-count-text',
            # ))

        for event in Score.parse_events(
                sorted(self.score.events + [Event(bar=bar) for bar in range(bar_from, bar_to + 1)],
                       key=lambda event: event.bar)):
            if not bar_from - 1 <= event.bar < bar_to + 1:
                continue

            text = ', '.join(filter(lambda x: x, [
                '#%g' % event.bar if float('%g' % event.bar).is_integer() else None,
                '%g BPM' % event.bpm if event.bpm else None,
                '%g/4' % event.bar_length if event.bar_length else None,
                event.section,
                event.text,
            ]))

            special = event.bpm or event.bar_length or event.section or event.text

            if not text:
                continue

            drawing.add(drawing.line(
                start=(
                    round(self.lane_size * 0),
                    round(self.pixel_per_second * self.score.get_time_delta(event.bar, bar_to) + self.padding),
                ),
                end=(
                    round(self.lane_size * 0 + self.padding),
                    round(self.pixel_per_second * self.score.get_time_delta(event.bar, bar_to) + self.padding),
                ),
                class_='bar-count-line' if not special else 'event-line',
            ))

            drawing.add(drawing.text(
                text,
                insert=(
                    round(self.padding + 8),
                    round(self.pixel_per_second * self.score.get_time_delta(event.bar, bar_to) + self.padding - 20),
                ),
                transform=f'''rotate(-90, {
                round(self.padding)
                }, {
                round(self.pixel_per_second * self.score.get_time_delta(event.bar, bar_to) + self.padding)
                })''',
                class_='bar-count-text' if not special else 'event-text',
            ))

        for word in self.words:
            if not bar_from - 1 <= word.bar < bar_to + 1:
                continue

            drawing.add(drawing.text(
                word.text,
                insert=(
                    round(self.lane_size * self.n_lanes + self.padding),
                    round(self.pixel_per_second * self.score.get_time_delta(word.bar, bar_to) + self.padding + 16),
                ),
                transform=f'''rotate(-90, {
                round(self.lane_size * self.n_lanes + self.padding)
                }, {
                round(self.pixel_per_second * self.score.get_time_delta(word.bar, bar_to) + self.padding)
                })''',
                class_='lyric-text',
            ))

        for slide_path in slide_paths:
            drawing.add(slide_path)

        for among_image in among_images:
            drawing.add(among_image)

        for tap_image in tap_images:
            drawing.add(tap_image)

        for flick_image in flick_images:
            drawing.add(flick_image)

        for tick_text in tick_texts:
            drawing.add(tick_text)

        return drawing

    def scale(self) -> svgwrite.Drawing:
        drawing = svgwrite.Drawing(size=(
            self.meta_size,
            self.meta_size,
        ))

        drawing.add(drawing.rect(
            insert=(0, 0),
            size=(
                self.meta_size,
                self.meta_size,
            ),
            fill=self.background_color
        ))

        drawing.add(drawing.rect(
            insert=(self.meta_size / 2 - self.lane_size * 2, 0),
            size=(
                self.lane_size * 4,
                self.meta_size,
            ),
            fill=self.track_color
        ))

        drawing.add(drawing.line(
            (self.meta_size / 2 - self.lane_size * 2, 0),
            (self.meta_size / 2 - self.lane_size * 2, self.meta_size),
            stroke='#e2e2e2',
            stroke_width=1,
        ))

        drawing.add(drawing.line(
            (0, self.meta_size / 2),
            (self.meta_size, self.meta_size / 2),
            stroke='#e2e2e2',
            stroke_width=1,
        ))

        for i in range(-16, 16):
            drawing.add(drawing.line(
                (self.meta_size / 2 - self.lane_size * 2, self.meta_size / 2 + i / 60 * self.pixel_per_second),
                (self.meta_size / 2 - self.lane_size * 2.5, self.meta_size / 2 + i / 60 * self.pixel_per_second),
                stroke='#e2e2e2',
                stroke_width=1,
            ))

        drawing.add(drawing.text(
            'frame',
            insert=(
                self.meta_size / 2 - self.lane_size * 2.5 - 4,
                self.meta_size / 2 - 2,
            ),
            text_anchor='end',
            font_family='Verdana',
            font_size=8,
            fill='#e2e2e2',
        ))

        drawing.add(drawing.line(
            (self.meta_size / 2 + self.lane_size * 2, 0),
            (self.meta_size / 2 + self.lane_size * 2, self.meta_size),
            stroke='#e2e2e2',
            stroke_width=1,
        ))

        for i, judge in [
            (7.5, 'BAD'),
            (6.5, 'GOOD'),
            (5.0, 'GREAT'),
            (2.5, 'PERFECT'),
            (-7.5, 'BAD'),
            (-6.5, 'GOOD'),
            (-5.0, 'GREAT'),
            (-2.5, 'PERFECT'),
        ]:
            drawing.add(drawing.line(
                (self.meta_size / 2 + self.lane_size * 2, self.meta_size / 2 + i / 60 * self.pixel_per_second),
                (self.meta_size / 2 + self.lane_size * 4, self.meta_size / 2 + i / 60 * self.pixel_per_second),
                stroke='#e2e2e2',
                stroke_width=1,
            ))

            drawing.add(drawing.text(
                judge,
                insert=(
                    self.meta_size / 2 + self.lane_size * 2 + 4,
                    self.meta_size / 2 + i / 60 * self.pixel_per_second + (
                        0 if i > 0 else 6
                    ),
                ),
                text_anchor='start',
                font_family='Verdana',
                font_size=8,
                fill='#e2e2e2',
            ))

        src = '%s/notes_%s_%s.png'
        drawing.add(svgwrite.image.Image(
            src % (self.note_host, 'normal', 'left'),
            size=(
                self.note_width * self.note_size,
                self.note_height * self.note_size,
            ),
            insert=(
                self.lane_size * 4 - self.note_width * self.note_size / 2,
                self.meta_size / 2 - self.note_height * self.note_size / 2,
            ),
        ))
        drawing.add(svgwrite.image.Image(
            src % (self.note_host, 'normal', 'right'),
            size=(
                self.note_width * self.note_size,
                self.note_height * self.note_size,
            ),
            insert=(
                self.lane_size * 8 - self.note_width * self.note_size / 2,
                self.meta_size / 2 - self.note_height * self.note_size / 2,
            ),
        ))
        drawing.add(svgwrite.image.Image(
            src % (self.note_host, 'normal', 'middle'),
            size=(
                self.lane_size * 4 - self.note_width * self.note_size,
                self.note_height * self.note_size,
            ),
            insert=(
                self.lane_size * 4 + self.note_width * self.note_size / 2,
                self.meta_size / 2 - self.note_height * self.note_size / 2,
            ),
            preserveAspectRatio='none',
        ))

        return drawing

    def export(self, file_name, style_sheet='', display_skill_extra=True):
        n_bars = math.ceil(self.score.notes[-1].bar - 1e-6)
        drawings: list[svgwrite.Drawing] = []

        width = 0
        height = 0

        bar = 0
        event = Event(bar=0, bpm=120, bar_length=4, sentence_length=4)

        # Add fever cover object
        if self.music_meta:
            for e in self.score.events:
                if e.text != 'SUPER FEVER!!':
                    continue
                self.special_cover_objects.append(CoverRect(
                    e.bar, "fever-duration", self.score.get_bar(self.music_meta["fever_end_time"])
                ))
                self.special_cover_objects.append(CoverText(
                    e.bar, "skill-score", "多+%.2f%%" % (self.music_meta["fever_score"] * 100)
                ))

        # Add skill cover object
        skill_i = 0
        for e in self.score.events:
            if e.text != "SKILL":
                continue
            # print(e)
            if display_skill_extra:
                self.special_cover_objects.append(CoverRect(
                    self.score.get_bar(self.score.get_time(e.bar) - 5 / 60),
                    "skill-great",
                    self.score.get_bar(self.score.get_time(e.bar) + 5 + 5 / 60)
                ))
                self.special_cover_objects.append(CoverRect(
                    self.score.get_bar(self.score.get_time(e.bar) - 2.5 / 60),
                    "skill-perfect",
                    self.score.get_bar(self.score.get_time(e.bar) + 5 + 2.5 / 60),
                ))
                self.special_cover_objects.append(CoverRect(
                    e.bar, "skill-duration", self.score.get_bar(self.score.get_time(e.bar) + 5)
                ))
            if self.music_meta:
                solo_skill_score = "+%.2f%%" % (self.music_meta["skill_score_solo"][skill_i] * 100)
                multi_skill_score = "+%.2f%%" % (self.music_meta["skill_score_multi"][skill_i] * 100)
                append_text = solo_skill_score
                if solo_skill_score != multi_skill_score:
                    append_text = "単%s 多%s" % (solo_skill_score, multi_skill_score)
                self.special_cover_objects.append(CoverText(
                    e.bar, "skill-score", append_text
                ))
            skill_i += 1

        for i in range(n_bars + 1):
            e = self.score.get_event(i)

            if bar != i and (
                    e.section != event.section or
                    e.sentence_length != event.sentence_length or
                    i == bar + event.sentence_length or
                    i == n_bars
            ):
                d = self[bar: i]

                width += d['width']
                if height < d['height']:
                    height = d['height']

                drawings.append(d)

                bar = i

            event |= e

        drawing = svgwrite.Drawing(file_name, size=(
            width + self.padding * 2,
            height + self.padding * 2 + self.meta_size + self.padding * 2,
        ))

        drawing.defs.add(drawing.style(style_sheet))

        drawing.add(drawing.rect(
            insert=(0, 0),
            size=(
                width + self.padding * 2,
                height + self.padding * 2,
            ),
            class_='background',
        ))

        drawing.add(drawing.rect(
            insert=(0, height + self.padding * 2),
            size=(
                width + self.padding * 2,
                self.meta_size + self.padding * 2,
            ),
            class_='meta',
        ))

        drawing.add(drawing.line(
            start=(
                0,
                height + self.padding * 2,
            ),
            end=(
                width + self.padding * 2,
                height + self.padding * 2,
            ),
            class_='meta-line',
        ))

        if self.meta.jacket:
            drawing.add(svgwrite.image.Image(
                href=self.meta.jacket,
                insert=(
                    self.padding * 2,
                    height + self.padding * 3,
                ),
                size=(self.meta_size, self.meta_size),
            ))

        drawing.add(svgwrite.text.Text(
            f'{self.meta.title} - {self.meta.artist}',
            insert=(
                self.meta_size + self.padding * 3,
                self.meta_size + height + self.padding * 3 - 8,
            ),
            class_='title',
        ))

        drawing.add(svgwrite.text.Text(
            f'{str(self.meta.difficulty).upper()} {self.meta.playlevel} 譜面確認 by ぷろせかもえ！ (pjsekai.moe)',
            insert=(
                self.meta_size + self.padding * 3,
                height + self.padding * 4,
            ),
            class_='subtitle',
        ))
        # if themehint:
        #     drawing.add(svgwrite.text.Text(
        #         '白色配色：/theme white',
        #         insert=(
        #             width - 300,
        #             height + self.padding * 3.4,
        #         ),
        #         class_='themehint',
        #     ))
        #     drawing.add(svgwrite.text.Text(
        #         '黑色配色：/theme black',
        #         insert=(
        #             width - 300,
        #             height + self.padding * 4.5,
        #         ),
        #         class_='themehint',
        #     ))
        #     drawing.add(svgwrite.text.Text(
        #         '彩色配色：/theme color',
        #         insert=(
        #             width - 300,
        #             height + self.padding * 5.6,
        #         ),
        #         class_='themehint',
        #     ))
        # scale = self.scale()
        # scale['x'] = width - self.meta_size
        # scale['y'] = height + self.padding * 2
        # drawing.add(scale)
        drawing.add(svgwrite.text.Text(
            'Code by ぷろせかもえ！ (pjsekai.moe)　& Unibot',
            insert=(
                width - 900,
                height + self.padding * 4.2,
            ),
            class_='themehint',
        ))
        drawing.add(svgwrite.text.Text(
            'Modified by 33 (3-3.dev & bilibili @xfl03)',
            insert=(
                width - 770,
                height + self.padding * 5.9,
            ),
            class_='themehint',
        ))
        width = 0
        for d in drawings:
            d['x'] = width + self.padding
            d['y'] = height - d['height'] + self.padding
            width += d['width']
            drawing.add(d)

        drawing.save()


if __name__ == '__main__':
    with open('ws32') as f:
        sus = SUS(f.readlines())

    with open('1.json') as f:
        rebase = json.load(f)

    sus.score = sus.score.rebase([
        Event(
            bar=event.get('bar'),
            bpm=event.get('bpm'),
            bar_length=event.get('barLength'),
            sentence_length=event.get('sentenceLength'),
            section=event.get('section'),
        )
        for event in rebase['events']
    ])

    drawing = sus.svg()
