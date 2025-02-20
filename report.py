import pymongo
import matplotlib.pyplot as plt
import numpy as np
from geopy.distance import geodesic
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime

# Connect to MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["gearchange"]
collection = db["vehicles"]

# Fetch all vehicle data
vehicles = list(collection.find(
    {}, {"vehicle_id": 1, "latitude": 1, "longitude": 1, "timestamp": 1, "_id": 0}))

# Count data points per vehicle
vehicle_counts = {}
vehicle_distances = {}
previous_positions = {}
timestamps = []

for record in vehicles:
    vid = record["vehicle_id"]
    lat = record["latitude"]
    lon = record["longitude"]
    # Extract Unix timestamp from parentheses
    unix_timestamp = int(record["timestamp"].split('(')[1].rstrip(')'))
    timestamps.append(unix_timestamp)

    vehicle_counts[vid] = vehicle_counts.get(vid, 0) + 1

    if vid in previous_positions:
        prev_lat, prev_lon = previous_positions[vid]
        distance = geodesic((prev_lat, prev_lon), (lat, lon)).km
        vehicle_distances[vid] = vehicle_distances.get(vid, 0) + distance

    previous_positions[vid] = (lat, lon)

# Compute duration range with formatted timestamps
start_time = datetime.fromtimestamp(
    timestamps[0]).strftime('%H:%M:%S %d-%m-%Y')
end_time = datetime.fromtimestamp(timestamps[-1]).strftime('%H:%M:%S %d-%m-%Y')
duration = f"Duration: {start_time} ({timestamps[0]}) to {end_time} ({timestamps[-1]})"

# Remove 99th percentile outliers
if vehicle_distances:
    threshold = np.percentile(list(vehicle_distances.values()), 99)
    outlier_vehicles = {k: v for k,
                        v in vehicle_distances.items() if v > threshold}
    vehicle_distances = {k: v for k,
                         v in vehicle_distances.items() if v <= threshold}

    # Print out the vehicles being left out
    for vid, dist in outlier_vehicles.items():
        print(
            f"Excluding vehicle {vid} with distance: {dist} km (Above 99th percentile)")

# Find min/max vehicles for distance and count
min_dist_vehicle = min(
    vehicle_distances, key=vehicle_distances.get, default=None)
max_dist_vehicle = max(
    vehicle_distances, key=vehicle_distances.get, default=None)
min_count_vehicle = min(vehicle_counts, key=vehicle_counts.get, default=None)
max_count_vehicle = max(vehicle_counts, key=vehicle_counts.get, default=None)

# Print min/max vehicle details
print(
    f"Vehicle with min distance: {min_dist_vehicle}, Distance: {vehicle_distances.get(min_dist_vehicle, 0)} km")
print(
    f"Vehicle with max distance: {max_dist_vehicle}, Distance: {vehicle_distances.get(max_dist_vehicle, 0)} km")
print(
    f"Vehicle with min count: {min_count_vehicle}, Count: {vehicle_counts.get(min_count_vehicle, 0)}")
print(
    f"Vehicle with max count: {max_count_vehicle}, Count: {vehicle_counts.get(max_count_vehicle, 0)}")

# After collecting timestamps in the main loop, add these plots:
if timestamps:
    # Convert timestamps to datetime for better readability
    datetime_stamps = [datetime.fromtimestamp(ts) for ts in timestamps]

    # Plot timestamp distribution
    plt.figure(figsize=(12, 6))
    plt.hist(datetime_stamps, bins=50, edgecolor='black')
    plt.xlabel("Time")
    plt.ylabel("Number of Data Points")
    plt.title("Distribution of Data Points Over Time")
    plt.xticks(rotation=45)
    plt.grid(True)
    plt.tight_layout()
    plt.savefig("timestamp_distribution.png")
    plt.close()

    # Box plot for timestamps - convert to numeric values first
    numeric_timestamps = np.array(timestamps)  # Use original Unix timestamps
    fig, ax = plt.subplots(figsize=(12, 4))
    bp = ax.boxplot(numeric_timestamps, vert=False)

    # Format x-axis ticks to show dates
    def format_date(x, p):
        return datetime.fromtimestamp(x).strftime('%Y-%m-%d %H:%M')

    ax.xaxis.set_major_formatter(plt.FuncFormatter(format_date))
    plt.xlabel("Time")
    plt.title("Distribution of Timestamps (Box Plot)")
    plt.grid(True)
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.savefig("timestamp_boxplot.png")
    plt.close()

    # Print timestamp statistics
    print("\nTimestamp Statistics:")
    print(f"Earliest data point: {min(datetime_stamps)}")
    print(f"Latest data point: {max(datetime_stamps)}")
    print(f"Total timespan: {max(datetime_stamps) - min(datetime_stamps)}")
    print(f"Total number of data points: {len(timestamps)}")

