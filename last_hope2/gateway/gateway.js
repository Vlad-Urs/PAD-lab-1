const express = require('express');
const axios = require('axios');
const rateLimit = require('express-rate-limit');
const Consul = require('consul');
const CircuitBreaker = require('opossum');
const metrics_client = require('prom-client');

let session_counter = 0;

const app = express();
app.use(express.json());

const consul = new Consul({
    host: 'consul', // Consul address
    port: 8500      // Consul port
});

let serviceUrls = {};  // To store latest URLs of services from Consul
let request_counter = 0;

// prometheus setup
const metricsRegistry = new metrics_client.Registry();
const gauge = new metrics_client.Gauge({
  name: "gateway_request_count",
  help: "Number of requests received",
  collect(){
    this.set(request_counter)
  }
})
metricsRegistry.registerMetric(gauge)

function updateRequestCount(req,res,next){
    request_counter++
    next();
  }



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

async function registerServices() {
    const services = [
        {
            name: 'auth_service',
            id: 'auth_service_1',
            address: 'auth_service',
            port: 5000
        }
    ];

    // Register each session_service instance under the same name and port
    const numSessionInstances = 3;  // Define the number of session_service instances here
    for (let i = 1; i <= numSessionInstances; i++) {
        services.push({
            name: `session_service${i}`,           // Use the same name for each instance
            id: `session_service_${i}`,        // Unique ID for each instance
            address: 'session_service',        // Service name as defined in Docker Compose
            port: 5001                         // The internal service port
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

registerServices();

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


// Circuit breaker stuff

const circuitBreakerOptions = {
    timeout: 3000, // If function takes longer than 3 seconds, trigger a failure
    errorThresholdPercentage: 50, // Trip the circuit when 50% of requests fail
    resetTimeout: 3000 // After 3 seconds, try again
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

//=======================================================================================================

// Prometeus metrics
app.get("/metrics", async (req, res) => {
    res.set('Content-Type', metricsRegistry.contentType);
    res.end(await metricsRegistry.metrics());
  })

// Simplified status route using circuit breaker
app.get('/status', updateRequestCount, async (req, res) => {
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
app.post('/session/init',updateRequestCount, async (req, res) => {
    const maxRetries = 3;
    let sessionInstances = await consul.agent.service.list();
    sessionInstances = Object.values(sessionInstances).filter(service => service.Service.includes('session_service'));
    let lastError = null;

    for (let i = 0; i < sessionInstances.length; i++) {
        const seshServiceUrl = `http://${sessionInstances[i].Address}:${sessionInstances[i].Port}`;
        let attempt = 0;

        while (attempt < maxRetries) {
            attempt++;
            console.log(`Attempt #${attempt} with service URL: ${seshServiceUrl}`);

            try {
                const serviceStatus = await serviceStatusBreaker.fire(`${seshServiceUrl}/status`);
                if (serviceStatus.status !== 'up') {
                    console.log(`Service ${seshServiceUrl} is down.`);
                    throw new Error('Service instance is down');
                }

                // If service is up, attempt the actual service request
                const response = await axios.post(`${seshServiceUrl}/session/init`, req.body, { timeout: 3000 });
                return res.status(response.status).json(response.data); // Success: Return immediately

            } catch (error) {
                console.log(`Service ${seshServiceUrl} failed on attempt #${attempt}`);
                lastError = error;

                if (attempt === maxRetries) {
                    console.log(`Instance ${seshServiceUrl} not working, checking next.`);
                    res.setHeader('Warning', `Instance ${seshServiceUrl} not working, checking next`);
                }
            }
        }
    }

    // After all instances fail, respond with an error message
    const errorMessage = lastError ? lastError.message : 'Unknown error';
    res.status(500).json({ message: 'Error registering session, all instances are down', error: errorMessage });
});



// Route to register a new user (using dynamic service discovery)
app.post('/auth/register',updateRequestCount, async (req, res) => {
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
app.post('/session/:session_id/npc/create',updateRequestCount, async (req, res) => {
    const maxRetries = 3;
    let sessionInstances = await consul.agent.service.list();
    sessionInstances = Object.values(sessionInstances).filter(service => service.Service.includes('session_service'));
    let lastError = null;
    const sessionId = req.params.session_id; // Extracting session ID from the route parameters

    for (let i = 0; i < sessionInstances.length; i++) {
        const seshServiceUrl = `http://${sessionInstances[i].Address}:${sessionInstances[i].Port}`;
        let attempt = 0;

        while (attempt < maxRetries) {
            attempt++;
            console.log(`Attempt #${attempt} with service URL: ${seshServiceUrl}`);

            try {
                const serviceStatus = await serviceStatusBreaker.fire(`${seshServiceUrl}/status`);
                if (serviceStatus.status !== 'up') {
                    console.log(`Service ${seshServiceUrl} is down.`);
                    throw new Error('Service instance is down');
                }

                // If service is up, attempt the actual service request
                const response = await axios.post(`${seshServiceUrl}/session/${sessionId}/npc/create`, req.body, { timeout: 3000 });
                return res.status(response.status).json(response.data); // Success: Return immediately

            } catch (error) {
                console.log(`Service ${seshServiceUrl} failed on attempt #${attempt}`);
                lastError = error;

                if (attempt === maxRetries) {
                    console.log(`Instance ${seshServiceUrl} not working, checking next.`);
                    res.setHeader('Warning', `Instance ${seshServiceUrl} not working, checking next`);
                }

                if (error.code === 'ECONNABORTED') {
                    console.log('Request timed out after 3 seconds');
                }
            }
        }
    }

    // After all instances fail, respond with an error message
    const errorMessage = lastError ? lastError.message : 'Unknown error';
    res.status(500).json({ message: 'Error creating NPC, all instances are down', error: errorMessage });
});


// Route to initiate a combat sequence
app.post('/session/:session_id/combat/initiate',updateRequestCount, async (req, res) => {
    const maxRetries = 3;
    let sessionInstances = await consul.agent.service.list();
    sessionInstances = Object.values(sessionInstances).filter(service => service.Service.includes('session_service'));
    let lastError = null;
    const sessionId = req.params.session_id; // Extracting session ID from the route parameters

    for (let i = 0; i < sessionInstances.length; i++) {
        const seshServiceUrl = `http://${sessionInstances[i].Address}:${sessionInstances[i].Port}`;
        let attempt = 0;

        while (attempt < maxRetries) {
            attempt++;
            console.log(`Attempt #${attempt} with service URL: ${seshServiceUrl}`);

            try {
                const serviceStatus = await serviceStatusBreaker.fire(`${seshServiceUrl}/status`);
                if (serviceStatus.status !== 'up') {
                    console.log(`Service ${seshServiceUrl} is down.`);
                    throw new Error('Service instance is down');
                }

                // If service is up, attempt the actual service request
                const response = await axios.post(`${seshServiceUrl}/session/${sessionId}/combat/initiate`, req.body, { timeout: 3000 });
                return res.status(response.status).json(response.data); // Success: Return immediately

            } catch (error) {
                console.log(`Service ${seshServiceUrl} failed on attempt #${attempt}`);
                lastError = error;

                if (attempt === maxRetries) {
                    console.log(`Instance ${seshServiceUrl} not working, checking next.`);
                    res.setHeader('Warning', `Instance ${seshServiceUrl} not working, checking next`);
                }

                if (error.code === 'ECONNABORTED') {
                    console.log('Request timed out after 3 seconds');
                }
            }
        }
    }

    // After all instances fail, respond with an error message
    const errorMessage = lastError ? lastError.message : 'Unknown error';
    res.status(500).json({ message: 'Error initiating combat, all instances are down', error: errorMessage });
});


// Authenticate a user
app.post('/auth',updateRequestCount, async (req, res) => {
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
app.post('/auth/create-character',updateRequestCount, async (req, res) => {
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
app.get('/auth/user/:userId',updateRequestCount, async (req, res) => {
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
app.get('/auth/character/:characterId',updateRequestCount, async (req, res) => {
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
const PORT = 3001;
app.listen(PORT, () => {
    console.log(`Gateway running on http://localhost:${PORT}`);
});
