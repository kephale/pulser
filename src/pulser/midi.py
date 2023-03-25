import time
from superqt.utils import thread_worker
from psygnal import Signal
import pygame.midi
import logging

import sys

LOGGER = logging.getLogger("pulser.midi")
# LOGGER.setLevel(logging.DEBUG)

streamHandler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
streamHandler.setFormatter(formatter)
LOGGER.addHandler(streamHandler)


# TODO XTouchMini should either be a dict/subclass of a MidiPulser or smth
class XTouchMini:
    """
    xtouch

    events = (keycode, control_element_id, value, 0)

    keycodes:
    - 186 is a knob
    - 154 is button down
    - 138 is button up

    values are 0-127

    Note: a and b layers change control_element_ids.

    (a, b)

    dials: 1-8, 11-18
    buttons
    dials: 0-7, 24-31
    row 1: 8-15, 32-39
    row 2: 16-23, 40-47
    slider: 9, 10"""

    SLIDER = 186
    BUTTON_DOWN = 154
    BUTTON_UP = 138

    def __init__(self) -> None:
        # All IDs
        # knobs a and b layers and slider
        self.knob_ids = set(range(1, 9)).union(range(11, 19)).union(range(9, 11))
        # buttons: knobs, rows 1 and 2
        self.button_ids = (
            set(range(0, 8))
            .union(range(24, 32))
            .union(range(8, 16))
            .union(range(32, 40))
            .union(range(16, 24))
            .union(range(40, 48))
        )

        # Setup signals
        # TODO this actually makes SignalInstance's because otherwise they dont work
        self.knob_signals = {
            idx: Signal(int, name=f"knob_{idx}").__get__(self) for idx in self.knob_ids
        }
        self.button_signals = {
            idx: Signal(bool, name=f"button_{idx}").__get__(self)
            for idx in self.button_ids
        }

        # Set initial values
        self._knob_values = {idx: 63 for idx in self.knob_ids}
        self._button_values = {idx: False for idx in self.button_ids}

        # Set state
        self.running = False
        self.worker = None

    def set_knob_value(self, idx, value) -> None:
        if value != self._knob_values[idx]:
            self._knob_values[idx] = value
            # emit the signal
            self.knob_signals[idx].emit(self._knob_values[idx])

    def set_button_value(self, idx, value) -> None:
        if value != self._button_values[idx]:
            self._button_values[idx] = value
            # emit the signal
            self.button_signals[idx].emit(self._button_values[idx])

    def get_button_value(self, idx) -> bool:
        return self._button_values[idx]

    def start(self):
        """Start an XTouch listener"""

        def xtouch_event_handler(event):
            """This logic is separate from the poller so it can be run
            in a different thread."""

            LOGGER.debug(f"event handler: {event}")

            event_code, timestamp = event
            keycode, control_element_id, value, _ = event_code

            if keycode == self.SLIDER:
                self.set_knob_value(control_element_id, value)
            elif keycode == self.BUTTON_DOWN:
                # Flip button state
                self.set_button_value(
                    control_element_id, not self.get_button_value(control_element_id)
                )

        @thread_worker
        def midi_poller(input_device):
            # This function should start a listener that yields events
            while self.running:
                if input_device.poll():
                    events = pygame.midi.Input.read(input_device, 1)
                    LOGGER.debug(f"Yielding {events[0]}")
                    yield events[0]
                # TODO make this sleep duration a parameter
                time.sleep(0.015)

        if not pygame.midi.get_init():
            pygame.midi.init()

        # We're assuming only 1 input device and it is xtouch mini
        input_device = pygame.midi.Input(pygame.midi.get_default_input_id())

        self.worker = midi_poller(input_device)
        self.worker.yielded.connect(xtouch_event_handler)

        self.worker.start()

        self.running = True

    def stop(self):
        self.worker.quit()
        self.running = False


if __name__ == "__main__":
    xtouch = XTouchMini()
    xtouch.start()

    pulser = xtouch.knob_signals[8]

    @pulser.connect
    def listener(value):
        LOGGER.debug(f"Slider 9 has value: {value}")
