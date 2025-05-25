import requests
import json
import psycopg2
import os
from dotenv import load_dotenv

# Load .env file if it exists
load_dotenv()

# PostgreSQL connection parameters
# For testing purposes, let's use localhost PostgreSQL if not available from environment
DB_CONNECTION_MODE = os.getenv("DB_CONNECTION_MODE", "local")
DATABASE_URL = os.getenv("AIVEN_DB_URL")

# Default test parameters - will be used if env vars not set
DEFAULT_DB_USER = "postgres"
DEFAULT_DB_PASSWORD = "postgres"
DEFAULT_DB_HOST = "localhost"
DEFAULT_DB_PORT = "5432"
DEFAULT_DB_NAME = "pixity"

# Parse DATABASE_URL if available, otherwise use defaults
if DATABASE_URL:
    try:
        # Extract credentials and host info
        credentials, rest = DATABASE_URL.split("@")
        user_pass = credentials.split("://")[1]
        host_port_db = rest.split("/")
        
        # Split user/pass and host/port
        if ":" in user_pass:
            user, password = user_pass.split(":")
        else:
            user, password = user_pass, ""
        
        host_port = host_port_db[0]
        if ":" in host_port:
            host, port = host_port.split(":")
        else:
            host, port = host_port, "5432"
        
        # Get database name
        dbname = host_port_db[1]
        if "?" in dbname:
            dbname = dbname.split("?")[0]
        
        print(f"Parsed connection parameters: host={host}, port={port}, dbname={dbname}, user={user}")
    except Exception as e:
        print(f"Error parsing DATABASE_URL: {e}")
        print("Using default connection parameters")
        user = DEFAULT_DB_USER
        password = DEFAULT_DB_PASSWORD
        host = DEFAULT_DB_HOST
        port = DEFAULT_DB_PORT
        dbname = DEFAULT_DB_NAME
else:
    print("No DATABASE_URL found. Using default connection parameters")
    user = DEFAULT_DB_USER
    password = DEFAULT_DB_PASSWORD
    host = DEFAULT_DB_HOST
    port = DEFAULT_DB_PORT
    dbname = DEFAULT_DB_NAME

# Execute direct SQL to add the column
def add_required_columns():
    try:
        print(f"Connecting to PostgreSQL: {host}:{port} database={dbname} user={user}")
        # Connect to PostgreSQL
        conn = psycopg2.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            dbname=dbname
        )
        
        # Create a cursor
        cursor = conn.cursor()
        
        # 1. Check if pinecone_index_name column already exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='chat_engine' AND column_name='pinecone_index_name';
        """)
        
        column_exists = cursor.fetchone()
        
        if not column_exists:
            print("Column 'pinecone_index_name' does not exist. Adding it...")
            # Add the pinecone_index_name column to the chat_engine table
            cursor.execute("""
                ALTER TABLE chat_engine
                ADD COLUMN pinecone_index_name VARCHAR NULL;
            """)
            conn.commit()
            print("Column 'pinecone_index_name' added successfully!")
        else:
            print("Column 'pinecone_index_name' already exists.")
            
        # 2. Check if characteristic column already exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='chat_engine' AND column_name='characteristic';
        """)
        
        characteristic_exists = cursor.fetchone()
        
        if not characteristic_exists:
            print("Column 'characteristic' does not exist. Adding it...")
            # Add the characteristic column to the chat_engine table
            cursor.execute("""
                ALTER TABLE chat_engine
                ADD COLUMN characteristic TEXT NULL;
            """)
            conn.commit()
            print("Column 'characteristic' added successfully!")
        else:
            print("Column 'characteristic' already exists.")
            
        # Close cursor and connection
        cursor.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error accessing PostgreSQL: {e}")
        print("Please make sure PostgreSQL is running and accessible.")
        return False

# Base URL
base_url = "http://localhost:7860"

