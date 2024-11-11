from flask import request
from flask_socketio import join_room, send, emit
import socketio, redis_client

# WebSocket event when a user connects
@socketio.on('connect')
def handle_connect():
    # Assuming you identify the user via a user_id in the request (could be token-based)
    user_id = request.args.get('user_id')

    if not user_id:
        emit('error', {'msg': 'User ID required'})
        return

    # Fetch the player based on the user_id
    player = Player.query.filter_by(player_id=user_id).first()
    
    if not player:
        emit('error', {'msg': 'Player not found'})
        return

    # Save session to Redis for tracking WebSocket connections
    redis_client.set(f"sid:user:{user_id}", request.sid)

    # The player is part of a session, join them to the session room
    session = Session.query.get(player.session_id)

    if session:
        join_room(f"session_{session.id}")
        send(f'Player {user_id} connected and joined session {session.id}')
    else:
        emit('error', {'msg': 'No active session found for player'})


# WebSocket event when a user disconnects
@socketio.on('disconnect')
def handle_disconnect():
    user_id = request.args.get('user_id')
    
    if user_id:
        redis_client.delete(f"sid:user:{user_id}")
        send(f'Player {user_id} disconnected')


# WebSocket event to handle incoming messages
@socketio.on('message')
def handle_message(data):
    message = data.get('message')

    if message:
        # Broadcast the message to all players in the session
        session_id = data.get('session_id')
        emit('session_message', {'msg': message}, room=f'session_{session_id}')
    else:
        emit('error', {'msg': 'Message is required'})


# WebSocket event to subscribe players to their session room
@socketio.on('subscribe')
def handle_subscribe(data):
    user_id = request.args.get('user_id')

    # Fetch the player based on the user_id
    player = Player.query.filter_by(player_id=user_id).first()

    if not player:
        emit('error', {'msg': 'Player not found'})
        return

    # Get the player's session
    session = Session.query.get(player.session_id)

    if session:
        # Join the WebSocket room for the session
        join_room(f"session_{session.id}")
        emit('subscribed', {'msg': f"Subscribed to session {session.id}"})
    else:
        emit('error', {'msg': 'Session not found'})


# Function to emit messages to all players in a session when an NPC is created
def notify_npc_created(session_id, npc_name):
    emit('npc_created', {'npc_name': npc_name}, room=f'session_{session_id}')


# Function to emit messages when combat is initiated in a session
def notify_combat_started(session_id, combat_id):
    emit('combat_started', {'combat_id': combat_id}, room=f'session_{session_id}')
