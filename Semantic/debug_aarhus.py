#!/usr/bin/env python3
"""
Debug script to check why Aarhus jobs are not found in semantic search
"""

import os
from supabase import create_client
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

supabase = create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_SERVICE_ROLE_KEY'))
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

def create_embedding_text(job):
    """Create embedding text using the same strategy as job_embedding_generator.py"""
    title = job.get('title', '') or ''
    company = job.get('company', '') or ''
    location = job.get('location', '') or ''
    description = job.get('description', '') or ''
    
    # Strip whitespace
    title = title.strip()
    company = company.strip()
    location = location.strip()
    description = description.strip()
    
    if not title:
        title = "Job"
    if not company:
        company = "Company"
    if not location:
        location = "Location not specified"
    
    weighted_description = f"{company} - {title}. {description}"
    # Give more weight to location by repeating it and putting it first
    embedding_text = f"Location: {location}\n{company} - {title}\nLocation: {location}\nDescription: {weighted_description}"
    
    return embedding_text.strip()

def debug_aarhus_search():
    print("🔍 Debugging Aarhus search...")
    
    # 1. Check how many Aarhus jobs exist
    response = supabase.table('jobs').select('*').ilike('location', '%aarhus%').gte('cfo_score', 1).execute()
    print(f"Total Aarhus jobs: {len(response.data)}")
    
    # 2. Check if they have embeddings
    with_embeddings = [job for job in response.data if job.get('embedding')]
    print(f"Aarhus jobs with embeddings: {len(with_embeddings)}")
    
    # 3. Show embedding text for a few examples
    print("\nEksempler på embedding tekst for Aarhus jobs:")
    for i, job in enumerate(response.data[:2], 1):
        print(f"\n{i}. {job.get('title')}")
        print(f"   Lokation: {job.get('location')}")
        embedding_text = create_embedding_text(job)
        print(f"   Embedding tekst (første 300 tegn):")
        print(f"   {embedding_text[:300]}...")
        print()
    
    # 4. Test semantic search with "aarhus"
    print("🔍 Testing semantic search with 'aarhus'...")
    response_embedding = openai_client.embeddings.create(
        model='text-embedding-ada-002',
        input='aarhus'
    )
    query_embedding = response_embedding.data[0].embedding
    
    search_response = supabase.rpc('match_jobs', {
        'query_embedding': query_embedding,
        'match_threshold': 0.1,
        'match_count': 10
    }).execute()
    
    print(f"Found {len(search_response.data)} total jobs")
    
    # Check for Aarhus jobs in results
    aarhus_jobs = [job for job in search_response.data if 'aarhus' in job.get('location', '').lower()]
    print(f"Found {len(aarhus_jobs)} Aarhus jobs in search results")
    
    if aarhus_jobs:
        print("\nAarhus jobs found:")
        for job in aarhus_jobs:
            print(f"- {job.get('title')} i {job.get('location')} (relevans: {job.get('similarity', 0):.3f})")
    else:
        print("\n❌ No Aarhus jobs found in search results!")
        
        # Show what we got instead
        print("\nTop 5 search results:")
        for i, job in enumerate(search_response.data[:5], 1):
            print(f"{i}. {job.get('title')} i {job.get('location')} (relevans: {job.get('similarity', 0):.3f})")
    
    # 5. Test with "aarhus location" to see if that helps
    print("\n🔍 Testing with 'aarhus location'...")
    response_embedding2 = openai_client.embeddings.create(
        model='text-embedding-ada-002',
        input='aarhus location'
    )
    query_embedding2 = response_embedding2.data[0].embedding
    
    search_response2 = supabase.rpc('match_jobs', {
        'query_embedding': query_embedding2,
        'match_threshold': 0.1,
        'match_count': 10
    }).execute()
    
    aarhus_jobs2 = [job for job in search_response2.data if 'aarhus' in job.get('location', '').lower()]
    print(f"Found {len(aarhus_jobs2)} Aarhus jobs with 'aarhus location' search")
    
    if aarhus_jobs2:
        print("\nAarhus jobs found with 'aarhus location':")
        for job in aarhus_jobs2:
            print(f"- {job.get('title')} i {job.get('location')} (relevans: {job.get('similarity', 0):.3f})")
    
    # 6. Test with very low threshold
    print("\n🔍 Testing with very low threshold (0.05)...")
    search_response3 = supabase.rpc('match_jobs', {
        'query_embedding': query_embedding,
        'match_threshold': 0.05,
        'match_count': 20
    }).execute()
    
    aarhus_jobs3 = [job for job in search_response3.data if 'aarhus' in job.get('location', '').lower()]
    print(f"Found {len(aarhus_jobs3)} Aarhus jobs with low threshold")
    
    if aarhus_jobs3:
        print("\nAarhus jobs found with low threshold:")
        for job in aarhus_jobs3:
            print(f"- {job.get('title')} i {job.get('location')} (relevans: {job.get('similarity', 0):.3f})")
    else:
        print("\n❌ Still no Aarhus jobs found even with low threshold!")
        
        # Show all results to see what we get
        print("\nAll results with low threshold:")
        for i, job in enumerate(search_response3.data[:10], 1):
            print(f"{i}. {job.get('title')} i {job.get('location')} (relevans: {job.get('similarity', 0):.3f})")

if __name__ == "__main__":
    debug_aarhus_search() 