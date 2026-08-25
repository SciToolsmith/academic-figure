#!/usr/bin/env python3
"""Generate the neutral fixed-seed demonstration data for this template."""
import csv
import random
from pathlib import Path

random.seed(41)
centers = {"State A": (-1.25, 0.25), "State B": (0.75, 0.95), "State C": (0.65, -1.0), "State D": (-0.55, -0.95)}
samples = {
    "Sample 1": [0.45, 0.25, 0.20, 0.10],
    "Sample 2": [0.35, 0.30, 0.20, 0.15],
    "Sample 3": [0.25, 0.35, 0.25, 0.15],
    "Sample 4": [0.20, 0.25, 0.35, 0.20],
    "Sample 5": [0.15, 0.20, 0.35, 0.30],
    "Sample 6": [0.20, 0.20, 0.25, 0.35],
}
categories = list(centers)
out = Path(__file__).with_name("simulated_fixed_seed_demo.csv")
with out.open("w", newline="", encoding="utf-8") as handle:
    writer = csv.writer(handle)
    writer.writerow(["observation_id", "sample_id", "x", "y", "category", "sample_order", "source_type", "source_seed"])
    oid = 0
    for order, (sample, weights) in enumerate(samples.items(), 1):
        counts = [round(40 * w) for w in weights]
        counts[-1] += 40 - sum(counts)
        for category, count in zip(categories, counts):
            cx, cy = centers[category]
            for _ in range(count):
                oid += 1
                writer.writerow([f"obs_{oid:03d}", sample, f"{random.gauss(cx, .28):.5f}", f"{random.gauss(cy, .25):.5f}", category, order, "simulated", 41])
print(out)
