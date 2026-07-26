
$ppt = New-Object -ComObject PowerPoint.Application
$pres = $ppt.Presentations.Open('C:\Users\tarun\Desktop\Eco-Loop Building Agents\Eco-Loop_Idea_Submission.pptx', 1, 0, 0)
$pres.SaveAs('C:\Users\tarun\Desktop\Eco-Loop Building Agents\Eco-Loop_Idea_Submission.pdf', 32)
$pres.SaveAs('C:\Users\tarun\Desktop\Eco-Loop Building Agents\pdf_deliverables\Eco-Loop_Idea_Submission.pdf', 32)
$pres.Close()
$ppt.Quit()
