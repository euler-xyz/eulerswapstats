#!/usr/bin/env python3
"""
Simple HTTP server with GraphQL proxy for EulerSwap NAV Tracker
"""
import http.server
import socketserver
import json
import urllib.request
import urllib.parse
import os
from datetime import datetime

# Database imports - optional if DATABASE_URL is not set
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    HAS_POSTGRES = True
except ImportError:
    HAS_POSTGRES = False
    print("PostgreSQL support not available, using in-memory storage")

# Database connection
db_conn = None
DATABASE_URL = os.environ.get('DATABASE_URL')

# In-memory storage for pool summaries (fallback)
pool_summaries = []

def init_database():
    """Initialize PostgreSQL database connection and create table if needed"""
    global db_conn, pool_summaries
    
    if not DATABASE_URL or not HAS_POSTGRES:
        # Fallback to file-based storage
        try:
            with open('pool_summaries.json', 'r') as f:
                pool_summaries = json.load(f)
                print(f"Loaded {len(pool_summaries)} existing pool summaries from file")
        except FileNotFoundError:
            print("No existing pool summaries found, starting fresh")
        except Exception as e:
            print(f"Error loading summaries from file: {e}")
        return
    
    try:
        # Connect to PostgreSQL
        db_conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        db_conn.autocommit = True
        
        # Create table if it doesn't exist
        with db_conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pool_summaries (
                    pool_address VARCHAR(42) PRIMARY KEY,
                    tokens VARCHAR(100),
                    current_nav NUMERIC(20, 2),
                    nav_apr VARCHAR(20),
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Load existing summaries into memory for fast access
            cursor.execute("SELECT * FROM pool_summaries ORDER BY updated_at DESC")
            rows = cursor.fetchall()
            pool_summaries = []
            if rows:
                # Use column names from cursor.description
                columns = [desc[0] for desc in cursor.description]
                for row in rows:
                    summary = dict(zip(columns, row))
                    # Convert to frontend format
                    if summary.get('pool_address'):
                        summary['poolAddress'] = summary.pop('pool_address')
                    if summary.get('current_nav'):
                        summary['currentNAV'] = str(summary.pop('current_nav'))
                    if summary.get('nav_apr'):
                        summary['navAPR'] = summary.pop('nav_apr')
                    if summary.get('updated_at'):
                        summary['timestamp'] = summary['updated_at'].isoformat()
                    pool_summaries.append(summary)
            print(f"Connected to PostgreSQL, loaded {len(pool_summaries)} existing pool summaries")
            
    except Exception as e:
        print(f"Database initialization error: {e}")
        print("Falling back to in-memory storage")
        db_conn = None

def get_summaries():
    """Get all pool summaries from database or memory"""
    global pool_summaries
    
    if db_conn and HAS_POSTGRES:
        try:
            with db_conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM pool_summaries ORDER BY updated_at DESC")
                results = cursor.fetchall()
                # Convert to regular dicts and format timestamps
                summaries = []
                for row in results:
                    summary = dict(row)
                    if summary.get('timestamp'):
                        summary['timestamp'] = summary['timestamp'].isoformat()
                    if summary.get('updated_at'):
                        summary['updated_at'] = summary['updated_at'].isoformat()
                    if summary.get('current_nav'):
                        summary['currentNAV'] = str(summary.pop('current_nav'))
                    if summary.get('nav_apr'):
                        summary['navAPR'] = summary.pop('nav_apr')
                    if summary.get('pool_address'):
                        summary['poolAddress'] = summary.pop('pool_address')
                    summaries.append(summary)
                return summaries
        except Exception as e:
            print(f"Error fetching summaries from database: {e}")
    
    return pool_summaries

def store_summary(summary_data):
    """Store or update a pool summary in database or memory"""
    global pool_summaries
    
    pool_address = summary_data.get('poolAddress', '')
    
    if db_conn and HAS_POSTGRES:
        try:
            with db_conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO pool_summaries (pool_address, tokens, current_nav, nav_apr, updated_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (pool_address) 
                    DO UPDATE SET 
                        tokens = EXCLUDED.tokens,
                        current_nav = EXCLUDED.current_nav,
                        nav_apr = EXCLUDED.nav_apr,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    pool_address,
                    summary_data.get('tokens', ''),
                    float(summary_data.get('currentNAV', 0)),
                    summary_data.get('navAPR', 'N/A')
                ))
                
                # Update in-memory cache
                pool_summaries = get_summaries()
                return True
                
        except Exception as e:
            print(f"Error storing summary in database: {e}")
            # Fall through to in-memory storage
    
    # Fallback to in-memory/file storage
    summary_data['timestamp'] = datetime.now().isoformat()
    existing_index = next((i for i, s in enumerate(pool_summaries) if s.get('poolAddress') == pool_address), None)
    
    if existing_index is not None:
        pool_summaries[existing_index] = summary_data
    else:
        pool_summaries.append(summary_data)
    
    # Save to file if not using database
    if not db_conn:
        try:
            with open('pool_summaries.json', 'w') as f:
                json.dump(pool_summaries, f, indent=2)
        except Exception as e:
            print(f"Error saving to file: {e}")
    
    return True

