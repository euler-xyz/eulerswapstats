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

class ProxyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        # Handle GraphQL proxy requests
        if self.path == '/graphql-proxy':
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