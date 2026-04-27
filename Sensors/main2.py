import threading
import time
import cv2
import numpy as np
from picamera2 import Picamera2
from ultralytics import YOLO
import grovepi
import json
import paho.mqtt.client as mqtt

THINGSBOARD_HOST = 'mqtt.eu.thingsboard.cloud'
ACCESS_TOKEN = 'cZ9i29BrJiAMTJv3d99w'

client = mqtt.Client()
client.username_pw_set(ACCESS_TOKEN)

try:
    print("Connecting to ThingsBoard")
    client.connect(THINGSBOARD_HOST, 1883, 60)
    client.loop_start()
    print("Successfully connected to ThingsBoard!")
except Exception as e:
    print(f"Failed to connect to ThingsBoard: {e}")

libraryStats = {
    "occupancy": 0,
    "temperature": 0,
    "humidity": 0,
    "noiseLevel": 0
}

last_update_time = time.time()
is_processing = True

latest_frame = None
frame_lock = threading.Lock()

model = YOLO('yolov8n.pt')

picam2 = Picamera2()
config = picam2.create_preview_configuration(
    main={"format": "RGB888", "size": (1440, 1080)}
)
picam2.configure(config)
picam2.start()

dhtPort = 4
soundPort = 0
grovepi.pinMode(soundPort, "INPUT")

def updateSensors():
    global libraryStats, latest_frame, last_update_time, is_processing
   
    while True:
        is_processing = True
        try:
            frame_to_process = None
            with frame_lock:
                if latest_frame is not None:
                    frame_to_process = latest_frame.copy()
           
            if frame_to_process is not None:
                results = model.predict(frame_to_process, classes=[0], conf=0.45, verbose=False)
                libraryStats["occupancy"] = len(results[0].boxes)

            [temp, humidity] = grovepi.dht(dhtPort, 0)
            noise = grovepi.analogRead(soundPort)

            if not isinstance(temp, float) or temp < -100:
                temp = libraryStats["temperature"]
            if not isinstance(humidity, float) or humidity < 0:
                humidity = libraryStats["humidity"]

            libraryStats["temperature"] = temp
            libraryStats["humidity"] = humidity
            libraryStats["noiseLevel"] = noise

            print(f"Stats Updated: {libraryStats}")

            try:
                telemetry_data = json.dumps(libraryStats)
                client.publish('v1/devices/me/telemetry', telemetry_data, 1)
                print("Data sent to ThingsBoard successfully.")
            except Exception as mqtt_err:
                print(f"Failed to publish to ThingsBoard: {mqtt_err}")

        except Exception as e:
            print(f"Error in sensor loop: {e}")
           
        is_processing = False
        last_update_time = time.time()
       
        time.sleep(10)


def draw_ui(frame, stats):
    global last_update_time, is_processing
   
    x, y, w, h = 30, 30, 600, 180
   
    overlay = frame.copy()
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 0), -1)
    alpha = 0.7
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.2
    color = (255, 255, 255)
    thickness = 1
   
    cv2.putText(frame, f"Occupancy: {stats['occupancy']} persons", (x + 20, y + 50), font, font_scale, color, thickness, cv2.LINE_AA)
   
    temp_str = f"{stats['temperature']:.1f}" if isinstance(stats['temperature'], float) else stats['temperature']
    hum_str = f"{stats['humidity']:.1f}" if isinstance(stats['humidity'], float) else stats['humidity']
   
    cv2.putText(frame, f"Temp: {temp_str} C", (x + 20, y + 100), font, font_scale, color, thickness, cv2.LINE_AA)
    cv2.putText(frame, f"Humidity: {hum_str}% | Noise: {stats['noiseLevel']}", (x + 20, y + 150), font, font_scale, color, thickness, cv2.LINE_AA)
   
    if is_processing:
        timer_text = "Updating Stats..."
        timer_color = (0, 255, 255)
    else:
        time_left = max(0.0, 10.0 - (time.time() - last_update_time))
        timer_text = f"Next update: {time_left:.1f}s"
        timer_color = (0, 255, 0)
       
    text_size = cv2.getTextSize(timer_text, font, font_scale, thickness)[0]
    text_width = text_size[0]
    frame_width = frame.shape[1]
   
    timer_x = frame_width - text_width - 30
    timer_y = 60
   
    cv2.rectangle(frame, (timer_x - 10, timer_y - 40), (timer_x + text_width + 10, timer_y + 15), (0, 0, 0), -1)
    cv2.putText(frame, timer_text, (timer_x, timer_y), font, font_scale, timer_color, thickness, cv2.LINE_AA)

    return frame


if __name__ == '__main__':
    print("Starting Library Monitor...")

    sensorThread = threading.Thread(target=updateSensors, daemon=True)
    sensorThread.start()

    cv2.namedWindow("Library Monitor Feed", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Library Monitor Feed", 1440, 1080)
   
    try:
        while True:
            frame = picam2.capture_array()
           
            with frame_lock:
                latest_frame = frame

            frame = draw_ui(frame, libraryStats)

            cv2.imshow("Library Monitor Feed", frame)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        picam2.stop()
        cv2.destroyAllWindows()
        client.loop_stop()
        client.disconnect()
        print("Disconnected from ThingsBoard.")
