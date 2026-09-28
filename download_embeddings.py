import os
import sys

# Add project root to sys.path so config can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config.settings import settings
from sentence_transformers import SentenceTransformer

def download_model():
    model_name = settings.embedding_model
    save_path = str(settings.embedding_model_path)
    
    # Ensure directory exists
    os.makedirs(save_path, exist_ok=True)
    
    if os.path.exists(os.path.join(save_path, "config.json")):
        print(f"[INFO] Model already downloaded at: {save_path}")
        return
        
    print(f"[INFO] Downloading embedding model '{model_name}' to local system...")
    print(f"[INFO] Destination: {save_path}")
    
    try:
        # Load model from huggingface
        model = SentenceTransformer(model_name)
        # Save model locally
        model.save(save_path)
        print("[OK] Download complete. The system will use this local model for offline operation.")
    except Exception as e:
        print(f"[ERROR] Failed to download embedding model: {e}")
        sys.exit(1)

if __name__ == "__main__":
    download_model()
