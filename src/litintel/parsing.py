from typing import List, Dict, Any, Tuple, Set
import xml.etree.ElementTree as ET
import re
import logging

logger = logging.getLogger(__name__)

def parse_pubmed_xml_stream(xml_data: str) -> List[Dict[str, Any]]:
    """Parses XML string using xml.etree.ElementTree"""
    if not xml_data:
        return []

    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as e:
        logger.error(f"XML Parse Error: {e}")
        return []
        
    parsed_items = []
    
    # EFetch returns PubmedArticleSet -> PubmedArticle
    for article in root.findall(".//PubmedArticle"):
        parsed_items.append(normalize_record(article))
        
    return parsed_items

def normalize_record(article_element: ET.Element) -> Dict[str, Any]:
    # Extract data from ElementTree Element
    
    medline = article_element.find("MedlineCitation")
    if medline is None:
        return {}
        
    article = medline.find("Article")
    if article is None:
        return {}
    
    # Title
    title_el = article.find("ArticleTitle")
    title = title_el.text if title_el is not None else ""
    
    # Abstract
    abstract_text = []
    abs_el = article.find("Abstract")
    if abs_el is not None:
        for t in abs_el.findall("AbstractText"):
            if t.text:
                abstract_text.append(t.text)
    abstract = " ".join(abstract_text)
    
    # Authors
    authors = []
    auth_list = article.find("AuthorList")
    if auth_list is not None:
        for au in auth_list.findall("Author"):
            last = au.find("LastName")
            initials = au.find("Initials")
            if last is not None:
                l_text = last.text or ""
                i_text = initials.text or "" if initials is not None else ""
                authors.append(f"{l_text} {i_text}")
    authors_str = ", ".join(authors)
    
    # Journal/Year
    journal = article.find("Journal")
    journal_title = ""
    year = ""
    
    if journal is not None:
        j_title_el = journal.find("Title")
        if j_title_el is not None:
            journal_title = j_title_el.text
            
        issue = journal.find("JournalIssue")
        if issue is not None:
            pub_date = issue.find("PubDate")
            if pub_date is not None:
                y = pub_date.find("Year")
                if y is not None:
                    year = y.text
                else:
                    med_date = pub_date.find("MedlineDate")
                    if med_date is not None and med_date.text:
                        year = med_date.text.split(" ")[0]

    # IDs
    pmid_el = medline.find("PMID")
    pmid = pmid_el.text if pmid_el is not None else ""
    
    doi = ""
    pubmed_data = article_element.find("PubmedData")
    if pubmed_data is not None:
        id_list = pubmed_data.find("ArticleIdList")
        if id_list is not None:
            for aid in id_list.findall("ArticleId"):
                if aid.get("IdType") == "doi":
                    doi = aid.text

    # Extract GEO/SRA/MeSH metadata
    geo_list, sra_list = extract_geo_sra_from_pubmed_xml(article_element)
    mesh_headings, mesh_terms, mesh_major = extract_mesh_from_pubmed_xml(article_element)

    return {
        "PMID": str(pmid),
        "DOI": str(doi) if doi else "",
        "Title": str(title) if title else "",
        "Abstract": str(abstract),
        "Authors": str(authors_str),
        "Journal": str(journal_title) if journal_title else "",
        "Year": str(year) if year else "",
        "GEO_Candidates": geo_list,  # From PubMed XML (fallback)
        "SRA_Candidates": sra_list,
        "MeSH_Headings": mesh_headings,
        "MeSH_Terms": mesh_terms,
        "MeSH_Major": mesh_major
    }


def extract_geo_sra_from_pubmed_xml(article_element: ET.Element) -> Tuple[str, str]:
    """
    Extract GEO and SRA accessions from PubMed article XML.
    
    Searches both DataBankList (structured metadata) and ReferenceList (citations)
    to capture data accessions. Many newer papers cite data repositories as
    references rather than using structured metadata.
    
    Args:
        article_element: PubmedArticle XML element
        
    Returns:
        Tuple of (geo_list, sra_project) as comma-separated strings
    """
    geo_accessions = set()
    sra_accessions = set()
    
    # Method 1: DataBankList (structured metadata)
    data_bank_list_elem = article_element.find(".//DataBankList")
    if data_bank_list_elem is not None:
        for databank in data_bank_list_elem.findall(".//DataBank"):
            db_name_elem = databank.find("DataBankName")
            db_name = db_name_elem.text.strip() if db_name_elem is not None and db_name_elem.text else ""
            acc_list_elem = databank.find("AccessionNumberList")
            if acc_list_elem is not None:
                accs = [acc.text.strip() for acc in acc_list_elem.findall("AccessionNumber") if acc.text]
                if db_name.upper() == "GEO":
                    geo_accessions.update(accs)
                elif db_name.upper() == "SRA":
                    sra_accessions.update(accs)
    
    # Method 2: ReferenceList (fallback for papers that cite data as references)
    # ReferenceList is under PubmedData, so we parse from the serialized article
    article_str = ET.tostring(article_element, encoding='unicode')
    if '<ReferenceList>' in article_str:
        temp_root = ET.fromstring(f'<temp>{article_str}</temp>')
        ref_list_elem = temp_root.find('.//ReferenceList')
        
        if ref_list_elem is not None:
            for ref in ref_list_elem.findall('.//Reference'):
                citation_elem = ref.find('Citation')
                if citation_elem is not None:
                    # Citation may have child elements like <i>, so use itertext()
                    citation_text = ''.join(citation_elem.itertext())
                    # Extract GEO accessions (GSE followed by digits)
                    geo_matches = re.findall(r'GSE\d+', citation_text)
                    geo_accessions.update(geo_matches)
                    # Extract SRA/BioProject accessions
                    sra_matches = re.findall(r'(?:PRJNA|SRP|SRR|SRX|SRS)\d+', citation_text)
                    sra_accessions.update(sra_matches)
    
    geo_list = ", ".join(sorted(geo_accessions)) if geo_accessions else ""
    sra_project = ", ".join(sorted(sra_accessions)) if sra_accessions else ""
    
    return geo_list, sra_project


