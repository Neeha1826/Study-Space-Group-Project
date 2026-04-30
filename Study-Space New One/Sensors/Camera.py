import os

# Silence libcamera / picamera2 logging
os.environ["LIBCAMERA_LOG_LEVELS"] = "*:ERROR"
os.environ["LIBCAMERA_LOG_TARGETS"] = "none"



# Silence Qt font warnings (do NOT force platform plugin)
os.environ["QT_LOGGING_RULES"] = "qt.qpa.fonts.warning=false"





import cv2                         # OpenCV for image processing and window display
from picamera2 import Picamera2   # Raspberry Pi Camera interface
import ncnn                       # NCNN inference engine for neural networks
import numpy as np                # Numerical operations
import time                       # Time handling (for 5‑second runtime)

# --------------------------------------------------
# Load YOLOv8 NCNN model
# --------------------------------------------------

model_path = "/home/pi/yolov8n_ncnn_model"  # Directory containing NCNN model files
net = ncnn.Net()                            # Create NCNN network instance
net.load_param(f"{model_path}/model.ncnn.param")  # Load model parameters
net.load_model(f"{model_path}/model.ncnn.bin")    # Load model weights

# --------------------------------------------------
# YOLO model configuration
# --------------------------------------------------

input_size = 640            # YOLOv8 expects 640x640 input images
conf_threshold = 0.45       # Confidence threshold for detections
nms_threshold = 0.45        # Non‑maximum suppression threshold

# --------------------------------------------------
# Camera initialization
# --------------------------------------------------

picam2 = Picamera2()        # Create PiCamera2 object

# Configure camera streams
config = picam2.create_preview_configuration(
    main={"format": "RGB888", "size": (1280, 720)},       # Main RGB stream
    raw={"format": "SRGGB10_CSI2P", "size": (1640, 1232)} # Raw sensor stream
)

picam2.configure(config)    # Apply camera configuration
picam2.start()              # Start the camera

# --------------------------------------------------
# YOLOv8 output decoding
# --------------------------------------------------

def decode_yolov8(mat_out, conf_thresh, nms_thresh, img_w, img_h):
    """
    Converts raw YOLOv8 output into filtered person bounding boxes.
    """

    out = np.array(mat_out)              # Convert NCNN output to NumPy array
    boxes, scores = [], []               # Store bounding boxes and confidences

    # Loop over all predictions
    for i in range(out.shape[1]):

        classes_scores = out[4:, i]      # All class probabilities
        score = np.max(classes_scores)  # Highest class probability

        # Only keep detections above confidence threshold
        if score > conf_thresh:

            class_id = np.argmax(classes_scores)

            # Class ID 0 corresponds to "person" in YOLO COCO dataset
            if class_id == 0:

                cx, cy, bw, bh = out[:4, i]  # Bounding box in center format

                # Scale bounding box back to original image size
                scale_w = img_w / input_size
                scale_h = img_h / input_size

                x1 = (cx - bw / 2) * scale_w  # Top‑left X
                y1 = (cy - bh / 2) * scale_h  # Top‑left Y

                boxes.append([
                    int(x1),
                    int(y1),
                    int(bw * scale_w),
                    int(bh * scale_h)
                ])
                scores.append(float(score))

    # Remove duplicate overlapping boxes
    indices = cv2.dnn.NMSBoxes(boxes, scores, conf_thresh, nms_thresh)

    # Return final boxes and scores
    return [(boxes[i], scores[i]) for i in indices]

# --------------------------------------------------
# Debug camera method (5 seconds)
# --------------------------------------------------

def run_camera_debug(duration, show_window=True):
    """
    Runs camera inference for the given number of seconds.
    Tracks and returns the highest number of people detected.
    If show_window is False, no camera window is displayed.
    """

    start_time = time.time()        # Record start time
    max_people_detected = 0         # Highest people count seen

    # Create debug window only if requested
    if show_window:
        cv2.namedWindow("Pi Detector", cv2.WINDOW_NORMAL)
        cv2.resizeWindow("Pi Detector", 1280, 720)

    try:
        while True:

            # Stop after 5 seconds
            if time.time() - start_time >= duration:
                break

            # Capture frame from camera
            frame = picam2.capture_array()

            # Flip image 180° because camera is mounted upside‑down
            frame = cv2.rotate(frame, cv2.ROTATE_180)

            # Convert RGB (camera format) to BGR (OpenCV format)
            img_draw = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

            h, w, _ = frame.shape     # Get frame dimensions

            # Prepare frame for NCNN inference
            mat_in = ncnn.Mat.from_pixels_resize(
                frame,
                ncnn.Mat.PixelType.PIXEL_RGB,
                w,
                h,
                input_size,
                input_size
            )

            # Normalize pixel values from [0‑255] to [0‑1]
            mat_in.substract_mean_normalize(
                [0, 0, 0],
                [1/255.0, 1/255.0, 1/255.0]
            )

            # Run YOLO inference
            ex = net.create_extractor()
            ex.input("in0", mat_in)
            _, mat_out = ex.extract("out0")

            # Decode detections
            detections = decode_yolov8(
                mat_out,
                conf_threshold,
                nms_threshold,
                w,
                h
            )

            # Update maximum number of people seen
            max_people_detected = max(
                max_people_detected,
                len(detections)
            )

            # Draw bounding boxes only if debug window is enabled
            if show_window:
                for (box, score) in detections:
                    bx, by, bw_box, bh_box = box
                    cv2.rectangle(
                        img_draw,
                        (bx, by),
                        (bx + bw_box, by + bh_box),
                        (0, 255, 0),
                        3
                    )

                # Overlay people count
                cv2.putText(
                    img_draw,
                    f"People: {len(detections)}",
                    (50, 80),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.5,
                    (255, 0, 0),
                    3
                )

                # Show debug window
                cv2.imshow("Pi Detector", img_draw)

                # Allow manual exit
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

    finally:
        if show_window:
            cv2.destroyAllWindows()
            
    
    return max_people_detected

# --------------------------------------------------
# Run once (debug enabled)
# --------------------------------------------------

#try:
    #highest_count = run_camera_debug(show_window=True)
    #print("Highest number of people detected:", highest_count)

#finally:
    #picam2.stop()   # Safely stop the camera
