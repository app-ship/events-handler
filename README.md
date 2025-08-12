# Events Handler Microservice

A centralized event handling microservice built with FastAPI that serves as the backbone for event-driven microservice architecture using Google Cloud Pub/Sub.

## Features

- **Auto-topic Creation**: Automatically creates Pub/Sub topics if they don't exist
- **Centralized Event Management**: Single point for all microservice events
- **Robust Error Handling**: Proper handling of GCP auth, network, and quota errors
- **Health Monitoring**: Built-in health checks for service and Pub/Sub connectivity
- **Scalable Architecture**: Clean separation of concerns for maintainability
- **Production Ready**: Proper logging, validation, and containerization

## API Endpoints

### Events Management
- `POST /api/v1/events/trigger` - Trigger an event (main endpoint)
- `GET /api/v1/events/topics` - List all topics
- `POST /api/v1/events/topics` - Create a topic manually
- `DELETE /api/v1/events/topics/{topic_id}` - Delete a topic

### Health Checks
- `GET /health` - Basic health check
- `GET /api/v1/health` - Detailed health check
- `GET /api/v1/health/pubsub` - Pub/Sub connectivity check
- `GET /api/v1/health/ready` - Readiness check
- `GET /api/v1/health/live` - Liveness check

## Quick Start

### Prerequisites

1. Python 3.10+ installed
2. Google Cloud Project with Pub/Sub API enabled
3. Service Account with appropriate permissions:
   - `pubsub.publisher`
   - `pubsub.subscriber`

### Installation

1. **Clone and setup**
   ```bash
   cd events-handler
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Google Cloud settings
   ```

3. **Set up Google Cloud authentication**
   ```bash
   # Option 1: Service Account File
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
   
   # Option 2: Application Default Credentials (if running on GCP)
   gcloud auth application-default login
   ```

4. **Run the service**
   ```bash
   python main.py
   ```

The service will start on `http://localhost:8000`

### Docker Setup

1. **Build the image**
   ```bash
   docker build -t events-handler .
   ```

2. **Run the container**
   ```bash
   docker run -d \
     --name events-handler \
     -p 8000:8000 \
     -e GOOGLE_CLOUD_PROJECT=your-project-id \
     -e GOOGLE_APPLICATION_CREDENTIALS=/app/service-account.json \
     -v /path/to/service-account.json:/app/service-account.json:ro \
     events-handler
   ```

## Usage Example

### Triggering an Event

```bash
curl -X POST "http://localhost:8000/api/v1/events/trigger" \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "deep-research-called",
    "event_data": {
      "user_id": "123",
      "query": "Latest AI research",
      "timestamp": "2025-08-06T10:00:00Z"
    },
    "attributes": {
      "priority": "high",
      "environment": "production"
    },
    "source_service": "deep-reseach-service"
  }'
```

### Response

```json
{
  "success": true,
  "message": "Event triggered successfully",
  "event_name": "deep-research-called",
  "topic_path": "projects/my-project/topics/deep-research-called",
  "message_id": "123456789",
  "topic_created": false,
  "timestamp": "2025-08-06T10:00:00.000Z"
}
```

## Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `GOOGLE_CLOUD_PROJECT` | Google Cloud Project ID | Yes | - |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON | No* | - |
| `DEBUG` | Enable debug mode | No | false |
| `PUBSUB_TIMEOUT` | Pub/Sub operation timeout (seconds) | No | 60.0 |
| `MAX_MESSAGES_PER_PULL` | Max messages per pull operation | No | 100 |
| `API_V1_PREFIX` | API v1 path prefix | No | /api/v1 |
| `ALLOWED_HOSTS` | CORS allowed hosts | No | * |

*Not required if using Application Default Credentials (ADC) on Google Cloud

## Project Structure

```
events-handler/
├── main.py                 # FastAPI application entry point
├── requirements.txt        # Dependencies
├── Dockerfile             # Container configuration
├── .env.example          # Environment variables template
└── app/
    ├── api/
    │   └── v1/
    │       ├── events.py   # Event management endpoints
    │       └── health.py   # Health check endpoints
    ├── core/
    │   ├── config.py       # Configuration management
    │   └── security.py     # GCP authentication setup
    ├── services/
    │   └── pubsub.py      # Google Cloud Pub/Sub service layer
    ├── models/
    │   └── events.py      # Pydantic models for API
    └── utils/
        └── exceptions.py  # Custom exception classes
```

## Integration with Other Microservices

### Example: Deep Research Service Integration

```python
import httpx

async def trigger_research_event(user_id: str, query: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://events-handler:8000/api/v1/events/trigger",
            json={
                "event_name": "deep-research-called",
                "event_data": {
                    "user_id": user_id,
                    "query": query,
                    "timestamp": datetime.utcnow().isoformat()
                },
                "source_service": "deep-reseach-service"
            }
        )
        return response.json()
```

## Error Handling

The service provides detailed error responses with error codes for programmatic handling:

```json
{
  "success": false,
  "error": "Failed to publish message to topic 'invalid-topic'",
  "error_code": "MESSAGE_PUBLISH_ERROR",
  "details": {
    "topic_id": "invalid-topic",
    "error": "Topic not found"
  },
  "timestamp": "2025-08-06T10:00:00.000Z"
}
```

## Monitoring and Logging

The service uses structured logging with JSON format for easy integration with log aggregation systems:

```json
{
  "event": "Request completed",
  "level": "info",
  "method": "POST",
  "path": "/api/v1/events/trigger",
  "status_code": 200,
  "timestamp": "2025-08-06T10:00:00.000Z"
}
```

## Development

### Running Tests

```bash
# Install development dependencies
pip install pytest pytest-asyncio

# Run tests
pytest
```

### Code Formatting

```bash
# Format code
black .
isort .
```

## Production Deployment

### Kubernetes Example

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: events-handler
spec:
  replicas: 3
  selector:
    matchLabels:
      app: events-handler
  template:
    metadata:
      labels:
        app: events-handler
    spec:
      containers:
      - name: events-handler
        image: events-handler:latest
        ports:
        - containerPort: 8000
        env:
        - name: GOOGLE_CLOUD_PROJECT
          value: "your-project-id"
        livenessProbe:
          httpGet:
            path: /api/v1/health/live
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /api/v1/health/ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

## License

MIT License

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request