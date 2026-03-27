
import sys
import os
import logging

# Load .env file
from dotenv import load_dotenv
load_dotenv()

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

from litintel.config import load_config_from_yaml
from litintel.pubmed.client import fetch_details, fetch_pmc_fulltext
from litintel.parsing import parse_pubmed_xml_stream, extract_pmc_sections
from litintel.enrich.prompt_templates import get_system_prompt, _TIER1_PCA_METHODS_INSTRUCTION

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_twopass_inputs(pmid):
    # 1. Load Config
    config_app = load_config_from_yaml("configs/tier1_pca.yaml")
    
    # 2. Fetch Data
    logger.info(f"Fetching {pmid}...")
    xml_str = fetch_details([pmid])
    records = parse_pubmed_xml_stream(xml_str)
    if not records:
        logger.error("No records found")
        return
    record = records[0]
    
    # 3. Get Full Text
    full_text = ""
    methods = ""
    results = ""
    pmc_id = record.get("PMCID")
    abstract = record.get("Abstract", "")
    authors = record.get("Authors", "")
    title = record.get("Title", "")
    
    if pmc_id:
        logger.info(f"Fetching PMC {pmc_id}...")
        pmc_map = fetch_pmc_fulltext([pmc_id])
        if pmc_id in pmc_map:
            pmc_xml = pmc_map[pmc_id]
            ft_parts = extract_pmc_sections(pmc_xml)
            if isinstance(ft_parts, tuple):
                full_text = ft_parts[0]
                methods = ft_parts[3] if len(ft_parts) > 3 else ""
                results = ft_parts[4] if len(ft_parts) > 4 else ""
            elif isinstance(ft_parts, dict):
                full_text = ft_parts.get("body", "")
                methods = ft_parts.get("methods", "")
                results = ft_parts.get("results", "")
            logger.info(f"Got Full Text: {len(full_text)} chars")
    
    # =========================================================================
    # PASS 1: SCORING PROMPT
    # =========================================================================
    pass1_system = get_system_prompt("tier1_pca_scoring")
    
    pass1_user = f"PMID: {pmid}\nAuthors: {authors}\nGroupFallbackCandidate: \n"
    pass1_user += f"\nTEXT_START\n{full_text if full_text else abstract}\nTEXT_END\n"
    
    # Save Pass 1
    with open(f"ai_input_pass1_{pmid}.txt", "w") as f:
        f.write("=" * 80 + "\n")
        f.write("PASS 1: SCORING & METADATA\n")
        f.write("=" * 80 + "\n\n")
        f.write("--- SYSTEM PROMPT ---\n")
        f.write(pass1_system)
        f.write("\n\n--- USER PROMPT ---\n")
        f.write(pass1_user)
    
    logger.info(f"Saved: ai_input_pass1_{pmid}.txt ({len(pass1_system) + len(pass1_user)} chars)")
    
    # =========================================================================
    # PASS 2: METHODS EXTRACTION PROMPT
    # =========================================================================
    if methods or results:
        pass2_system = _TIER1_PCA_METHODS_INSTRUCTION
        
        pass2_user = f"PMID: {pmid}\nAnalyze these sections for computational methods:\n\n"
        pass2_user += f"=== METHODS ===\n{methods}\n\n"
        pass2_user += f"=== RESULTS ===\n{results}\n"
        
        # Save Pass 2
        with open(f"ai_input_pass2_{pmid}.txt", "w") as f:
            f.write("=" * 80 + "\n")
            f.write("PASS 2: COMPUTATIONAL METHODS EXTRACTION\n")
            f.write("=" * 80 + "\n\n")
            f.write("--- SYSTEM PROMPT ---\n")
            f.write(pass2_system)
            f.write("\n\n--- USER PROMPT ---\n")
            f.write(pass2_user)
        
        logger.info(f"Saved: ai_input_pass2_{pmid}.txt ({len(pass2_system) + len(pass2_user)} chars)")
    else:
        logger.info("No methods/results sections - Pass 2 would be skipped")
    
    print(f"\n[OK] Generated input files for PMID {pmid}")
    print(f"   - ai_input_pass1_{pmid}.txt (Scoring)")
    print(f"   - ai_input_pass2_{pmid}.txt (Methods)")

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "41258098"
    generate_twopass_inputs(target)
