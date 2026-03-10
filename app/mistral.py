# ai_review.py
from mistral import MistralModel

# Load your local Mistral model
model = MistralModel(model_name="mistral-7b")  # replace with your local model if different

def generate_pr_review(pr_files: dict):
    """
    pr_files: dict of {filename: content}
    returns: dict of {filename: AI review string}
    """
    reviews = {}
    for filename, content in pr_files.items():
        prompt = f"Review the following code changes and provide comments or suggestions:\n\nFile: {filename}\n{content}\n\nComments:"
        response = model.generate(prompt, max_tokens=300)
        reviews[filename] = response
    return reviews
