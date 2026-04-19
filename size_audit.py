import os

def get_heavy_files(root_dir, min_size_mb=1.0):
    heavy_files = []
    for root, dirs, files in os.walk(root_dir):
        # Skip git and venv
        if '.git' in root or 'venv' in root:
            continue
            
        for name in files:
            filepath = os.path.join(root, name)
            try:
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                if size_mb >= min_size_mb:
                    rel_path = os.path.relpath(filepath, root_dir)
                    heavy_files.append((rel_path, size_mb))
            except Exception:
                continue
                
    # Sort by size descending
    heavy_files.sort(key=lambda x: x[1], reverse=True)
    
    print(f"{'FILE PATH':<70} | {'SIZE (MB)':<10}")
    print("-" * 83)
    for path, size in heavy_files[:20]:
        print(f"{path[:70]:<70} | {size:>8.2f} MB")

if __name__ == "__main__":
    get_heavy_files('.')
