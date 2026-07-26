"""
Utility script to convert Markdown deliverables to HTML and PDF via headless Microsoft Edge.
Handles the hackathon fallback requirement: 'In case of errors uploading zip files, convert/print all files to pdf and upload.'
"""

import sys
import os
import subprocess
import html
import re

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def md_to_clean_html(md_text: str, title: str) -> str:
    """Simple Markdown to HTML renderer for PDF printing."""
    lines = md_text.splitlines()
    html_lines = []
    in_code = False
    in_list = False
    
    for line in lines:
        if line.startswith("```"):
            if in_code:
                html_lines.append("</pre></div>")
                in_code = False
            else:
                html_lines.append("<div class='code-box'><pre>")
                in_code = True
            continue
            
        if in_code:
            html_lines.append(html.escape(line))
            continue

        if line.startswith("# "):
            html_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            html_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("### "):
            html_lines.append(f"<h3>{html.escape(line[4:])}</h3>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            item = html.escape(line[2:])
            item = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', item)
            item = re.sub(r'\*(.*?)\*', r'<em>\1</em>', item)
            html_lines.append(f"<li>{item}</li>")
        elif line.startswith("> "):
            html_lines.append(f"<blockquote>{html.escape(line[2:])}</blockquote>")
        elif line.strip() == "":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<p></p>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            text = html.escape(line)
            text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
            text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
            html_lines.append(f"<p>{text}</p>")
            
    if in_list:
        html_lines.append("</ul>")
        
    body = "\n".join(html_lines)
    
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{html.escape(title)}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #1e293b; line-height: 1.6; font-size: 14px; }}
        h1 {{ color: #0f172a; border-bottom: 2px solid #0284c7; padding-bottom: 8px; font-size: 24px; }}
        h2 {{ color: #0369a1; border-bottom: 1px solid #cbd5e1; padding-bottom: 6px; font-size: 18px; margin-top: 24px; }}
        h3 {{ color: #0f172a; font-size: 15px; margin-top: 18px; }}
        code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-family: 'Courier New', monospace; font-size: 12px; }}
        .code-box {{ background: #0f172a; color: #f8fafc; padding: 14px; border-radius: 8px; font-family: 'Courier New', monospace; font-size: 12px; margin: 12px 0; overflow-x: auto; }}
        blockquote {{ background: #f0f9ff; border-left: 4px solid #0284c7; margin: 12px 0; padding: 10px 16px; color: #0369a1; }}
        ul {{ margin-left: 20px; }}
        li {{ margin-bottom: 4px; }}
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        th, td {{ border: 1px solid #cbd5e1; padding: 8px 12px; text-align: left; }}
        th {{ background: #f1f5f9; color: #0f172a; }}
    </style>
</head>
<body>
{body}
</body>
</html>"""

def convert_md_file_to_pdf(md_path: str, pdf_path: str):
    if not os.path.exists(md_path):
        print(f"File not found: {md_path}")
        return False
        
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()
        
    title = os.path.basename(md_path)
    html_content = md_to_clean_html(md_text, title)
    
    html_temp_path = md_path.replace(".md", "_temp.html")
    with open(html_temp_path, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    abs_html = os.path.abspath(html_temp_path)
    abs_pdf = os.path.abspath(pdf_path)
    
    edge_executable = "msedge"
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"msedge.exe",
    ]:
        if os.path.exists(p):
            edge_executable = p
            break

    edge_cmd = [
        edge_executable,
        "--headless",
        "--disable-gpu",
        f"--print-to-pdf={abs_pdf}",
        abs_html
    ]
    
    try:
        res = subprocess.run(edge_cmd, capture_output=True, text=True)
        if os.path.exists(abs_pdf):
            size_kb = round(os.path.getsize(abs_pdf) / 1024.0, 1)
            print(f"[OK] Created PDF: {os.path.basename(abs_pdf)} ({size_kb} KB)")
            if os.path.exists(html_temp_path):
                os.remove(html_temp_path)
            return True
        else:
            print(f"[WARN] Edge PDF conversion warning: {res.stderr}")
    except Exception as e:
        print(f"[ERROR] Edge execution error: {e}")
        
    return False

def main():
    print("--- Converting Hackathon Deliverable Documents to PDF ---")
    
    pdf_dir = os.path.join(PROJECT_ROOT, "pdf_deliverables")
    os.makedirs(pdf_dir, exist_ok=True)
    
    docs_to_convert = [
        ("SYSTEM_ARCHITECTURE.md", "Deliverable_4_System_Architecture.pdf"),
        ("PRESENTATION_SLIDES.md", "Presentation_Slides_Deck.pdf"),
        ("README.md", "Project_Readme_and_Deliverables.pdf"),
        ("AGENTS.md", "Architectural_Guardrails_and_Invariants.pdf"),
        ("docs/demo/DEMO_SCRIPT.md", "Deliverable_5_Video_Demonstration_Guide.pdf"),
    ]
    
    for src_rel, pdf_name in docs_to_convert:
        src_path = os.path.join(PROJECT_ROOT, src_rel)
        out_pdf = os.path.join(pdf_dir, pdf_name)
        convert_md_file_to_pdf(src_path, out_pdf)
        
    print(f"\nAll PDF deliverables saved to: {pdf_dir}/")

if __name__ == "__main__":
    main()
