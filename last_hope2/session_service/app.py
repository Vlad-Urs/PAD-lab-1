from flask import Flask, Blueprint, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, join_room, send, emit
from dotenv import load_dotenv
import os
from sqlalchemy.dialects.postgresql import JSON
from prometheus_client import start_http_server, Counter,generate_latest
import requests
from flask_cors import CORS

load_dotenv()  # Load environment variables from .env

request_counter = Counter('session_requests', 'Number of requests')

db = SQLAlchemy()
socketio = SocketIO()

# Models
class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    gm_id = db.Column(db.Integer, nullable=False)
    campaign_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='active')
    players = db.relationship('Player', backref='session', cascade="all, delete")
    npcs = db.relationship('NPC', backref='session', cascade="all, delete")
    combats = db.relationship('Combat', backref='session', cascade="all, delete")

class Player(db.Model):
    __tablename__ = 'players'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    player_id = db.Column(db.Integer, nullable=False)
    character_id = db.Column(db.Integer, nullable=False)

class NPC(db.Model):
    __tablename__ = 'npcs'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    npc_name = db.Column(db.String(100), nullable=False)
    npc_stats = db.Column(db.JSON, nullable=False)
    npc_role = db.Column(db.String(50), nullable=False)

class Combat(db.Model):
    __tablename__ = 'combats'
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('sessions.id'), nullable=False)
    participants = db.Column(db.JSON, nullable=False)

session_routes = Blueprint('session_routes', __name__)
CORS(session_routes)

# Prometheus endpoint for Prometheus to scrape metrics
@session_routes.route('/metrics')
def metrics():
    return generate_latest(), 200

# Status endpoint
@session_routes.route('/status', methods=['GET'])
def status():
    request_counter.inc()
    try:
        session_count = Session.query.count()
        npc_count = NPC.query.count()
        combat_count = Combat.query.count()
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected - {str(e)}"

    

    return jsonify({
        "server_status": "running",
        "database_status": db_status,
        "session_count": session_count,
        "npc_count": npc_count,
        "combat_count": combat_count,
        "message": "Service is operational"
    }), 200

# Initialize a game session
@session_routes.route('/session/init', methods=['POST'])
def initialize_session():
    print('got here')
    request_counter.inc()
    data = request.get_json()

    # Validate incoming data
    if not data or not data.get("gm_id") or not data.get("campaign_name") or not data.get("players"):
        return jsonify({"error": "Invalid data, 'gm_id', 'campaign_name', and 'players' are required"}), 400

    gm_id = data["gm_id"]
    players = data["players"]

    # Communicate with the other service to validate gm_id and player details
    try:
        # Validate GM ID
        gm_response = requests.get(f'http://auth_service:5000/auth/user/{gm_id}')
        if gm_response.status_code != 200:
            return jsonify({"error": "Invalid GM ID"}), 404

        # Validate each player in the `players` list
        for player in players:
            player_id = player["player_id"]
            character_id = player["character_id"]

            # Check if player exists in the User table
            player_response = requests.get(f'http://auth_service:5000/auth/user/{player_id}')
            if player_response.status_code != 200:
                return jsonify({"error": f"Invalid player ID {player_id}"}), 404

            # Check if character exists in the Character table
            character_response = requests.get(f'http://auth_service:5000/auth/character/{character_id}')
            if character_response.status_code != 200:
                return jsonify({"error": f"Invalid character ID {character_id} for player {player_id}"}), 404

    except requests.exceptions.RequestException as e:
        print(e)
        return jsonify({"error": "Error communicating with the authentication service", "details": str(e)}), 500

    # Create a new session in the database
    session = Session(
        gm_id=gm_id,
        campaign_name=data["campaign_name"],
        status="active"
    )
    db.session.add(session)
    db.session.commit()

    # Add players to the session
    for player in players:
        player_obj = Player(session_id=session.id, player_id=player["player_id"], character_id=player["character_id"])
        db.session.add(player_obj)

    db.session.commit()

    return jsonify({"session_id": session.id, "message": "Game session initialized"}), 201

# Create an NPC for a particular session
@session_routes.route('/session/<int:session_id>/npc/create', methods=['POST'])
def create_npc(session_id):
    request_counter.inc()
    data = request.get_json()

    if not data or not data.get("npc_name") or not data.get("npc_stats") or not data.get("npc_role"):
        return jsonify({"error": "Invalid data, 'npc_name', 'npc_stats', and 'npc_role' are required"}), 400

    npc = NPC(
        session_id=session_id,
        npc_name=data["npc_name"],
        npc_stats=data["npc_stats"],
        npc_role=data["npc_role"]
    )
    db.session.add(npc)
    db.session.commit()

    return jsonify({"npc_id": npc.id, "message": "NPC created successfully"}), 201

# Start a combat sequence
@session_routes.route('/session/<int:session_id>/combat/initiate', methods=['POST'])
def initiate_combat(session_id):
    request_counter.inc()
    data = request.get_json()

    if not data or not data.get("participants"):
        return jsonify({"error": "Invalid data, 'participants' are required"}), 400

    combat = Combat(session_id=session_id, participants=data["participants"])
    db.session.add(combat)
    db.session.commit()

    return jsonify({"combat_id": combat.id, "message": "Combat initiated"}), 201

# End a session
@session_routes.route('/session/<int:session_id>/end', methods=['POST'])
def end_session(session_id):
    request_counter.inc()
    data = request.get_json()

    if not data or not data.get("gm_id"):
        return jsonify({"error": "Invalid data, 'gm_id' is required"}), 400

    session = Session.query.get(session_id)
    if session:
        session.status = "ended"
        db.session.commit()
        return jsonify({"message": "Game session ended"}), 200
    else:
        return jsonify({"error": "Session not found"}), 404
    
