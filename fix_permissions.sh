#!/bin/bash

# Fix Events Handler Service Account Permissions
# This script grants the necessary permissions for PubSub operations

set -e

PROJECT_ID="infis-ai"
SERVICE_ACCOUNT="pub-sub-trigger@${PROJECT_ID}.iam.gserviceaccount.com"

echo "🔧 Fixing permissions for Events Handler service account..."
echo "Project: $PROJECT_ID"
echo "Service Account: $SERVICE_ACCOUNT"

# Grant PubSub Publisher permission (required for publishing messages)
echo "📤 Granting Pub/Sub Publisher permission..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/pubsub.publisher" \
    --condition=None

# Grant PubSub Editor permission (required for creating topics)
echo "🏗️ Granting Pub/Sub Editor permission..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/pubsub.editor" \
    --condition=None

# Grant Logging Writer permission (for application logs)
echo "📝 Granting Logging Writer permission..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/logging.logWriter" \
    --condition=None

echo "✅ Permissions updated successfully!"
echo ""
echo "🚀 Now redeploy your service to apply the changes:"
echo "   gcloud builds submit --config cloudbuild.yaml"
echo ""
echo "📊 To verify permissions, check:"
echo "   gcloud projects get-iam-policy $PROJECT_ID --flatten='bindings[].members' --filter='bindings.members:$SERVICE_ACCOUNT'" 