# Plot distance distribution
if vehicle_distances:
    distances = list(vehicle_distances.values())
    plt.figure(figsize=(10, 5))
    plt.boxplot(distances, vert=False)
    plt.xlabel("Distance Travelled (km)")
    plt.title(
        f"Distribution of Distance Travelled per Vehicle (Excluding 99th Percentile Outliers)\n{duration}")
    plt.grid(True)
    plt.savefig("distance_distribution.png")

    # Add histogram of vehicle distances
    plt.figure(figsize=(10, 5))
    # Creates bins from 0 to 200 in steps of 20
    bins = np.arange(0, 201, 20)
    plt.hist(distances, bins=bins, edgecolor='black')
    plt.xlabel("Distance Travelled (km)")
    plt.ylabel("Number of Vehicles")
    plt.title(f"Histogram of Vehicle Distances (0-200km)\n{duration}")
    plt.grid(True)
    plt.savefig("distance_histogram.png")

# Plot 10 lowest vehicles by count
low_count_vehicles = sorted(vehicle_counts.items(), key=lambda x: x[1])[:10]
plt.figure(figsize=(10, 5))
plt.bar([x[0] for x in low_count_vehicles], [x[1] for x in low_count_vehicles])
plt.xlabel("Vehicle ID")
plt.ylabel("Data Points Logged")
plt.title("10 Lowest Vehicles by Count")
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("low_count_vehicles.png")

# Plot 10 lowest vehicles by distance
low_distance_vehicles = sorted(
    vehicle_distances.items(), key=lambda x: x[1])[:10]
plt.figure(figsize=(10, 5))
plt.bar([x[0] for x in low_distance_vehicles], [x[1]
        for x in low_distance_vehicles])
plt.xlabel("Vehicle ID")
plt.ylabel("Distance Travelled (km)")
plt.title("10 Lowest Vehicles by Distance")
plt.xticks(rotation=45, ha='right')
plt.tight_layout()
plt.savefig("low_distance_vehicles.png")

# Generate PDF Report with ReportLab


def create_pdf_report(pdf_filename):
    pdf = canvas.Canvas(pdf_filename, pagesize=letter)
    width, height = letter

    # Set consistent left margin
    left_margin = 50

    pdf.setFont("Helvetica", 16)
    pdf.drawString(left_margin, height - 50, "Vehicle Data Analysis Report")
    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 70, duration)

    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 100,
                   "Histogram of Data Points Logged per Vehicle")
    pdf.drawImage("histogram.png", left_margin,
                  height - 400, width=500, height=250)
    pdf.showPage()

    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 100,
                   "Distribution of Distance Travelled per Vehicle (Excluding 99th Percentile Outliers)")
    pdf.drawImage("distance_distribution.png", left_margin,
                  height - 400, width=500, height=250)
    pdf.showPage()

    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 100, "10 Lowest Vehicles by Count")
    pdf.drawImage("low_count_vehicles.png", left_margin,
                  height - 400, width=500, height=250)
    pdf.showPage()

    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 100, "10 Lowest Vehicles by Distance")
    pdf.drawImage("low_distance_vehicles.png", left_margin,
                  height - 400, width=500, height=250)
    pdf.showPage()

    # Add new histogram page
    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 100,
                   "Histogram of Vehicle Distances (0-200km)")
    pdf.drawImage("distance_histogram.png", left_margin,
                  height - 400, width=500, height=250)
    pdf.showPage()

    # Add timestamp distribution page
    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 100,
                   "Distribution of Data Points Over Time")
    pdf.drawImage("timestamp_distribution.png", left_margin,
                  height - 400, width=500, height=250)
    pdf.showPage()

    # Add timestamp box plot page
    pdf.setFont("Helvetica", 12)
    pdf.drawString(left_margin, height - 100,
                   "Distribution of Timestamps (Box Plot)")
    pdf.drawImage("timestamp_boxplot.png", left_margin,
                  height - 400, width=500, height=250)
    pdf.showPage()

    pdf.save()


create_pdf_report("report.pdf")
print("Report generated: report.pdf")


print(f"Number of vehicles: {len(vehicle_counts.keys())}")
# pprint.pprint(vehicle_counts)
# pprint.pprint(vehicle_distances)
