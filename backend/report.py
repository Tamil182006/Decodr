import os
import re
import sys
import lizard
import matplotlib.pyplot as plt
import tempfile
from datetime import datetime
from fpdf import FPDF
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from collections import defaultdict
from explainer import ALLOWED_EXTENSIONS, EXCLUDE_DIRS

EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", "venv", ".idea", ".vscode"}
OUTPUT_DIR = os.path.join(tempfile.gettempdir(), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def remove_unicode(text):
    return re.sub(r'[^\x00-\x7F]+', '', text)

def create_complexity_chart(functions, output_path):
    # Prepare data for chart
    complexities = [func.cyclomatic_complexity for func in functions]
    
    # Categorize complexity
    low = len([c for c in complexities if c <= 5])
    medium = len([c for c in complexities if 5 < c <= 10])
    high = len([c for c in complexities if 10 < c <= 20])
    very_high = len([c for c in complexities if c > 20])
    
    # Create bar chart
    categories = ['Low (1-5)', 'Medium (6-10)', 'High (11-20)', 'Very High (20+)']
    values = [low, medium, high, very_high]
    
    # Create the chart
    fig, ax = plt.subplots(figsize=(8, 6))
    bars = ax.bar(categories, values, color=['green', 'yellow', 'orange', 'red'])
    
    # Add value labels on bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                f'{int(height)}', ha='center', va='bottom')
    
    ax.set_ylabel('Number of Functions')
    ax.set_title('Cyclomatic Complexity Distribution')
    plt.tight_layout()
    
    # Save the chart
    chart_path = os.path.join(output_path, 'complexity_chart.png')
    plt.savefig(chart_path)
    plt.close()
    
    return chart_path

def create_file_type_chart(file_types, output_path):
    # Create pie chart for file types
    labels = list(file_types.keys())
    sizes = list(file_types.values())
    
    fig, ax = plt.subplots(figsize=(8, 6))
    ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
    ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    ax.set_title('File Type Distribution')
    
    # Save the chart
    chart_path = os.path.join(output_path, 'file_types_chart.png')
    plt.savefig(chart_path)
    plt.close()
    
    return chart_path

def run_lizard(path):
    results = []
    file_count = 0
    total_complexity = 0
    file_complexities = {}
    
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            if any(file.endswith(ext) for ext in [".js", ".py", ".java", ".cpp", ".c", ".ts", ".jsx"]):
                file_path = os.path.join(root, file)
                try:
                    file_analysis = lizard.analyze_file(file_path)
                    results.extend(file_analysis.function_list)
                    file_count += 1
                    file_complexity = sum(func.cyclomatic_complexity for func in file_analysis.function_list)
                    total_complexity += file_complexity
                    file_complexities[file] = file_complexity
                except Exception as e:
                    print(f"⚠️ Error analyzing {file_path}: {e}")
    
    return results, file_count, total_complexity, file_complexities

def generate_complexity_stats(functions):
    if not functions:
        return "No functions analyzed."
    
    # Calculate statistics
    complexities = [func.cyclomatic_complexity for func in functions]
    locs = [func.length for func in functions]
    nloc = [func.nloc for func in functions]
    
    stats = [
        f"<b>Total Functions:</b> {len(functions)}",
        f"<b>Average Complexity:</b> {sum(complexities)/len(complexities):.2f}",
        f"<b>Max Complexity:</b> {max(complexities)}",
        f"<b>Average LOC:</b> {sum(locs)/len(locs):.2f}",
        f"<b>Total LOC:</b> {sum(locs)}",
        f"<b>Maintainability Index:</b> {calculate_maintainability_index(complexities, locs, nloc):.2f}"
    ]
    
    # Identify complex functions (complexity > 10)
    complex_funcs = [func for func in functions if func.cyclomatic_complexity > 10]
    if complex_funcs:
        stats.append(f"<br/><b>⚠️ Complex Functions (CC > 10):</b> {len(complex_funcs)}")
        for func in complex_funcs[:5]:  # Show top 5 most complex
            stats.append(f"  - {func.name}: CC={func.cyclomatic_complexity}, LOC={func.length}, File: {os.path.basename(func.filename)}")
    
    # Identify long functions (LOC > 50)
    long_funcs = [func for func in functions if func.length > 50]
    if long_funcs:
        stats.append(f"<br/><b>⚠️ Long Functions (LOC > 50):</b> {len(long_funcs)}")
        for func in long_funcs[:3]:  # Show top 3 longest
            stats.append(f"  - {func.name}: LOC={func.length}, CC={func.cyclomatic_complexity}, File: {os.path.basename(func.filename)}")
    
    return "<br/>".join(stats)

def calculate_maintainability_index(complexities, locs, nloc):
    # Simplified maintainability index calculation
    if not complexities:
        return 100
    
    avg_complexity = sum(complexities) / len(complexities)
    avg_loc = sum(locs) / len(locs)
    
    # Heuristic formula (not the standard one but useful for comparison)
    mi = max(0, 100 - (avg_complexity * 2) - (avg_loc / 2))
    return min(100, mi)

def generate_report(project_path):
    print("📊 Running complexity analysis...")
    functions, file_count, total_complexity, file_complexities = run_lizard(project_path)
    complexity_stats = generate_complexity_stats(functions)
    
    # Create charts
    charts_dir = os.path.join(OUTPUT_DIR, "charts")
    os.makedirs(charts_dir, exist_ok=True)
    complexity_chart = create_complexity_chart(functions, charts_dir)
    
    # Get file type distribution
    file_types = get_file_type_distribution(project_path)
    file_type_chart = create_file_type_chart(file_types, charts_dir) if file_types else None
    
    summary_text = generate_project_summary(project_path, file_count, total_complexity, file_types)
    ai_suggestions = generate_ai_suggestions(functions)
    detailed_analysis = generate_detailed_analysis(functions, file_complexities)
    
    # Create PDF with ReportLab
    output_path = os.path.join(OUTPUT_DIR, "project_analysis_report.pdf")
    doc = SimpleDocTemplate(output_path, pagesize=letter)
    styles = getSampleStyleSheet()
    
    # Add custom styles
    styles.add(ParagraphStyle(
        name='Heading1Blue',
        parent=styles['Heading1'],
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=14
    ))
    
    styles.add(ParagraphStyle(
        name='Heading2Blue',
        parent=styles['Heading2'],
        textColor=colors.HexColor('#2C3E50'),
        spaceAfter=12
    ))
    
    story = []
    
    # Cover page
    story.append(Paragraph("CODE ANALYSIS REPORT", styles["Title"]))
    story.append(Spacer(1, 20))
    story.append(Paragraph(f"Project: {os.path.basename(project_path)}", styles["Heading2"]))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles["Normal"]))
    story.append(Paragraph(f"Generated by: Code Analysis Tool", styles["Italic"]))
    story.append(Spacer(1, 60))
    story.append(Paragraph("EXECUTIVE SUMMARY", styles["Heading1Blue"]))
    story.append(Spacer(1, 20))
    
    # Executive summary
    exec_summary = generate_executive_summary(file_count, total_complexity, functions, file_types)
    story.append(Paragraph(exec_summary, styles["Normal"]))
    story.append(Spacer(1, 30))
    
    # Add page break
    story.append(Spacer(1, 30))
    story.append(Paragraph("DETAILED ANALYSIS", styles["Heading1Blue"]))
    
    # Project info
    story.append(Paragraph("Project Overview", styles["Heading2Blue"]))
    story.append(Paragraph(summary_text, styles["Normal"]))
    story.append(Spacer(1, 20))
    
    # Add complexity chart
    if os.path.exists(complexity_chart):
        story.append(Paragraph("Complexity Distribution", styles["Heading2Blue"]))
        img = Image(complexity_chart, width=6*inch, height=4.5*inch)
        story.append(img)
        story.append(Spacer(1, 20))
    
    # Add file type chart if available
    if file_type_chart and os.path.exists(file_type_chart):
        story.append(Paragraph("File Type Distribution", styles["Heading2Blue"]))
        img = Image(file_type_chart, width=6*inch, height=4.5*inch)
        story.append(img)
        story.append(Spacer(1, 20))
    
    # Complexity Analysis
    story.append(Paragraph("Complexity Analysis", styles["Heading2Blue"]))
    story.append(Paragraph(complexity_stats, styles["Normal"]))
    story.append(Spacer(1, 20))
    
    # Detailed functions
    if functions:
        story.append(Paragraph("Top Complex Functions", styles["Heading2Blue"]))
        
        # Prepare table data
        table_data = [['Function', 'Complexity', 'LOC', 'File']]
        for func in sorted(functions, key=lambda x: x.cyclomatic_complexity, reverse=True)[:10]:
            table_data.append([
                func.name, 
                str(func.cyclomatic_complexity),
                str(func.length),
                os.path.basename(func.filename)
            ])
        
        # Create table
        table = Table(table_data, colWidths=[2*inch, 1*inch, 1*inch, 2*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2C3E50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#ECF0F1')),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(table)
        story.append(Spacer(1, 20))
    
    # Detailed analysis
    story.append(Paragraph("Detailed Analysis", styles["Heading2Blue"]))
    story.append(Paragraph(detailed_analysis, styles["Normal"]))
    story.append(Spacer(1, 20))
    
    # Suggestions
    story.append(Paragraph("Code Quality Recommendations", styles["Heading2Blue"]))
    story.append(Paragraph(ai_suggestions, styles["Normal"]))
    
    # Build PDF
    doc.build(story)
    print(f"✅ Enhanced report generated: {output_path}")
    
    return output_path

def get_file_type_distribution(project_path):
    file_types = defaultdict(int)
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                file_types[ext] += 1
    
    return dict(file_types)

def generate_executive_summary(file_count, total_complexity, functions, file_types):
    """Generate an executive summary with key metrics"""
    if not functions:
        return "No functions analyzed for executive summary."
    
    complexities = [func.cyclomatic_complexity for func in functions]
    locs = [func.length for func in functions]
    
    # Calculate quality score (0-100)
    avg_complexity = sum(complexities) / len(complexities)
    quality_score = max(0, 100 - (avg_complexity * 5))
    
    # Determine quality rating
    if quality_score >= 80:
        rating = "Excellent"
        color = "green"
    elif quality_score >= 60:
        rating = "Good"
        color = "blue"
    elif quality_score >= 40:
        rating = "Fair"
        color = "orange"
    else:
        rating = "Needs Improvement"
        color = "red"
    
    summary = [
        f"This report provides a comprehensive analysis of the codebase with {file_count} files ",
        f"and {len(functions)} functions. The overall code quality score is ",
        f"<b><font color={color}>{quality_score:.1f}/100 ({rating})</font></b>.",
        "<br/><br/>",
        f"<b>Key Metrics:</b>",
        f"• Average Cyclomatic Complexity: {avg_complexity:.2f}",
        f"• Total Lines of Code: {sum(locs)}",
        f"• File Types: {', '.join([f'{count} {ext}' for ext, count in file_types.items()])}",
        "<br/>",
        f"<b>Recommendation:</b> {get_overall_recommendation(quality_score, functions)}"
    ]
    
    return "".join(summary)

def get_overall_recommendation(quality_score, functions):
    if quality_score >= 80:
        return "Code quality is excellent. Maintain current standards with regular reviews."
    elif quality_score >= 60:
        return "Code quality is good. Focus on refactoring complex functions identified in this report."
    elif quality_score >= 40:
        return "Code quality needs attention. Prioritize refactoring of complex components and add tests."
    else:
        complex_funcs = len([f for f in functions if f.cyclomatic_complexity > 10])
        return f"Code quality needs significant improvement. Refactor {complex_funcs} complex functions and improve test coverage."

def generate_project_summary(project_path, file_count, total_complexity, file_types):
    """Generate a detailed project summary"""
    total_loc = 0
    file_details = defaultdict(list)
    
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                try:
                    with open(os.path.join(root, file), 'r', encoding='utf-8', errors='ignore') as f:
                        lines = len(f.readlines())
                        total_loc += lines
                        file_details[ext].append((file, lines))
                except:
                    pass
    
    summary = [
        f"<b>Project Name:</b> {os.path.basename(project_path)}",
        f"<b>Total Files Analyzed:</b> {file_count}",
        f"<b>Total Lines of Code:</b> {total_loc}",
        f"<b>Total Cyclomatic Complexity:</b> {total_complexity}",
        "<br/>",
        f"<b>File Type Breakdown:</b>"
    ]
    
    for ext, files in file_details.items():
        file_count = len(files)
        loc_sum = sum(loc for _, loc in files)
        summary.append(f"• {ext}: {file_count} files, {loc_sum} LOC")
    
    summary.extend([
        "<br/>",
        "<b>Analysis Scope:</b>",
        "This report analyzes JavaScript, Python, Java, C++, C, TypeScript, and JSX files.",
        "Excluded directories: node_modules, .git, __pycache__, venv, .idea, .vscode"
    ])
    
    return "<br/>".join(summary)

def generate_detailed_analysis(functions, file_complexities):
    """Generate detailed analysis with specific insights"""
    if not functions:
        return "No functions analyzed for detailed analysis."
    
    # Find most complex files
    complex_files = sorted(file_complexities.items(), key=lambda x: x[1], reverse=True)[:5]
    
    analysis = [
        "<b>Key Findings:</b>",
        f"• Codebase contains {len(functions)} functions with an average complexity of {sum(f.cyclomatic_complexity for f in functions)/len(functions):.2f}",
        f"• {len([f for f in functions if f.cyclomatic_complexity > 10])} functions exceed the recommended complexity threshold (CC > 10)",
        f"• {len([f for f in functions if f.length > 50])} functions are longer than recommended (LOC > 50)",
        "<br/>",
        "<b>Most Complex Files:</b>"
    ]
    
    for file, complexity in complex_files:
        analysis.append(f"• {file}: {complexity} total complexity")
    
    analysis.extend([
        "<br/>",
        "<b>Maintainability Assessment:</b>",
        f"The maintainability index of {calculate_maintainability_index([f.cyclomatic_complexity for f in functions], [f.length for f in functions], [f.nloc for f in functions]):.2f} indicates " + 
        ("excellent maintainability" if calculate_maintainability_index([f.cyclomatic_complexity for f in functions], [f.length for f in functions], [f.nloc for f in functions]) > 80 
         else "good maintainability" if calculate_maintainability_index([f.cyclomatic_complexity for f in functions], [f.length for f in functions], [f.nloc for f in functions]) > 60 
         else "moderate maintainability" if calculate_maintainability_index([f.cyclomatic_complexity for f in functions], [f.length for f in functions], [f.nloc for f in functions]) > 40 
         else "poor maintainability")
    ])
    
    return "<br/>".join(analysis)

def generate_ai_suggestions(functions):
    """Generate detailed suggestions based on complexity analysis"""
    if not functions:
        return "No functions analyzed for suggestions."
    
    complex_funcs = [f for f in functions if f.cyclomatic_complexity > 10]
    long_funcs = [f for f in functions if f.length > 50]
    very_complex_funcs = [f for f in functions if f.cyclomatic_complexity > 20]
    
    suggestions = ["<b>Priority Recommendations:</b>"]
    
    if very_complex_funcs:
        suggestions.append(f"• <font color='red'>CRITICAL</font>: Refactor {len(very_complex_funcs)} extremely complex functions (CC > 20):")
        for func in very_complex_funcs[:3]:
            suggestions.append(f"  - {func.name} (CC: {func.cyclomatic_complexity}, LOC: {func.length}) in {os.path.basename(func.filename)}")
    
    if complex_funcs:
        suggestions.append(f"• <font color='orange'>HIGH</font>: Address {len(complex_funcs)} complex functions (CC > 10):")
        suggestions.append("  - Break down into smaller functions with single responsibilities")
        suggestions.append("  - Consider using strategy pattern or state pattern for complex conditional logic")
    
    if long_funcs:
        suggestions.append(f"• <font color='orange'>HIGH</font>: Refactor {len(long_funcs)} long functions (LOC > 50):")
        suggestions.append("  - Extract helper functions for discrete operations")
        suggestions.append("  - Consider if function is violating the Single Responsibility Principle")
    
    suggestions.extend([
        "<br/>",
        "<b>General Best Practices:</b>",
        "• Add comments to complex algorithms for better maintainability",
        "• Consider adding unit tests for critical functions, especially those with high complexity",
        "• Implement code review processes to catch complexity issues early",
        "• Use static analysis tools in your CI/CD pipeline",
        "• Consider using guard clauses and early returns to reduce nesting",
        "• Extract complex conditions into well-named helper functions or variables"
    ])
    
    # Add technology-specific suggestions
    suggestions.extend([
        "<br/>",
        "<b>Technology-Specific Suggestions:</b>",
        "• For React components: Consider splitting large components into smaller presentational and container components",
        "• For JavaScript: Use modern ES6+ features like arrow functions, destructuring, and async/await to simplify code",
        "• For Python: Use list comprehensions and built-in functions where appropriate to reduce complexity",
        "• For Java/C++: Consider using design patterns to manage complexity in large codebases"
    ])
    
    return "<br/>".join(suggestions)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python report.py <project_path>")
        sys.exit(1)
    generate_report(sys.argv[1])