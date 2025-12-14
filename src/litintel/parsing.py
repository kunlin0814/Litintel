from typing import List, Dict, Any
import xml.etree.ElementTree as ET
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

    return {
        "PMID": str(pmid),
        "DOI": str(doi) if doi else "",
        "Title": str(title) if title else "",
        "Abstract": str(abstract),
        "Authors": str(authors_str),
        "Journal": str(journal_title) if journal_title else "",
        "Year": str(year) if year else ""
    }
