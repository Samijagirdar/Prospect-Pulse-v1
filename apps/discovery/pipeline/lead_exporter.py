"""
Lead Exporter Utility for Prospect Pulse v1.
Generates beautifully formatted Excel (.xlsx), PDF (.pdf), and Word Document (.docx)
exports of decision-maker leads with full contact intelligence:
Lead Name, Position, Account, Email, Phone, and LinkedIn Profile.
"""

import io
from datetime import datetime


def export_leads_excel(leads):
    """
    Exports leads as a formatted Microsoft Excel (.xlsx) workbook styled with
    Agentyne's official brand theme: Crimson Red (#D40000) headers, obsidian accents,
    subtle alternating zebra rows, and active Excel filters.
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Agentyne Leads"
    ws.views.sheetView[0].showGridLines = True

    headers = [
        "Lead Name", "Position / Designation", "Account / Company", 
        "Email Address", "Phone Number", "LinkedIn Profile"
    ]
    ws.append(headers)

    # Agentyne Crimson Red Header (#D40000) with crisp white text
    header_fill = PatternFill(start_color="D40000", end_color="D40000", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="left", vertical="center", wrap_text=True)

    header_border_side = Side(border_style="thin", color="B80000")
    header_bottom_side = Side(border_style="medium", color="7F0000")
    header_border = Border(
        left=header_border_side,
        right=header_border_side,
        top=header_border_side,
        bottom=header_bottom_side
    )

    ws.row_dimensions[1].height = 30
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align
        cell.border = header_border

    # Agentyne Surface2 (#F5F5F5) and Pure White (#FFFFFF) zebra striping
    even_fill = PatternFill(start_color="F5F5F5", end_color="F5F5F5", fill_type="solid")
    odd_fill = PatternFill(start_color="FFFFFF", end_color="FFFFFF", fill_type="solid")
    
    thin_border_side = Side(border_style="thin", color="E5E7EB")
    thin_border = Border(
        left=thin_border_side,
        right=thin_border_side,
        top=thin_border_side,
        bottom=thin_border_side
    )

    data_font = Font(name="Segoe UI", size=10, color="222222")
    name_font = Font(name="Segoe UI", size=10, bold=True, color="0A0A0A")
    link_font = Font(name="Segoe UI", size=10, color="0A66C2", underline="single")
    left_align = Alignment(horizontal="left", vertical="center")

    for row_idx, lead in enumerate(leads, start=2):
        name = getattr(lead, 'name', None) or "—"
        position = getattr(lead, 'designation', None) or "—"
        account = getattr(lead, 'organization_name', None) or "—"
        email = getattr(lead, 'email', None) or "—"
        phone = getattr(lead, 'phone', None) or "—"
        linkedin = getattr(lead, 'linkedin_url', None) or "—"

        ws.append([name, position, account, email, phone, linkedin])
        ws.row_dimensions[row_idx].height = 24
        current_fill = even_fill if row_idx % 2 == 0 else odd_fill

        for col_idx in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col_idx)
            cell.fill = current_fill
            cell.border = thin_border
            if col_idx == 1:
                cell.font = name_font
                cell.alignment = left_align
            elif col_idx == 6 and linkedin != "—":
                cell.font = link_font
                cell.alignment = left_align
                if str(linkedin).startswith("http"):
                    cell.hyperlink = linkedin
            else:
                cell.alignment = left_align
                cell.font = data_font

    # Enable native Excel AutoFilter across all lead columns
    end_col_letter = get_column_letter(len(headers))
    total_rows = max(len(leads) + 1, 2)
    ws.auto_filter.ref = f"A1:{end_col_letter}{total_rows}"

    # Auto-fit column widths with safety minimum
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col_letter].width = max(max_len + 5, 16)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


def export_leads_pdf(leads):
    """
    Exports leads as a modern, publication-grade PDF styled with Agentyne's executive brand:
    Obsidian dark header bar with a bold Crimson Red (#D40000) accent divider, crisp typography,
    subtle alternating zebra rows, and linked LinkedIn profiles.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import landscape, letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buf = io.BytesIO()
    # Usable width: 792 pt - (24 * 2) = 744 pt
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(letter),
        leftMargin=24,
        rightMargin=24,
        topMargin=24,
        bottomMargin=24
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0A0A0A')
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#6E6E6E')
    )
    th_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white
    )
    td_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#222222')
    )
    td_name_style = ParagraphStyle(
        'TableCellName',
        parent=td_style,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#0A0A0A')
    )
    td_link_style = ParagraphStyle(
        'TableCellLink',
        parent=td_style,
        textColor=colors.HexColor('#0A66C2'),
        fontSize=8,
        leading=10
    )
    footer_style = ParagraphStyle(
        'DocFooter',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#94A3B8')
    )

    elements = []

    # Title & Metadata Banner styled with Agentyne brand tokens
    current_time = datetime.now().strftime("%b %d, %Y • %I:%M %p")
    elements.append(Paragraph(
        '<font color="#D40000"><b>AGENTYNE</b></font> <font color="#94A3B8">|</font> <font color="#0A0A0A"><b>PROSPECT PULSE</b></font> <font color="#6E6E6E">— Verified Leads Intelligence</font>',
        title_style
    ))
    elements.append(Spacer(1, 4))
    elements.append(Paragraph(
        f"Verified B2B Decision-Maker Intelligence &bull; <b>{len(leads)}</b> Leads Exported &bull; Generated on {current_time}",
        subtitle_style
    ))
    elements.append(Spacer(1, 8))
    # Agentyne Crimson Red (#D40000) divider bar
    elements.append(HRFlowable(width="100%", thickness=2.5, color=colors.HexColor('#D40000'), spaceAfter=14))

    # Col Widths sum = 744 pt across 6 columns
    col_widths = [120, 130, 120, 144, 90, 140]

    headers = [
        Paragraph("LEAD NAME", th_style),
        Paragraph("POSITION", th_style),
        Paragraph("ACCOUNT", th_style),
        Paragraph("EMAIL", th_style),
        Paragraph("PHONE", th_style),
        Paragraph("LINKEDIN PROFILE", th_style),
    ]

    table_data = [headers]

    for lead in leads:
        name = getattr(lead, 'name', None) or "—"
        position = getattr(lead, 'designation', None) or "—"
        account = getattr(lead, 'organization_name', None) or "—"
        email = getattr(lead, 'email', None) or "—"
        phone = getattr(lead, 'phone', None) or "—"
        linkedin = getattr(lead, 'linkedin_url', None) or "—"

        if linkedin and str(linkedin).startswith("http"):
            linkedin_cell = Paragraph(f'<a href="{linkedin}"><u>{linkedin}</u></a>', td_link_style)
        else:
            linkedin_cell = Paragraph(linkedin, td_style)

        table_data.append([
            Paragraph(name, td_name_style),
            Paragraph(position, td_style),
            Paragraph(account, td_style),
            Paragraph(email, td_style),
            Paragraph(phone, td_style),
            linkedin_cell,
        ])

    table = Table(table_data, colWidths=col_widths, repeatRows=1)

    t_style = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0A0A0A')),
        ('LINEBELOW', (0, 0), (-1, 0), 2.0, colors.HexColor('#D40000')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#0A0A0A')),
    ]

    for r in range(1, len(table_data)):
        if r % 2 == 0:
            t_style.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor('#F5F5F5')))
        else:
            t_style.append(('BACKGROUND', (0, r), (-1, r), colors.white))

    table.setStyle(TableStyle(t_style))
    elements.append(table)

    # Footer note
    elements.append(Spacer(1, 14))
    elements.append(Paragraph(
        "Generated by <b>Agentyne Prospect Pulse</b> &bull; Confidential B2B Growth & Lead Intelligence",
        footer_style
    ))

    doc.build(elements)
    buf.seek(0)
    return buf.getvalue()


