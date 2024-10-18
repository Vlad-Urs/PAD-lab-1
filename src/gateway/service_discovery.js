const grpc = require('@grpc/grpc-js');
const protoLoader = require('@grpc/proto-loader');
const dotenv = require('dotenv');
dotenv.config();


// gRPC client setup for service discovery
const packageDefinition = protoLoader.loadSync('service_discovery.proto');
const serviceDiscoveryProto = grpc.loadPackageDefinition(packageDefinition);

// Adjust the client initialization
const client = new serviceDiscoveryProto.ServiceInfo(
    process.env.SERVICE_DISCOVERY_HOST, 
    grpc.credentials.createInsecure()
);

// Function to get service info dynamically
async function getServices() {
    return new Promise((resolve, reject) => {
        client.GetServices({}, (error, response) => {
            if (error) {
                console.error("gRPC Error:", error);
                return reject(error);
            }
            // Map response to service info
            if (response && response.services) {
                const serviceMap = response.services.reduce((acc, serviceEntry) => {
                    acc[serviceEntry.serviceName] = serviceEntry.serviceDetails;
                    return acc;
                }, {});
                resolve(serviceMap);
            } else {
                reject(new Error("No services found in response."));
            }
        });
    });
};

async function deleteService(serviceName, serviceAddress, servicePort) {
    return new Promise((resolve, reject) => {
        client.DeleteService({ serviceName, serviceAddress, servicePort }, (error, response) => {
            console.log("DeleteService triggered in gateway")
            if (error) {
                console.error("gRPC Delete Error:", error);
                return reject(error);
            }
            resolve(response);
        });
    });
}

module.exports = {
    getServices,
    deleteService
};