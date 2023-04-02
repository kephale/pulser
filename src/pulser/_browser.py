from flask import Flask, request, render_template_string, jsonify
import datetime
import time
import threading

from dataclasses import Field, InitVar, asdict, dataclass, field, fields
import threading
from threading import Thread
from typing import Any, Callable, ClassVar, Protocol

import toolz as tz
import numpy as np

from functools import partial

from napari.utils.events import EmitterGroup, Event

import logging

log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)

"""
This is still a work in progress.

This is a merging of a previous implementation for phone control with
Talley's pattern from https://github.com/kephale/pulser/pull/3
"""

class QueueLike(Protocol):
    def get(self) -> Any:
        ...

    def put(self, item: Any, block: bool = True, timeout: int | None = None) -> None:
        ...

    def empty(self) -> bool:
        ...


class FlaskController:
    def __init__(self):
        self.events = EmitterGroup(
            accelerometer=Event,
            gyroscope=Event,
        )
        self.lookup = {}
        self._accelerometer = np.array((0, 0, 0, 0))
        self._gyroscope = np.array((0, 0, 0))

    @property
    def accelerometer(self):
        return self._accelerometer

    @accelerometer.setter
    def accelerometer(self, array):
        if np.all(array == self._accelerometer):
            return
        self._accelerometer = np.array(array)
        self.events.accelerometer()

    @property
    def gyroscope(self):
        return self._gyroscope

    @gyroscope.setter
    def gyroscope(self, array):
        if np.all(array == self._gyroscope):
            return
        self._gyroscope = np.array(array)
        self.events.gyroscope()


@dataclass
class RemoteBrowser:
    _NAME: str
    _types: ClassVar[dict[str, type]] = {}
    # _output: ClassVar[pygame.midi.Output | None] = None
    # _input: ClassVar[pygame.midi.Input | None] = None
    _EVENT2NAME: ClassVar[dict[tuple[int, int], str]] = {}
    _NAME2EVENT: ClassVar[dict[str, tuple[int, int]]] = {}

    def __post_init__(self) -> None:
        self._types = {f.name: f.type for f in fields(self)}  # type: ignore
        self._stop_event = threading.Event()
        self._thread: Thread | None = None

        # TODO the __name__ here is prob wrong
        self.app = Flask(__name__)

        self._controller = FlaskController()

        target = _block_and_read_to_attr
        args = (self.app, self._controller)

        # Combine existing page.html with this

        self._thread = Thread(target=target, args=args)
        self._thread.start()

    def __setattr__(self, name: str, value: Any) -> None:
        type_ = self._types.get(name)
        if type_ is not None and not isinstance(value, type_):
            value = type_(value)
        super().__setattr__(name, value)
        if name in self._NAME2EVENT is not None:
            self._send_value(name, value)

    def _send_value(self, name: str, value: int) -> None:
        """Send a value to the midi device."""
        status, data1 = self._NAME2EVENT[name]
        if isinstance(value, bool):
            value = 127 if value else 0

    def send_all(self) -> None:
        """Sync the state of the python model with the midi device.
        I don't think MIDI has a spec for reading the state of a device, so
        this is the best we can do.
        """
        for name, value in asdict(self).items():
            self._send_value(name, value)

    def stop(self) -> None:
        """Stop the thread watching the midi device."""
        self._stop_event.set()

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


# TODO note that this one doesn't block anymore
# thread target that directly writes attributes
# in the case of an evented dataclass, this will emit events in the thread
# that's watching the midi device
def _block_and_read_to_attr(
    flask_app: Flask,
    _controller: FlaskController,
) -> None:
    if flask_app is None:
        raise RuntimeError("No Flask app found")

    partial_update_view = partial(update_view, controller=_controller)

    # Add routes for both displaying and the update trigger
    flask_app.add_url_rule("/", "index", view_func=index_view)
    flask_app.add_url_rule("/<device>/<action>", "index", view_func=index_view)
    flask_app.add_url_rule(
        "/update", "update", view_func=partial_update_view, methods=["POST"]
    )

    # TODO make these configurable
    host_name = "0.0.0.0"
    port = "5000"

    flask_app.run(host=host_name, port=port, debug=True, use_reloader=False)


