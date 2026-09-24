import os
import re

md_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "RAPPORT_DE_STAGE_ENIT.md")
html_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "RAPPORT_DE_STAGE_ENIT.html")

with open(md_path, "r", encoding="utf-8") as f:
    text = f.read()

lines = text.split("\n")
html_lines = [
    "<!DOCTYPE html>",
    "<html lang='fr'>",
    "<head>",
    "<meta charset='utf-8'>",
    "<title>Rapport de Stage Ingénieur - Aya BOUKARI - ENIT / DGRE</title>",
    "<style>",
    "@page { size: A4; margin: 2.5cm; }",
    "body { font-family: 'Segoe UI', Calibri, Arial, sans-serif; line-height: 1.6; color: #1a202c; max-width: 850px; margin: 30px auto; padding: 20px; }",
    "h1, h2, h3, h4 { color: #0b3c5d; font-weight: 700; margin-top: 1.4em; }",
    "h1 { font-size: 22pt; border-bottom: 2px solid #0b3c5d; padding-bottom: 8px; text-align: center; }",
    "h2 { font-size: 16pt; border-bottom: 1px solid #cbd5e0; padding-bottom: 5px; color: #0b3c5d; }",
    "h3 { font-size: 13pt; color: #1d70b8; }",
    "h4 { font-size: 11pt; color: #2b6cb0; }",
    "table { width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 10pt; }",
    "th, td { border: 1px solid #cbd5e0; padding: 8px 10px; text-align: left; }",
    "th { background-color: #f7fafc; color: #2d3748; font-weight: 600; }",
    "tr:nth-child(even) { background-color: #f8fafc; }",
    "code { background-color: #f1f5f9; font-family: Consolas, monospace; padding: 2px 5px; border-radius: 4px; font-size: 9.5pt; color: #b91c1c; }",
    "pre { background-color: #f8fafc; padding: 12px; border: 1px solid #e2e8f0; border-radius: 6px; overflow-x: auto; font-family: Consolas, monospace; font-size: 9pt; }",
    "pre code { background: none; color: #1e293b; padding: 0; }",
    "blockquote { border-left: 4px solid #0b3c5d; padding-left: 15px; color: #4a5568; margin: 15px 0; font-style: italic; }",
    "hr { border: none; border-top: 1px solid #e2e8f0; margin: 30px 0; }",
    ".page-break { page-break-after: always; height: 1px; }",
    "</style>",
    "</head>",
    "<body>"
]

in_pre = False
in_table = False

for line in lines:
    if line.startswith("```"):
        if not in_pre:
            html_lines.append("<pre><code>")
            in_pre = True
        else:
            html_lines.append("</code></pre>")
            in_pre = False
        continue

    if in_pre:
        html_lines.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        continue

    if line.strip() == "\\newpage":
        html_lines.append("<div class='page-break'></div>")
        continue

    if line.startswith("|") and "|" in line[1:]:
        if not in_table:
            html_lines.append("<table>")
            in_table = True
            cells = [c.strip() for c in line.strip().split("|")[1:-1]]
            html_lines.append("<thead><tr>" + "".join(f"<th>{c}</th>" for c in cells) + "</tr></thead><tbody>")
            continue
        elif "---" in line:
            continue
        else:
            cells = [c.strip() for c in line.strip().split("|")[1:-1]]
            html_lines.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            continue
    else:
        if in_table:
            html_lines.append("</tbody></table>")
            in_table = False

    if line.startswith("# "):
        html_lines.append(f"<h1>{line[2:]}</h1>")
    elif line.startswith("## "):
        html_lines.append(f"<h2>{line[3:]}</h2>")
    elif line.startswith("### "):
        html_lines.append(f"<h3>{line[4:]}</h3>")
    elif line.startswith("#### "):
        html_lines.append(f"<h4>{line[5:]}</h4>")
    elif line.startswith("---"):
        html_lines.append("<hr>")
    elif line.strip() == "":
        continue
    else:
        l = line
        l = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", l)
        l = re.sub(r"\*(.*?)\*", r"<em>\1</em>", l)
        l = re.sub(r"`(.*?)`", r"<code>\1</code>", l)
        html_lines.append(f"<p>{l}</p>")

if in_table:
    html_lines.append("</tbody></table>")
if in_pre:
    html_lines.append("</code></pre>")

html_lines.append("</body></html>")

with open(html_path, "w", encoding="utf-8") as f:
    f.write("\n".join(html_lines))

print("Rapport HTML généré avec succès dans :", html_path)
