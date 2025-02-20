import pymongo
import pandas as pd

# Connect to MongoDB
client = pymongo.MongoClient("mongodb://localhost:27017/")
db = client["gearchange"]
collection = db["vehicles"]

# Fetch all vehicle data
data = list(collection.find())

# Convert ObjectId to string
for doc in data:
    doc["_id"] = str(doc["_id"])

# Convert to DataFrame
df = pd.DataFrame(data)

# Save to Excel
df.to_excel("db.xlsx", index=False)

print("Data exported to db.xlsx")
