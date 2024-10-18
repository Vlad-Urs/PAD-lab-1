const express = require('express');
const axios = require('axios');
const rateLimit = require('express-rate-limit');
const Consul = require('consul');

// Initialize Consul client
const consul = new Consul({
    host: process.env.CONSUL_HOST || 'consul',
    port: process.env.CONSUL_PORT || '8500',
});

// Function to get the service URL from Consul
async function getServiceUrl(serviceName) {
    return new Promise((resolve, reject) => {
        consul.agent.service.list((err, result) => {
            if (err) {
                return reject(err);
            }

            const service = Object.values(result).find(s => s.Service === serviceName);
            if (service) {
                const serviceUrl = `http://${service.Address}:${service.Port}`;
                return resolve(serviceUrl);
            }

            reject(new Error(`Service ${serviceName} not found`));
        });
    });
}

// Create an Express app
const app = express();
app.use(express.json());

// Rate limiting middleware
const limiter = rateLimit({
    windowMs: 5 * 60 * 1000, // 5 minutes window
    max: 10, // limit each IP to 10 requests per windowMs
    message: 'Too many requests, try again after 5 minutes',
});
app.use(limiter);

// Status route for checking gateway health
app.get('/status', async (req, res) => {
    try {
        const playerServiceUrl = await getServiceUrl('auth_service');
        const gameServiceUrl = await getServiceUrl('session_service');

        const playerServiceResponse = await axios.get(`${playerServiceUrl}/status`, { timeout: 3000 });
        const gameServiceResponse = await axios.get(`${gameServiceUrl}/status`, { timeout: 3000 });

        res.json({
            playerServiceStatus: playerServiceResponse.data,
            gameServiceStatus: gameServiceResponse.data,
            message: "Gateway is operational",
        });
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to service timed out after 3 seconds.' });
        }
        res.status(500).json({ message: 'Error checking service statuses', error: error.message });
    }
});

// Example route to forward requests to auth_service
app.post('/auth/register', async (req, res) => {
    try {
        const playerServiceUrl = await getServiceUrl('auth_service');
        const response = await axios.post(`${playerServiceUrl}/auth/register`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to player service timed out after 3 seconds.' });
        }
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }
        res.status(500).json({ message: 'Error registering user', error: error.message });
    }
});

// Start the gateway server
const PORT = 3000;
app.listen(PORT, () => {
    console.log(`Gateway running on http://localhost:${PORT}`);
});

/*
const express = require('express');
const axios = require('axios');
const rateLimit = require('express-rate-limit'); 

const app = express();
app.use(express.json());

// Define service URLs
const PLAYER_SERVICE_URL = 'http://auth_service:5000';
const GAME_SERVICE_URL = 'http://session_service:5001';

// Rate limiting middleware
const limiter = rateLimit({
    windowMs: 5 * 60 * 1000, // 5 minutes window
    max: 10, // limit each IP to 10 requests per windowMs
    message: 'Too many requests, try again after 5 minutes'
});

app.use(limiter);

// Status route for checking gateway health
app.get('/status', async (req, res) => {
    try {
        const playerServiceResponse = await axios.get(`${PLAYER_SERVICE_URL}/status`, { timeout: 3000 });
        const gameServiceResponse = await axios.get(`${GAME_SERVICE_URL}/status`, { timeout: 3000 });

        res.json({
            playerServiceStatus: playerServiceResponse.data,
            gameServiceStatus: gameServiceResponse.data,
            message: "Gateway is operational"
        });
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to service timed out after 3 seconds.' });
        }
        res.status(500).json({ message: 'Error checking service statuses', error: error.message });
    }
});


// Route to register a new user
app.post('/auth/register', async (req, res) => {
    try {
        const response = await axios.post(`${PLAYER_SERVICE_URL}/auth/register`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to player service timed out after 3 seconds.' });
        }

        // Propagate the service error directly
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }

        res.status(500).json({ message: 'Error registering user', error: error.message });
    }
});



// Forward user authentication requests to the player service
app.post('/auth', async (req, res) => {
    try {
        const response = await axios.post(`${PLAYER_SERVICE_URL}/auth`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to player service timed out after 3 seconds.' });
        }

        // Propagate the service error directly
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }

        res.status(error.response?.status || 500).json({ message: 'Error authenticating user', error: error.message });
    }
});

// Route to create a new game session
app.post('/session/init', async (req, res) => {
    try {
        const response = await axios.post(`${GAME_SERVICE_URL}/session/init`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to game service timed out after 3 seconds.' });
        }

        // Propagate the service error directly
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }

        res.status(error.response?.status || 500).json({ message: 'Error initializing game session', error: error.message });
    }
});

// Route to create an NPC
app.post('/session/:session_id/npc/create', async (req, res) => {
    const { session_id } = req.params;
    try {
        const response = await axios.post(`${GAME_SERVICE_URL}/session/${session_id}/npc/create`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to game service timed out after 3 seconds.' });
        }

        // Propagate the service error directly
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }

        res.status(error.response?.status || 500).json({ message: 'Error creating NPC', error: error.message });
    }
});

// Route to initiate combat
app.post('/session/:session_id/combat/initiate', async (req, res) => {
    const { session_id } = req.params;
    try {
        const response = await axios.post(`${GAME_SERVICE_URL}/session/${session_id}/combat/initiate`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to game service timed out after 3 seconds.' });
        }

        // Propagate the service error directly
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }

        res.status(error.response?.status || 500).json({ message: 'Error initiating combat', error: error.message });
    }
});

// Route to end a session
app.post('/session/:session_id/end', async (req, res) => {
    const { session_id } = req.params;
    try {
        const response = await axios.post(`${GAME_SERVICE_URL}/session/${session_id}/end`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to game service timed out after 3 seconds.' });
        }

        // Propagate the service error directly
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }
        
        res.status(error.response?.status || 500).json({ message: 'Error ending session', error: error.message });
    }
});

// Start the gateway server
const PORT = 3000;
app.listen(PORT, () => {
    console.log(`Gateway running on http://localhost:${PORT}`);
});
*/