#!/bin/bash
set -e

PX4_GAZEBO_DIR="$HOME/PX4-Autopilot/Tools/simulation/gazebo-classic/sitl_gazebo-classic"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PATCH_FILE="$SCRIPT_DIR/iris_camera.patch"
WORLD_FILE="$SCRIPT_DIR/yolo_scenario.world"
MODELS_DIR="$HOME/.gazebo/models"

if [ ! -d "$PX4_GAZEBO_DIR" ]; then
    echo "ERROR: Δεν βρέθηκε το $PX4_GAZEBO_DIR"
    echo "       Βεβαιώσου ότι το PX4-Autopilot είναι ήδη cloned στο ~/PX4-Autopilot"
    exit 1
fi

# ---- 1. Camera patch στο iris ----
cd "$PX4_GAZEBO_DIR"
if grep -q "camera_link" models/iris/iris.sdf.jinja 2>/dev/null; then
    echo "✓ Το iris camera patch είναι ήδη εφαρμοσμένο."
else
    echo "Εφαρμόζω το iris_camera.patch (RGB κάμερα στο iris model)..."
    git apply "$PATCH_FILE"
    echo "✓ Το patch εφαρμόστηκε."
fi

# ---- 2. Custom world file ----
echo "Αντιγράφω το yolo_scenario.world..."
cp "$WORLD_FILE" "$PX4_GAZEBO_DIR/worlds/yolo_scenario.world"
echo "✓ World file έτοιμο."

# ---- 3. Download Fuel models ----
mkdir -p "$MODELS_DIR"
cd "$MODELS_DIR"

declare -A MODELS=(
    ["oak_tree"]="OpenRobotics/Oak%20tree"
    ["pine_tree"]="OpenRobotics/Pine%20Tree"
    ["car"]="OpenRobotics/Hatchback%20red"
    ["house"]="OpenRobotics/House%201"
    ["bus"]="OpenRobotics/Bus"
    ["boat"]="OpenRobotics/RC%20Boat"
    ["walking_person"]="OpenRobotics/Walking%20person"
    ["standing_person"]="OpenRobotics/Standing%20person"
)

for name in "${!MODELS[@]}"; do
    if [ -d "$MODELS_DIR/$name" ] && [ -f "$MODELS_DIR/$name/model.sdf" ]; then
        echo "✓ Model '$name' υπάρχει ήδη."
        continue
    fi
    path="${MODELS[$name]}"
    echo "Κατεβάζω '$name'..."
    wget -q "https://fuel.gazebosim.org/1.0/${path}.zip" -O "/tmp/${name}.zip"
    mkdir -p "$MODELS_DIR/$name"
    unzip -q -o "/tmp/${name}.zip" -d "$MODELS_DIR/$name"
    rm "/tmp/${name}.zip"
    echo "✓ '$name' κατέβηκε."
done

# ---- 4. Path fixes (τα Fuel models έχουν λάθος model:// refs) ----
echo "Διορθώνω paths μέσα στα model.sdf αρχεία..."
sed -i 's|model://Oak tree/|model://oak_tree/|g' "$MODELS_DIR/oak_tree/model.sdf" 2>/dev/null || true
sed -i 's|model://Pine Tree/|model://pine_tree/|g' "$MODELS_DIR/pine_tree/model.sdf" 2>/dev/null || true
sed -i 's|model://house_1/|model://house/|g' "$MODELS_DIR/house/model.sdf" 2>/dev/null || true
sed -i 's|model://RC Boat/|model://boat/|g' "$MODELS_DIR/boat/model.sdf" 2>/dev/null || true
sed -i 's|model://person_walking/|model://walking_person/|g' "$MODELS_DIR/walking_person/model.sdf" 2>/dev/null || true
sed -i 's|model://person_standing/|model://standing_person/|g' "$MODELS_DIR/standing_person/model.sdf" 2>/dev/null || true

# ---- 5. Boat scale fix (το mesh είναι πολύ μικρό by default) ----
if [ -f "$MODELS_DIR/boat/model.sdf" ] && ! grep -q "<scale>8.0" "$MODELS_DIR/boat/model.sdf"; then
    echo "Διορθώνω scale της βάρκας..."
    sed -i 's|<scale>1.0 1.0 1.0</scale>|<scale>8.0 8.0 8.0</scale>|g' "$MODELS_DIR/boat/model.sdf"
    python3 - "$MODELS_DIR/boat/model.sdf" << 'PYEOF'
import re, sys
path = sys.argv[1]
with open(path) as f:
    content = f.read()
if content.count("<scale>8.0 8.0 8.0</scale>") < 5:
    content = re.sub(
        r"(</submesh>\s*)(</mesh>)",
        r"\1<scale>8.0 8.0 8.0</scale>\n          \2",
        content
    )
    with open(path, "w") as f:
        f.write(content)
PYEOF
    echo "✓ Boat scale διορθώθηκε."
fi

echo ""
echo "Setup ολοκληρώθηκε επιτυχώς."
echo "Διαθέσιμος κόσμος: 'yolo_scenario' (πόλη με σπίτια, δέντρα, οχήματα, ανθρώπους,"
echo "καλωδιακή γραμμή και 'φωτιές' - 10 κατηγορίες detection)."
echo "Χρήση: ./Tools/simulation/gazebo-classic/sitl_multiple_run.sh -n 3 -m iris -w yolo_scenario"
