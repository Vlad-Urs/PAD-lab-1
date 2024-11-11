const express = require('express');
const axios = require('axios');
const rateLimit = require('express-rate-limit');
const Consul = require('consul');
const CircuitBreaker = require('opossum');

let session_counter = 0;

const app = express();
app.use(express.json());

const consul = new Consul({
    host: 'consul', // Consul address
    port: 8500      // Consul port
});

let serviceUrls = {};  // To store latest URLs of services from Consul



async function deregisterAllServices() {
    try {
        // Retrieve all services from Consul
        const services = await consul.agent.service.list();

        // Loop through each service and deregister it
        for (const serviceId of Object.keys(services)) {
            await consul.agent.service.deregister(serviceId);
            console.log(`Deregistered service with ID: ${serviceId}`);
        }

        console.log('All services have been deregistered from Consul');
    } catch (error) {
        console.error(`Error deregistering services: ${error.message}`);
    }
}

// Example usage: Call this function to remove all services
//deregisterAllServices();

// Service registration function with automated instance registration
async function registerServices() {
    const services = [
        {
            name: 'auth_service',
            id: 'auth_service_1',
            address: `auth_service`,
            port: 5000
        }
    ];

    const numSessionInstances = 3; // Define the number of session_service instances here
    for (let i = 1; i <= numSessionInstances; i++) {
        services.push({
            name: `session_service${i}`,
            id: `session_service_${i}`,
            address: `session_service${i}`,
            port: 5001
        });
    }

    for (const service of services) {
        await consul.agent.service.register({
            Name: service.name,
            ID: service.id,
            Address: service.address,
            Port: service.port
        });
        console.log(`${service.name} with ID ${service.id} registered with Consul`);
    }
}
registerServices()

// Function to periodically update service URLs from Consul
async function updateServiceUrls() {
    try {
        const services = await consul.agent.service.list();
        serviceUrls = {}; // Clear old data

        // Populate the new list of services
        Object.values(services).forEach(service => {
            const serviceName = service.Service;
            const serviceUrl = `http://${service.Address}:${service.Port}`;
            if (!serviceUrls[serviceName]) serviceUrls[serviceName] = [];
            serviceUrls[serviceName].push(serviceUrl); // Multiple instances of the same service
        });

        console.log('Updated service URLs:', serviceUrls);
    } catch (error) {
        console.error('Error updating service URLs from Consul:', error.message);
    }
}

// Poll Consul every 10 seconds to refresh service URLs
setInterval(updateServiceUrls, 10000);

// Initial call to set up service URLs on startup
updateServiceUrls();

// Rate limiting middleware
const limiter = rateLimit({
    windowMs: 5 * 60 * 1000, // 5 minutes window
    max: 100, // limit each IP to 10 requests per windowMs
    message: 'Too many requests, try again after 5 minutes'
});

app.use(limiter);

const getSessionServiceUrl = async () => {
    try {
        // Retrieve all services from Consul
        const services = await consul.agent.service.list();
        
        // Filter for session services
        const seshServices = Object.values(services).filter(service => service.Service.includes('session_service'));
        
        if (seshServices.length === 0) {
            throw new Error('No session services found');
        }

        // Construct the session service URL using the current counter
        const seshServiceUrl = `http://${seshServices[session_counter].Address}:${seshServices[session_counter].Port}`;
        
        // Increment and reset the session counter
        session_counter++;
        if (session_counter >= seshServices.length) {
            session_counter = 0; // Reset counter if it exceeds the available services
        }
        
        return seshServiceUrl;
    } catch (error) {
        console.error('Error retrieving session service URL:', error.message);
        throw error; // Rethrow the error for handling elsewhere
    }
};


const circuitBreakerOptions = {
    timeout: 3000, // If function takes longer than 3 seconds, trigger a failure
    errorThresholdPercentage: 50, // Trip the circuit when 50% of requests fail
    resetTimeout: 3000 // After 30 seconds, try again
};

// Async function to check service health
async function checkServiceStatus(serviceUrl) {
    const response = await axios.get(serviceUrl, { timeout: 3000 });
    return { status: 'up', response: response.data };
}


// Create the circuit breaker for the service check
const serviceStatusBreaker = new CircuitBreaker(checkServiceStatus, circuitBreakerOptions);

// Circuit breaker fallback if open
serviceStatusBreaker.fallback(() => ({ status: 'service is down DDD:' }));

// Simplified status route using circuit breaker
app.get('/status', async (req, res) => {
    try {
        const services = await consul.agent.service.list();
        const serviceChecks = Object.values(services).map(async (service) => {
            const serviceUrl = `http://${service.Address}:${service.Port}/status`;
            try {
                const serviceStatus = await serviceStatusBreaker.fire(serviceUrl);
                return {
                    name: service.Service,
                    status: serviceStatus.status,
                    address: service.Address,
                    port: service.Port,
                    response: serviceStatus.response || {}
                };
            } catch {
                return {
                    name: service.Service,
                    status: 'down',
                    address: service.Address,
                    port: service.Port
                };
            }
        });

        const serviceStatuses = await Promise.all(serviceChecks);
        const operationalCount = serviceStatuses.filter(s => s.status === 'up').length;

        res.json({
            totalServices: serviceStatuses.length,
            operationalServices: operationalCount,
            serviceDetails: serviceStatuses,
            message: "Gateway health check complete"
        });
    } catch (error) {
        res.status(500).json({ message: 'Error checking gateway health', error: error.message });
    }
});

