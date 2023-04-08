from psygnal.qt import start_emitting_from_queue
from qtpy.QtCore import QCoreApplication

from pulser._xtouch import XTouchMini

app = QCoreApplication([])
d = XTouchMini()

# connect signals to be emitted in the main thread
d.knob.changed.connect(lambda k, v: print(f"knob {k} changed to {v}"), thread="main")
d.button.pressed.connect(lambda b: print(f"button {b} pressed"), thread="main")
# press the stop button to quit
d.button[14].pressed.connect(lambda: app.quit(), thread="main")

# start the midi thread
d.watch()
# start QTimer emitting signals from the main thread
start_emitting_from_queue()

print("Press the stop button to quit    ")
app.exec_()