def index_view(device=None, action=None):
    global running
    global value

    # if device:
    #     if action == 'on':
    #         if not running:
    #             print('start')
    #             running = True
    #             threading.Thread(target=rpi_function).start()
    #         else:
    #             print('already running')
    #     elif action == 'off':
    #         if running:
    #             print('stop')
    #             running = False  # it should stop thread
    #         else:
    #             print('not running')

    return render_template_string(
        """<!DOCTYPE html>
   <head>
      <script src="https://ajax.googleapis.com/ajax/libs/jquery/3.3.1/jquery.min.js"></script>
   </head>
   <body>
        <a href="/bioR/on">TURN ON</a>  
        <a href="/bioR/off">TURN OFF</a>

<p style="margin-top:1rem;">Num. of datapoints: <span class="badge badge-warning" id="num-observed-events">0</span></p>


<h4 style="margin-top:0.75rem;">Orientation</h4>
<ul>
  <li>X-axis (&beta;): <span id="Orientation_b">0</span><span>&deg;</span></li>
  <li>Y-axis (&gamma;): <span id="Orientation_g">0</span><span>&deg;</span></li>
  <li>Z-axis (&alpha;): <span id="Orientation_a">0</span><span>&deg;</span></li>
</ul>

<h4>Accelerometer</h4>
<ul>
  <li>X-axis: <span id="Accelerometer_x">0</span><span> m/s<sup>2</sup></span></li>
  <li>Y-axis: <span id="Accelerometer_y">0</span><span> m/s<sup>2</sup></span></li>
  <li>Z-axis: <span id="Accelerometer_z">0</span><span> m/s<sup>2</sup></span></li>
  <li>Data Interval: <span id="Accelerometer_i">0</span><span> ms</span></li>
</ul>

<h4>Accelerometer including gravity</h4>

<ul>
  <li>X-axis: <span id="Accelerometer_gx">0</span><span> m/s<sup>2</sup></span></li>
  <li>Y-axis: <span id="Accelerometer_gy">0</span><span> m/s<sup>2</sup></span></li>
  <li>Z-axis: <span id="Accelerometer_gz">0</span><span> m/s<sup>2</sup></span></li>
</ul>

<h4>Gyroscope</h4>
<ul>
  <li>X-axis: <span id="Gyroscope_x">0</span><span>&deg;/s</span></li>
  <li>Y-axis: <span id="Gyroscope_y">0</span><span>&deg;/s</span></li>
  <li>Z-axis: <span id="Gyroscope_z">0</span><span>&deg;/s</span></li>
</ul>
    
        <script>

let orientationA = 0;
let orientationB = 0;
let orientationG = 0;
let accelerometerX = 0;
let accelerometerY = 0;
let accelerometerZ = 0;
let accelerometerI = 0;
let gyroscopeZ = 0;
let gyroscopeY = 0;
let gyroscopeX = 0;                        
    
function handleOrientation(event) {
  updateFieldIfNotNull('Orientation_a', event.alpha);
  updateFieldIfNotNull('Orientation_b', event.beta);
  updateFieldIfNotNull('Orientation_g', event.gamma);
    orientationA = event.alpha;
    orientationB = event.beta;
    orientationG = event.gamma;
  incrementEventCount();
}

function incrementEventCount(){
  let counterElement = document.getElementById("num-observed-events")
  let eventCount = parseInt(counterElement.innerHTML)
  counterElement.innerHTML = eventCount + 1;
}

function updateFieldIfNotNull(fieldName, value, precision=10){
  if (value != null)
    document.getElementById(fieldName).innerHTML = value.toFixed(precision);
}

function handleMotion(event) {
  updateFieldIfNotNull('Accelerometer_gx', event.accelerationIncludingGravity.x);
  updateFieldIfNotNull('Accelerometer_gy', event.accelerationIncludingGravity.y);
  updateFieldIfNotNull('Accelerometer_gz', event.accelerationIncludingGravity.z);

    accelerometerX = event.accelerationIncludingGravity.x;
    accelerometerY = event.accelerationIncludingGravity.y;
    accelerometerZ = event.accelerationIncludingGravity.z;
    accelerometerI = event.interval;
    gyroscopeZ = event.rotationRate.alpha;
    gyroscopeX = event.rotationRate.beta;
    gyroscopeY = event.rotationRate.gamma;

  updateFieldIfNotNull('Accelerometer_x', event.acceleration.x);
  updateFieldIfNotNull('Accelerometer_y', event.acceleration.y);
  updateFieldIfNotNull('Accelerometer_z', event.acceleration.z);

  updateFieldIfNotNull('Accelerometer_i', event.interval, 2);

  updateFieldIfNotNull('Gyroscope_z', event.rotationRate.alpha);
  updateFieldIfNotNull('Gyroscope_x', event.rotationRate.beta);
  updateFieldIfNotNull('Gyroscope_y', event.rotationRate.gamma);

  // TODO send event information to server
  // https://www.geeksforgeeks.org/how-to-send-data-from-client-side-to-node-js-server-using-ajax-without-page-reloading/
  incrementEventCount();


}

window.addEventListener("devicemotion", handleMotion);
window.addEventListener("deviceorientation", handleOrientation);    
    
            setInterval(function(){$.ajax({
                url: '/update',
                type: 'POST',
                contentType: 'application/x-www-form-urlencoded; charset=UTF-8',
                data: jQuery.param({
    accelerometerX: accelerometerX,
    accelerometerY: accelerometerY,
    accelerometerZ: accelerometerZ,
    accelerometerI: accelerometerI,
    gyroscopeX: gyroscopeX,
    gyroscopeY: gyroscopeY,
    gyroscopeZ: gyroscopeZ}),
                success: function(response) {
                    console.log(response);
    document.getElementById("num-observed-events")
                    $("#num").html(response["value"]);
                    $("#time").html(response["time"]);
                },
                error: function(error) {
                    console.log(error);
                }
            })}, 100);

    
        </script>
   </body>
</html>
"""
    )