@session_routes.route('/get_session/<int:session_id>', methods=['GET'])
def get_session(session_id):
    request_counter.inc()
    session = Session.query.get(session_id)
    if session:
        session_data = {
            "session_id": session.id,
            "gm_id": session.gm_id,
            "campaign_name": session.campaign_name,
            "status": session.status,
            "players": [{"player_id": player.player_id, "character_id": player.character_id} for player in session.players],
            "npcs": [{"npc_id": npc.id, "npc_name": npc.npc_name, "npc_stats": npc.npc_stats, "npc_role": npc.npc_role} for npc in session.npcs],
            "combats": [{"combat_id": combat.id, "participants": combat.participants} for combat in session.combats]
        }
        return jsonify(session_data), 200
    else:
        return jsonify({"error": "Session not found"}), 404
    

@session_routes.route('/get_sessions', methods=['GET'])
def get_sessions():
    request_counter.inc()
    sessions = Session.query.all()
    session_data = []
    for session in sessions:
        session_data.append({
            "session_id": session.id,
            "gm_id": session.gm_id,
            "campaign_name": session.campaign_name,
            "status": session.status,
            "players": [{"player_id": player.player_id, "character_id": player.character_id} for player in session.players],
            "npcs": [{"npc_id": npc.id, "npc_name": npc.npc_name, "npc_stats": npc.npc_stats, "npc_role": npc.npc_role} for npc in session.npcs],
            "combats": [{"combat_id": combat.id, "participants": combat.participants} for combat in session.combats]
        })

    return jsonify(session_data), 200

@session_routes.route('/players/all', methods=['GET'])
def get_all_players():
    request_counter.inc()
    try:
        players = Player.query.all()
        if not players:
            return jsonify({"message": "No players found"}), 404

        players_data = []
        for player in players:
            players_data.append({
                "player_id": player.player_id,
                "character_id": player.character_id,
                "session_id": player.session_id
            })

        return jsonify({"players": players_data}), 200
    except Exception as e:
        return jsonify({"error": "Failed to retrieve players", "details": str(e)}), 500

# Transfer character ownership from one player to another
# Saga pattern implementation 
@session_routes.route('/session/transfer-character', methods=['POST'])
def transfer_character():
    data = request.get_json()

    session_id = int(data.get('session_id'))
    old_player_id = int(data.get('old_player_id'))
    new_player_id = int(data.get('new_player_id'))
    character_id = int(data.get('character_id'))

    if not session_id or not old_player_id or not new_player_id or not character_id:
        return jsonify({"error": "Invalid input data"}), 400

    try:
        # Step 2: Update Player in session_service
        player = Player.query.filter_by(session_id=session_id, player_id=old_player_id, character_id=character_id).first()
        if not player:
            return jsonify({"error": "Player or character not found in session"}), 404

        player.player_id = new_player_id
        db.session.commit()
        

        return jsonify({"message": "Character ownership transferred successfully"}), 200

    except Exception as e:
        print(f"Error occurred in session_service: {e}")
        #db.session.rollback()  # Roll back changes if something fails
        player.player_id = old_player_id
        db.session.commit()

        return jsonify({"error": "Transaction failed", "details": str(e)}), 500

    

#=============================================================================================
# WebSocket Events
@socketio.on('connect')
def handle_connect():
    user_id = request.args.get('user_id')
    if not user_id:
        emit('error', {'msg': 'User ID required'})
        return

    player = Player.query.filter_by(player_id=user_id).first()
    if not player:
        emit('error', {'msg': 'Player not found'})
        return

    session = Session.query.get(player.session_id)
    if session:
        join_room(f"session_{session.id}")
        send(f'Player {user_id} connected and joined session {session.id}')
    else:
        emit('error', {'msg': 'No active session found for player'})

@socketio.on('disconnect')
def handle_disconnect():
    user_id = request.args.get('user_id')
    if user_id:
        send(f'Player {user_id} disconnected')

@socketio.on('message')
def handle_message(data):
    message = data.get('message')
    session_id = data.get('session_id')
    if message and session_id:
        emit('session_message', {'msg': message}, room=f'session_{session_id}')
    else:
        emit('error', {'msg': 'Message and session ID are required'})

@socketio.on('subscribe')
def handle_subscribe(data):
    user_id = request.args.get('user_id')
    player = Player.query.filter_by(player_id=user_id).first()
    if not player:
        emit('error', {'msg': 'Player not found'})
        return

    session = Session.query.get(player.session_id)
    if session:
        join_room(f"session_{session.id}")
        emit('subscribed', {'msg': f"Subscribed to session {session.id}"})
    else:
        emit('error', {'msg': 'Session not found'})

def notify_npc_created(session_id, npc_name):
    emit('npc_created', {'npc_name': npc_name}, room=f'session_{session_id}')

def notify_combat_started(session_id, combat_id):
    emit('combat_started', {'combat_id': combat_id}, room=f'session_{session_id}')

# Create the Flask app and integrate with SocketIO
def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')

    # Initialize extensions
    db.init_app(app)
    socketio.init_app(app)  # Initialize SocketIO

    # Register Blueprints
    app.register_blueprint(session_routes)

    with app.app_context():
        db.create_all()

    return app

# Create the app instance at the module level
app = create_app()

  

# Run both Flask and WebSocket server
if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=True,allow_unsafe_werkzeug=True)

    # Start a separate HTTP server for Prometheus metrics on port 8000
    start_http_server(8001)