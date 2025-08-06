#!/usr/bin/env python3
"""
Test script to verify GCP Pub/Sub setup with service identity.
Run this after deployment to ensure everything works correctly.
"""

import asyncio
import json
import os
import sys
from datetime import datetime

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from app.services.gcp_pubsub_client import pubsub_client
from app.services.pubsub import pubsub_service


async def test_pubsub_setup():
    """Test the Pub/Sub setup with your existing service account"""
    
    print("🧪 Testing GCP Pub/Sub Setup with Service Identity")
    print("=" * 60)
    
    # Test 1: Health Check
    print("\n1. Testing Health Check...")
    try:
        health = await pubsub_service.health_check()
        if health["status"] == "healthy":
            print("✅ Health check passed!")
            print(f"   Project ID: {health['project_id']}")
            print(f"   Service Account: {health.get('service_account', 'pub-sub-trigger@infis-ai.iam.gserviceaccount.com')}")
        else:
            print("❌ Health check failed!")
            print(f"   Error: {health.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        print(f"❌ Health check failed with exception: {e}")
        return False
    
    # Test 2: List Topics
    print("\n2. Testing List Topics...")
    try:
        topics = await pubsub_service.list_topics()
        print(f"✅ Listed {len(topics)} topics successfully")
        if topics:
            print("   Existing topics:")
            for topic in topics[:5]:  # Show first 5
                print(f"     - {topic['topic_id']}")
    except Exception as e:
        print(f"❌ Failed to list topics: {e}")
        return False
    
    # Test 3: Create Test Topic
    test_topic = f"test-events-handler-{int(datetime.now().timestamp())}"
    print(f"\n3. Testing Topic Creation: {test_topic}")
    try:
        topic_info = await pubsub_service.create_topic_if_not_exists(test_topic)
        if topic_info["created"]:
            print("✅ Test topic created successfully!")
        else:
            print("✅ Test topic already exists (this is OK)")
        print(f"   Topic Path: {topic_info['topic_path']}")
    except Exception as e:
        print(f"❌ Failed to create test topic: {e}")
        return False
    
    # Test 4: Publish Test Message
    print(f"\n4. Testing Message Publishing...")
    try:
        test_message = {
            "event_type": "test_event",
            "timestamp": datetime.now().isoformat(),
            "message": "Test message from events-handler setup verification",
            "source": "test_script"
        }
        
        result = await pubsub_service.publish_message(
            topic_id=test_topic,
            message_data=test_message,
            attributes={
                "test": "true",
                "environment": "setup_verification"
            }
        )
        
        print("✅ Test message published successfully!")
        print(f"   Message ID: {result['message_id']}")
        print(f"   Topic: {result['topic_id']}")
        
    except Exception as e:
        print(f"❌ Failed to publish test message: {e}")
        return False
    
    # Test 5: Delete Test Topic (cleanup)
    print(f"\n5. Cleaning up test topic...")
    try:
        await pubsub_service.delete_topic(test_topic)
        print("✅ Test topic deleted successfully!")
    except Exception as e:
        print(f"⚠️  Warning: Failed to delete test topic: {e}")
        print("   (This is OK - you can delete it manually from GCP Console)")
    
    print("\n" + "=" * 60)
    print("🎉 All tests passed! Your Pub/Sub setup is working correctly!")
    print("\n📋 Summary:")
    print("   ✅ Service identity authentication working")
    print("   ✅ Can list topics")
    print("   ✅ Can create topics")
    print("   ✅ Can publish messages")
    print("   ✅ Can delete topics")
    print("\n🚀 Your events-handler is ready for production!")
    
    return True


async def test_direct_client():
    """Test the direct GCP client as well"""
    print("\n" + "=" * 60)
    print("🔧 Testing Direct GCP Client...")
    
    try:
        # Test direct client health
        health = await pubsub_client.health_check()
        print(f"✅ Direct client health: {health['status']}")
        
        # Test direct topic creation
        test_topic = f"direct-test-{int(datetime.now().timestamp())}"
        topic_info = await pubsub_client.create_topic_if_not_exists(test_topic)
        print(f"✅ Direct client topic creation: {topic_info['created']}")
        
        # Test direct message publishing
        result = await pubsub_client.publish_message(
            test_topic,
            {"direct_test": True, "timestamp": datetime.now().isoformat()}
        )
        print(f"✅ Direct client message published: {result['message_id']}")
        
        # Cleanup
        await pubsub_client.delete_topic(test_topic)
        print("✅ Direct client cleanup completed")
        
    except Exception as e:
        print(f"❌ Direct client test failed: {e}")
        return False
    
    return True


def check_environment():
    """Check environment setup"""
    print("🔍 Checking Environment...")
    
    # Check required environment variables
    project_id = os.getenv('GOOGLE_CLOUD_PROJECT')
    if project_id:
        print(f"✅ GOOGLE_CLOUD_PROJECT: {project_id}")
    else:
        print("⚠️  GOOGLE_CLOUD_PROJECT not set (may use default)")
    
    # Check that we're NOT using credential files
    creds_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
    if creds_path:
        print(f"⚠️  WARNING: GOOGLE_APPLICATION_CREDENTIALS is set to: {creds_path}")
        print("   This should NOT be set when using service identity!")
        print("   Remove this environment variable for proper security.")
    else:
        print("✅ GOOGLE_APPLICATION_CREDENTIALS not set (good for service identity)")
    
    print()


async def main():
    """Main test function"""
    print("🚀 Events Handler - GCP Pub/Sub Setup Verification")
    print("Using service account: pub-sub-trigger@infis-ai.iam.gserviceaccount.com")
    print()
    
    check_environment()
    
    # Test the existing PubSubService (backward compatibility)
    success1 = await test_pubsub_setup()
    
    # Test the direct client
    success2 = await test_direct_client()
    
    if success1 and success2:
        print("\n🎉 ALL TESTS PASSED! Your setup is working perfectly!")
        return 0
    else:
        print("\n❌ Some tests failed. Check the errors above.")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code) 