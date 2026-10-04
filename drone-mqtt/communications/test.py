import time
from datetime import datetime
from mqtt_client import SwarmClient, TOPIC_DETECTIONS, TOPIC_ALERTS

def on_alert_received(topic, data):
    """Callback συνάρτηση όταν ένα drone λαμβάνει alert από το LLM."""
    print(f"\n[DRONE] Ελήφθη σήμα κινδύνου στο {topic}!")
    print(f"Ενέργεια: {data.get('action')} | Κίνδυνος: {data.get('risk_level')}\n")

def main():
    print("=== Έναρξη Mock Drones Test ===")
    
    # 1. Δημιουργία 2 ψεύτικων drones
    drone1 = SwarmClient("drone_1")
    drone2 = SwarmClient("drone_2")
    
    # Το drone 1 ακούει για alerts που στέλνει το LLM σε όλο το σμήνος
    drone1.subscribe(TOPIC_ALERTS, on_alert_received)
    
    time.sleep(1) # Δίνουμε 1 δευτερόλεπτο να ολοκληρωθεί η σύνδεση στον broker
    
    # 2. Mock δεδομένα για το Drone 1 (ακριβώς με τα πεδία που συμφωνήσατε)
    det1 = {
        "drone_id": "drone_1",
        "object": "person",
        "confidence": 0.78,
        "direction": "left",
        "bbox": [120, 80, 220, 300],
        "frame": 450,
        "timestamp": datetime.now().isoformat()
    }
    
    # 3. Mock δεδομένα για το Drone 2
    det2 = {
        "drone_id": "drone_2",
        "object": "car",
        "confidence": 0.92,
        "direction": "center",
        "bbox": [400, 200, 600, 400],
        "frame": 455,
        "timestamp": datetime.now().isoformat()
    }
    
    # Στέλνουμε τα detections
    print("Το Drone 1 εντόπισε person. Γίνεται αποστολή...")
    drone1.publish(TOPIC_DETECTIONS.format(id="drone_1"), det1)
    time.sleep(2)
    
    print("Το Drone 2 εντόπισε car. Γίνεται αποστολή...")
    drone2.publish(TOPIC_DETECTIONS.format(id="drone_2"), det2)
    time.sleep(2)
    
    # 4. Προσομοίωση του LLM: Θα χρησιμοποιήσουμε το drone2 για να στείλει 
    # ένα ψεύτικο Alert στο σμήνος, παριστάνοντας τον κεντρικό κόμβο LLM
    mock_alert = {
        "drone_id": "drone_1",
        "object": "person",
        "description": "Ένας άνθρωπος περπατάει στα αριστερά...",
        "risk_level": "high",
        "action": "track_person",
        "recommendation": "Κράτα απόσταση",
        "broadcast": True,
        "target_drone": "all",
        "decision_source": "llm_mock"
    }
    print("Προσομοίωση LLaMA: Αποστολή Alert στο σμήνος...")
    drone2.publish(TOPIC_ALERTS, mock_alert)
    
    # Περιμένουμε λίγο για να προλάβει το drone 1 να τυπώσει το alert
    time.sleep(2)
    
    # Κλείνουμε τις συνδέσεις καθαρά
    drone1.stop()
    drone2.stop()
    print("=== Τέλος Test ===")

if __name__ == "__main__":
    main()