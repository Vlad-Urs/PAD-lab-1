FROM python:3.12-slim

# Copy local code to the container image.
WORKDIR /app
COPY . ./

# Install production dependencies.
RUN pip install -r requirements.txt
RUN consul agent -dev -join=consul &

# Run the web service on container startup.
CMD ["python", "app.py"]