// Route to register a new session
app.post('/session/init', async (req, res) => {
    let tries = 0;
    let lastError = null;

    while (tries < 3) {
        tries++;
        const seshServiceUrl = await getSessionServiceUrl();
        console.log(`Attempt #${tries} with service URL: ${seshServiceUrl}`);

        const serviceStatus = await serviceStatusBreaker.fire(seshServiceUrl);
        console.log('Service status:', serviceStatus.status);
        if (serviceStatus.status != 'up') {
            console.log(`Service ${seshServiceUrl} is down, moving to next instance.`);
            continue; // Skip to the next instance if service is down
        }

        // Try the actual service request if breaker allows
        try {
            const response = await axios.post(`${seshServiceUrl}/session/init`, req.body, { timeout: 3000 });
            return res.status(response.status).json(response.data); // Success: Return immediately

        } catch (error) {
            console.log(`Service ${seshServiceUrl} failed on attempt #${tries}`);
            console.log('\n');

            // Capture the error details for reporting after all attempts
            lastError = error;
            console.log('Error:', error.message);

            // If the error is from a service response, return the response status and data
            if (error.response) {
                return res.status(error.response.status).json(error.response.data);
            }
        }
    }

    // After all attempts fail, respond with an error message
    const errorMessage = lastError ? lastError.message : 'Unknown error';
    res.status(500).json({ message: 'Error registering session, all services are down', error: errorMessage });
});


// Route to register a new user (using dynamic service discovery)
app.post('/auth/register', async (req, res) => {
    try {
        const services = await consul.agent.service.list();
        const authServices = Object.values(services).filter(service => service.Service === 'auth_service');
        const authServiceUrl = `http://${authServices[0].Address}:${authServices[0].Port}`;
        const response = await axios.post(`${authServiceUrl}/auth/register`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to auth service timed out after 3 seconds.' });
        }
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }
        res.status(500).json({ message: 'Error registering user', error: error.message });
    }
});

// Route to create an NPC for a particular session
app.post('/session/:session_id/npc/create', async (req, res) => {
    try {
        const seshServiceUrl = await getSessionServiceUrl();
        const sessionId = req.params.session_id; // Extracting session ID from the route parameters
        const response = await axios.post(`${seshServiceUrl}/session/${sessionId}/npc/create`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to create NPC timed out after 3 seconds.' });
        }
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }
        res.status(500).json({ message: 'Error creating NPC', error: error.message });
    }
});

// Route to start a combat sequence
app.post('/session/:session_id/combat/initiate', async (req, res) => {
    try {
        const seshServiceUrl = await getSessionServiceUrl();
        const sessionId = req.params.session_id; // Extracting session ID from the route parameters
        const response = await axios.post(`${seshServiceUrl}/session/${sessionId}/combat/initiate`, req.body, { timeout: 3000 });
        res.status(response.status).json(response.data);
    } catch (error) {
        if (error.code === 'ECONNABORTED') {
            return res.status(504).json({ message: 'Request to initiate combat timed out after 3 seconds.' });
        }
        if (error.response) {
            return res.status(error.response.status).json(error.response.data);
        }
        res.status(500).json({ message: 'Error initiating combat', error: error.message });
    }
});


// Authenticate a user
app.post('/auth', async (req, res) => {
    try {
        const services = await consul.agent.service.list();
        const authServices = Object.values(services).filter(service => service.Service === 'auth_service');
        const authServiceUrl = `http://${authServices[0].Address}:${authServices[0].Port}`;
        const response = await axios.post(`${authServiceUrl}/auth`, req.body);
        res.status(response.status).json(response.data);
    } catch (error) {
        res.status(500).json({ message: 'Error authenticating user', error: error.message });
    }
});

// Create a new character
app.post('/auth/create-character', async (req, res) => {
    try {
        const services = await consul.agent.service.list();
        const authServices = Object.values(services).filter(service => service.Service === 'auth_service');
        const authServiceUrl = `http://${authServices[0].Address}:${authServices[0].Port}`;
        const response = await axios.post(`${authServiceUrl}/auth/create-character`, req.body);
        res.status(response.status).json(response.data);
    } catch (error) {
        res.status(500).json({ message: 'Error creating character', error: error.message });
    }
});

// Get user details by user_id
app.get('/auth/user/:userId', async (req, res) => {
    try {
        const services = await consul.agent.service.list();
        const authServices = Object.values(services).filter(service => service.Service === 'auth_service');
        const authServiceUrl = `http://${authServices[0].Address}:${authServices[0].Port}`;
        const response = await axios.get(`${authServiceUrl}/auth/user/${req.params.userId}`);
        res.status(response.status).json(response.data);
    } catch (error) {
        res.status(500).json({ message: 'Error retrieving user details', error: error.message });
    }
});

// Get character details by character_id
app.get('/auth/character/:characterId', async (req, res) => {
    try {
        const services = await consul.agent.service.list();
        const authServices = Object.values(services).filter(service => service.Service === 'auth_service');
        const authServiceUrl = `http://${authServices[0].Address}:${authServices[0].Port}`;
        const response = await axios.get(`${authServiceUrl}/auth/character/${req.params.characterId}`);
        res.status(response.status).json(response.data);
    } catch (error) {
        res.status(500).json({ message: 'Error retrieving character details', error: error.message });
    }
});




// Start the gateway server
const PORT = 3000;
app.listen(PORT, () => {
    console.log(`Gateway running on http://localhost:${PORT}`);
});
