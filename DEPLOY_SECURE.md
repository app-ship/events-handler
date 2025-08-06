# 🚀 Secure Deployment Guide

This guide shows you how to deploy your events-handler with proper security using your existing service account.

## 📋 Prerequisites

✅ You have `pub-sub-trigger@infis-ai.iam.gserviceaccount.com` service account  
✅ You've read `REDUCE_PERMISSIONS.md` (strongly recommended)  
✅ You have `gcloud` CLI configured  

## 🔄 Quick Deployment

### 1. Deploy to Cloud Run

Your `cloudbuild.yaml` is already configured to use your service account:

```bash
# Deploy using Cloud Build
gcloud builds submit . --config=cloudbuild.yaml
```

The deployment will:
- Build your Docker container
- Deploy to Cloud Run 
- Attach your service account (`pub-sub-trigger@infis-ai.iam.gserviceaccount.com`)
- Use service identity (no credential files!)

### 2. Test the Deployment

After deployment, test that everything works:

```bash
# Make the test script executable
chmod +x test_pubsub_setup.py

# Run the verification test
python test_pubsub_setup.py
```

### 3. Test Your API Endpoints

Get your Cloud Run service URL:

```bash
# Get your service URL
gcloud run services describe events-handler-staging --region=us-central1 --format='value(status.url)'
```

Test the endpoints:

```bash
# Replace YOUR_SERVICE_URL with the actual URL
export SERVICE_URL="https://your-service-url"

# Test health check
curl "$SERVICE_URL/health"

# Test API health
curl "$SERVICE_URL/api/v1/health"

# Test list topics
curl "$SERVICE_URL/api/v1/events/topics"

# Test create topic
curl -X POST "$SERVICE_URL/api/v1/events/topics" \
  -H "Content-Type: application/json" \
  -d '{"topic_id": "test-topic"}'

# Test trigger event (creates topic and publishes message)
curl -X POST "$SERVICE_URL/api/v1/events/trigger" \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "user_signup",
    "event_data": {
      "user_id": "123",
      "email": "test@example.com"
    },
    "attributes": {
      "source": "web_app"
    }
  }'
```

## 🔧 Configuration

Your service is configured with these environment variables (from `cloudbuild.yaml`):

- `GOOGLE_CLOUD_PROJECT`: Your project ID (auto-set)
- `DEBUG`: false (production mode)
- `APP_NAME`: "Events Handler API"
- `APP_VERSION`: "1.0.0"
- `PUBSUB_TIMEOUT`: 60.0 seconds
- `MAX_MESSAGES_PER_PULL`: 100
- `API_V1_PREFIX`: "/api/v1"
- `ALLOWED_HOSTS`: "*"

**Note**: `GOOGLE_APPLICATION_CREDENTIALS` is **NOT** set - your service uses service identity instead!

## 🔍 Monitoring

### View Logs

```bash
# View Cloud Run logs
gcloud logs read "resource.type=cloud_run_revision AND resource.labels.service_name=events-handler-staging" --limit=50

# View real-time logs
gcloud logs tail "resource.type=cloud_run_revision AND resource.labels.service_name=events-handler-staging"
```

### Monitor in Console

1. Go to [Cloud Run Console](https://console.cloud.google.com/run)
2. Click on your `events-handler-staging` service
3. Check the **Logs** tab for real-time monitoring
4. Check the **Metrics** tab for performance data

## 🎯 Usage Examples

### Create and Publish to Topic

```python
import requests

# Your Cloud Run service URL
SERVICE_URL = "https://your-service-url"

# Trigger an event (creates topic if needed and publishes message)
response = requests.post(f"{SERVICE_URL}/api/v1/events/trigger", json={
    "event_name": "order_created", 
    "event_data": {
        "order_id": "order_123",
        "customer_id": "customer_456",
        "amount": 99.99
    },
    "attributes": {
        "source_service": "ecommerce_api",
        "priority": "high"
    }
})

print(response.json())
# Output: {"success": true, "message_id": "...", "topic_created": true, ...}
```

### List All Topics

```python
response = requests.get(f"{SERVICE_URL}/api/v1/events/topics")
print(response.json())
# Output: {"success": true, "topics": [...], "count": 5}
```

## 🚨 Troubleshooting

### Authentication Errors

If you see authentication errors:

1. **Check service account attachment**:
   ```bash
   gcloud run services describe events-handler-staging --region=us-central1 --format='value(spec.template.spec.serviceAccountName)'
   ```

2. **Verify permissions**:
   ```bash
   gcloud projects get-iam-policy infis-ai \
     --flatten="bindings[].members" \
     --filter="bindings.members:pub-sub-trigger@infis-ai.iam.gserviceaccount.com"
   ```

3. **Check logs for specific errors**:
   ```bash
   gcloud logs read "resource.type=cloud_run_revision" --filter="severity=ERROR" --limit=10
   ```

### Permission Denied Errors

If you get permission denied errors, your service account might need additional roles:

```bash
# Add Pub/Sub permissions (if following security recommendations)
gcloud projects add-iam-policy-binding infis-ai \
    --member="serviceAccount:pub-sub-trigger@infis-ai.iam.gserviceaccount.com" \
    --role="roles/pubsub.editor"
```

### Service Unavailable

If the service is unavailable:

1. Check if Cloud Run service is running
2. Verify the service has allocated CPU/memory
3. Check if VPC connector is properly configured
4. Review startup logs for initialization errors

## 📚 Next Steps

1. **Reduce Permissions** (IMPORTANT): Follow `REDUCE_PERMISSIONS.md` to improve security
2. **Set up monitoring**: Configure alerts for errors and performance metrics
3. **Add authentication**: Implement API authentication if needed for production
4. **Custom domain**: Map a custom domain to your Cloud Run service
5. **CI/CD**: Set up automated deployments with GitHub Actions or other CI/CD tools

## 🔗 Useful Links

- [Cloud Run Console](https://console.cloud.google.com/run)
- [Pub/Sub Console](https://console.cloud.google.com/cloudpubsub)
- [Cloud Logging](https://console.cloud.google.com/logs)
- [IAM Console](https://console.cloud.google.com/iam-admin)

---

**🎉 Congratulations!** Your events-handler is now deployed securely with service identity! 