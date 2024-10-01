from flask import Flask, jsonify, request
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)

# Function to connect to the MongoDB database
client = MongoClient("mongodb://localhost:27017/")  
db = client["authDB"]
users_collection = db["users"]
characters_collection = db["characters"]

# Status endpoint
@app.route('/status', methods=['GET'])
def status():
    # Check if the server is running
    server_status = "running"

    # Check database connection
    try:
        # Perform a simple command to check database connectivity
        db.command("ping")
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected - {str(e)}"

    # Get counts of users and characters
    user_count = users_collection.count_documents({})
    character_count = characters_collection.count_documents({})

    # Compile the status information into a response
    response = {
        "server_status": server_status,
        "database_status": db_status,
        "user_count": user_count,
        "character_count": character_count,
        "message": "Service is operational"
    }

    return jsonify(response), 200

@app.route("/delete_all_users", methods=['DELETE'])
def delete_all_users():
    users_collection.delete_many({})
    characters_collection.delete_many({})
    return jsonify({"message": "All users and characters deleted successfully!"}), 200

# Route to register a new player (POST) api/auth/register
@app.route('/auth/register', methods=['POST'])
def register_user():
    # Get user data from the request
    user_data = request.json
    
    if not user_data or not user_data.get("username") or not user_data.get("email") or not user_data.get("password"):
        return jsonify({"error": "Invalid user data. 'username', 'email', and 'password' are required"}), 400
    
    print(f"Registering user: {user_data}")
    
    # Check if the user already exists
    if users_collection.find_one({"email": user_data["email"]}):
        return jsonify({"error": "User with this email already exists."}), 409
    
    # Insert user data into the database
    user_id = users_collection.insert_one(user_data).inserted_id
    
    return jsonify({"user_id": str(user_id), "message": "Registration successful"}), 201

# Route to authenticate a user (POST) api/auth
@app.route('/auth', methods=['POST'])
def authenticate_user():
    auth_data = request.json
    
    if not auth_data or not auth_data.get("email") or not auth_data.get("password"):
        return jsonify({"error": "Invalid credentials. 'email' and 'password' are required"}), 400
    
    # Check if the user exists and password matches
    user = users_collection.find_one({"email": auth_data["email"], "password": auth_data["password"]})
    
    if user:
        return jsonify({"user_id": str(user["_id"]), "message": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid email or password"}), 401

# Route to create a new character sheet (POST) api/auth/create-session
@app.route('/auth/create-character', methods=['POST'])
def create_character():
    character_data = request.json
    
    if not character_data or not character_data.get("user_id") or not character_data.get("character_name") or not character_data.get("character_class") or not character_data.get("character_race") or not character_data.get("starting_stats"):
        return jsonify({"error": "Invalid character data. Required fields: 'user_id', 'character_name', 'character_class', 'character_race', 'starting_stats'"}), 400
    
    print(f"Creating character for user: {character_data['user_id']}")
    
    character_id = characters_collection.insert_one(character_data).inserted_id
    
    return jsonify({"character_id": str(character_id), "message": "Character created successfully"}), 201

# Route to get a player's user details (POST) api/auth/player/{character_id}
@app.route('/auth/user/<user_id>', methods=['GET'])
def get_user(user_id):
    # Find character by ID
    user = users_collection.find_one({"_id": ObjectId(user_id)})
    
    if user:
        user_info = {
            "unser_id": str(user["_id"]),
            "username": user["username"],
            "email": user["email"]
        }
        return jsonify({"character": user_info, "message": "User details retrieved successfully"}), 200
    else:
        return jsonify({"error": "User not found"}), 404

# Route to get a player's character details (POST) api/auth/player/{character_id}
@app.route('/auth/character/<character_id>', methods=['GET'])
def get_player_character(character_id):
    # Find character by ID
    character = characters_collection.find_one({"_id": ObjectId(character_id)})
    
    if character:
        character_info = {
            "character_id": str(character["_id"]),
            "character_name": character["character_name"],
            "character_class": character["character_class"],
            "character_race": character["character_race"],
            "stats": character["starting_stats"]
        }
        return jsonify({"character": character_info, "message": "Character details retrieved successfully"}), 200
    else:
        return jsonify({"error": "Character not found"}), 404

# Route to get all registered users
@app.route('/get_users', methods=['GET'])
def get_users():
    _users = users_collection.find()
    users = [{"user_id": str(user["_id"]),"username": user["username"], "email": user["email"]} for user in _users]
    return jsonify({"users": users}), 200


# Route to get all registered characters
@app.route('/get_characters', methods=['GET'])
def get_characters():
    _characters = characters_collection.find()
    
    # Transform MongoDB data into JSON format
    characters = [{
        "character_id": str(character["_id"]),
        "user_id": character["user_id"],
        "character_name": character["character_name"],
        "character_class": character["character_class"],
        "character_race": character["character_race"],
        "starting_stats": character["starting_stats"]
    } for character in _characters]
    
    return jsonify({"characters": characters}), 200


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
