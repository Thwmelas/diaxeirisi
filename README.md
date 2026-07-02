# AI-Enabled Drone Swarm — Simulation & Integration



##Τι φτιάξαμε

Φτιάξαμε ένα σύστημα όπου 3 drones πετούν αυτόνομα πάνω από μια εικονική πόλη βλέπουν αντικείμενα με κάμερα αποφασίζουν αν υπάρχει κίνδυνος και ειδοποιούν το υπόλοιπο σμήνος αυτόματα.

Όλο αυτό τρέχει σε προσομοίωση μέσω Gazebo και ROS2



##Πώς λειτουργεί

Κάθε drone έχει μια κάμερα που στέλνει ζωντανό video.Το video πηγαίνει σε ένα YOLO μοντέλο που αναγνωρίζει αντικείμενα (αυτοκίνητα, ανθρώπους, κτίρια κλπ). Αν εντοπιστεί κάτι, το σύστημα αξιολογεί τον κίνδυνο (χαμηλός/μέτριος/υψηλός/κρίσιμος) και στέλνει ειδοποίηση μέσω MQTT σε ολόκληρο το σμήνος.

Τα drones δεν μένουν σταθερά — κάνουν αυτόνομη περιπολία σε τυχαία σημεία και σε κάθε σημείο περιστρέφονται 360° για να δουν ολόκληρη την περιοχή γύρω τους.



##Γιατί κάναμε κάποιες επιλογές

**Γιατί iris drone αντί για typhoon_h480:**  
Το typhoon_h480 έχει bug στον EKF2 estimator σε PX4 v1.14.3 που το εμποδίζει να κάνει arm. Επιλέξαμε το iris και προσθέσαμε κάμερα πάνω του με patch στο SDF model.

**Γιατί GStreamer/UDP αντί για ROS2 image topic:**  
Το iris με patch στέλνει video μέσω GStreamer/H264 στο UDP port 5601/5602/5603  ένα port για κάθε drone, αποφεύγει την ανάγκη για επιπλέον ROS2 bridge που θα πρόσθετε περιττή πολυπλοκότητα.


**Γιατί rule-based fallback στο LLM:**  
Το LLM module έχει ενσωματωμένο rule-based fallback για να μην εξαρτάται από εξωτερικό API Έτσι το σύστημα λειτουργεί πάντα ακόμα και χωρίς σύνδεση στο internet.


## Τα βασικά αρχεία και τι κάνουν

### `setup.sh`
Το πρώτο πράγμα που τρέχεις σε νέο μηχάνημα. Κάνει αυτόματα τρία πράγματα:
- Εφαρμόζει το camera patch στο iris model (προσθέτει RGB κάμερα)
- Αντιγράφει τον custom κόσμο (`yolo_scenario.world`) στο σωστό μέρος μέσα στο PX4
- Κατεβάζει αυτόματα τα 8 Gazebo models από το Fuel repository (σπίτια, δέντρα, αυτοκίνητα, άνθρωποι κλπ) και διορθώνει τα paths τους

Χωρίς αυτό το script, θα έπρεπε να κάνεις όλα αυτά χειροκίνητα κάθε φορά.

### `simulation_launch/run_all.sh`
Ξεκινά ολόκληρο το pipeline με μία εντολή. Ανοίγει 3 ξεχωριστά terminal windows:
- Ένα για το Gazebo simulation (3 drones μέσα στον κόσμο της πόλης)
- Ένα για το decision node (λαμβάνει MQTT alerts και καταγράφει αποφάσεις)
- Ένα για το integration node (YOLO + LLM + MQTT sender)

Επίσης ελέγχει αν τρέχει ο Mosquitto broker και τον ξεκινά αν χρειάζεται. Περιμένει 20 δευτερόλεπτα για να σταθεροποιηθεί το simulation πριν ξεκινήσει τα υπόλοιπα.

