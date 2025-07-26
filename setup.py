#!/usr/bin/env python3
"""
Setup script for Jobindex Scraper with Supabase
"""

import os
import sys

def create_env_file():
    """Create a .env file with Supabase configuration"""
    
    print("🚀 Jobindex Scraper Setup")
    print("=" * 40)
    
    # Check if .env file already exists
    if os.path.exists('.env'):
        print("⚠️  .env file already exists")
        overwrite = input("Do you want to overwrite it? (y/N): ").lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return
    
    print("\n📋 Supabase Configuration")
    print("You'll need your Supabase project URL and anon key.")
    print("Get these from: https://supabase.com/dashboard/project/[YOUR-PROJECT]/settings/api")
    
    # Get Supabase credentials
    supabase_url = input("\nEnter your Supabase URL (e.g., https://your-project.supabase.co): ").strip()
    supabase_key = input("Enter your Supabase anon key: ").strip()
    
    if not supabase_url or not supabase_key:
        print("❌ Both URL and key are required!")
        return
    
    # Create .env file
    env_content = f"""# Supabase Configuration
SUPABASE_URL={supabase_url}
SUPABASE_ANON_KEY={supabase_key}

# Optional: Custom table name (default is 'jobs')
SUPABASE_TABLE_NAME=jobs
"""
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ .env file created successfully!")
        
        # Test the configuration
        print("\n🧪 Testing configuration...")
        test_configuration(supabase_url, supabase_key)
        
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")

def test_configuration(supabase_url, supabase_key):
    """Test the Supabase configuration"""
    
    try:
        from supabase import create_client, Client
        
        # Create client
        supabase: Client = create_client(supabase_url, supabase_key)
        print("✅ Supabase client created successfully")
        
        # Test connection
        result = supabase.table('jobs').select('*').limit(1).execute()
        print("✅ Successfully connected to Supabase!")
        print(f"📊 Jobs table accessible ({len(result.data)} records)")
        
        print("\n🎉 Setup complete! You can now run:")
        print("   python playwright_scraper.py")
        
    except ImportError:
        print("❌ Supabase package not installed. Run: pip install supabase")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("\n💡 Make sure:")
        print("   1. Your credentials are correct")
        print("   2. The 'jobs' table exists in your Supabase project")
        print("   3. Your project is active")

def show_instructions():
    """Show setup instructions"""
    
    print("📖 Setup Instructions")
    print("=" * 40)
    print("""
1. Create a Supabase project:
   - Go to https://supabase.com
   - Click "New Project"
   - Follow the setup wizard

2. Get your credentials:
   - Go to Project Settings → API
   - Copy the "Project URL" and "anon public" key

3. Create the database table:
   - Go to SQL Editor in your Supabase dashboard
   - Run this SQL:

CREATE TABLE jobs (
    id BIGSERIAL PRIMARY KEY,
    job_id TEXT UNIQUE NOT NULL,
    title TEXT,
    job_url TEXT,
    company TEXT,
    company_url TEXT,
    location TEXT,
    publication_date DATE,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_jobs_job_id ON jobs(job_id);
CREATE INDEX idx_jobs_company ON jobs(company);
CREATE INDEX idx_jobs_publication_date ON jobs(publication_date);

4. Run this setup script:
   python setup.py

5. Run the scraper:
   python playwright_scraper.py
""")

def main():
    """Main setup function"""
    
    if len(sys.argv) > 1 and sys.argv[1] == '--help':
        show_instructions()
        return
    
    print("Choose an option:")
    print("1. Interactive setup (recommended)")
    print("2. Show instructions")
    print("3. Exit")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == '1':
        create_env_file()
    elif choice == '2':
        show_instructions()
    elif choice == '3':
        print("Setup cancelled.")
    else:
        print("Invalid choice. Please run 'python setup.py --help' for instructions.")

if __name__ == "__main__":
    main() 