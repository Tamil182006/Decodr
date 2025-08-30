# backend/app.py
import os
import zipfile
import shutil
import tempfile
import time
import glob
import sys  # ← ADD THIS IMPORT
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    print("Warning: OPENROUTER_API_KEY not set in .env (explainer will fail to call LLM).")

# allow front-end dev origin
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # allow all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# import your explainer (make sure explainer.py is next to this file)
from explainer import process_folder, OUTPUT_DIR  # explainer.py must define these

ALLOWED_EXTENSIONS = {".py", ".js", ".html", ".css", ".ts", ".jsx", ".java", ".cpp"}
EXCLUDE_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__"}

def cleanup_old_temp_zips(zip_dir, max_age_hours=1):
    """Remove temporary zip files older than max_age_hours"""
    current_time = time.time()
    for zip_file in glob.glob(os.path.join(zip_dir, "result_bundle_*.zip")):
        try:
            file_age = current_time - os.path.getctime(zip_file)
            if file_age > max_age_hours * 3600:  # Convert hours to seconds
                os.remove(zip_file)
                print(f"🧹 Cleaned up old temp file: {zip_file}")
        except Exception as e:
            print(f"⚠️ Could not clean up {zip_file}: {e}")

def collect_allowed_files(root_dir, max_files=20):
    """Return list of file paths (absolute) limited to max_files."""
    files = []
    for root, dirs, filenames in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in sorted(filenames):
            ext = os.path.splitext(f)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                files.append(os.path.join(root, f))
                if len(files) >= max_files:
                    return files
    return files

@app.post("/upload")
async def upload_project(file: UploadFile = File(...), max_files: int = 20):
    # Basic validation
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads allowed")

    # Create a persistent directory for the result zip
    result_zip_dir = os.path.join(OUTPUT_DIR, "temp_zips")
    os.makedirs(result_zip_dir, exist_ok=True)
    
    # Clean up old temp files first
    cleanup_old_temp_zips(result_zip_dir)
    
    # Create unique zip filename
    timestamp = int(time.time())
    result_zip = os.path.join(result_zip_dir, f"result_bundle_{timestamp}.zip")

    # Use temporary directory only for extraction
    with tempfile.TemporaryDirectory() as tmpdir:
        upload_path = os.path.join(tmpdir, "upload.zip")
        with open(upload_path, "wb") as f:
            contents = await file.read()
            f.write(contents)

        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(upload_path, "r") as z:
            z.extractall(extract_dir)

        # collect allowed files (limit)
        selected = collect_allowed_files(extract_dir, max_files=max_files)

        if not selected:
            raise HTTPException(status_code=400, detail="No allowed files found in zip")

        # create a clean temp dir with only selected files (preserve relative structure)
        selected_dir = os.path.join(tmpdir, "selected_project")
        for src in selected:
            rel = os.path.relpath(src, extract_dir)
            dst = os.path.join(selected_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

        # Clear OUTPUT_DIR before processing (optional). OUTPUT_DIR is from explainer.py
        if os.path.exists(OUTPUT_DIR):
            try:
                # remove old output files only (careful!)
                for f in Path(OUTPUT_DIR).glob("*"):
                    if f.is_file() and not f.name.startswith('temp_zips'):
                        f.unlink()
            except Exception as e:
                print("Could not clear old outputs:", e)

        # Run your existing processing code (this writes PDFs into OUTPUT_DIR)
        process_folder(selected_dir)

        # Check if PDFs were created successfully
        pdf_files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.pdf')]
        if not pdf_files:
            raise HTTPException(status_code=500, detail="Processing failed; no PDFs were generated")

        # Package generated outputs into one zip to return
        with zipfile.ZipFile(result_zip, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(OUTPUT_DIR):
                for fname in files:
                    if fname.endswith('.pdf'):  # Only include PDF files
                        fpath = os.path.join(root, fname)
                        arcname = fname  # Just the filename, not the full path
                        z.write(fpath, arcname=arcname)

        if not os.path.exists(result_zip):
            raise HTTPException(status_code=500, detail="Processing failed; no outputs produced")

    # Return the zip file from a persistent location
    return FileResponse(
        result_zip, 
        media_type="application/zip", 
        filename=f"code_documentation_{timestamp}.zip"
    )

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "output_dir": OUTPUT_DIR}
    
@app.post("/generate-report")
async def generate_report_endpoint(file: UploadFile = File(...), max_files: int = 20):
    if not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads allowed")

    # Create persistent directory for the report
    result_pdf_dir = os.path.join(OUTPUT_DIR, "temp_reports")
    os.makedirs(result_pdf_dir, exist_ok=True)
    result_pdf = os.path.join(result_pdf_dir, f"project_analysis_report_{int(time.time())}.pdf")

    with tempfile.TemporaryDirectory() as tmpdir:
        upload_path = os.path.join(tmpdir, "upload.zip")
        with open(upload_path, "wb") as f:
            contents = await file.read()
            f.write(contents)

        extract_dir = os.path.join(tmpdir, "extracted")
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(upload_path, "r") as z:
            z.extractall(extract_dir)

        selected = collect_allowed_files(extract_dir, max_files=max_files)
        if not selected:
            raise HTTPException(status_code=400, detail="No allowed files found in zip")

        selected_dir = os.path.join(tmpdir, "selected_project")
        for src in selected:
            rel = os.path.relpath(src, extract_dir)
            dst = os.path.join(selected_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)

        # Generate the analysis report
        try:
            # Add current directory to Python path
            sys.path.append(os.path.dirname(__file__))
            from report import generate_report
            
            print("📊 Starting analysis report generation...")
            report_path = generate_report(selected_dir)
            
            # Move the generated report to persistent storage
            if os.path.exists(report_path):
                shutil.move(report_path, result_pdf)
            
            if os.path.exists(result_pdf):
                return FileResponse(
                    result_pdf,
                    media_type="application/pdf",
                    filename="project_analysis_report.pdf"
                )
            else:
                raise HTTPException(status_code=500, detail="Report PDF was not created")
            
        except ImportError as e:
            print(f"❌ Import error: {e}")
            raise HTTPException(status_code=500, detail=f"Report module error: {str(e)}")
        except Exception as e:
            print(f"❌ Report generation error: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")

# Add cleanup function for report files
def cleanup_old_temp_reports(report_dir, max_age_hours=1):
    """Remove temporary report files older than max_age_hours"""
    current_time = time.time()
    for report_file in glob.glob(os.path.join(report_dir, "project_analysis_report_*.pdf")):
        try:
            file_age = current_time - os.path.getctime(report_file)
            if file_age > max_age_hours * 3600:
                os.remove(report_file)
                print(f"🧹 Cleaned up old report: {report_file}")
        except Exception as e:
            print(f"⚠️ Could not clean up {report_file}: {e}")

# Update startup event to clean both zip and report files
@app.on_event("startup")
async def startup_event():
    """Clean up old temp files on startup"""
    # Clean zip files
    result_zip_dir = os.path.join(OUTPUT_DIR, "temp_zips")
    os.makedirs(result_zip_dir, exist_ok=True)
    cleanup_old_temp_zips(result_zip_dir)
    
    # Clean report files
    result_pdf_dir = os.path.join(OUTPUT_DIR, "temp_reports")
    os.makedirs(result_pdf_dir, exist_ok=True)
    cleanup_old_temp_reports(result_pdf_dir)
    
    print("✅ Server started and temp files cleaned up")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)