### `simulation_launch/stop_all.sh`
Σταματά καθαρά όλες τις διεργασίες του συστήματος (Gazebo, PX4, MicroXRCEAgent, integration node, decision node). Χρήσιμο γιατί αν κλείσεις τα terminals με το X χωρίς να σταματήσεις πρώτα τις διεργασίες μπορεί να μείνουν ζωντανές στο background και να προκαλέσουν προβλήματα στην επόμενη εκκίνηση.

### `drone_control/takeoff.py`
Στέλνει εντολή arm και απογείωσης στο px4_1 drone μέσω ROS2 offboard control. Το σημαντικό εδώ είναι ότι δεν απλά στέλνει μια εντολή και τελειώνει πρέπει να τρέχει συνεχώς γιατί το PX4 σε offboard mode απαιτεί συνεχές heartbeat σήμα. Αν το σταματήσεις το drone μπαίνει αυτόματα σε failsafe και προσγειώνεται. Γι' αυτό προσθέσαμε graceful land με Ctrl+C αντί να πέφτει το drone απότομα στέλνει πρώτα εντολή ομαλής προσγείωσης.

### `drone_control/patrol.py`
Αυτόνομη περιπολία ενός drone. Επιλέγει τυχαία 6 σημεία μέσα στη σκηνή και πετάει από το ένα στο άλλο. Μόλις φτάσει σε κάθε σημείο, κάνει αργή περιστροφή 360° (20 δευτερόλεπτα) ώστε η κάμερα να καλύψει ολόκληρη την περιβάλλουσα περιοχή. Μετά από όλα τα waypoints, επιστρέφει στο κέντρο και προσγειώνεται μόνο του.

### `drone_control/patrol_swarm.py`
Κάνει ακριβώς ό,τι το `patrol.py` αλλά για και τα 3 drones ταυτόχρονα. Ξεκινά 3 παράλληλα processes, το καθένα με διαφορετικά τυχαία waypoints, ώστε να καλύπτουν διαφορετικές περιοχές της σκηνής παράλληλα. Τα logs όλων εμφανίζονται στο ίδιο terminal με prefix [px4_1], [px4_2], [px4_3].

### `perception_node/drone_integration.py`
Το κεντρικό αρχείο που συνδέει όλα τα κομμάτια. Κάνει τρία πράγματα παράλληλα σε ένα loop:
1. Διαβάζει frames από την κάμερα του drone μέσω GStreamer
2. Τρέχει YOLO detection + HSV fire detection σε κάθε frame
3. Για κάθε ανίχνευση, παίρνει την πραγματική θέση του drone από ROS2, ζητά απόφαση από το LLM module, και στέλνει MQTT alert

### `drone_swarm/tf_broadcaster.py`
Διαβάζει τη θέση και τον προσανατολισμό κάθε drone από ROS2 topics και τα δημοσιεύει ως TF transforms. Αυτό επιτρέπει στο RViz2 να εμφανίζει τα 3 drones σε πραγματικό χρόνο σε 3D χώρο, ώστε να βλέπεις οπτικά πού βρίσκεται το καθένα και πώς κινείται.



## Πώς να το τρέξεις

Πρώτα χρειάζεσαι:
- ROS2 Humble + Gazebo Classic 11 σε Ubuntu 22.04
- PX4-Autopilot v1.14.3 στο `~/PX4-Autopilot`
- Python packages: `pip install ultralytics paho-mqtt "numpy<2" --user`
- Mosquitto: `sudo apt install mosquitto mosquitto-clients`
- Το `best.pt` (YOLO weights) `perception_node/best.pt`

Μετά, τρέξε το setup script μία φορά:
```bash
bash setup.sh
```

Και για να ξεκινήσεις όλο το σύστημα:
```bash
bash simulation_launch/run_all.sh
```

Για αυτόνομη περιπολία και των 3 drones ταυτόχρονα (αφού ανέβει πρώτα το simulation):
```bash
source /opt/ros/humble/setup.bash
source ~/drone_ws/install/setup.bash
python3 drone_control/patrol_swarm.py
```


