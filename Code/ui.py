import cv2
import time
import state

#Draws a semi-transparent HUD (Heads Up Display) onto the camera frame
def draw_ui(frame, stats):

    # Define the coordinates and size for the dark background box
    x, y, w, h = 30, 30, 600, 180

    # Create a copy of the frame to draw the box on
    overlay = frame.copy()

    # Draw a solid black rectangle
    cv2.rectangle(overlay, (x, y), (x + w, y + h), (0, 0, 0), -1)

    # Blend the solid black box with the original frame set its transparency to 70%
    alpha = 0.7
    cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0, frame)

    # Setup text styling
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 1.2
    color = (255, 255, 255)
    thickness = 1

    # Draw the Occupancy data
    cv2.putText(frame, f"Occupancy: {stats['occupancy']} persons", (x + 20, y + 50), font, font_scale, color, thickness, cv2.LINE_AA)

    # Format the sensor data, floats round it to 1 decimal place
    temp_str = f"{stats['temperature']:.1f}" if isinstance(stats['temperature'], float) else stats['temperature']
    hum_str = f"{stats['humidity']:.1f}" if isinstance(stats['humidity'], float) else stats['humidity']

    # Draw Sensor data
    cv2.putText(frame, f"Temp: {temp_str} C", (x + 20, y + 100), font, font_scale, color, thickness, cv2.LINE_AA)
    cv2.putText(frame, f"Humidity: {hum_str}% | Noise: {stats['noiseLevel']}", (x + 20, y + 150), font, font_scale,
                color, thickness, cv2.LINE_AA)

    # Status/Timer UI Logic
    if state.is_processing:
        # If the background thread is working, show yellow "Updating" text
        timer_text = "Updating Stats..."
        timer_color = (0, 255, 255)  # Yellow
    else:
        # Calculate how much time is left until the next 10-second update
        time_left = max(0.0, 10.0 - (time.time() - state.last_update_time))
        timer_text = f"Next update: {time_left:.1f}s"
        timer_color = (0, 255, 0)

    # Calculate the exact width of the text so we can align it on the screen
    text_size = cv2.getTextSize(timer_text, font, font_scale, thickness)[0]
    text_width = text_size[0]
    frame_width = frame.shape[1]

    # Position the timer text in the top right corner
    timer_x = frame_width - text_width - 30
    timer_y = 60

    # Draw a small black background box just for the timer
    cv2.rectangle(frame, (timer_x - 10, timer_y - 40), (timer_x + text_width + 10, timer_y + 15), (0, 0, 0), -1)
    # Draw the timer text
    cv2.putText(frame, timer_text, (timer_x, timer_y), font, font_scale, timer_color, thickness, cv2.LINE_AA)

    # Return the modified frame so main.py can display it
    return frame