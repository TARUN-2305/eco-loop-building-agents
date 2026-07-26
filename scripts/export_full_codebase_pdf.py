"""
Export script to convert the ENTIRE Eco-Loop Building Agents codebase,
architecture specifications, configuration files, and presentation slides into unified PDF documents via headless Microsoft Edge.
Fulfills: 'In case of errors uploading zip files, convert/print all files to pdf and upload.'
"""

import sys
import os
import subprocess
import html
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_codebase_files():
    """Collects all primary source code, configuration, test, and documentation files."""
    files = [
        "README.md",
        "SYSTEM_ARCHITECTURE.md",
        "PRESENTATION_SLIDES.md",
        "AGENTS.md",
        "build.bat",
        "main.py",
        "configs/agent.yaml",
        "configs/baseline.yaml",
        "src/bridge/lifecycle.py",
        "src/bridge/handles.py",
        "src/bridge/callbacks.py",
        "src/agent/orchestrator.py",
        "src/agent/llm_client.py",
        "src/mcp_server/server.py",
        "src/mcp_server/tools/apply_setpoints.py",
        "src/mcp_server/tools/validate_action.py",
        "src/mcp_server/tools/propose_setpoints.py",
        "src/mcp_server/tools/compute_pmv.py",
        "src/mcp_server/tools/get_zone_state.py",
        "src/mcp_server/tools/get_weather_forecast.py",
        "src/mcp_server/tools/get_history.py",
        "src/comfort/pmv.py",
        "src/optimizer/solver.py",
        "src/storage/writer.py",
        "src/storage/queries.py",
        "src/monitoring/health.py",
        "src/idf_tools/ecm_sweep.py",
        "tests/integration/test_idf_config_consistency.py",
        "tests/integration/test_bridge_lifecycle.py",
        "tests/integration/test_full_agent_closed_loop.py",
    ]
    return [os.path.join(PROJECT_ROOT, f) for f in files if os.path.exists(os.path.join(PROJECT_ROOT, f))]


def generate_unified_codebase_html():
    """Generates a clean, syntax-styled HTML document containing the entire codebase."""
    files = get_codebase_files()
    html_parts = []
    
    html_parts.append("""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Eco-Loop Building Agents — Unified Complete Codebase & Deliverables</title>
    <style>
        body { font-family: 'Segoe UI', Arial, sans-serif; margin: 30px; color: #0f172a; line-height: 1.5; font-size: 12px; }
        .cover { text-align: center; margin-top: 100px; margin-bottom: 120px; page-break-after: always; }
        .cover h1 { font-size: 32px; color: #0284c7; margin-bottom: 10px; }
        .cover h2 { font-size: 18px; color: #475569; font-weight: normal; margin-bottom: 30px; }
        .cover-meta { font-size: 14px; color: #64748b; margin-top: 40px; }
        .file-header { background: #0284c7; color: #ffffff; padding: 8px 14px; font-weight: bold; font-family: monospace; font-size: 14px; border-radius: 6px 6px 0 0; margin-top: 30px; page-break-before: always; }
        .code-box { background: #0f172a; color: #f8fafc; padding: 14px; border-radius: 0 0 6px 6px; font-family: 'Courier New', monospace; font-size: 11px; white-space: pre-wrap; word-wrap: break-word; margin-bottom: 20px; border: 1px solid #1e293b; }
        h1, h2, h3 { color: #0f172a; }
        blockquote { background: #f0f9ff; border-left: 4px solid #0284c7; padding: 8px 12px; margin: 10px 0; color: #0369a1; }
        ul { margin-left: 20px; }
        table { border-collapse: collapse; width: 100%; margin: 10px 0; }
        th, td { border: 1px solid #cbd5e1; padding: 6px 10px; text-align: left; font-size: 11px; }
        th { background: #f1f5f9; }
    </style>
</head>
<body>
    <div class="cover">
        <h1>Eco-Loop Building Agents</h1>
        <h2>Unified Complete Codebase & Physical AI Deliverables</h2>
        <div class="cover-meta">
            <p><strong>NREL EnergyPlus C++ API Closed-Loop HVAC Control System</strong></p>
            <p>GitHub Repository: https://github.com/TARUN-2305/eco-loop-building-agents</p>
            <p>Generated for PDF Submission Portal Upload</p>
        </div>
    </div>
""")

    for filepath in files:
        rel_path = os.path.relpath(filepath, PROJECT_ROOT)
        html_parts.append(f'<div class="file-header">📄 FILE: {html.escape(rel_path)}</div>')
        
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
            
        html_parts.append(f'<div class="code-box">{html.escape(content)}</div>')

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


def convert_html_to_pdf(html_path: str, pdf_path: str):
    edge_exec = "msedge"
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]:
        if os.path.exists(p):
            edge_exec = p
            break
            
    abs_html = os.path.abspath(html_path)
    abs_pdf = os.path.abspath(pdf_path)
    
    cmd = [edge_exec, "--headless", "--disable-gpu", f"--print-to-pdf={abs_pdf}", abs_html]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if os.path.exists(abs_pdf):
            size_mb = round(os.path.getsize(abs_pdf) / (1024.0 * 1024.0), 2)
            print(f"[OK] Successfully Generated PDF: {os.path.basename(abs_pdf)} ({size_mb} MB)")
            return True
        else:
            print(f"[WARN] Failed to create PDF: {res.stderr}")
    except Exception as e:
        print(f"[ERROR] Edge PDF conversion error: {e}")
        
    return False


def main():
    print("--- Exporting Entire Codebase and Deliverables to Unified PDF ---")
    
    html_content = generate_unified_codebase_html()
    temp_html = os.path.join(PROJECT_ROOT, "unified_codebase_temp.html")
    
    with open(temp_html, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    pdf_dir = os.path.join(PROJECT_ROOT, "pdf_deliverables")
    os.makedirs(pdf_dir, exist_ok=True)
    
    # 1. Entire Codebase PDF
    codebase_pdf = os.path.join(pdf_dir, "Entire_Codebase_and_Deliverables.pdf")
    convert_html_to_pdf(temp_html, codebase_pdf)
    
    # Copy to root as well for easy access
    root_codebase_pdf = os.path.join(PROJECT_ROOT, "Entire_Codebase_and_Deliverables.pdf")
    if os.path.exists(codebase_pdf):
        import shutil
        shutil.copyfile(codebase_pdf, root_codebase_pdf)
        print(f"[OK] Root PDF Deliverable Created: Entire_Codebase_and_Deliverables.pdf")
        
    if os.path.exists(temp_html):
        os.remove(temp_html)


if __name__ == "__main__":
    main()
