import threading
import cv2
from picamera2 import Picamera2
import state
from mqtt_client import connect_mqtt, disconnect_mqtt
from ui import draw_ui
from sensor_worker import updateSensors

if __name__ == '__main__':
    print("Starting Library Monitor...")

    # Connect to the MQTT Broker
    connect_mqtt()

    # Initialize the Raspberry Pi Camera
    picam2 = Picamera2()
    cam_config = picam2.create_preview_configuration(
        main={"format": "RGB888", "size": (1440, 1080)}  # Set resolution and color format
    )
    picam2.configure(cam_config)
    picam2.start()

    # Launch the Background Worker Thread
    # daemon=True means this thread will automatically die when we close the main program
    sensorThread = threading.Thread(target=updateSensors, daemon=True)
    sensorThread.start()

    #Setup the display window
    cv2.namedWindow("Library Monitor Feed", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Library Monitor Feed", 1440, 1080)

    try:
        # This loop runs as fast as the camera can provide frames (usually 30+ times a second)
        while True:
            # Grab a frame from the camera
            frame = picam2.capture_array()

            # Safely update the shared state so the background thread can grab it
            with state.frame_lock:
                state.latest_frame = frame

            # Pass the frame to ui.py to draw the text and graphics
            frame = draw_ui(frame, state.libraryStats)

            # Show the final composite frame on the screen
            cv2.imshow("Library Monitor Feed", frame)

            # Listen for keyboard input. If 'q' is pressed, break the loop and exit.
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    except KeyboardInterrupt:
        # Catches CTRL+C in the terminal
        print("Shutting down...")
    finally:
        # Clean up resources safely
        picam2.stop()
        cv2.destroyAllWindows()
        disconnect_mqtt()