def extract_mesh_from_pubmed_xml(article_element: ET.Element) -> Tuple[str, str, str]:
    """
    Extract MeSH terms and headings from PubMed article XML.
    
    Args:
        article_element: PubmedArticle XML element
        
    Returns:
        Tuple of (mesh_heading_list, mesh_terms, major_mesh) as semicolon-separated strings
    """
    mesh_terms_set: Set[str] = set()
    major_mesh_set: Set[str] = set()
    mesh_heading_entries = []
    
    for mh in article_element.findall(".//MeshHeading"):
        desc = mh.find("DescriptorName")
        if desc is None:
            continue
        desc_text = desc.text
        major_topic_yn = desc.attrib.get("MajorTopicYN", "N")
        
        qualifiers = []
        for q in mh.findall("QualifierName"):
            if q.text:
                qualifiers.append(q.text)
                if q.attrib.get("MajorTopicYN", "N") == "Y":
                    major_topic_yn = "Y"
        
        if qualifiers:
            entry = f"{desc_text} ({', '.join(qualifiers)})"
        else:
            entry = desc_text
        mesh_heading_entries.append(entry)
        mesh_terms_set.add(desc_text)
        if major_topic_yn == "Y":
            major_mesh_set.add(desc_text)
    
    mesh_heading_list = "; ".join(mesh_heading_entries) if mesh_heading_entries else ""
    mesh_terms = "; ".join(sorted(mesh_terms_set)) if mesh_terms_set else ""
    major_mesh = "; ".join(sorted(major_mesh_set)) if major_mesh_set else ""
    
    return mesh_heading_list, mesh_terms, major_mesh


def extract_pmc_sections(pmc_xml: str) -> Tuple[str, str, str]:
    """
    Extract relevant sections from PMC full-text XML plus GEO/SRA accessions.
    
    Parses the PMC XML and extracts:
    - Text sections: Abstract, Methods, Results, Data/Code Availability
    - GEO/SRA accessions: Found via regex in full-text (primary source)
    
    Args:
        pmc_xml: Raw PMC XML string from efetch
        
    Returns:
        Tuple of (sections_text, geo_accessions, sra_accessions)
        - sections_text: Concatenated text from extracted sections
        - geo_accessions: Comma-separated GSE IDs
        - sra_accessions: Comma-separated PRJNA/SRP/SRR IDs
    """
    try:
        root = ET.fromstring(pmc_xml)
        
        sections = []
        all_text = []  # Collect all text for accession extraction
        
        # Abstract - usually in <abstract>
        abstract = root.find(".//abstract")
        if abstract is not None:
            abstract_text = " ".join(abstract.itertext()).strip()
            if abstract_text:
                sections.append(f"ABSTRACT:\n{abstract_text}")
                all_text.append(abstract_text)
        
        # Methods and Results - search in <body> sections
        body = root.find(".//body")
        if body is not None:
            for sec in body.findall(".//sec"):
                title_elem = sec.find("title")
                if title_elem is None:
                    continue
                    
                title = (title_elem.text or "").strip().lower()
                
                # Methods section
                if any(keyword in title for keyword in ["method", "material", "experimental"]):
                    methods_text = " ".join(sec.itertext()).strip()
                    sections.append(f"METHODS:\n{methods_text}")
                    all_text.append(methods_text)
                
                # Results section
                elif any(keyword in title for keyword in ["result", "finding"]):
                    results_text = " ".join(sec.itertext()).strip()
                    sections.append(f"RESULTS:\n{results_text}")
                    all_text.append(results_text)
        
        # Data Availability - in <back> matter
        back = root.find(".//back")
        if back is not None:
            for sec in back.findall(".//sec"):
                title_elem = sec.find("title")
                if title_elem is None:
                    continue
                    
                title = (title_elem.text or "").strip().lower()
                
                # Data Availability
                if "data availability" in title or "data access" in title:
                    data_text = " ".join(sec.itertext()).strip()
                    sections.append(f"DATA AVAILABILITY:\n{data_text}")
                    all_text.append(data_text)
                
                # Code Availability
                if "code availability" in title or "software availability" in title:
                    code_text = " ".join(sec.itertext()).strip()
                    sections.append(f"CODE AVAILABILITY:\n{code_text}")
                    all_text.append(code_text)
        
        # Extract GEO/SRA accessions from all collected text
        combined_text = " ".join(all_text)
        
        geo_accessions = set(re.findall(r'GSE\d+', combined_text))
        sra_accessions = set(re.findall(r'(?:PRJNA|SRP|SRR|SRX|SRS)\d+', combined_text))
        
        sections_text = "\n\n".join(sections) if sections else ""
        geo_list = ", ".join(sorted(geo_accessions)) if geo_accessions else ""
        sra_list = ", ".join(sorted(sra_accessions)) if sra_accessions else ""
        
        return sections_text, geo_list, sra_list
        
    except Exception as e:
        logger.error(f"Error parsing PMC XML: {e}")
        return "", "", ""

