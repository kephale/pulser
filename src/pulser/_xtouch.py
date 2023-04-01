import time
from dataclasses import Field, InitVar, asdict, dataclass, field, fields
from threading import Event, Thread
from typing import Any, Callable, ClassVar, Protocol

import pygame.midi
from psygnal import evented


class QueueLike(Protocol):
    def get(self) -> Any:
        ...

    def put(self, item: Any, block: bool = True, timeout: int | None = None) -> None:
        ...

    def empty(self) -> bool:
        ...


@dataclass
class BaseMidi:
    _INTERFACE: ClassVar[bytes] = b"CoreMIDI"

    _NAME: ClassVar[bytes]
    _types: ClassVar[dict[str, type]] = {}
    _output: ClassVar[pygame.midi.Output | None] = None
    _input: ClassVar[pygame.midi.Input | None] = None
    _EVENT2NAME: ClassVar[dict[tuple[int, int], str]] = {}
    _NAME2EVENT: ClassVar[dict[str, tuple[int, int]]] = {}

    start_watch: InitVar[bool] = True

    def __post_init__(self, start_watch: bool) -> None:
        self._types = {f.name: f.type for f in fields(self)}  # type: ignore
        self._stop_event = Event()
        self._thread: Thread | None = None

        pygame.midi.init()
        for i in range(pygame.midi.get_count()):
            interface, name, is_in, is_out, is_open = pygame.midi.get_device_info(i)
            if interface == self._INTERFACE and name == self._NAME:  # type: ignore
                if is_open:
                    raise RuntimeError("Device is already open")
                if is_in:
                    self._input: pygame.midi.Input | None = pygame.midi.Input(i)
                if is_out:
                    self._output = pygame.midi.Output(i)

        self.send_all()
        if start_watch:
            self.watch()

    def __setattr__(self, name: str, value: Any) -> None:
        type_ = self._types.get(name)
        if type_ is not None and not isinstance(value, type_):
            value = type_(value)
        super().__setattr__(name, value)
        if name in self._NAME2EVENT and self._output is not None:
            self._send_value(name, value)

    def _send_value(self, name: str, value: int) -> None:
        """Send a value to the midi device."""
        status, data1 = self._NAME2EVENT[name]
        if isinstance(value, bool):
            value = 127 if value else 0
        self._output.write_short(status, data1, value)  # type: ignore

    def send_all(self) -> None:
        """Sync the state of the python model with the midi device.

        I don't think MIDI has a spec for reading the state of a device, so
        this is the best we can do.
        """
        if self._output is not None:
            for name, value in asdict(self).items():
                self._send_value(name, value)

    def stop(self) -> None:
        """Stop the thread watching the midi device."""
        self._stop_event.set()

    def watch(
        self,
        sleep_duration: float = 0.001,
        read_size: int = 10,
        q: QueueLike | None = None,
    ) -> None:
        """Watch the midi device for changes and update the python model."""
        if self._input is None:
            raise RuntimeError("No input device found")
        if q is not None:
            target: Callable = _block_and_read_to_q
            args: tuple = (self._input, q, self._stop_event, sleep_duration, read_size)
        else:
            target = _block_and_read_to_attr
            args = (self, sleep_duration, read_size)
        self._thread = Thread(target=target, args=args)
        self._thread.start()

    def __setitem__(self, key: tuple[int, int], value: Any) -> None:
        """Set the value of a field based on the event key (status, data1)."""
        setattr(self, self._EVENT2NAME[key], value)

    def __init_subclass__(cls) -> None:
        """Parse the metadata for each field and build a mapping of events to names."""
        for name in cls.__annotations__:
            default = getattr(cls, name, None)
            if isinstance(default, Field) and "ids" in default.metadata:
                for item in default.metadata["ids"]:
                    cls._EVENT2NAME[item] = name
                    cls._NAME2EVENT[name] = item


# thread target that directly writes attributes
# in the case of an evented dataclass, this will emit events in the thread
# that's watching the midi device
def _block_and_read_to_attr(
    x_touch: BaseMidi,
    sleep_duration: float = 0.001,
    read_size: int = 10,
) -> None:
    if x_touch._input is None:
        raise RuntimeError("No input device found")
    pygame.midi.init()
    while not x_touch._stop_event.is_set():
        try:
            if not x_touch._input.poll():
                time.sleep(sleep_duration)
                continue
            # read_size acts as a debounce.
            # if you read too few events, they'll pile up and be read slowly
            event, _ = x_touch._input.read(read_size)[-1]
            # midi_event = MidiEvent(*event, timestamp)  # type: ignore
            status, data1, value = event[:3]  # type: ignore
            x_touch[(status, data1)] = value
        except Exception:
            return


# thread target that writes to a queue
# it is expected that some other main thread timer object will watch the queue
# and emit events in the main thread.
def _block_and_read_to_q(
    input_: pygame.midi.Input,
    q: QueueLike,
    stop_event: Event,
    sleep_duration: float = 0.001,
    read_size: int = 10,
) -> None:
    pygame.midi.init()
    while not stop_event.is_set():
        try:
            if not input_.poll():
                time.sleep(sleep_duration)
                continue
            # read_size acts as a debounce.
            # if you read too few events, they'll pile up and be read slowly
            event, _ = input_.read(read_size)[-1]
            # midi_event = MidiEvent(*event, timestamp)  # type: ignore
            q.put(event)
        except Exception:
            return


