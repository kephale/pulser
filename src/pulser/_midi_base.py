from __future__ import annotations

from threading import Event, Thread
from typing import Iterator, Mapping, TypeVar, cast

import pygame.midi
from psygnal import Signal, SignalInstance

T = TypeVar("T")
EventId = tuple[int, int]


class Button:
    """A button on a midi device."""

    pressed = Signal()
    released = Signal()


class Knob:
    """A knob on a midi device."""

    changed = Signal(float)


class MidiDevice:
    """Generic midi device.

    Parameters
    ----------
    name : bytes
        The name of the device to connect to.
    knobs : dict[str, EventId], optional
        A mapping of knob names to the midi event id for that knob, where an event
        id is a tuple of pygame.midi (status, data1).
    buttons : dict[str, tuple[EventId, EventId]], optional
        A mapping of button names to a 2-tuple of midi event ids for the pressed and
        released events.
    interface : bytes, optional
        The name of the midi interface to use, by default b"CoreMIDI"
    """

    def __init__(
        self,
        name: bytes,
        knobs: dict[str, EventId] | None = None,
        buttons: dict[str, tuple[EventId, EventId]] | None = None,
        interface: bytes = b"CoreMIDI",
    ) -> None:
        self._interface = interface
        self._name = name
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._input: pygame.midi.Input | None = None
        self._output: pygame.midi.Output | None = None

        # create the signal emitters
        self._knobs = KnobGroup(knobs)
        self._buttons = ButtonGroup(buttons)

        # lookup table for events -> emitters
        self._emitters: dict[EventId, tuple[SignalInstance, bool]] = {}
        if knobs:
            for k, v in knobs.items():
                self._emitters[v] = self._knobs[k].changed, True
        if buttons:
            for k, (pressed, released) in buttons.items():
                self._emitters[pressed] = self._buttons[k].pressed, False
                self._emitters[released] = self._buttons[k].released, False

        pygame.midi.init()
        for i in range(pygame.midi.get_count()):
            _inter, _name, is_in, is_out, is_open = pygame.midi.get_device_info(i)
            if _inter == interface and _name == name:  # type: ignore
                if is_open:
                    raise RuntimeError("Device is already open")
                if is_in:
                    self._input = pygame.midi.Input(i)
                if is_out:
                    self._output = pygame.midi.Output(i)

    @property
    def knob(self) -> KnobGroup:
        """The knobs on the device.

        Examples
        --------
        >>> x.knob[1].changed.connect(lambda v: print(f"knob 1 changed to {v}"))
        >>> x.knob.changed.connect(lambda k, v: print(f"knob {k} changed to {v}"))
        """
        return self._knobs

    @property
    def button(self) -> ButtonGroup:
        """The buttons on the device.

        Examples
        --------
        >>> x.button[1].pressed.connect(lambda: print("button 1 pressed"))
        >>> x.button[1].released.connect(lambda: print("button 1 released"))
        >>> x.button.pressed.connect(lambda k: print(f"button {k} pressed"))
        >>> x.button.released.connect(lambda k: print(f"button {k} released"))
        """
        return self._buttons

    def watch(
        self, sleep_duration: float = 0.001, read_size: int = 10, block: bool = False
    ) -> None | Thread:
        """Watch the midi device for changes and update the python model.

        Parameters
        ----------
        sleep_duration : float, optional
            The time to sleep between each read, by default 0.001
        read_size : int, optional
            The number of events to read at once, by default 10
        block : bool, optional
            If True, block the current thread until the device is closed.
            If False, return a thread that will watch the device in the background.
            By default False.
        """
        if self._input is None:
            raise RuntimeError("No input device found")

        if block:
            self._block_and_read(sleep_duration, read_size)
            return None
        else:
            args = (sleep_duration, read_size)
            self._thread = Thread(target=self._block_and_read, args=args, daemon=True)
            self._thread.start()
            return self._thread

    def _block_and_read(
        self,
        sleep_duration: float = 0.001,
        read_size: int = 10,
    ) -> None:
        import time

        _input = cast(pygame.midi.Input, self._input)
        while not self._stop_event.is_set():
            try:
                if not _input.poll():
                    time.sleep(sleep_duration)
                    continue
                # read_size acts as a debounce.
                # if you read too few events, they'll pile up and be read slowly
                event, _ = _input.read(read_size)[-1]
                status, data1, value = event[:3]  # type: ignore
                emitter, emit_args = self._emitters[(status, data1)]
                if emit_args:
                    emitter.emit(value)
                else:
                    emitter.emit()
            except KeyboardInterrupt:
                break


# just a read-only mapping
class _Map(Mapping[str, T]):
    def __init__(self, data: dict[str, T]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> T:
        return self._data[str(key)]

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return repr(self._data)

    def __str__(self) -> str:
        return str(self._data)

    def __contains__(self, key: object) -> bool:
        return key in self._data


class KnobGroup(_Map[Knob]):
    """A group of knobs.  Allows connecting to any knob change."""

    changed = Signal(str, float)

    def __init__(self, knobs: dict[str, EventId] | None = None) -> None:
        super().__init__({k: Knob() for k, v in (knobs or {}).items()})
        # connect to any knob change
        for k, v in self.items():
            v.changed.connect(lambda value, k=k: self.changed.emit(k, value))


class ButtonGroup(_Map[Button]):
    """A group of buttons.  Allows connecting to any button change."""

    pressed = Signal(str)
    released = Signal(str)

    def __init__(
        self, buttons: dict[str, tuple[EventId, EventId]] | None = None
    ) -> None:
        super().__init__({k: Button() for k, v in (buttons or {}).items()})
        # connect to any button press/release
        for k, v in self.items():
            v.pressed.connect(lambda k=k: self.pressed.emit(k))
            v.released.connect(lambda k=k: self.released.emit(k))
