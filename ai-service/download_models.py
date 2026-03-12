print("Downloading BART large classifier (~1.5GB)...")
from transformers import pipeline
pipeline("zero-shot-classification", model="facebook/bart-large-mnli")
print("BART done!")

print("Downloading sentence embeddings (~90MB)...")
from sentence_transformers import SentenceTransformer
SentenceTransformer("all-MiniLM-L6-v2")
print("All models ready!")