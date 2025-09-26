#!/usr/bin/env python3
"""
Advanced Document Conversion Tool - Convert .docx files to .pdf
Uses python-docx to extract content and reportlab to generate PDF
"""

import sys
import os
from pathlib import Path
from docx import Document
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors

def extract_docx_content(docx_path):
    """Extract text content from a DOCX file"""
    try:
        doc = Document(docx_path)
        content = []
        
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                content.append(paragraph.text)
        
        return content
    except Exception as e:
        print(f"Error reading DOCX file: {e}")
        return None

def create_pdf_from_content(content, output_path):
    """Create a PDF from extracted content using reportlab"""
    try:
        # Create the PDF document
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )
        
        # Define styles
        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        body_style = ParagraphStyle(
            'CustomBody',
            parent=styles['Normal'],
            fontSize=10,
            spaceAfter=12,
            leading=14
        )
        
        # Build the story (content for PDF)
        story = []
        
        # Add title if first paragraph looks like a title
        if content and len(content[0]) < 100:
            story.append(Paragraph(content[0], title_style))
            content = content[1:]  # Remove title from body content
            story.append(Spacer(1, 20))
        
        # Add body content
        for paragraph_text in content:
            if paragraph_text.strip():
                # Clean and format the text
                clean_text = paragraph_text.replace('\r', '').replace('\n', ' ')
                story.append(Paragraph(clean_text, body_style))
                story.append(Spacer(1, 6))
        
        # Build the PDF
        doc.build(story)
        return True
        
    except Exception as e:
        print(f"Error creating PDF: {e}")
        return False

def convert_docx_to_pdf(input_path, output_path=None):
    """
    Convert a .docx file to .pdf using python-docx and reportlab
    
    Args:
        input_path (str): Path to the input .docx file
        output_path (str): Path for the output PDF
    
    Returns:
        bool: True if conversion successful, False otherwise
    """
    input_file = Path(input_path)
    
    if not input_file.exists():
        print(f"Error: Input file does not exist: {input_path}")
        return False
        
    if not input_file.suffix.lower() == '.docx':
        print(f"Error: Input file is not a .docx file: {input_path}")
        return False
    
    # Set output path
    if output_path is None:
        output_path = input_file.parent / (input_file.stem + '.pdf')
    else:
        output_path = Path(output_path)
    
    try:
        print(f"Converting: {input_file.name} → {output_path.name}")
        
        # Extract content from DOCX
        content = extract_docx_content(str(input_file))
        if content is None:
            return False
        
        if not content:
            print(f"Warning: No text content found in {input_file.name}")
            # Create empty PDF
            content = ["Document appears to be empty or contains no extractable text."]
        
        # Create PDF from content
        success = create_pdf_from_content(content, output_path)
        
        # Verify the PDF was created
        if success and output_path.exists():
            file_size = output_path.stat().st_size
            print(f"✅ Successfully converted: {output_path.name} ({file_size:,} bytes)")
            return True
        else:
            print(f"❌ Failed to create PDF: {output_path.name}")
            return False
            
    except Exception as e:
        print(f"❌ Conversion failed for {input_file.name}: {str(e)}")
        return False

def main():
    """Convert all .docx files in the specified directory to PDF"""
    
    docs_dir = Path(os.getenv("DOCS_DIRECTORY", "./docs"))
    
    if not docs_dir.exists():
        print(f"Error: Directory does not exist: {docs_dir}")
        sys.exit(1)
    
    # Find all .docx files
    docx_files = list(docs_dir.glob("*.docx"))
    
    if not docx_files:
        print("No .docx files found in the directory")
        sys.exit(0)
    
    print(f"Found {len(docx_files)} .docx file(s) to convert")
    print("-" * 60)
    
    successful_conversions = 0
    failed_conversions = 0
    
    # Convert each file
    for docx_file in docx_files:
        if convert_docx_to_pdf(str(docx_file)):
            successful_conversions += 1
        else:
            failed_conversions += 1
        print()  # Add blank line between conversions
    
    # Summary
    print("-" * 60)
    print(f"Conversion Summary:")
    print(f"✅ Successful: {successful_conversions}")
    print(f"❌ Failed: {failed_conversions}")
    print(f"📁 Output directory: {docs_dir}")
    
    if failed_conversions > 0:
        print("⚠️  Some conversions failed. Check error messages above.")
        sys.exit(1)
    else:
        print("🎉 All conversions completed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()