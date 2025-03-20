import argparse
import time
import requests
import os
import pandas as pd
from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToJson
import json
from dotenv import load_dotenv
import pymongo
from pymongo import MongoClient
from datetime import datetime
import pytz
import boto3

# Load all env vars from chatbot's .env - this file is not tracked by
# git but created by the caller of this script and contains the API_KEY
# environment variable.
load_dotenv()


DTS_API_URL = "https://delhi.transportstack.in/api/dataset/otd/get-file?agency=delhi-buses&category=realtime_gtfs&filename=VehiclePositions.pb"

OUTPUT_FILE = "vehicles.xlsx"

OTD_API_URL = "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb?key=%s"

FEED_FILE = "last_feed.json"

DST_BUCKET_NAME = "climate-gearchange-2024"


client = None


def get_mongo_collection(mongo_uri, db_name, collection_name):
    global client
    if client is None:
        client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]
    return collection


def save_to_db(data, mongo_uri, db_name, collection_name):
    collection = get_mongo_collection(mongo_uri, db_name, collection_name)

    # Check if compound index exists before creating
    index_exists = False
    for index in collection.list_indexes():
        if "vehicle_id_1_timestamp_1" in str(index["name"]):
            index_exists = True
            break

    if not index_exists:
        print("Creating compound index on vehicle_id and timestamp")
        collection.create_index(
            [("vehicle_id", 1), ("timestamp", 1)], unique=True)

    if data:
        operations = []
        for record in data:
            # Check if document already exists
            existing_doc = collection.find_one({
                "vehicle_id": record["vehicle_id"],
                "timestamp": record["timestamp"]
            })

            if existing_doc and existing_doc != record:
                # Compare all fields and show differences
                for key in set(existing_doc.keys()) | set(record.keys()):
                    # Skip MongoDB's internal _id field
                    if key == '_id':
                        continue
                    old_val = existing_doc.get(key, 'NOT_PRESENT')
                    new_val = record.get(key, 'NOT_PRESENT')
                    if old_val != new_val:
                        print(
                            f"Duplicate key found with different values for vehicle {record['vehicle_id']}@%s!" % record['timestamp'])
                        print(f"{key}: {old_val} -> {new_val}\n")
                        print(f"Existing_doc: {existing_doc}\n")
                        print(f"New doc: {record}\n")
                        print("-------------------")

            operations.append(
                pymongo.UpdateOne(
                    {
                        "vehicle_id": record["vehicle_id"],
                        "timestamp": record["timestamp"]
                    },
                    {"$set": record},
                    upsert=True
                )
            )

        result = collection.bulk_write(operations)
        print(
            f"MongoDB bulk write results: {result.upserted_count} new records inserted, "
            f"{result.matched_count} records matched, {result.modified_count} existing records modified"
        )


def fetch_data(api_key, url=DTS_API_URL):
    headers = {}
    if url == DTS_API_URL:
        headers = {"x-api-key": api_key}
    elif url == OTD_API_URL:
        url = url % api_key
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.content
    else:
        print(f"Error fetching data: {response.status_code} - {response.text}")
        return None


def parse_gtfs(data):
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    records = []

    with open(FEED_FILE, "w") as f:
        f.write(MessageToJson(feed))

    for entity in feed.entity:
        if entity.HasField("vehicle"):
            vehicle = entity.vehicle
            records.append({
                "entity_wrapper_id": entity.id,
                "vehicle_id": vehicle.vehicle.id,
                "route_id": vehicle.trip.route_id,
                "vehicle_label": vehicle.vehicle.label,
                "trip_id": vehicle.trip.trip_id,
                "trip_start_time": vehicle.trip.start_time,
                "trip_start_date": vehicle.trip.start_date,
                "latitude": vehicle.position.latitude,
                "longitude": vehicle.position.longitude,
                "timestamp": "%s (%s)" % (time.strftime(
                    '%H:%M:%S %d-%m-%Y', time.localtime(
                        vehicle.timestamp)), vehicle.timestamp),
                "raw_timestamp": vehicle.timestamp,
            })
    return records


def read_existing_excel(output_file):
    """Attempt to read and validate existing Excel file.

    @param output_file: The path to the Excel file to read.

    @return:    
        If the file is unreadable/corrupt, it deletes it and returns None.
        Otherwise, it returns the dataframe.
    """
    # Debug existing file
    file_size = os.path.getsize(output_file)
    print(f"Found existing file: {output_file}, size: {file_size} bytes")

    try:
        with open(output_file, 'rb') as f:
            header = f.read(4)
            if len(header) < 4:
                raise ValueError("File header is incomplete")
            print(f"File header bytes: {header.hex()}")

        # Try reading the Excel file
        existing_df = pd.read_excel(
            output_file, sheet_name='GTFS-RT', engine='openpyxl')
        return existing_df

    except Exception as e:
        print(f"Error reading existing Excel file: {e}")
        print("Removing corrupted file and starting fresh")
        os.remove(output_file)
        return None