@evented
@dataclass
class XTouch(BaseMidi):
    """Wrapper around the XTouch controller."""

    _NAME: ClassVar[bytes] = b"X-TOUCH MINI"

    # metadata.ids are (status, data1) for events related to that field

    knob_1: int = field(default=0, metadata={"ids": [(186, 1)]})
    knob_2: int = field(default=0, metadata={"ids": [(186, 2)]})
    knob_3: int = field(default=0, metadata={"ids": [(186, 3)]})
    knob_4: int = field(default=0, metadata={"ids": [(186, 4)]})
    knob_5: int = field(default=0, metadata={"ids": [(186, 5)]})
    knob_6: int = field(default=0, metadata={"ids": [(186, 6)]})
    knob_7: int = field(default=0, metadata={"ids": [(186, 7)]})
    knob_8: int = field(default=0, metadata={"ids": [(186, 8)]})
    fader: int = field(default=0, metadata={"ids": [(186, 9)]})
    btn_1: bool = field(default=False, metadata={"ids": [(154, 8), (138, 8)]})
    btn_2: bool = field(default=False, metadata={"ids": [(154, 9), (138, 9)]})
    btn_3: bool = field(default=False, metadata={"ids": [(154, 10), (138, 10)]})
    btn_4: bool = field(default=False, metadata={"ids": [(154, 11), (138, 11)]})
    btn_5: bool = field(default=False, metadata={"ids": [(154, 12), (138, 12)]})
    btn_6: bool = field(default=False, metadata={"ids": [(154, 13), (138, 13)]})
    btn_7: bool = field(default=False, metadata={"ids": [(154, 14), (138, 14)]})
    btn_8: bool = field(default=False, metadata={"ids": [(154, 15), (138, 15)]})
    btn_9: bool = field(default=False, metadata={"ids": [(154, 16), (138, 16)]})
    btn_10: bool = field(default=False, metadata={"ids": [(154, 17), (138, 17)]})
    btn_11: bool = field(default=False, metadata={"ids": [(154, 18), (138, 18)]})
    btn_12: bool = field(default=False, metadata={"ids": [(154, 19), (138, 19)]})
    btn_13: bool = field(default=False, metadata={"ids": [(154, 20), (138, 20)]})
    btn_14: bool = field(default=False, metadata={"ids": [(154, 21), (138, 21)]})
    btn_15: bool = field(default=False, metadata={"ids": [(154, 22), (138, 22)]})
    btn_16: bool = field(default=False, metadata={"ids": [(154, 23), (138, 23)]})

    # LAYER B

    b_knob_1: int = field(default=0, metadata={"ids": [(186, 11)]})
    b_knob_2: int = field(default=0, metadata={"ids": [(186, 12)]})
    b_knob_3: int = field(default=0, metadata={"ids": [(186, 13)]})
    b_knob_4: int = field(default=0, metadata={"ids": [(186, 14)]})
    b_knob_5: int = field(default=0, metadata={"ids": [(186, 15)]})
    b_knob_6: int = field(default=0, metadata={"ids": [(186, 16)]})
    b_knob_7: int = field(default=0, metadata={"ids": [(186, 17)]})
    b_knob_8: int = field(default=0, metadata={"ids": [(186, 18)]})
    b_fader: int = field(default=0, metadata={"ids": [(186, 10)]})
    b_btn_1: bool = field(default=False, metadata={"ids": [(154, 32), (138, 32)]})
    b_btn_2: bool = field(default=False, metadata={"ids": [(154, 33), (138, 33)]})
    b_btn_3: bool = field(default=False, metadata={"ids": [(154, 34), (138, 34)]})
    b_btn_4: bool = field(default=False, metadata={"ids": [(154, 35), (138, 35)]})
    b_btn_5: bool = field(default=False, metadata={"ids": [(154, 36), (138, 36)]})
    b_btn_6: bool = field(default=False, metadata={"ids": [(154, 37), (138, 37)]})
    b_btn_7: bool = field(default=False, metadata={"ids": [(154, 38), (138, 38)]})
    b_btn_8: bool = field(default=False, metadata={"ids": [(154, 39), (138, 39)]})
    b_btn_9: bool = field(default=False, metadata={"ids": [(154, 40), (138, 40)]})
    b_btn_10: bool = field(default=False, metadata={"ids": [(154, 41), (138, 41)]})
    b_btn_11: bool = field(default=False, metadata={"ids": [(154, 42), (138, 42)]})
    b_btn_12: bool = field(default=False, metadata={"ids": [(154, 43), (138, 43)]})
    b_btn_13: bool = field(default=False, metadata={"ids": [(154, 44), (138, 44)]})
    b_btn_14: bool = field(default=False, metadata={"ids": [(154, 45), (138, 45)]})
    b_btn_15: bool = field(default=False, metadata={"ids": [(154, 46), (138, 46)]})
    b_btn_16: bool = field(default=False, metadata={"ids": [(154, 47), (138, 47)]})
