# src/config.py



YOLO_MODEL = "yolov8n.pt"  # Use 'n' (nano) for speed, 's' for accuracy
CONF_THRES=0.35

# VIDEO_SOURCE = "rtsp://admin:sss12345@172.16.2.154:554/Streaming/Channels/101"
# CONF_THRES = 0.35  # Lower for CCTV (distant people)

# For Webcam Testing
VIDEO_SOURCE = 0


# For Video File
# VIDEO_SOURCE = "test_video.mp4"
# CONF_THRES = 0.40