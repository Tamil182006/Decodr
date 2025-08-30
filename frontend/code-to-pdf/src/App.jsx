// frontend/code-report-ui/src/App.jsx
import React, { useState } from "react";
import axios from "axios";
import JSZip from "jszip";
import { saveAs } from "file-saver";
import "./App.css";

const API_URL =
  import.meta.env.VITE_API_URL || "https://decodr.onrender.com";



export default function App() {
  const [zipFile, setZipFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(false);
  const [generatingReport, setGeneratingReport] = useState(false);

  const onZipSelected = (e) => {
    setZipFile(e.target.files[0] || null);
    setError(null);
    setSuccess(false);
  };

  const onFolderSelected = async (e) => {
    const files = Array.from(e.target.files);
    if (!files.length) return;

    setLoading(true);
    setError(null);
    setSuccess(false);

    try {
      const zip = new JSZip();
      files.forEach((f) => {
        const path = f.webkitRelativePath || f.name;
        zip.file(path, f);
      });

      const blob = await zip.generateAsync({ type: "blob" }, (metadata) => {
        setProgress(Math.round(metadata.percent));
      });

      const file = new File([blob], "project_upload.zip", {
        type: "application/zip",
      });
      setZipFile(file);
      setSuccess(true);
    } catch (err) {
      console.error("Zipping failed", err);
      setError("Zipping failed. Please try again.");
    } finally {
      setLoading(false);
      setProgress(0);
    }
  };

  const upload = async () => {
    if (!zipFile) {
      setError("Please select a ZIP file or folder first!");
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(false);
    setProgress(0);

    const form = new FormData();
    form.append("file", zipFile);
    form.append("max_files", "20");

    try {
      const res = await axios.post(`${API_URL}/upload`,  form, {
        responseType: "blob",
        onUploadProgress: (p) => {
          if (p.total) setProgress(Math.round((p.loaded * 100) / p.total));
        },
        timeout: 300000, // 5 minutes timeout
      });

      // Get filename from content-disposition or use default
      const contentDisposition = res.headers["content-disposition"];
      let filename = "code_documentation.zip";
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?(.+)"?/);
        if (filenameMatch && filenameMatch[1]) {
          filename = filenameMatch[1];
        }
      }

      // Download the file
      const blob = new Blob([res.data], { type: "application/zip" });
      saveAs(blob, filename);

      setSuccess(true);
      setError(null);
    } catch (err) {
      console.error("Upload error:", err);

      if (err.response?.data instanceof Blob) {
        try {
          const errorText = await err.response.data.text();
          const errorData = JSON.parse(errorText);
          setError(errorData.detail || "Processing failed. Please try again.");
        } catch {
          setError("Processing failed. Please try a different project.");
        }
      } else if (err.code === "ECONNABORTED") {
        setError(
          "Request timeout. The project might be too large. Try with fewer files."
        );
      } else {
        setError(
          "Upload failed. Please check if the backend server is running."
        );
      }
    } finally {
      setLoading(false);
      setProgress(0);
    }
  };

  const generateAnalysisReport = async () => {
    if (!zipFile) {
      setError("Please select a ZIP file first!");
      return;
    }

    setGeneratingReport(true);
    setError(null);

    const form = new FormData();
    form.append("file", zipFile);
    form.append("max_files", "20");

    try {
      const res = await axios.post(`${API_URL}/generate-report`,
        form,
        {
          responseType: "blob",
          timeout: 300000,
        }
      );

      const blob = new Blob([res.data], { type: "application/pdf" });
      saveAs(blob, "project_analysis_report.pdf");

      setSuccess(true);
    } catch (err) {
      console.error("Report generation error:", err);
      setError("Failed to generate analysis report. Please try again.");
    } finally {
      setGeneratingReport(false);
    }
  };

  const clearSelection = () => {
    setZipFile(null);
    setError(null);
    setSuccess(false);
  };

  return (
   
    <div className="app-container">
      <div className="header">
        <div className="logo">
          <span className="logo-icon">📚</span>
          <h1>Code Documentation Generator</h1>
        </div>
        <p className="subtitle">
          Transform your code into beautiful PDF documentation
        </p>
      </div>

      <div className="upload-section">
        <div className="upload-card">
          <div className="upload-options">
            <div className="upload-option">
              <label className="file-input-label">
                <input
                  type="file"
                  accept=".zip"
                  onChange={onZipSelected}
                  disabled={loading || generatingReport}
                />
                <div className="upload-box">
                  <span className="upload-icon">📦</span>
                  <h3>Upload ZIP File</h3>
                  <p>Fast and recommended</p>
                </div>
              </label>
            </div>

            <div className="upload-option">
              <label className="file-input-label">
                <input
                  type="file"
                  webkitdirectory="true"
                  directory="true"
                  multiple
                  onChange={onFolderSelected}
                  disabled={loading || generatingReport}
                />
                <div className="upload-box">
                  <span className="upload-icon">📁</span>
                  <h3>Upload Folder</h3>
                  <p>Chrome/Edge browsers only</p>
                </div>
              </label>
            </div>
          </div>

          {zipFile && (
            <div className="file-info">
              <div className="file-details">
                <span className="file-icon">📄</span>
                <div className="file-text">
                  <strong>{zipFile.name}</strong>
                  <span>{Math.round(zipFile.size / 1024)} KB</span>
                </div>
                <button
                  onClick={clearSelection}
                  className="clear-btn"
                  disabled={loading || generatingReport}
                >
                  ×
                </button>
              </div>
            </div>
          )}

          <button
            onClick={upload}
            disabled={loading || generatingReport || !zipFile}
            className={`generate-btn ${loading ? "loading" : ""}`}
          >
            {loading ? (
              <>
                <div className="spinner"></div>
                Processing... {progress}%
              </>
            ) : (
              "🚀 Generate Documentation"
            )}
          </button>

          <button
            onClick={generateAnalysisReport}
            disabled={generatingReport || loading || !zipFile}
            className={`report-btn ${generatingReport ? "loading" : ""}`}
          >
            {generatingReport ? (
              <>
                <div className="spinner"></div>
                Generating Analysis...
              </>
            ) : (
              "📊 Generate Analysis Report"
            )}
          </button>

          {error && (
            <div className="error-message">
              <span className="error-icon">⚠️</span>
              {error}
            </div>
          )}

          {success && !loading && !generatingReport && (
            <div className="success-message">
              <span className="success-icon">✅</span>
              Documentation generated successfully! Check your downloads.
            </div>
          )}

          <div className="info-tips">
            <h4>💡 Tips:</h4>
            <ul>
              <li>Maximum 20 files will be processed</li>
              <li>Supported: .py, .js, .jsx, .ts, .html, .css, .java, .cpp</li>
              <li>Large projects may take several minutes</li>
              <li>Check console for detailed progress</li>
            </ul>
          </div>
        </div>
      </div>

      <div className="features">
        <h2>What you'll get:</h2>
        <div className="features-grid">
          <div className="feature">
            <span className="feature-icon">📄</span>
            <h3>Code PDF</h3>
            <p>Complete source code in formatted PDF</p>
          </div>
          <div className="feature">
            <span className="feature-icon">📝</span>
            <h3>Explanations</h3>
            <p>AI-generated explanations for each file</p>
          </div>
          <div className="feature">
            <span className="feature-icon">🧠</span>
            <h3>Quiz</h3>
            <p>Interactive quiz to test understanding</p>
          </div>
          <div className="feature">
            <span className="feature-icon">📊</span>
            <h3>Analysis Report</h3>
            <p>Advanced code complexity analysis</p>
          </div>
          <div className="feature">
            <span className="feature-icon">📦</span>
            <h3>ZIP Bundle</h3>
            <p>All documents packaged together</p>
          </div>
        </div>
      </div>

      <footer className="footer">
        <p>@rtv ✨</p>
      </footer>
    </div>
  );
}
