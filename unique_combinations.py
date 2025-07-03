#!/usr/bin/env python3
"""
unique_connections_input.py

1) Prompt the user for a number of points (n) and print all unique 2-point connections.
2) Prompt the user to input the measured distance for each connection (in mm).
3) Compute the mean distance and reject the part if any measurement is off by >5%.
"""

import itertools

def unique_connections(n):
    """
    Return a list of unique 2-point connections for points labeled 1..n.
    """
    if n < 2:
        return []
    return list(itertools.combinations(range(1, n+1), 2))

def get_float(prompt):
    """
    Prompt until we get a valid float > 0.
    """
    while True:
        try:
            val = float(input(prompt))
            if val <= 0:
                print("Please enter a positive number.")
                continue
            return val
        except ValueError:
            print("Invalid input. Please enter a number.")

def main():
    # 1) Number of points
    while True:
        try:
            n = int(input("Enter number of points: "))
            if n < 2:
                print("Please enter an integer ≥ 2.")
                continue
            break
        except ValueError:
            print("Invalid input. Please enter an integer.")

    # 2) Unique connections
    connections = unique_connections(n)
    print("\nUnique connections:")
    for idx, (a, b) in enumerate(connections, start=1):
        print(f"  {idx}. {a} ↔ {b}")

    # 3) Read in distances
    print("\nEnter measured distances (in mm) for each connection:")
    distances = []
    for (a, b) in connections:
        d = get_float(f"  Distance for connection {a}-{b}: ")
        distances.append(d)

    # 4) Check for outliers
    mean_dist = sum(distances) / len(distances)
    tol = 0.05  # 5%
    outliers = []
    for (a, b), d in zip(connections, distances):
        rel_err = abs(d - mean_dist) / mean_dist
        if rel_err > tol:
            outliers.append(((a, b), d, rel_err))

    print("\nResults:")
    print(f"  Mean distance = {mean_dist:.3f} mm")
    if outliers:
        print("  ⚠️  Part REJECTED. Connection(s) outside ±5%:")
        for (a, b), d, rel_err in outliers:
            pct = rel_err * 100
            print(f"    • {a}-{b}: {d:.3f} mm ({pct:.1f}% off)")
    else:
        print("  ✔️  All measurements within ±5%. Part ACCEPTED.")

if __name__ == "__main__":
    main()