def export_leads_docx(leads):
    """
    Exports leads as a styled Microsoft Word Document (.docx) styled with Agentyne's executive brand:
    Agentyne Crimson Red (#D40000) accents, obsidian headers, clean table layout, and linked LinkedIn profiles.
    """
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.section import WD_ORIENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    doc = docx.Document()

    # Landscape Letter with 0.5 in margins (usable width = 10.0 in)
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Inches(11.0)
    section.page_height = Inches(8.5)
    section.top_margin = Inches(0.5)
    section.bottom_margin = Inches(0.5)
    section.left_margin = Inches(0.5)
    section.right_margin = Inches(0.5)

    # Brand Title: AGENTYNE in Red (#D40000) | PROSPECT PULSE in Dark (#0A0A0A)
    title_p = doc.add_paragraph()
    title_p.paragraph_format.space_after = Pt(2)
    
    run_brand = title_p.add_run("AGENTYNE ")
    run_brand.font.name = "Calibri"
    run_brand.font.size = Pt(16)
    run_brand.font.bold = True
    run_brand.font.color.rgb = RGBColor(212, 0, 0)

    run_title = title_p.add_run("| PROSPECT PULSE — Verified Leads Intelligence")
    run_title.font.name = "Calibri"
    run_title.font.size = Pt(16)
    run_title.font.bold = True
    run_title.font.color.rgb = RGBColor(10, 10, 10)

    # Subtitle with Agentyne Red bottom accent line
    current_time = datetime.now().strftime("%b %d, %Y • %I:%M %p")
    sub_p = doc.add_paragraph()
    sub_p.paragraph_format.space_after = Pt(14)
    run_sub = sub_p.add_run(f"Verified B2B Decision-Maker Intelligence • {len(leads)} Leads Exported • Generated on {current_time}")
    run_sub.font.name = "Calibri"
    run_sub.font.size = Pt(9.5)
    run_sub.font.italic = True
    run_sub.font.color.rgb = RGBColor(110, 110, 110)

    # Add Agentyne red horizontal border beneath subtitle
    pPr = sub_p._p.get_or_add_pPr()
    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="18" w:space="8" w:color="D40000"/></w:pBdr>')
    pPr.append(pBdr)

    headers = [
        "Lead Name", "Position", "Account", "Email", 
        "Phone", "LinkedIn Profile"
    ]
    col_widths = [
        Inches(1.6), Inches(1.7), Inches(1.6), Inches(1.9),
        Inches(1.3), Inches(1.9)
    ]

    table = doc.add_table(rows=len(leads) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # Header Row: Obsidian (#0A0A0A) background with Crimson Red (#D40000) bottom border
    hdr_cells = table.rows[0].cells
    for i, h_text in enumerate(headers):
        cell = hdr_cells[i]
        cell.width = col_widths[i]
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="0A0A0A"/>')
        cell._tc.get_or_add_tcPr().append(shading)

        hdr_borders = parse_xml(
            f'<w:tcBorders {nsdecls("w")}>'
            f'<w:bottom w:val="single" w:sz="18" w:space="0" w:color="D40000"/>'
            f'<w:top w:val="none"/>'
            f'<w:left w:val="none"/>'
            f'<w:right w:val="none"/>'
            f'</w:tcBorders>'
        )
        cell._tc.get_or_add_tcPr().append(hdr_borders)

        tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="120" w:type="dxa"/><w:bottom w:w="120" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>')
        cell._tc.get_or_add_tcPr().append(tcMar)

        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.space_before = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        run = p.add_run(h_text)
        run.font.name = "Calibri"
        run.font.size = Pt(9.5)
        run.font.bold = True
        run.font.color.rgb = RGBColor(255, 255, 255)

    # Data Rows
    for r_idx, lead in enumerate(leads, start=1):
        row_cells = table.rows[r_idx].cells
        name = getattr(lead, 'name', None) or "—"
        position = getattr(lead, 'designation', None) or "—"
        account = getattr(lead, 'organization_name', None) or "—"
        email = getattr(lead, 'email', None) or "—"
        phone = getattr(lead, 'phone', None) or "—"
        linkedin = getattr(lead, 'linkedin_url', None) or "—"

        values = [name, position, account, email, phone, linkedin]
        bg_hex = "F5F5F5" if r_idx % 2 == 0 else "FFFFFF"

        for c_idx, val in enumerate(values):
            cell = row_cells[c_idx]
            cell.width = col_widths[c_idx]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

            if bg_hex != "FFFFFF":
                shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg_hex}"/>')
                cell._tc.get_or_add_tcPr().append(shd)

            borders = parse_xml(
                f'<w:tcBorders {nsdecls("w")}>'
                f'<w:top w:val="single" w:sz="4" w:space="0" w:color="E5E7EB"/>'
                f'<w:bottom w:val="single" w:sz="4" w:space="0" w:color="E5E7EB"/>'
                f'<w:left w:val="single" w:sz="4" w:space="0" w:color="E5E7EB"/>'
                f'<w:right w:val="single" w:sz="4" w:space="0" w:color="E5E7EB"/>'
                f'</w:tcBorders>'
            )
            cell._tc.get_or_add_tcPr().append(borders)

            tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="80" w:type="dxa"/><w:bottom w:w="80" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tcMar>')
            cell._tc.get_or_add_tcPr().append(tcMar)

            p = cell.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.space_before = Pt(0)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT

            run = p.add_run(val)
            run.font.name = "Calibri"
            run.font.size = Pt(8.5)
            if c_idx == 0:
                run.font.bold = True
                run.font.color.rgb = RGBColor(10, 10, 10)
            elif c_idx == 5 and val != "—":
                run.font.color.rgb = RGBColor(10, 102, 194)
                run.font.underline = True
            else:
                run.font.color.rgb = RGBColor(34, 34, 34)

    # Footer note
    footer_p = doc.add_paragraph()
    footer_p.paragraph_format.space_before = Pt(14)
    run_footer = footer_p.add_run("Generated by Agentyne Prospect Pulse • Confidential B2B Growth & Lead Intelligence")
    run_footer.font.name = "Calibri"
    run_footer.font.size = Pt(8)
    run_footer.font.italic = True
    run_footer.font.color.rgb = RGBColor(148, 163, 184)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()

