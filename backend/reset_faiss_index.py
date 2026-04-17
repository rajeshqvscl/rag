#!/usr/bin/env python3
"""
Reset FAISS index for new embedding dimensions.
Run this after switching from 384-dim (all-MiniLM-L6-v2) to 1536-dim (voyage-large-2)
"""
import os
import shutil
import sys

def reset_faiss_index():
    """Delete old FAISS index files to force rebuild with new dimensions"""
    index_dir = "app/data/faiss_index"
    index_file = os.path.join(index_dir, "index.faiss")
    meta_file = os.path.join(index_dir, "meta.pkl")
    
    print("=" * 50)
    print("FAISS Index Reset Tool")
    print("=" * 50)
    print(f"\nTarget directory: {index_dir}")
    
    # Check if files exist
    index_exists = os.path.exists(index_file)
    meta_exists = os.path.exists(meta_file)
    
    if not index_exists and not meta_exists:
        print("\n✓ No existing FAISS index found. Ready to build new index.")
        return
    
    print(f"\nFound existing index files:")
    if index_exists:
        size = os.path.getsize(index_file) / (1024 * 1024)  # MB
        print(f"  - index.faiss: {size:.2f} MB (OLD - 384-dim incompatible)")
    if meta_exists:
        size = os.path.getsize(meta_file) / (1024 * 1024)
        print(f"  - meta.pkl: {size:.2f} MB (OLD - incompatible)")
    
    print(f"\n⚠ WARNING: These files were built with 384-dim embeddings (all-MiniLM-L6-v2)")
    print(f"⚠ The new VoyageAI model uses 1536-dim embeddings")
    print(f"⚠ Old index is INCOMPATIBLE and must be deleted\n")
    
    response = input("Delete and reset FAISS index? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        try:
            if index_exists:
                os.remove(index_file)
                print(f"✓ Deleted: index.faiss")
            if meta_exists:
                os.remove(meta_file)
                print(f"✓ Deleted: meta.pkl")
            print(f"\n✅ FAISS index reset complete!")
            print(f"\nNext steps:")
            print(f"1. Restart the backend server")
            print(f"2. Re-ingest your documents to build new 1536-dim index")
            print(f"3. The new index will use VoyageAI voyage-large-2 embeddings")
        except Exception as e:
            print(f"\n❌ Error deleting files: {e}")
            sys.exit(1)
    else:
        print(f"\nCancelled. Index not reset.")
        print(f"⚠ The backend will FAIL if you don't reset - dimension mismatch!")

if __name__ == "__main__":
    reset_faiss_index()