# Initialize database on startup
init_database()

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        # Handle summary retrieval
        if self.path == '/api/summaries':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            summaries = get_summaries()
            self.wfile.write(json.dumps(summaries).encode())
        else:
            # Default GET handler
            super().do_GET()
    def do_POST(self):
        # Handle pool summary storage
        if self.path == '/api/store-summary':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                summary_data = json.loads(post_data)
                
                # Store using the new function
                success = store_summary(summary_data)
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'success': success, 'count': len(get_summaries())}).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
                
        # Handle GraphQL proxy requests
        elif self.path == '/graphql-proxy':
            try:
                # Read the request body
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                
                # Parse the request to log it
                request_data = json.loads(post_data)
                print(f"GraphQL Query: {request_data.get('query', '')[:200]}...")
                print(f"Variables: {request_data.get('variables', {})}")
                
                # Forward to the actual GraphQL endpoint
                graphql_url = 'https://index-dev.euler.finance/graphql'
                
                req = urllib.request.Request(
                    graphql_url,
                    data=post_data,
                    headers={
                        'Content-Type': 'application/json',
                        'Accept': 'application/json',
                        'User-Agent': 'EulerSwap-NAV-Tracker/1.0'
                    }
                )
                
                # Make the request
                with urllib.request.urlopen(req) as response:
                    response_data = response.read()
                    
                # Log response summary
                response_json = json.loads(response_data)
                if 'data' in response_json:
                    print(f"GraphQL Response: Success - {len(str(response_data))} bytes")
                    # Log swap count if available
                    swaps = response_json.get('data', {}).get('eulerSwapSwaps', {}).get('items', [])
                    if isinstance(swaps, list):
                        print(f"Swaps returned: {len(swaps)}")
                else:
                    print(f"GraphQL Response: Error - {response_json.get('errors', 'Unknown')}")
                    
                # Send the response back
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type')
                self.end_headers()
                self.wfile.write(response_data)
                
            except Exception as e:
                # Send error response
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                error_response = json.dumps({'error': str(e)})
                self.wfile.write(error_response.encode())
        else:
            # Default POST handler
            super().do_POST()
    
    def do_OPTIONS(self):
        # Handle CORS preflight requests
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def end_headers(self):
        # Add CORS headers to all responses
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()

def run_server(port=8000):
    Handler = ProxyHTTPRequestHandler
    
    # Change to the directory containing index.html
    web_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(web_dir)
    
    with socketserver.TCPServer(("", port), Handler) as httpd:
        print(f"Server running on port {port}")
        print(f"GraphQL proxy available at /graphql-proxy")
        httpd.serve_forever()

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8000))
    run_server(port)