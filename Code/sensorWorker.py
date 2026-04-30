import time
import json
from ultralytics import YOLO
import grovepi

import config
import state
from mqtt_client import client

# Load the AI model and configure hardware once when the script starts
model = YOLO(config.YOLO_MODEL)
grovepi.pinMode(config.SOUND_PORT, "INPUT")


def updateSensors(): #the function runs continusly in the background
    while True:
        state.is_processing = True  # tell the UI we are starting an update
        try:
            # make a copy of the current camera frame
            frame_to_process = None
            with state.frame_lock:  # lock the frame so the main thread doesn't change it=
                if state.latest_frame is not None:
                    frame_to_process = state.latest_frame.copy()

            # Run YOLO Object Detection
            if frame_to_process is not None:
                # classes=[0] means only look for class 0 (people). conf=0.45 is the confidence threshold.
                results = model.predict(frame_to_process, classes=[0], conf=0.45, verbose=False)
                # Count how many bounding boxes (people) were found
                state.libraryStats["occupancy"] = len(results[0].boxes)

            #Read GrovePi Sensors
            [temp, humidity] = grovepi.dht(config.DHT_PORT, 0)
            noise = grovepi.analogRead(config.SOUND_PORT)

            # Error Checking (Sensors sometimes return bad data), If the data is invalid, keep the previous known value
            if not isinstance(temp, float) or temp < -100:
                temp = state.libraryStats["temperature"]
            if not isinstance(humidity, float) or humidity < 0:
                humidity = state.libraryStats["humidity"]

            # Update the shared state dictionary
            state.libraryStats["temperature"] = temp
            state.libraryStats["humidity"] = humidity
            state.libraryStats["noiseLevel"] = noise

            print(f"Stats Updated: {state.libraryStats}")

            #Send Data to the Cloud
            try:
                # Convert the Python dictionary to a JSON string
                telemetry_data = json.dumps(state.libraryStats)
                # Publish to the standard ThingsBoard telemetry topic
                client.publish('v1/devices/me/telemetry', telemetry_data, 1)
                print("Data sent to ThingsBoard successfully.")
            except Exception as mqtt_err:
                print(f"Failed to publish to ThingsBoard: {mqtt_err}")

        except Exception as e:
            print(f"Error in sensor loop: {e}")

        # Mark processing as finished and record the time
        state.is_processing = False
        state.last_update_time = time.time()

        # Pause this thread for 10 seconds before doing it all again
        time.sleep(10)