def test_create_engine():
    """Test creating a new chat engine"""
    url = f"{base_url}/rag/chat-engine"
    data = {
        "name": "Test Engine",
        "answer_model": "models/gemini-2.0-flash",
        "system_prompt": "You are an AI assistant that helps users find information about Da Nang.",
        "empty_response": "I don't have information about this question.",
        "use_public_information": True,
        "similarity_top_k": 5,
        "vector_distance_threshold": 0.7,
        "grounding_threshold": 0.2,
        "pinecone_index_name": "testbot768",
        "characteristic": "You are friendly, helpful, and concise. You use a warm and conversational tone, and occasionally add emojis to seem more personable. You always try to be specific in your answers and provide examples when relevant.",
        "status": "active"
    }
    
    response = requests.post(url, json=data)
    print(f"Create Engine Response Status: {response.status_code}")
    if response.status_code == 201 or response.status_code == 200:
        print(f"Successfully created engine: {response.json()}")
        return response.json().get("id")
    else:
        print(f"Failed to create engine: {response.text}")
        return None

def test_get_engine(engine_id):
    """Test getting a specific chat engine"""
    url = f"{base_url}/rag/chat-engine/{engine_id}"
    response = requests.get(url)
    print(f"Get Engine Response Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Engine details: {response.json()}")
    else:
        print(f"Failed to get engine: {response.text}")

def test_list_engines():
    """Test listing all chat engines"""
    url = f"{base_url}/rag/chat-engines"
    response = requests.get(url)
    print(f"List Engines Response Status: {response.status_code}")
    if response.status_code == 200:
        engines = response.json()
        print(f"Found {len(engines)} engines")
        for engine in engines:
            print(f"  - ID: {engine.get('id')}, Name: {engine.get('name')}")
    else:
        print(f"Failed to list engines: {response.text}")

def test_update_engine(engine_id):
    """Test updating a chat engine"""
    url = f"{base_url}/rag/chat-engine/{engine_id}"
    data = {
        "name": "Updated Test Engine",
        "system_prompt": "You are an updated AI assistant for Da Nang information.",
        "characteristic": "You speak in a very professional and formal tone. You are direct and to the point, avoiding unnecessary chatter. You prefer to use precise language and avoid colloquialisms."
    }
    
    response = requests.put(url, json=data)
    print(f"Update Engine Response Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Successfully updated engine: {response.json()}")
    else:
        print(f"Failed to update engine: {response.text}")

def test_chat_with_engine(engine_id):
    """Test chatting with a specific engine"""
    url = f"{base_url}/rag/chat/{engine_id}"
    data = {
        "user_id": "test_user_123",
        "question": "What are some popular attractions in Da Nang?",
        "include_history": True,
        "limit_k": 10,
        "similarity_metric": "cosine",
        "session_id": "test_session_123",
        "first_name": "Test",
        "last_name": "User",
        "username": "testuser"
    }
    
    response = requests.post(url, json=data)
    print(f"Chat With Engine Response Status: {response.status_code}")
    if response.status_code == 200:
        print(f"Chat response: {response.json()}")
    else:
        print(f"Failed to chat with engine: {response.text}")

def test_delete_engine(engine_id):
    """Test deleting a chat engine"""
    url = f"{base_url}/rag/chat-engine/{engine_id}"
    response = requests.delete(url)
    print(f"Delete Engine Response Status: {response.status_code}")
    if response.status_code == 204:
        print(f"Successfully deleted engine with ID: {engine_id}")
    else:
        print(f"Failed to delete engine: {response.text}")

# Execute tests
if __name__ == "__main__":
    print("First, let's add the missing columns to the database")
    if add_required_columns():
        print("\nStarting RAG Chat Engine API Tests")
        print("---------------------------------")
        
        # 1. Create a new engine
        print("\n1. Testing Create Engine API")
        engine_id = test_create_engine()
        
        if engine_id:
            # 2. Get engine details
            print("\n2. Testing Get Engine API")
            test_get_engine(engine_id)
            
            # 3. List all engines
            print("\n3. Testing List Engines API")
            test_list_engines()
            
            # 4. Update the engine
            print("\n4. Testing Update Engine API")
            test_update_engine(engine_id)
            
            # 5. Chat with the engine
            print("\n5. Testing Chat With Engine API")
            test_chat_with_engine(engine_id)
            
            # 6. Delete the engine
            print("\n6. Testing Delete Engine API")
            test_delete_engine(engine_id)
        
        print("\nAPI Tests Completed") 