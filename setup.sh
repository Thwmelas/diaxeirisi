#!/bin/bash

set -e

PX4_GAZEBO_DIR="$HOME/PX4-Autopilot/Tools/simulation/gazebo-classic/sitl_gazebo-classic"
PATCH_FILE="$(dirname "$0")/iris_camera.patch"

if [ ! -d "$PX4_GAZEBO_DIR" ]; then
    echo "ERROR: Δεν βρέθηκε το $PX4_GAZEBO_DIR"
    echo "       Βεβαιώσου ότι το PX4-Autopilot είναι ήδη cloned στο ~/PX4-Autopilot"
    exit 1
fi

cd "$PX4_GAZEBO_DIR"

# Έλεγχος αν το patch έχει ήδη εφαρμοστεί 
if grep -q "camera_link" models/iris/iris.sdf.jinja 2>/dev/null; then
    echo "✓ Το iris camera patch είναι ήδη εφαρμοσμένο."
else
    echo "Εφαρμόζω το iris_camera.patch (προσθήκη RGB κάμερας στο iris model)..."
    git apply "$PATCH_FILE"
    echo "✓ Το patch εφαρμόστηκε επιτυχώς."
fi

echo ""
echo "Setup ολοκληρώθηκε. Το iris model έχει πλέον ενσωματωμένη RGB κάμερα"
echo "(GStreamer stream στο UDP port 5600+N, όπου N = instance number)."
