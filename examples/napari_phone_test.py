import napari
import numpy as np
import toolz as tz

from pulser._browser import RemoteBrowser

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

    viewer.camera.center = viewer.camera.center + controller.accelerometer[:3][::-1] * 0.1

    angles = controller.gyroscope


# phone_controller.events.gyroscope.connect(on_event)
my_pulser._controller.events.accelerometer.connect(on_event)

# napari.run()
