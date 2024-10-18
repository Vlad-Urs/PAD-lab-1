from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
from flask import Blueprint, request, jsonify
from sqlalchemy.dialects.postgresql import JSON

load_dotenv()  # Load environment variables from .env

db = SQLAlchemy()

# Models
class Session(db.Model):
    __tablename__ = 'sessions'
    id = db.Column(db.Integer, primary_key=True)
    gm_id = db.Column(db.Integer, nullable=False)
    campaign_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(50), default='active')
    players = db.relationship('Player', backref='session', cascade="all, delete")

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

# Status endpoint
@session_routes.route('/status', methods=['GET'])
def status():
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
    data = request.get_json()

    if not data or not data.get("gm_id") or not data.get("campaign_name") or not data.get("players"):
        return jsonify({"error": "Invalid data, 'gm_id', 'campaign_name', and 'players' are required"}), 400

    session = Session(
        gm_id=data["gm_id"],
        campaign_name=data["campaign_name"],
        status="active"
    )
    db.session.add(session)
    db.session.commit()

    for player in data["players"]:
        player_obj = Player(session_id=session.id, player_id=player["player_id"], character_id=player["character_id"])
        db.session.add(player_obj)

    db.session.commit()

    return jsonify({"session_id": session.id, "message": "Game session initialized"}), 201

# Create an NPC for a particular session
@session_routes.route('/session/<int:session_id>/npc/create', methods=['POST'])
def create_npc(session_id):
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
    


#=============================================================================================
def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    

    # Initialize extensions
    db.init_app(app)

    # Register Blueprints
    app.register_blueprint(session_routes)

    with app.app_context():
        # Create the tables if they don't exist
        db.create_all()

    return app

# Create the app instance at the module level
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)