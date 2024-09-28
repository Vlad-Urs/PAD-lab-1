# Dungeons and Dragons online platform :dragon_face:
#### made by Vlad Ursu,  FAF-212

<br>

## Intro
D&D has been a window into social interactions for many a nerd since the distant ages of the 1970s, and now using the tools invented by the very same nerds, the D&D experience can expand far beyond a single physical tabletop.

With the arcane arts of microservices, we can create a scalable, easily maintainable, and fault-tolerant online platform, bringing a new dimension to the classic game.

## Assesing suitability
1. **Modular game logic:** The whole D&D game process is already modularized, as it easily separates between: Game Master and the Players themselves, thus creating a service to handle each part of the game is a logical follow-up.

2. **Scalability:** Part of the game such as campaign making, character creation/registration, or ongoing matches may have different loads. Microservices would make possible scaling each component independetly, thus  assuring an optimal resource allocation.

3. **Resilience:** If one service, or instance of a service goes down, the game will not be affected, and the problem will be dealt with quetly, minimizing any disruptions.

4. **Easily updated/expanded:** It is easier to implement new features (such as rules, or creatures, or a whole new edition of D&D) in a microservice architecture.

## Similar products

Most online multiplayer games (League of Legends, Fortnite, etc) use an architecture based on matchmaking, and creating a new child instance of the service for each game session.

## Service Boundaries
The two services in this architecture can be defined as such: 
- **Authentication Service**

This service would be responsible for player authentication, character creation, customization, etc.

- **Game Session Service**

This service will be responsible for creating instances of each game session, using tools like Kubernetes, for handling each game session, combat, messages, movement, NPCs, etc.

<img src="PAD1.PNG">

## Technology stack & Communication Patterns

- Python (Flask) - for writing the 2 services.
- Node.js - for the Gateway, the Service Discovery and Load Balancing.
- MongoDB - for the service databases.
- Redis - for the shared service cache.

The microservices are communicating between themselves synchronously using REST-APIs, and asynchronously when it comes to caching in the redis db, and load balancing.

Additionally the user will employ websockets for real time communication.

## Data Management

### Authentication API Endpoints

- ```(POST) api/auth/register```: used for registering a new player.

```
Request:
{
  "username": "string",
  "email": "string",
  "password": "string"
}

Response:
{
  "user_id": "string",
  "message": "Registration successful"
}
```

---

- ```(POST) api/auth/create-session```: Create a new character sheet.

```
Request:
{
  "user_id": "string",
  "character_name": "string",
  "character_class": "string",
  "character_race": "string",
  "starting_stats": {
    "strength": "int",
    "dexterity": "int",
    "intelligence": "int",
    "wisdom": "int",
    "charisma": "int"
  }
}

Response:
{
  "character_id": "string",
  "message": "Character created successfully"
}

```

- ```(POST) api/auth```: Account authentication.

```
Request:
{
  "email": "string",
  "password": "string"
}

Response:
{
  "user_id": "string",
  "message": "Login successful"
}

```

---

- ```(POST) api/auth/player{character_id}```: Used for returning a player's info.

```
Response:
{
  "character_id": "string",
  "character_name": "string",
  "character_class": "string",
  "character_race": "string",
  "stats": {
    "strength": "int",
    "dexterity": "int",
    "intelligence": "int",
    "wisdom": "int",
    "charisma": "int"
  },
  "message": "Character details retrieved successfully"
}

```

---


### Game Session API Endpoints

---

- ```(POST) api/session/init```: Initialiaze a game session.

```
Request:
{
  "gm_id": "string",
  "campaign_name": "string",
  "players": [
    {
      "player_id": "string",
      "character_id": "string"
    },
    ...
  ]
}

Response:
{
  "session_id": "string",
  "message": "Game session initialized"
}

```

---

- ```(POST) api/session/{session_id}/npc/create```: Create an NPC for a particular session.

```
Request:
{
  "session_id": "string",
  "npc_name": "string",
  "npc_stats": {
    "strength": "int",
    "dexterity": "int",
    "intelligence": "int"
  },
  "npc_role": "string"  // Example: "villain", "merchant", etc.
}

Response:
{
  "npc_id": "string",
  "message": "NPC created successfully"
}

```

---

- ```(POST) api/session/{session_id}/combat/initiate```: Starts a combat sequence between players and NPCs.

```
Request:
{
  "session_id": "string",
  "participants": [
    {
      "character_id": "string",
      "npc_id": "string",
      "action": "attack"
    }
  ]
}

Response:
{
  "combat_id": "string",
  "message": "Combat initiated"
}

```

---

- ```(POST) /session/{session_id}/message/send```: Send a message within a session.

```
Request:
{
  "session_id": "string",
  "sender_id": "string",
  "message": "string"
}

Response:
{
  "message_id": "string",
  "message": "Message sent successfully"
}

```
---

- ```(POST) /session/{session_id}/end```:Ends the current game session. 
```
Request:
{
  "session_id": "string",
  "gm_id": "string"
}

Response:
{
  "message": "Game session ended"
}

```

## Deployement and Scaling

Docker containers will be used for running each service and Docker Compose and Kubernetes for managing and scaling.