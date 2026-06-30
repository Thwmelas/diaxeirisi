#!/bin/bash
echo "Σταματάω όλα τα processes..."
pkill -9 -f gzserver 2>/dev/null
pkill -9 -f gzclient 2>/dev/null
pkill -9 -f px4 2>/dev/null
pkill -9 -f MicroXRCEAgent 2>/dev/null
pkill -9 -f perception_placeholder 2>/dev/null
pkill -9 -f decision_placeholder 2>/dev/null
echo "Όλα σταμάτησαν."
