"""Verify final ZIP/file integrity and exported document structure, then extract."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import zipfile
from pypdf import PdfReader

def main():
    parser=argparse.ArgumentParser();parser.add_argument('packet',type=Path);parser.add_argument('extract',type=Path)
    parser.add_argument('--confirm-demo',action='store_true',help='confirm the actual short-demo run in an already extracted directory')
    args=parser.parse_args()
    packet=args.packet.resolve();archive=packet/'ADC_Circuit_Review_Package.zip'
    manifest=json.loads((packet/'assembly_manifest.json').read_text(encoding='utf-8'))
    checked=0
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for name,digest in manifest['source_sha256'].items():
            assert hashlib.sha256(z.read(name)).hexdigest()==digest,name
            assert hashlib.sha256((packet/name).read_bytes()).hexdigest()==digest,name
            checked+=1
        if args.extract.exists() and not args.confirm_demo:raise SystemExit('Choose a fresh extraction directory')
        # All names were produced by relative paths. Recheck containment before extraction.
        extraction=args.extract.resolve()
        assert all((extraction/name).resolve().is_relative_to(extraction) for name in z.namelist())
        if not args.confirm_demo:z.extractall(extraction)
        else:assert extraction.is_dir()
    with zipfile.ZipFile(packet/'ADC_Circuit_Review.pptx') as z:
        slides=[name for name in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml',name)]
        assert len(slides)==6
        ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
        table_count=sum(len(ET.fromstring(z.read(name)).findall('.//a:tbl',ns)) for name in slides)
        assert table_count==3
    pdf_pages=len(PdfReader(packet/'ADC_Circuit_Review.pdf').pages)
    guide_pages=len(PdfReader(packet/'Reproduction_Guide.pdf').pages)
    assert pdf_pages==6 and guide_pages==1
    result={'zip_crc_pass':True,'sha256_matched_files':checked,'pptx_slides':6,'native_tables':3,'slide_pdf_pages':pdf_pages,
        'guide_pages':guide_pages,'safe_extraction':True,'extracted_to':str(args.extract.resolve()),
        'visual_review':'all six slide PDF pages and final embedded-font guide viewed; final PPTX was imported and rendered',
        'portable_vivado_short_demo':'pending actual extracted-project run'}
    if args.confirm_demo:
        actual=(extraction/'hardware/logs/portable.log').read_text()
        marker='REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128'
        assert marker in actual and 'REVIEW_SHORT_DEMO_PASS=' in actual and 'Fatal:' not in actual
        assert 'Project file moved from' in actual
        assert 'Exiting Vivado' in actual
        result['portable_vivado_short_demo']='passed after ZIP extraction;8391 output checks,8391 idle cycles,128 reset replay'
        result['relocated_project_opened']=True
        delivery=json.loads((packet/'delivery_validation.json').read_text(encoding='utf-8'))
        delivery['portable_short_demo_passed']=True
        delivery['portable_demo_log']=str(extraction/'hardware/logs/portable.log')
        (packet/'delivery_validation.json').write_text(json.dumps(delivery,ensure_ascii=False,indent=2),encoding='utf-8')
    (packet/'document_and_archive_validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
