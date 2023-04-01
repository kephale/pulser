import threading
from queue import SimpleQueue
from typing import Any

from psygnal import Signal
from qtpy.QtCore import QObject, Qt, QTimer, Signal
from qtpy.QtWidgets import QApplication, QPushButton

from pulser._xtouch import XTouch


class QueueRelay(QTimer):
    on_q = Signal(object)

    def __init__(
        self,
        interval_ms: int = 0,
        single_shot: bool = False,
        timer_type: Qt.TimerType = Qt.TimerType.PreciseTimer,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        if interval_ms:
            self.setInterval(interval_ms)
        self.setSingleShot(single_shot)
        self.setTimerType(timer_type)

        self.queue: SimpleQueue[Any] = SimpleQueue()
        self.timeout.connect(self._emit_queue_contents)

    def _emit_queue_contents(self) -> None:
        while not self.queue.empty():
            self.on_q.emit(self.queue.get())


print("Main Thread name", threading.current_thread().name)
app = QApplication([])

EMIT_FROM_MAIN_THREAD = False
m = XTouch(start_watch=False)

# some callback to inspect the events
def on_event(event):
    print(event, "from", threading.current_thread().name)

if EMIT_FROM_MAIN_THREAD:
    # to emit from the main thread, we need a QObject in the main thread
    # that watches a queue and emits the contents of the queue
    # this kind of object could be created for any event loop driver.
    t = QueueRelay()
    t.on_q.connect(on_event)

    # passing the queue to the watch method tells it to dump events to the queue
    # instead of emitting them directly
    m.watch(q=t.queue)
    t.start()
else:
    # otherwise, 
    m.events.connect(on_event)
    m.watch()

button = QPushButton("Quit")
button.show()
button.clicked.connect(m.stop)
button.clicked.connect(app.quit)

app.exec_()
