from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import os
from flask import Blueprint, request, jsonify
from sqlalchemy.dialects.postgresql import JSON
import redis

load_dotenv()  # Load environment variables from .env

db = SQLAlchemy()
cache = redis.Redis(host='redis', port=6379, db=0)  # Update host and port as necessary

# Define the User model
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password = db.Column(db.String(100), nullable=False)

    # Constructor (init method)
    def __init__(self, username, email, password):
        self.username = username
        self.email = email
        self.password = password

    def __repr__(self):
        return f"<User {self.title}>"

# Define the Character model
class Character(db.Model):
    __tablename__ = 'characters'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    character_name = db.Column(db.String(100), nullable=False)
    character_class = db.Column(db.String(50), nullable=False)
    character_race = db.Column(db.String(50), nullable=False)
    starting_stats = db.Column(JSON, nullable=False)

    # Constructor (init method)
    def __init__(self, user_id, character_name, character_class, character_race, starting_stats):
        self.user_id = user_id
        self.character_name = character_name
        self.character_class = character_class
        self.character_race = character_race
        self.starting_stats = starting_stats

    def __repr__(self):
        return f"<Character {self.title}>"
    
auth_routes = Blueprint('auth_routes', __name__)

# Status endpoint
@auth_routes.route('/status', methods=['GET'])
def status():
    try:
        user_count = User.query.count()
        character_count = Character.query.count()
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected - {str(e)}"
        user_count = 0
        character_count = 0

    return jsonify({
        "server_status": "running",
        "database_status": db_status,
        "user_count": user_count,
        "character_count": character_count,
        "message": "Service is operational"
    }), 200

# Delete all users and characters
@auth_routes.route("/delete_all_users", methods=['DELETE'])
def delete_all_users():
    try:
        db.session.query(User).delete()
        db.session.query(Character).delete()
        db.session.commit()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"message": "All users and characters deleted successfully!"}), 200

# Register a new user
@auth_routes.route('/auth/register', methods=['POST'])
def register_user():
    user_data = request.json

    if not user_data or not user_data.get("username") or not user_data.get("email") or not user_data.get("password"):
        return jsonify({"error": "Invalid user data. 'username', 'email', and 'password' are required"}), 400

    try:
        existing_user = User.query.filter_by(email=user_data["email"]).first()
        if existing_user:
            return jsonify({"error": "User with this email already exists."}), 409

        new_user = User(
            username=user_data["username"],
            email=user_data["email"],
            password=user_data["password"]
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"user_id": new_user.id, "message": "Registration successful"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Authenticate a user
@auth_routes.route('/auth', methods=['POST'])
def authenticate_user():
    auth_data = request.json

    if not auth_data or not auth_data.get("email") or not auth_data.get("password"):
        return jsonify({"error": "Invalid credentials. 'email' and 'password' are required"}), 400

    try:
        user = User.query.filter_by(email=auth_data["email"], password=auth_data["password"]).first()
        if user:
            return jsonify({"user_id": user.id, "message": "Login successful"}), 200
        else:
            return jsonify({"error": "Invalid email or password"}), 401

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Create a new character
@auth_routes.route('/auth/create-character', methods=['POST'])
def create_character():
    character_data = request.json

    if not character_data or not character_data.get("user_id") or not character_data.get("character_name") or not character_data.get("character_class") or not character_data.get("character_race") or not character_data.get("starting_stats"):
        return jsonify({"error": "Invalid character data. Required fields: 'user_id', 'character_name', 'character_class', 'character_race', 'starting_stats'"}), 400

    try:
        new_character = Character(
            user_id=character_data["user_id"],
            character_name=character_data["character_name"],
            character_class=character_data["character_class"],
            character_race=character_data["character_race"],
            starting_stats=character_data["starting_stats"]
        )
        db.session.add(new_character)
        db.session.commit()
        return jsonify({"character_id": new_character.id, "message": "Character created successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get user details by user_id
@auth_routes.route('/auth/user/<int:user_id>', methods=['GET'])
def get_user(user_id):
    # Check cache first
    cached_user = cache.get(f"user:{user_id}")
    if cached_user:
        return jsonify(eval(cached_user)), 200  # Use eval to convert back to dict (caution with eval in production)

    try:
        user = User.query.get(user_id)
        if user:
            user_data = {
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email
                },
                "message": "User details retrieved successfully"
            }
            # Store user data in cache
            cache.set(f"user:{user_id}", str(user_data))  # Convert to string for caching
            return jsonify(user_data), 200
        else:
            return jsonify({"error": "User not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get character details by character_id
@auth_routes.route('/auth/character/<int:character_id>', methods=['GET'])
def get_player_character(character_id):
    # Check cache first
    cached_character = cache.get(f"character:{character_id}")
    if cached_character:
        return jsonify(eval(cached_character)), 200  # Use eval to convert back to dict (caution with eval in production)

    try:
        character = Character.query.get(character_id)
        if character:
            character_data = {
                "character": {
                    "id": character.id,
                    "character_name": character.character_name,
                    "character_class": character.character_class,
                    "character_race": character.character_race,
                    "character_stats": character.starting_stats
                },
                "message": "Character details retrieved successfully"
            }
            # Store character data in cache
            cache.set(f"character:{character_id}", str(character_data))  # Convert to string for caching
            return jsonify(character_data), 200
        else:
            return jsonify({"error": "Character not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    try:
        character = Character.query.get(character_id)
        if character:
            return jsonify({
                "character": {
                    "id": character.id, 
                    "character_name": character.character_name, 
                    "character_class": character.character_class, 
                    "character_race": character.character_race,
                    "character_stats": character.starting_stats
                }, 
                "message": "Character details retrieved successfully"}), 200
        else:
            return jsonify({"error": "Character not found"}), 404

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get all registered users
@auth_routes.route('/get_users', methods=['GET'])
def get_users():
    try:
        users = User.query.all()
        return jsonify({
            "users": [
                {"id": user.id, "username": user.username, "email": user.email} for user in users
            ]
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Get all registered characters
@auth_routes.route('/get_characters', methods=['GET'])
def get_characters():
    try:
        characters = Character.query.all()
        return jsonify({
            "characters": [
                {"id": char.id, "character_name": char.character_name, "character_class": char.character_class, "character_race": char.character_race} for char in characters
            ]
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

#===============================================================================================================================


def create_app():
    app = Flask(__name__)

    # Load configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')

    # Initialize extensions
    db.init_app(app)

    # Register Blueprints
    #from auth_service_routes import auth_routes
    app.register_blueprint(auth_routes)

    with app.app_context():
        # Create the tables if they don't exist
        db.create_all()

    return app

# Create the app instance at the module level
app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


