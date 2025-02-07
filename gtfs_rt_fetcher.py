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

# Load all env vars from chatbot's .env - this file is not tracked by
# git but created by the caller of this script and contains the API_KEY
# environment variable.
load_dotenv()


DTS_API_URL = "https://delhi.transportstack.in/api/dataset/otd/get-file?agency=delhi-buses&category=realtime_gtfs&filename=VehiclePositions.pb"

OUTPUT_FILE = "vehicles.xlsx"

OTD_API_URL = "https://otd.delhi.gov.in/api/realtime/VehiclePositions.pb?key=%s"

FEED_FILE = "last_feed.json"


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
                "vehicle_id": vehicle.vehicle.id,
                "route_id": vehicle.trip.route_id,
                "trip_id": vehicle.trip.trip_id,
                "trip_start_time": vehicle.trip.start_time,
                "trip_start_date": vehicle.trip.start_date,
                "latitude": vehicle.position.latitude,
                "longitude": vehicle.position.longitude,
                "timestamp": "%s (%s)" % (time.strftime(
                    '%H:%M:%S %d-%m-%Y', time.localtime(
                        vehicle.timestamp)), vehicle.timestamp),
            })
    return records


def save_to_excel(data, output_file):
    global in_memory_data

    print(f"Number of rows in data: {len(data)}")
    new_df = pd.DataFrame(data)

    # If file doesn't exist, save all data as new
    if not os.path.exists(output_file):
        print(f"Creating new file with {len(new_df)} records")
        new_df.to_excel(
            output_file, sheet_name='GTFS-RT', index=False, engine='openpyxl')
        return

    # Read existing data
    existing_df = pd.read_excel(
        output_file, sheet_name='GTFS-RT', engine='openpyxl')

    combined_df = pd.concat([existing_df, new_df], ignore_index=True)

    combind_df = combined_df.drop_duplicates()

    print(f"Writing {len(combined_df)} total records to Excel")
    combined_df.to_excel(output_file, sheet_name='GTFS-RT',
                         index=False, engine='openpyxl')


def main(
        api_key, interval, output_file, url, mongo_uri, db_name, collection_name, should_save_to_db):
    if not should_save_to_db and output_file is None:
        raise ValueError(
            "Output file is required when saving to db is disabled.")
    while True:
        print("Fetching GTFS-RT data...")
        data = fetch_data(api_key, url)
        if data:
            parsed_data = parse_gtfs(data)
            if output_file:
                save_to_excel(parsed_data, output_file)
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
    args = parser.parse_args()

    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env_var, default=None)
    if api_key is None:
        raise ValueError(
            f"API_KEY env var is not set. Please set the {args.api_key_env_var} environment variable.")

    if args.url_enum.lower() == "otd":
        main(api_key, args.interval, args.output_file, OTD_API_URL,
             args.mongo_uri, args.db_name, args.collection_name, not args.skip_db)
    else:
        main(api_key, args.interval, args.output_file, DTS_API_URL,
             args.mongo_uri, args.db_name, args.collection_name, not args.skip_db)
