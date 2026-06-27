import cv2

pipeline = "udpsrc port=5601 ! application/x-rtp ! rtph264depay ! avdec_h264 ! videoconvert ! appsink"
cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)

if not cap.isOpened():
    print("ERROR: Could not open stream")
else:
    ret, frame = cap.read()
    print("ret:", ret)
    if ret:
        print("frame shape:", frame.shape)
        cv2.imwrite("test_frame.jpg", frame)
        print("Saved test_frame.jpg")
    cap.release()
