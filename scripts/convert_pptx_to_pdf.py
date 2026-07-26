import sys
import os
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
pptx_path = os.path.join(PROJECT_ROOT, "Eco-Loop_Idea_Submission.pptx")
pdf_path = os.path.join(PROJECT_ROOT, "Eco-Loop_Idea_Submission.pdf")
pdf_dest_path = os.path.join(PROJECT_ROOT, "pdf_deliverables", "Eco-Loop_Idea_Submission.pdf")

ps_script = f"""
$ppt = New-Object -ComObject PowerPoint.Application
$pres = $ppt.Presentations.Open('{pptx_path}', 1, 0, 0)
$pres.SaveAs('{pdf_path}', 32)
$pres.SaveAs('{pdf_dest_path}', 32)
$pres.Close()
$ppt.Quit()
"""

ps_file = os.path.join(PROJECT_ROOT, "scripts", "convert_ppt.ps1")
with open(ps_file, "w", encoding="utf-8") as f:
    f.write(ps_script)

print(f"Executing PowerPoint conversion script for: {pptx_path}")
res = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", ps_file], capture_output=True, text=True)
print("Stdout:", res.stdout)
print("Stderr:", res.stderr)

if os.path.exists(pdf_path):
    size_kb = round(os.path.getsize(pdf_path) / 1024.0, 1)
    print(f"✅ SUCCESS: Converted {os.path.basename(pptx_path)} to {os.path.basename(pdf_path)} ({size_kb} KB)")
else:
    print("⚠️ PDF not created yet.")