def save_to_excel(data, output_file):
    print(f"Number of rows in data: {len(data)}")
    new_df = pd.DataFrame(data)

    if not os.path.exists(output_file):
        print(f"Creating new file with {len(new_df)} records")
        with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
            new_df.to_excel(writer, sheet_name='GTFS-RT', index=False)
        print(f"New file created and closed: {output_file}")
        return

    # Try to read and combine with existing data
    existing_df = read_existing_excel(output_file)

    if existing_df is not None:
        # Combine dataframes
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)

        # Count records before deduplication
        records_before = len(combined_df)

        # Perform deduplication
        combined_df = combined_df.drop_duplicates(
            subset=['vehicle_id', 'timestamp', 'latitude',
                    'longitude', 'route_id', 'trip_id'],
            keep='last'
        )

        # Calculate and log the number of dropped records
        records_dropped = records_before - len(combined_df)
        print(
            f"Deduplication: dropped {records_dropped} records ({records_before} -> {len(combined_df)})")
    else:
        # Use only new data if existing file was corrupted
        combined_df = new_df

    print(f"Writing {len(combined_df)} total records to Excel")
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        combined_df.to_excel(writer, sheet_name='GTFS-RT', index=False)
    print(f"Combined file saved and closed: {output_file}")


def rotate_excel(output_file):
    """Rename the excel file with IST timestamp"""
    if not os.path.exists(output_file):
        return

    ist = pytz.timezone('Asia/Kolkata')
    # Modified format string to include separators and better ordering
    timestamp = datetime.now(ist).strftime('%Y%m%d_%H%M')

    # Create new filename with timestamp
    new_filename = f"{output_file.rsplit('.', 1)[0]}_{timestamp}.xlsx"

    try:
        os.rename(output_file, new_filename)
        print(f"Rotated file to: {new_filename}")

        s3_client = boto3.client('s3')
        s3_key = os.path.basename(new_filename)
        s3_client.upload_file(new_filename, DST_BUCKET_NAME, s3_key)

        print(f"Uploaded {new_filename} to {DST_BUCKET_NAME}")
        os.remove(new_filename)
        print(f"Deleted {new_filename}")
    except Exception as e:
        print(f"Error during file rotation: {e}")


def parse_time_to_minutes(time_str):
    """Convert time string like '60m' or '1h' to minutes"""
    unit = time_str[-1].lower()
    value = int(time_str[:-1])
    if unit == 'h':
        return value * 60
    elif unit == 'm':
        return value
    raise ValueError("Time must be specified in 'm' (minutes) or 'h' (hours)")


def main(
        api_key, interval, output_file, url, mongo_uri, db_name, collection_name,
        should_save_to_db, rotation_period):
    if not should_save_to_db and output_file is None:
        raise ValueError(
            "Output file is required when saving to db is disabled.")

    last_rotation = time.time()
    rotation_period_seconds = rotation_period * 60  # Convert to seconds

    while True:
        print("Fetching GTFS-RT data...")
        data = fetch_data(api_key, url)
        if data:
            parsed_data = parse_gtfs(data)
            if output_file:
                save_to_excel(parsed_data, output_file)
                # Check if it's time to rotate
                if time.time() - last_rotation >= rotation_period_seconds:
                    rotate_excel(output_file)
                    last_rotation = time.time()
            if should_save_to_db:
                save_to_db(parsed_data, mongo_uri, db_name, collection_name)
        if interval == 0:
            break
        time.sleep(interval)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch and store GTFS-RT data for Delhi Buses.")
    parser.add_argument("--api-key-env-var", required=True,
                        help="API key env var, for authentication. This env var is set by the caller of this script, typically via a .env file.")
    parser.add_argument("--interval", type=int, required=False,
                        help="Polling interval in seconds (0 for single fetch).", default=0)
    parser.add_argument("--output-file", required=False,
                        help="Output Excel file to store data. If provided, data is stored here AND in the db, otherwise only in the db (see --save-to-db).", default=None)
    parser.add_argument("--url-enum", required=False,
                        help="either DTS for Delhi Transport Stack or OTD for Open Transit Data url.")

    parser.add_argument("--mongo-uri", required=False,
                        help="MongoDB connection URI", default="mongodb://localhost:27017")
    parser.add_argument("--db-name", required=False,
                        help="MongoDB database name", default="gearchange")
    parser.add_argument("--collection-name", required=False,
                        help="MongoDB collection name", default="vehicles")
    parser.add_argument("--skip-db", required=False,
                        help="Skip saving to db?", type=bool, default=False)
    parser.add_argument("--rotation-period", required=False,
                        help="Period for excel file rotation (e.g., '60m' or '1h')",
                        default="60m")
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env_var, default=None)
    if api_key is None:
        raise ValueError(
            f"API_KEY env var is not set. Please set the {args.api_key_env_var} environment variable.")

    # Convert rotation period to minutes
    rotation_period = parse_time_to_minutes(args.rotation_period)

    if args.url_enum.lower() == "otd":
        main(api_key, args.interval, args.output_file, OTD_API_URL,
             args.mongo_uri, args.db_name, args.collection_name, not args.skip_db, rotation_period)
    else:
        main(api_key, args.interval, args.output_file, DTS_API_URL,
             args.mongo_uri, args.db_name, args.collection_name, not args.skip_db, rotation_period)
