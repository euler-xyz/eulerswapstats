#!/usr/bin/env python3
"""
Check PostgreSQL connection and query pool_summaries table
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
import json

DATABASE_URL = os.environ.get('DATABASE_URL')

print("=" * 60)
print("PostgreSQL Connection Check")
print("=" * 60)

if not DATABASE_URL:
    print("❌ DATABASE_URL environment variable is not set")
    print("   We're using fallback file-based storage")
    
    # Check for local file
    if os.path.exists('pool_summaries.json'):
        with open('pool_summaries.json', 'r') as f:
            data = json.load(f)
        print(f"\n📁 Found pool_summaries.json with {len(data)} entries")
        for entry in data[:5]:  # Show first 5
            print(f"   - {entry.get('poolAddress', 'N/A')}: {entry.get('tokens', 'N/A')}")
    else:
        print("\n📁 No pool_summaries.json file found")
else:
    print("✅ DATABASE_URL is set")
    print(f"   URL: {DATABASE_URL[:30]}...")  # Show first 30 chars for security
    
    try:
        # Connect to PostgreSQL
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        print("✅ Successfully connected to PostgreSQL")
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Check if table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'pool_summaries'
                )
            """)
            table_exists = cursor.fetchone()['exists']
            
            if table_exists:
                print("✅ Table 'pool_summaries' exists")
                
                # Get row count
                cursor.execute("SELECT COUNT(*) as count FROM pool_summaries")
                count = cursor.fetchone()['count']
                print(f"   Found {count} entries in database")
                
                # Show recent entries
                cursor.execute("""
                    SELECT pool_address, tokens, current_nav, nav_apr, updated_at
                    FROM pool_summaries 
                    ORDER BY updated_at DESC 
                    LIMIT 5
                """)
                results = cursor.fetchall()
                
                if results:
                    print("\n📊 Recent entries:")
                    for row in results:
                        print(f"   - {row['pool_address'][:10]}...")
                        print(f"     Tokens: {row['tokens']}")
                        print(f"     NAV: ${row['current_nav']}")
                        print(f"     APR: {row['nav_apr']}%")
                        print(f"     Updated: {row['updated_at']}")
                        print()
                else:
                    print("\n📊 No entries found in table")
            else:
                print("❌ Table 'pool_summaries' does not exist")
                print("   It will be created on first use")
                
        conn.close()
        
    except Exception as e:
        print(f"❌ Failed to connect to PostgreSQL: {e}")
        print("   Falling back to file-based storage")

print("=" * 60)

# For Railway deployment
print("\n📝 To use PostgreSQL on Railway:")
print("1. Add PostgreSQL to your Railway project: railway add -d postgres")
print("2. Deploy: railway up")
print("3. DATABASE_URL will be automatically set by Railway")
print("4. Data will persist across deployments")

print("\n📝 To test locally with PostgreSQL:")
print("1. Set DATABASE_URL environment variable")
print("2. Example: export DATABASE_URL='postgresql://user:pass@host:5432/dbname'")
print("3. Restart the server")