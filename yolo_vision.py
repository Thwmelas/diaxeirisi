import cv2
from ultralytics import YOLO

# Φόρτωση του εκπαιδευμένου μοντέλου
model = YOLO('best.pt')

def detect_objects(gazebo_camera_frame):
    # Πρόβλεψη στο τρέχον καρέ
    results = model.predict(source=gazebo_camera_frame, imgsz=1024, conf=0.5, verbose=False)
    
    for result in results:
        for box in result.boxes:
            # Εξαγωγή κλάσης, συντεταγμένων και σιγουριάς
            class_id = int(box.cls[0].item())
            class_name = model.names[class_id]
            
            coords = box.xyxy[0].tolist()
            confidence = box.conf[0].item()
            
            print(f"Εντοπίστηκε: {class_name} | Confidence: {confidence:.2f} | Coords: {coords}")

    # Επιστρέφει το frame με τα σχεδιασμένα bounding boxes
    return results[0].plot()
