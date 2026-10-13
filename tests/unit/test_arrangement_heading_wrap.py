from xml.etree import ElementTree as ET

from calb_diagrams.ac_block_arrangement_v2 import render_plan_svg, US_NFPA_OIL


def test_long_heading_stays_inside_page_without_changing_equipment_layout():
    title='2.50 MW AC Block - 2 x 1250 kW PCS - 20ft simplified model'
    short, before=render_plan_svg(2, US_NFPA_OIL, block_label='Short')
    long, after=render_plan_svg(2, US_NFPA_OIL, block_label=title)
    assert before==after
    root=ET.fromstring(long)
    width=float(root.attrib['viewBox'].split()[2])
    lines=[e for e in root.iter('{http://www.w3.org/2000/svg}text') if e.attrib.get('text-anchor')=='start' and float(e.attrib['y']) < 85]
    heading=' '.join(e.text or '' for e in lines)
    assert title in heading
    assert US_NFPA_OIL.market_label in heading
    assert len(lines)>1
    for line in lines:
        assert float(line.attrib['x'])+len(line.text or '')*13*.65 < width
    assert float(root.attrib['viewBox'].split()[3]) > float(ET.fromstring(short).attrib['viewBox'].split()[3])
