import os
import sys
import re
import requests
import pypandoc
from dotenv import load_dotenv
import time
import random
import json
from typing import List, Tuple

# === Load environment variables ===
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")
# Use multiple free models as fallbacks
FREE_MODELS = [
    "qwen/qwen3-coder:free",
    "google/gemma-2-9b-it:free",
    "mistralai/mistral-7b-instruct:free"
]

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "../output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".py", ".js", ".html", ".css", ".ts", ".jsx", ".java", ".cpp"}
EXCLUDE_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__"}

def safe_path(path: str) -> str:
    """Make file paths safe for Markdown/PDF conversion."""
    return path.replace("\\", "/")

def read_code(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception as e:
        print(f"⚠️ Error reading {file_path}: {e}")
        return ""

def save_pdf_from_markdown(markdown_text, output_path):
    """Convert markdown to PDF using WeasyPrint (beautiful output)."""
    try:
        # First convert markdown to HTML using pandoc with syntax highlighting
        html_content = pypandoc.convert_text(
            markdown_text,
            'html',
            format='md',
            extra_args=['--highlight-style=pygments']
        )
        
        # Add beautiful CSS styling
        styled_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    margin: 40px;
                    color: #333;
                    background-color: #fff;
                }}
                
                h1, h2, h3, h4 {{
                    color: #2c3e50;
                    border-bottom: 2px solid #ecf0f1;
                    padding-bottom: 10px;
                    margin-top: 30px;
                }}
                
                pre {{
                    background-color: #f8f9fa;
                    padding: 15px;
                    border-radius: 5px;
                    border-left: 4px solid #3498db;
                    overflow-x: auto;
                    margin: 20px 0;
                    font-size: 14px;
                }}
                
                code {{
                    font-family: 'Fira Code', 'Consolas', 'Monaco', monospace;
                    background-color: #f8f9fa;
                    padding: 2px 5px;
                    border-radius: 3px;
                    color: #e74c3c;
                }}
                
                pre code {{
                    background: none;
                    padding: 0;
                    color: inherit;
                }}
                
                .filename {{
                    background-color: #34495e;
                    color: white;
                    padding: 8px 15px;
                    border-radius: 5px 5px 0 0;
                    font-family: monospace;
                    font-weight: bold;
                    margin-bottom: -5px;
                }}
            </style>
        </head>
        <body>
            {html_content}
        </body>
        </html>
        """
        
        # Convert HTML to PDF using WeasyPrint
        from weasyprint import HTML
        HTML(string=styled_html).write_pdf(output_path)
        print(f"✅ Beautiful PDF saved: {output_path}")
        
    except Exception as e:
        print(f"❌ Error with WeasyPrint: {e}")
        # Fallback to simple method if WeasyPrint fails
        try:
            pypandoc.convert_text(
                markdown_text,  # Use original text without escaping
                'pdf',
                format='md',
                outputfile=output_path,
                extra_args=['--pdf-engine=xelatex', '--standalone']
            )
            print(f"✅ PDF saved with fallback method: {output_path}")
        except Exception as fallback_error:
            print(f"❌ All methods failed: {fallback_error}")
            raise


def call_llm(prompt: str, model_index: int = 0, retries: int = 3) -> str:
    """Smart LLM calling with model rotation and intelligent backoff."""
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    # Rotate through free models
    current_model = FREE_MODELS[model_index % len(FREE_MODELS)]
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost",
        "X-Title": "Code Tool"
    }
    
    payload = {
        "model": current_model,
        "messages": [
            {"role": "system", "content": "You are a helpful programming tutor. Be concise."},
            {"role": "user", "content": prompt[:8000]}  # Limit prompt size
        ],
        "max_tokens": 300,  # Limit response length
        "temperature": 0.3   # More deterministic responses
    }

    for attempt in range(retries):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=45)
            
            if resp.status_code == 429:
                # Intelligent backoff: longer waits for repeated rate limits
                wait_time = min(120, (2 ** attempt) * 5 + random.uniform(0, 5))
                print(f"⚠️ Rate limit on {current_model}. Retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                # Try next model on rate limit
                return call_llm(prompt, model_index + 1, retries - 1)
                
            resp.raise_for_status()
            response_text = resp.json()["choices"][0]["message"]["content"]
            return response_text.encode('ascii', errors='ignore').decode('ascii')
            
        except requests.exceptions.RequestException as e:
            if attempt == retries - 1:
                print(f"❌ Final failure on {current_model}: {e}")
                return f"⚠️ Could not generate explanation due to API error: {e}"
            
            wait_time = (2 ** attempt) + random.uniform(0, 3)
            print(f"⚠️ Error on {current_model}: {e}. Retrying in {wait_time:.1f}s...")
            time.sleep(wait_time)
    
    return "⚠️ Explanation unavailable due to API issues"
def get_explanation(code: str, filename: str) -> str:
    """Get ultra-concise explanation of a code file."""
    prompt = (
        f"You are a senior coding tutor. Summarize the purpose and flow of {filename} "
        f"in **5–8 clear bullet points** (avoid repeating code).\n\n"
        f"Code snippet:\n```python\n{code[:2000]}\n```\n"
        "Answer:"
    )
    return call_llm(prompt)


def generate_batch_explanations(file_batch: List[Tuple[str, str, str]]) -> List[str]:
    """Process multiple files in one API call."""
    batch_prompt = "Explain each code snippet in exactly 10 words:\n\n"
    
    for i, (filename, code, ext) in enumerate(file_batch):
        batch_prompt += f"{i+1}. {filename} ({ext}):\n```{ext}\n{code[:500]}\n```\n\n"
    
    batch_prompt += "Provide explanations as a numbered list, each exactly 10 words:"
    
    response = call_llm(batch_prompt)
    return parse_batch_response(response, len(file_batch))

def parse_batch_response(response: str, expected_count: int) -> List[str]:
    """Parse batch response into individual explanations."""
    explanations = []
    lines = response.split('\n')
    
    for line in lines:
        if re.match(r'^\d+[\.\)]', line.strip()):
            explanation = re.sub(r'^\d+[\.\)]\s*', '', line.strip())
            explanations.append(explanation)
    
    # If parsing failed, return generic explanations
    if len(explanations) != expected_count:
        return [f"Code file {i+1}" for i in range(expected_count)]
    
    return explanations

def process_folder(folder_path: str):
    """Process folder with smart batching and rate limiting."""
    code_md = "# Project Code\n\n"
    explanation_md = "# Project Explanations\n\n"
    
    # Collect all files first
    all_files = []
    counter = 1
    
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in sorted(files):
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                file_path = os.path.join(root, file)
                if os.path.getsize(file_path) <= 30_000:  # Smaller limit
                    rel_path = os.path.relpath(file_path, folder_path)
                    all_files.append((file_path, rel_path, ext, counter))
                    counter += 1

    # Process in batches of 3-5 files to reduce API calls
    batch_size = min(4, max(2, len(all_files) // 10))  # Dynamic batch size
    explanations = [""] * len(all_files)
    
    for i in range(0, len(all_files), batch_size):
        batch = all_files[i:i + batch_size]
        batch_data = []
        
        # Prepare batch data
        for file_path, rel_path, ext, counter in batch:
            code = read_code(file_path)
            if code:
                batch_data.append((rel_path, code, ext[1:]))
                # Add to code markdown
                code_md += f"## {counter}. {safe_path(rel_path)}\n```{ext[1:]}\n{code}\n```\n\n"
        
        if batch_data:
            print(f"🤖 Processing batch {i//batch_size + 1}/{(len(all_files)-1)//batch_size + 1} ({len(batch_data)} files)...")
            batch_explanations = generate_batch_explanations(batch_data)
            
            # Assign explanations
            for j, explanation in enumerate(batch_explanations):
                idx = i + j
                if idx < len(explanations):
                    explanations[idx] = explanation
                    rel_path = all_files[idx][1]
                    explanation_md += f"## {all_files[idx][3]}. {safe_path(rel_path)}\n\n{explanation}\n\n"
            
            # Delay between batches
            if i + batch_size < len(all_files):
                delay = random.uniform(2, 5)
                time.sleep(delay)

    # Save outputs
    print("💾 Saving outputs...")
    save_pdf_from_markdown(code_md, os.path.join(OUTPUT_DIR, "code_only.pdf"))
    save_pdf_from_markdown(explanation_md, os.path.join(OUTPUT_DIR, "code_with_explanation.pdf"))
    
    # Generate simple quiz without API call
    quiz_md = generate_simple_quiz(explanations)
    save_pdf_from_markdown(quiz_md, os.path.join(OUTPUT_DIR, "quiz.pdf"))
    
    print("✅ All done! PDFs saved in output folder")

def generate_simple_quiz(explanations: List[str]) -> str:
    """Generate a simple quiz without API calls."""
    quiz_md = "# Quick Project Quiz\n\n"
    quiz_md += "## Based on the code explanations\n\n"
    
    for i, explanation in enumerate(explanations[:10]):  # Limit to 10 questions
        if explanation and not explanation.startswith("⚠️"):
            quiz_md += f"### Question {i+1}\n"
            quiz_md += f"What does this code do?\n\n"
            quiz_md += f"**Hint:** {explanation}\n\n"
            quiz_md += "A) It processes data  \nB) It handles user input  \nC) It manages state  \nD) It renders UI\n\n"
            quiz_md += "**Answer:** *Discuss with your team!*\n\n"
    
    return quiz_md

def main():
    if not API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set in environment variables.")

    if len(sys.argv) < 2:
        print("Usage: python explainer.py <folder_path>")
        sys.exit(1)

    folder_path = sys.argv[1]
    if not os.path.isdir(folder_path):
        print(f"❌ '{folder_path}' is not a valid folder.")
        sys.exit(1)

    process_folder(folder_path)

if __name__ == "__main__":
    main()