@tz.curry
def update_view(controller=None):
    accel = np.array(
        (
            float(request.form["accelerometerX"]),
            float(request.form["accelerometerY"]),
            float(request.form["accelerometerZ"]),
            float(request.form["accelerometerI"]),
        )
    )
    gyro = np.array(
        (
            float(request.form["gyroscopeX"]),
            float(request.form["gyroscopeY"]),
            float(request.form["gyroscopeZ"]),
        )
    )

    controller.accelerometer = accel
    controller.gyroscope = gyro
    #    for k, v in request.form.items():
    #        phone_controller.lookup[k] = float(v)
    return jsonify(
        {
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
        }
    )


# ############ Graphics part
import napari
import numpy as np


viewer = napari.Viewer(ndisplay=3)

w = h = d = 100

# img = np.zeros((w, h))
img = np.random.rand(w, h, d)

cx = int(w / 2)
cy = int(h / 2)

layer = viewer.add_image(img)

layer.contrast_limits = [0, 1]
layer.colormap = "viridis"

listening = True

my_pulser = RemoteBrowser("Phone")


@tz.curry
def on_event(event, pulser=my_pulser):
    controller = pulser._controller
    print(f"currently gyro: {controller.gyroscope} accel: {controller.accelerometer}")
    viewer.camera.angles = controller.gyroscope * 0.1

    viewer.camera.center = viewer.camera.center + controller.accelerometer[:3] * 0.1

    angles = controller.gyroscope


# phone_controller.events.gyroscope.connect(on_event)
my_pulser._controller.events.accelerometer.connect(on_event)

# napari.run()
