import threading
import time

# State variables
libraryStats = {
    "occupancy": 0,
    "temperature": 0,
    "humidity": 0,
    "noiseLevel": 0
}

# Threading controls
last_update_time = time.time()
is_processing = True
latest_frame = None
frame_lock = threading.Lock()