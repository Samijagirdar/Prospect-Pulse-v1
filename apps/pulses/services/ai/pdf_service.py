from pypdf import PdfReader

def extract_text_from_pdf(pdf_file_field):
    try:
        reader = PdfReader(pdf_file_field)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text)
        return "\n".join(pages_text)
    except Exception as e:
        print(f"Error parsing PDF file: {e}")
        return ""
