# Secure GCP Service Account Setup for Events Handler

This guide explains how to properly set up service accounts for the Events Handler microservice without using credential files.

## Why No Service Account Files?

**NEVER** use service account JSON files in Cloud Run! Instead, use **Service Identity** which:
- ✅ Eliminates credential files entirely  
- ✅ Automatic credential rotation
- ✅ No risk of credential leakage
- ✅ Follows GCP security best practices
- ✅ Reduces attack surface

## Setup Instructions

### 1. Create Dedicated Service Account

```bash
# Set your project ID
export PROJECT_ID="your-project-id"

# Create a dedicated service account
gcloud iam service-accounts create events-handler-sa \
    --display-name="Events Handler Service Account" \
    --description="Service account for events-handler microservice" \
    --project=$PROJECT_ID
```

### 2. Grant Minimal Required Permissions

Only grant the permissions your service actually needs:

```bash
# For Pub/Sub operations
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.publisher"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.subscriber"

# For Cloud Logging (if needed)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter"

# For Cloud Storage (if needed)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.objectCreator"
```

### 3. Deploy to Cloud Run

Deploy with the service account attached:

```bash
gcloud run deploy events-handler \
    --image=us-central1-docker.pkg.dev/$PROJECT_ID/infis-repo/events-handler:latest \
    --region=us-central1 \
    --service-account=events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com \
    --allow-unauthenticated \
    --memory=2Gi \
    --cpu=2 \
    --min-instances=0 \
    --max-instances=10 \
    --port=8080
```

### 4. Update Your Python Code

Your application code should use Google Cloud client libraries **without any credential files**:

```python
from google.cloud import pubsub_v1
from google.cloud import logging

# These automatically use the attached service account
publisher = pubsub_v1.PublisherClient()
logging_client = logging.Client()

# No GOOGLE_APPLICATION_CREDENTIALS needed!
```

## Security Best Practices Applied

✅ **Principle of Least Privilege**: Service account only has required permissions
✅ **No Credential Files**: Uses Cloud Run service identity  
✅ **Single Purpose**: Dedicated service account per microservice
✅ **Proper Naming**: Clear naming convention (`events-handler-sa`)
✅ **No Default Service Account**: Avoids overprivileged default account

## What NOT to Do

❌ **Don't** use `GOOGLE_APPLICATION_CREDENTIALS` environment variable
❌ **Don't** include JSON credential files in your container
❌ **Don't** commit credential files to Git  
❌ **Don't** use the default Compute Engine service account
❌ **Don't** grant overly broad roles like `Editor` or `Owner`

## Verification

Verify your setup is working:

```bash
# Check your service account
gcloud iam service-accounts describe events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com

# Check your Cloud Run service
gcloud run services describe events-handler --region=us-central1

# Test your service
curl https://events-handler-YOUR_HASH-uc.a.run.app/health
```

## Troubleshooting

If you get authentication errors:

1. Verify the service account is attached to your Cloud Run service
2. Check that the service account has the required IAM roles  
3. Ensure your code is using Google Cloud client libraries correctly
4. Check Cloud Run logs for detailed error messages

## Migration from Service Account Files

If you currently use service account files:

1. Remove the `GOOGLE_APPLICATION_CREDENTIALS` environment variable
2. Remove credential files from your container/codebase  
3. Follow the setup steps above
4. Deploy with the `--service-account` flag
5. Test thoroughly

This approach is more secure, easier to manage, and follows Google Cloud's recommended practices. 