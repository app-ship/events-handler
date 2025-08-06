# Migration Guide: From Service Account Files to Service Identity

This guide helps you migrate from using service account JSON files to the secure Service Identity approach.

## Current State Analysis

Your `events-handler` currently has these credential files in the `creds/` directory:
- `pubsub_service_key.json` - Pub/Sub service account key
- `storage_service_key.json` - Storage service account key  
- `infis-ai-53ac614672f0.json` - Main project service account key
- `gmail_token.json` - Gmail OAuth token
- `client_secret_gmail.json` - Gmail client secret

**⚠️ These files represent security risks and should be eliminated.**

## Migration Steps

### Step 1: Create Proper Service Account

```bash
# Set your project ID
export PROJECT_ID="your-project-id"

# Create dedicated service account
gcloud iam service-accounts create events-handler-sa \
    --display-name="Events Handler Service Account" \
    --description="Service account for events-handler microservice"
```

### Step 2: Grant Required Permissions

Based on your current credential files, grant only the permissions you need:

```bash
# For Pub/Sub (replacing pubsub_service_key.json)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.publisher"

gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/pubsub.subscriber"

# For Cloud Storage (replacing storage_service_key.json)
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/storage.objectCreator"

# For Cloud Logging
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com" \
    --role="roles/logging.logWriter"
```

### Step 3: Update Your Code

Replace any code that references credential files with the Google Cloud client libraries:

**Before (❌ Don't do this):**
```python
import os
from google.cloud import pubsub_v1

# This is insecure and should be removed
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'creds/pubsub_service_key.json'
publisher = pubsub_v1.PublisherClient()
```

**After (✅ Secure approach):**
```python
from google.cloud import pubsub_v1

# This automatically uses the attached service account
publisher = pubsub_v1.PublisherClient()
```

### Step 4: Update Environment Variables

Remove credential-related environment variables from your deployment:

**Remove these from your Cloud Build or environment:**
- `GOOGLE_APPLICATION_CREDENTIALS=creds/pubsub_service_key.json`
- Any references to credential files

**Keep these environment variables:**
- `GOOGLE_CLOUD_PROJECT=$PROJECT_ID` (this is fine)
- Application-specific variables like `DEBUG`, `APP_NAME`, etc.

### Step 5: Update Cloud Build Configuration

Your `cloudbuild.yaml` has already been updated to:
- Remove the `GOOGLE_APPLICATION_CREDENTIALS` environment variable
- Add the `--service-account` flag

### Step 6: Handle Gmail OAuth (Special Case)

For Gmail functionality, you have two options:

**Option A: Use Service Account with Domain-Wide Delegation (if you own the domain)**
```bash
# Grant domain-wide delegation to your service account
# This requires Google Workspace admin access
```

**Option B: Use OAuth Flow (Recommended for most cases)**
```python
# Implement OAuth flow for user consent
# This is more secure than storing refresh tokens
```

### Step 7: Remove Credential Files

**⚠️ IMPORTANT: Only do this after testing the new setup!**

```bash
# Backup first (just in case)
cp -r creds/ creds_backup/

# Remove credential files (they're already gitignored)
rm creds/pubsub_service_key.json
rm creds/storage_service_key.json  
rm creds/infis-ai-53ac614672f0.json

# Gmail files may still be needed depending on your OAuth implementation
# rm creds/gmail_token.json
# rm creds/client_secret_gmail.json
```

### Step 8: Deploy and Test

```bash
# Deploy with the new service account
gcloud builds submit . --config=cloudbuild.yaml

# Test your endpoints
curl https://your-service-url/health
curl https://your-service-url/api/v1/events

# Check logs for any authentication errors
gcloud logs read "resource.type=cloud_run_revision"
```

## Verification Checklist

✅ Service account created with minimal permissions  
✅ Cloud Run service updated with `--service-account` flag  
✅ `GOOGLE_APPLICATION_CREDENTIALS` removed from environment  
✅ Code updated to use client libraries without credential files  
✅ All endpoints working correctly  
✅ No authentication errors in logs  
✅ Credential files removed (after testing)  

## Rollback Plan (If Needed)

If something goes wrong:

1. Restore the credential files from backup
2. Revert the `cloudbuild.yaml` changes  
3. Add back the `GOOGLE_APPLICATION_CREDENTIALS` environment variable
4. Redeploy the previous configuration

## Benefits After Migration

✅ **Enhanced Security**: No credential files to leak  
✅ **Automatic Rotation**: Google manages credential lifecycle  
✅ **Simplified Deployment**: No secrets to manage  
✅ **Better Auditing**: Clear service account attribution  
✅ **Compliance**: Follows GCP security best practices  

## Gmail Integration Notes

The Gmail OAuth files (`gmail_token.json`, `client_secret_gmail.json`) may still be needed depending on your Gmail integration:

- If you use service account with domain-wide delegation, you can remove them
- If you use OAuth flow, you'll need to implement proper token management
- Consider using Cloud Secret Manager for OAuth refresh tokens

## Need Help?

If you encounter issues:

1. Check Cloud Run logs: `gcloud logs read "resource.type=cloud_run_revision"`
2. Verify service account permissions: `gcloud iam service-accounts get-iam-policy events-handler-sa@$PROJECT_ID.iam.gserviceaccount.com`
3. Test authentication: Use the provided example code to verify GCP client libraries work
4. Review the `SECURITY_SETUP.md` guide for troubleshooting steps 