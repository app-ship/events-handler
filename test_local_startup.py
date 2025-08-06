#!/usr/bin/env python3
"""
Test script to verify the Events Handler API can start locally
"""

import asyncio
import subprocess
import time
import requests
import sys
import os


async def test_local_startup():
    """Test that the application starts and responds to health checks"""
    
    # Set environment variables for testing
    os.environ['GOOGLE_CLOUD_PROJECT'] = 'infis-ai'
    os.environ['DEBUG'] = 'true'
    os.environ['PORT'] = '8001'
    
    print("🚀 Starting Events Handler API locally...")
    
    # Start the application
    process = subprocess.Popen([
        sys.executable, 'api.py'
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    # Give it time to start
    print("⏳ Waiting for startup...")
    await asyncio.sleep(5)
    
    try:
        # Test basic health check
        print("🏥 Testing basic health endpoint...")
        response = requests.get('http://localhost:8001/health', timeout=10)
        
        if response.status_code == 200:
            print("✅ Basic health check passed!")
            print(f"   Response: {response.json()}")
        else:
            print(f"❌ Basic health check failed with status: {response.status_code}")
            return False
        
        # Test root endpoint
        print("🏠 Testing root endpoint...")
        response = requests.get('http://localhost:8001/', timeout=10)
        
        if response.status_code == 200:
            print("✅ Root endpoint working!")
            print(f"   Service: {response.json().get('service', 'Unknown')}")
        else:
            print(f"❌ Root endpoint failed with status: {response.status_code}")
            return False
        
        # Test PubSub health (may fail, but shouldn't crash)
        print("🔗 Testing PubSub health endpoint...")
        try:
            response = requests.get('http://localhost:8001/api/v1/health/pubsub', timeout=15)
            print(f"   PubSub health status: {response.status_code}")
            if response.status_code in [200, 503]:
                print("✅ PubSub health endpoint responding (connection may be unavailable, but that's OK)")
            else:
                print(f"⚠️  Unexpected PubSub health response: {response.status_code}")
        except requests.exceptions.RequestException as e:
            print(f"⚠️  PubSub health check failed (expected in local testing): {e}")
        
        print("\n🎉 Application startup test PASSED!")
        print("   The application should now work in Cloud Run")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to the application - startup failed")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False
    finally:
        # Clean up
        print("\n🧹 Cleaning up...")
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


if __name__ == "__main__":
    print("🧪 Events Handler API Startup Test")
    print("=" * 50)
    
    result = asyncio.run(test_local_startup())
    
    if result:
        print("\n✅ Test PASSED - Ready for deployment!")
        sys.exit(0)
    else:
        print("\n❌ Test FAILED - Fix issues before deploying")
        sys.exit(1) 