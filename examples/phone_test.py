import threading
from queue import SimpleQueue
from typing import Any

import toolz as tz

from psygnal import Signal
from qtpy.QtCore import QObject, Qt, QTimer, Signal
from qtpy.QtWidgets import QApplication, QPushButton

from pulser._browser import RemoteBrowser


print("Main Thread name", threading.current_thread().name)
app = QApplication([])

m = RemoteBrowser("Phone")

# some callback to inspect the events
@tz.curry
def on_event(event, pulser=m):
    controller = pulser._controller
    print(f"currently gyro: {controller.gyroscope} accel: {controller.accelerometer}")


m.events.connect(on_event)

button = QPushButton("Quit")
button.show()
button.clicked.connect(m.stop)
button.clicked.connect(app.quit)

# app.exec_()
