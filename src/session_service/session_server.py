from flask import Flask, jsonify, request
from pymongo import MongoClient
from bson.objectid import ObjectId
import requests

app = Flask(__name__)

# Connect to MongoDB
client = MongoClient("mongodb://localhost:27017/")
db = client["gameDB"]
sessions_collection = db["sessions"]
npcs_collection = db["npcs"]
combats_collection = db["combats"]

PLAYER_SERVICE_URL = "http://127.0.0.1:5000"

# Status endpoint
@app.route('/status', methods=['GET'])
def status():
    # Check if the server is running
    server_status = "running"

    # Check MongoDB connection
    try:
        db.command("ping")  # Pings the database to check connectivity
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected - {str(e)}"

    # Get counts of current sessions, NPCs, and combats
    session_count = sessions_collection.count_documents({})
    npc_count = npcs_collection.count_documents({})
    combat_count = combats_collection.count_documents({})

    # Compile the status information into a response
    response = {
        "server_status": server_status,
        "database_status": db_status,
        "session_count": session_count,
        "npc_count": npc_count,
        "combat_count": combat_count,
        "message": "Service is operational"
    }

    return jsonify(response), 200

# Initialize a game session
@app.route('/session/init', methods=['POST'])
def initialize_session():
    data = request.get_json()
    
    if not data or not data.get("gm_id") or not data.get("campaign_name") or not data.get("players"):
        return jsonify({"error": "Invalid data, 'gm_id', 'campaign_name', and 'players' are required"}), 400

    valid_players = []
    
    # Check if each player and character exists by querying the first service
    for player in data["players"]:
        player_id = player.get("player_id")
        character_id = player.get("character_id")

        if not player_id or not character_id:
            return jsonify({"error": "Invalid data, 'player_id' and 'character_id' are required for each player"}), 400

        # Query the player service to check if the player exists
        player_response = requests.get(f"{PLAYER_SERVICE_URL}/auth/user/{player_id}")
        if player_response.status_code != 200:
            return jsonify({"error": f"Player with ID {player_id} not found"}), 404
        
        # Query the player service to check if the character exists
        character_response = requests.get(f"{PLAYER_SERVICE_URL}/auth/character/{character_id}")
        if character_response.status_code != 200:
            return jsonify({"error": f"Character with ID {character_id} not found"}), 404
        
        # Append valid player and character data to the session
        valid_players.append({
            "player_id": player_id,
            "character_id": character_id
        })
    
    session_data = {
        "gm_id": data["gm_id"],
        "campaign_name": data["campaign_name"],
        "players": valid_players,
        "status": "active"
    }

    session_id = sessions_collection.insert_one(session_data).inserted_id
    
    return jsonify({"session_id": str(session_id), "message": "Game session initialized"}), 201


# Create an NPC for a particular session
@app.route('/session/<session_id>/npc/create', methods=['POST'])
def create_npc(session_id):
    data = request.get_json()
    
    if not data or not data.get("npc_name") or not data.get("npc_stats") or not data.get("npc_role"):
        return jsonify({"error": "Invalid data, 'npc_name', 'npc_stats', and 'npc_role' are required"}), 400
    
    npc_data = {
        "session_id": session_id,
        "npc_name": data["npc_name"],
        "npc_stats": data["npc_stats"],
        "npc_role": data["npc_role"]
    }
    
    npc_id = npcs_collection.insert_one(npc_data).inserted_id
    
    return jsonify({"npc_id": str(npc_id), "message": "NPC created successfully"}), 201

# Start a combat sequence
@app.route('/session/<session_id>/combat/initiate', methods=['POST'])
def initiate_combat(session_id):
    data = request.get_json()
    
    if not data or not data.get("participants"):
        return jsonify({"error": "Invalid data, 'participants' are required"}), 400
    
    combat_data = {
        "session_id": session_id,
        "participants": data["participants"]
    }
    
    combat_id = combats_collection.insert_one(combat_data).inserted_id
    
    return jsonify({"combat_id": str(combat_id), "message": "Combat initiated"}), 201

# End a session
@app.route('/session/<session_id>/end', methods=['POST'])
def end_session(session_id):
    data = request.get_json()
    
    if not data or not data.get("gm_id"):
        return jsonify({"error": "Invalid data, 'gm_id' is required"}), 400
    
    # Update the session status to "ended"
    sessions_collection.update_one({"_id": ObjectId(session_id)}, {"$set": {"status": "ended"}})
    
    return jsonify({"message": "Game session ended"}), 200

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001)
