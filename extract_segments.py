import fitz
import glob
import os
import sys
import re
import csv
import argparse
from datetime import datetime
from collections import defaultdict

# Ensure standard output uses UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

MONTHS = {
    'january': 1, 'jan': 1, 'february': 2, 'feb': 2, 'march': 3, 'mar': 3,
    'april': 4, 'apr': 4, 'may': 5, 'may': 5, 'june': 6, 'jun': 6, 'july': 7, 'jul': 7,
    'august': 8, 'aug': 8, 'september': 9, 'sep': 9, 'sept': 9, 'october': 10,
    'oct': 10, 'november': 11, 'nov': 11, 'december': 12, 'dec': 12
}

def parse_date_range(text, fallback_year=2024):
    """
    Parses flexible date range strings from NDMA advisories into standardized
    'YYYY-MM-DD to YYYY-MM-DD' or 'YYYY-MM-DD' format.
    Handles connectives ('to', '-', '&', 'and') and parenthetical qualifiers (e.g. '(night)').
    """
    text_clean = re.sub(r'\([^\)]+\)', '', text)
    text_clean = ' '.join(text_clean.split())
    
    # 1. Day Month to Day Month Year (e.g., 29th July to 05th August 2026)
    m1 = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(?:to|-|&|and)\s+(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:,|\s+)?\s*(\d{4})', text_clean, re.IGNORECASE)
    if m1:
        d1, m1_str, d2, m2_str, y = m1.groups()
        m1_num = MONTHS.get(m1_str.lower()[:3])
        m2_num = MONTHS.get(m2_str.lower()[:3])
        if m1_num and m2_num:
            return f'{y}-{m1_num:02d}-{int(d1):02d} to {y}-{m2_num:02d}-{int(d2):02d}'
            
    # 2. Day to Day Month Year (e.g., 10th to 12th May 2026, 06th & 07th October 2026)
    m2 = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|-|&|and)\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:,|\s+)?\s*(\d{4})', text_clean, re.IGNORECASE)
    if m2:
        d1, d2, m_str, y = m2.groups()
        m_num = MONTHS.get(m_str.lower()[:3])
        if m_num:
            if fallback_year == 2026 and y == '2025' and 'MARCH' in text_clean.upper():
                y = '2026'
            return f'{y}-{m_num:02d}-{int(d1):02d} to {y}-{m_num:02d}-{int(d2):02d}'

    # 3. Day to Day Month (no year specified, use fallback_year)
    m3 = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s*(?:to|-|&|and)\s*(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)', text_clean, re.IGNORECASE)
    if m3:
        d1, d2, m_str = m3.groups()
        m_num = MONTHS.get(m_str.lower()[:3])
        if m_num:
            return f'{fallback_year}-{m_num:02d}-{int(d1):02d} to {fallback_year}-{m_num:02d}-{int(d2):02d}'

    # 4. Single Date with Month and Year (e.g., 22 July 2026)
    m4 = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)(?:,|\s+)?\s*(\d{4})', text_clean, re.IGNORECASE)
    if m4:
        d, m_str, y = m4.groups()
        m_num = MONTHS.get(m_str.lower()[:3])
        if m_num:
            return f'{y}-{m_num:02d}-{int(d):02d}'

    # 5. Month Day, Year (e.g., July 22, 2026)
    m5 = re.search(r'([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,|\s+)?\s*(\d{4})', text_clean, re.IGNORECASE)
    if m5:
        m_str, d, y = m5.groups()
        m_num = MONTHS.get(m_str.lower()[:3])
        if m_num:
            return f'{y}-{m_num:02d}-{int(d):02d}'
            
    return text.strip()

DIRECT_PATTERNS = [
    ('Hunza', re.compile(r'\bHunza\b', re.IGNORECASE)),
    ('Skardu', re.compile(r'\bSkardu\b', re.IGNORECASE)),
    ('Gilgit', re.compile(r'\bGilgit\b(?!\s*[-–]\s*Baltistan|\s+Baltistan)', re.IGNORECASE)),
    ('Naran', re.compile(r'\bNaran\b', re.IGNORECASE)),
    ('Swat', re.compile(r'\b(Swat|Kalam)\b', re.IGNORECASE)),
    ('Murree/Galliyat', re.compile(r'\b(Murree|Gall?iy?at)\b', re.IGNORECASE)),
    ('Chitral', re.compile(r'\bChitral\b', re.IGNORECASE)),
    ('Dir', re.compile(r'\bDir\b')),
    ('Neelum Valley', re.compile(r'\bNeel[ua]m(?:\s*Valley)?\b', re.IGNORECASE)),
]

REGION_PATTERNS = [
    ('Gilgit-Baltistan', re.compile(r'\b(?:Gilgit\s*[-–]?\s*Baltistan|G\.?B\.?)\b', re.IGNORECASE), ['Hunza', 'Skardu', 'Gilgit']),
    ('Khyber Pakhtunkhwa', re.compile(r'\b(?:Khyber\s*[-–]?\s*Pakhtunkhwa|K\.?P\.?|KPK)\b', re.IGNORECASE), ['Naran', 'Swat', 'Chitral', 'Dir']),
    ('Kashmir', re.compile(r'\b(?:Kashmir|AJ&K|AJK|A\.J\.&K\.?|Azad\s+Jammu\s*(?:&|and)?\s*Kashmir|State\s+of\s+AJ&K)\b', re.IGNORECASE), ['Neelum Valley']),
    ('Mansehra/Kaghan', re.compile(r'\b(?:Mansehra|Kaghan)\b', re.IGNORECASE), ['Naran']),
]

def clean_page(p_text):
    """
    Cleans running page headers, footers, and official stationery noise.
    """
    lines = p_text.split('\n')
    out = []
    for l in lines:
        s = l.strip()
        if re.match(r'^Page\s+\d+\s+of\s+\d+', s, re.IGNORECASE):
            continue
        if s in ['MOST IMMEDIATE / BY FAX', 'MOST IMMEDIATE/ BY FAX', 'MOST IMMEDIATE', 
                'Government of Pakistan', 'Prime Minister’s Office', 'Prime Minister\'s Office', 
                'National Disaster Management Authority (HQ)', 'National Disaster Management Authority', 'ISLAMABAD']:
            continue
        if 'Main Murree Road' in s or 'Near ITP Office' in s:
            continue
        if re.match(r'^F\.?\s*2?\s*\(E\)', s) or re.match(r'^F\.?\s*10?\s*\(E\)', s):
            continue
        out.append(l)
    return '\n'.join(out)

def is_gov_directive(text):
    """
    Detects administrative directives, public awareness tips, and operational instructions
    that do not represent tourist hazard forecasts.
    """
    t_lower = text.lower()
    patterns = [
        r'\b(?:pdma|gbdma|sdma|ddma|leas?|traffic police|nh&mp|rescue 1122|fwo|nha|eocs?|ministries|departments|line depts)\b.*?\b(?:ensure|coordinate|preplace|deploy|activate|manage|direct|redirect|instruct|staffing|drills?|requested|advised to ensure|devise|maintain enhanced|identification of|be on stand-by|undertake regular)\b',
        r'\b(?:ensure|coordinate|preplace|deploy|activate|manage|direct|redirect|instruct|devise|maintain enhanced|identification of)\b.*?\b(?:pdma|gbdma|sdma|ddma|leas?|traffic police|nh&mp|rescue 1122|line departments|line depts|eocs?|civic agencies)\b',
        r'all concerned federal ministries',
        r'in this regard, all concerned',
        r'in light of prevailing situation all concerned',
        r'all concerned are requested to promptly ensure',
        r'press information department',
        r'aspects for mass awareness',
        r'safety tips for general public',
        r'travel safety checklist',
        r'key precautions & safety measures',
        r'during hailstorm, follow these safety tips',
        r'during thunder-storm and lightning strike',
        r'limit the number of tourists',
        r'regulate traffic at picnic',
        r'properly dispose-off garbage',
        r'ask hotel staff about emergency exits',
        r'cooperate with locals and district authorities',
        r'sensitize all concerned on risks',
        r'keep at least 20 feet distance',
        r'wear weather appropriate clothing',
        r'choose hotels or guest houses located on higher ground',
        r'avoid walking or driving through flooded areas',
        r'avoid trekking, hiking, or camping',
        r'avoid self-driving in unfamiliar or hilly areas',
        r'do not attempt to cross bridges',
        r'do not risk cross any drain',
        r'do not risk enter a ponded',
        r'do not handle/ repair any electrical equipment',
        r'forwarded for information',
        r'acting director',
        r'director \(response\)',
        r'tel:\s*051',
        r'fax:\s*051',
        r'copy to:',
        r'to:\s*federal ministries',
        r'to:\s*chief secretary',
        r'to:\s*director general',
        r'deputy director \(response\)',
        r'for information & necessary action',
        r'dg \(response\)',
        r'guide lines\s*•',
        r'general public is advised to'
    ]
    for p in patterns:
        if re.search(p, t_lower):
            return True
    return False

def is_distribution_entry(text):
    """
    Identifies lines belonging to the inter-agency distribution list.
    """
    t_lower = text.lower()
    dist_keywords = [
        'director general, pdma', 'director general, gbdma', 'director general, sdma',
        'chief secretary, provincial', 'chief secretary, government', 'chief secretary, all',
        'secretary, ministry', 'inspector general', 'headquarters, national highway',
        'headquarters, frontier works', 'director (coordination)', 'headquarters, pak',
        'distribution list', 'deputy director ict', 'pro, ndma', 'joint crises management',
        'military operations directorate', 'national flood response', 'army flood control',
        'kashmir affairs and gilgit-baltistan and safron'
    ]
    for kw in dist_keywords:
        if kw in t_lower:
            return True
    return False

def get_weak_label_hint(text):
    """
    Assigns rule-based weak label hint (0=routine, 1=caution/disruption, 2=restriction/blockage).
    """
    t_low = text.lower()
    class_2_indicators = [
        'road closure', 'closure', 'blockage', 'blocked', 'landslide', 'mudslide',
        'flash flood', 'glof', 'impassable', 'slippery conditions', 'snowfall may cause road',
        'disrupt roads', 'disrupt traffic', 'heavy snowfall may'
    ]
    class_0_indicators = [
        'partly cloudy', 'light rain', 'cold and dry', 'shallow fog', 'pleasant', 'stable atmospheric'
    ]
    for ind in class_2_indicators:
        if ind in t_low:
            return '2'
    for ind in class_0_indicators:
        if ind in t_low:
            return '0'
    return '1'

# Curated transcriptions for legacy scanned image PDFs
SCANNED_ADVISORIES_DATA = {
    '4zaJEoGNf1i5ELNiQ0Qm.pdf': {
        'issue_date': '06 May 2022',
        'hazard_date_range': '2022-05-09 to 2022-05-15',
        'section1_was_image': True,
        'segments': [
            {
                'text': 'Day temperatures are likely to remain 07-09°C above normal in upper Punjab, Islamabad, Rawalpindi, Khyber Pakhtunkhwa, Gilgit-Baltistan and Kashmir from 09th to 12th May 2022.',
                'date_range': '2022-05-09 to 2022-05-12',
                'section': 'Annex - Forecast',
                'direct': [],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Khyber Pakhtunkhwa'
            },
            {
                'text': 'In Gilgit-Baltistan and Khyber Pakhtunkhwa, the water flows will increase in rivers and nullahs due to high rate of snow and ice melting.',
                'date_range': '2022-05-09 to 2022-05-15',
                'section': 'Annex - Likely Impact',
                'direct': [],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir'],
                'matched_region': 'Gilgit-Baltistan, Khyber Pakhtunkhwa'
            }
        ]
    },
    'JNEGsz6KQOnm3Vx4yoHI.pdf': {
        'issue_date': '19 January 2022',
        'hazard_date_range': '2022-01-21 to 2022-01-23',
        'section1_was_image': True,
        'segments': [
            {
                'text': 'Rain-wind-thunderstorm with isolated heavy fall and snowfall over the hills is expected in Khyber Pakhtunkhwa, Gilgit-Baltistan, Kashmir, Murree and Galliyat from Friday, 21st January (night) to Sunday, 23rd January 2022.',
                'date_range': '2022-01-21 to 2022-01-23',
                'section': 'Annex - Forecast',
                'direct': ['Murree/Galliyat'],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Khyber Pakhtunkhwa'
            },
            {
                'text': 'Heavy snowfall may cause road closures in Murree, Galiyat, Nathiagali, Naran, Kaghan, Dir, Swat, Shangla, Buner, Neelum Valley, Bagh, Haveli, Rawalakot, Hunza and Skardu during the forecast period.',
                'date_range': '2022-01-21 to 2022-01-23',
                'section': 'Annex - Likely Impact',
                'direct': ['Hunza', 'Skardu', 'Naran', 'Swat', 'Murree/Galliyat', 'Dir', 'Neelum Valley'],
                'implied': [],
                'matched_region': ''
            },
            {
                'text': 'Possibility of landslides in Malakand, Hazara, Gilgit-Baltistan and Kashmir cannot be ruled out during the period.',
                'date_range': '2022-01-21 to 2022-01-23',
                'section': 'Annex - Likely Impact',
                'direct': [],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir'
            }
        ]
    },
    'eBXqgDcvLn5FyAK34k19.pdf': {
        'issue_date': '14 January 2022',
        'hazard_date_range': '2022-01-16 to 2022-01-19',
        'section1_was_image': True,
        'segments': [
            {
                'text': 'Rain-thunderstorm with snowfall over the hills is expected in Chitral, Dir, Swat, Malakand, Kohistan, Shangla, Buner, Mansehra, Abbottabad, Haripur, Swabi, Mardan, Nowshera, Peshawar, Murree, Galliyat, Neelum Valley, Bagh, Haveli, Rawalakot, Gilgit-Baltistan (Diamer, Astore, Ghizer, Skardu, Hunza, Gilgit, Ghanche) from Sunday, 16th January (night) to Wednesday, 19th January 2022.',
                'date_range': '2022-01-16 to 2022-01-19',
                'section': 'Annex - Forecast',
                'direct': ['Hunza', 'Skardu', 'Gilgit', 'Swat', 'Murree/Galliyat', 'Chitral', 'Dir', 'Neelum Valley'],
                'implied': ['Naran'],
                'matched_region': 'Mansehra/Kaghan'
            },
            {
                'text': 'Snowfall may cause road closures in Murree, Galiyat, Nathiagali, Kaghan, Naran, Dir, Swat, Kohistan, Astore, Hunza, Skardu, Neelum Valley, Bagh and Rawalakot on Monday and Tuesday.',
                'date_range': '2022-01-17 to 2022-01-18',
                'section': 'Annex - Likely Impact',
                'direct': ['Hunza', 'Skardu', 'Naran', 'Swat', 'Murree/Galliyat', 'Dir', 'Neelum Valley'],
                'implied': [],
                'matched_region': ''
            },
            {
                'text': 'Landslides may also occur in vulnerable areas of Dir, Swat, Kohistan, Shangla, Buner, Gilgit-Baltistan and Kashmir during the period.',
                'date_range': '2022-01-16 to 2022-01-19',
                'section': 'Annex - Likely Impact',
                'direct': ['Swat', 'Dir'],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir'
            }
        ]
    },
    'rIGDng1CwzgI8DzqSNvB.pdf': {
        'issue_date': '05 January 2023',
        'hazard_date_range': '2023-01-07 to 2023-01-09',
        'section1_was_image': True,
        'segments': [
            {
                'text': 'Moderate rain-wind/snowfall over the hills is expected in Murree, Galliyat, Neelum Valley, Bagh, Haveli, Rawalakot, Chitral, Dir, Swat, Kohistan, Shangla, Mansehra, Abbottabad and Gilgit-Baltistan from Saturday, 07th January (night) to Monday, 09th January 2023.',
                'date_range': '2023-01-07 to 2023-01-09',
                'section': 'Annex - Forecast',
                'direct': ['Swat', 'Murree/Galliyat', 'Chitral', 'Dir', 'Neelum Valley'],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran'],
                'matched_region': 'Gilgit-Baltistan, Mansehra/Kaghan'
            },
            {
                'text': 'Moderate snowfall may cause road disruption / closures in Murree, Galiyat, Nathiagali, Naran, Kaghan, Dir, Swat, Kohistan, Mansehra, Abbottabad, Shangla, Astore, Hunza, Skardu and Neelum Valley on 08th and 09th January.',
                'date_range': '2023-01-08 to 2023-01-09',
                'section': 'Annex - Likely Impact',
                'direct': ['Hunza', 'Skardu', 'Naran', 'Swat', 'Murree/Galliyat', 'Dir', 'Neelum Valley'],
                'implied': [],
                'matched_region': ''
            },
            {
                'text': 'Possibility of landslides in hilly areas of Khyber Pakhtunkhwa, Gilgit-Baltistan and Kashmir cannot be ruled out during the period.',
                'date_range': '2023-01-07 to 2023-01-09',
                'section': 'Annex - Likely Impact',
                'direct': [],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Khyber Pakhtunkhwa'
            }
        ]
    },
    'vFgtChxxUfeS2fNzQaNC.pdf': {
        'issue_date': '14 March 2022',
        'hazard_date_range': '2022-03-16 to 2022-03-21',
        'section1_was_image': True,
        'segments': [
            {
                'text': 'Day temperatures are likely to remain 07-08°C above normal in Khyber Pakhtunkhwa, Gilgit-Baltistan and Kashmir from 16th to 21st March 2022.',
                'date_range': '2022-03-16 to 2022-03-21',
                'section': 'Annex - Forecast',
                'direct': [],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Khyber Pakhtunkhwa'
            },
            {
                'text': 'In Gilgit-Baltistan and Khyber Pakhtunkhwa, the water flows will increase in rivers and nullahs due to high rate of snow and ice melting.',
                'date_range': '2022-03-16 to 2022-03-21',
                'section': 'Annex - Likely Impact',
                'direct': [],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir'],
                'matched_region': 'Gilgit-Baltistan, Khyber Pakhtunkhwa'
            }
        ]
    },
    'QM4Sr8IjmE1ootNMQHvo.pdf': {
        'issue_date': '08 August 2022',
        'hazard_date_range': '2022-08-10 to 2022-08-13',
        'section1_was_image': True,
        'segments': [
            {
                'text': 'Rain-wind/thundershower with isolated heavy falls is expected in Khyber Pakhtunkhwa, Gilgit-Baltistan, Kashmir, Murree and Galliyat from Wednesday, 10th August to Saturday, 13th August 2022.',
                'date_range': '2022-08-10 to 2022-08-13',
                'section': 'Annex - Forecast',
                'direct': ['Murree/Galliyat'],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Khyber Pakhtunkhwa'
            },
            {
                'text': 'Flash flooding is expected in Local Nullahs of Mansehra, Dir, Swat, Kohistan, Shangla, Buner, Kurram and Kashmir on 11th and 12th August.',
                'date_range': '2022-08-11 to 2022-08-12',
                'section': 'Annex - Likely Impact',
                'direct': ['Swat', 'Dir'],
                'implied': ['Naran', 'Neelum Valley'],
                'matched_region': 'Kashmir, Mansehra/Kaghan'
            },
            {
                'text': 'Landslides may occur in vulnerable hilly areas of Khyber Pakhtunkhwa, Gilgit-Baltistan, Kashmir, Murree and Galiyat during the forecast period.',
                'date_range': '2022-08-10 to 2022-08-13',
                'section': 'Annex - Likely Impact',
                'direct': ['Murree/Galliyat'],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Khyber Pakhtunkhwa'
            }
        ]
    },
    'AzzPgpM0ZiIwAMit6B30.pdf': {
        'issue_date': '09 September 2022',
        'hazard_date_range': '2022-09-10 to 2022-09-14',
        'section1_was_image': True,
        'segments': [
            {
                'text': 'Rain-wind/thundershower (with isolated heavy falls) is expected in Chitral, Dir, Swat, Kohistan, Shangla, Buner, Mansehra, Abbottabad, Haripur, Malakand, Bajaur, Peshawar, Mardan, Charsadda, Swabi, Nowshera, Kurram, Kohat, Waziristan, Kashmir, Gilgit-Baltistan, Islamabad, Rawalpindi, Murree, Attock, Chakwal, Jhelum, Sialkot, Narowal, Lahore, Gujranwala, Gujrat, Sheikhupura, Mianwali, Khushab, Sargodha, Hafizabad, Mandi Bahauddin, Jhang and Faisalabad from 10th to 14th September, while Bhakkar, Layyah, D.G.Khan and Muzaffargarh on 13th and 14th September with occasional gaps.',
                'date_range': '2022-09-10 to 2022-09-14',
                'section': 'Annex - Forecast',
                'direct': ['Swat', 'Murree/Galliyat', 'Chitral', 'Dir'],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Mansehra/Kaghan'
            },
            {
                'text': 'Rainfall may trigger landslides in Kashmir, hilly areas of Khyber Pakhtunkhwa, Gilgit Baltistan, Galiyat and Murree during the forecast period.',
                'date_range': '2022-09-10 to 2022-09-14',
                'section': 'Annex - Likely Impact',
                'direct': ['Murree/Galliyat'],
                'implied': ['Hunza', 'Skardu', 'Gilgit', 'Naran', 'Swat', 'Chitral', 'Dir', 'Neelum Valley'],
                'matched_region': 'Gilgit-Baltistan, Kashmir, Khyber Pakhtunkhwa'
            }
        ]
    }
}

def process_single_pdf(fpath):
    """
    Extracts structured hazard segments and document audit metadata from an individual PDF.
    """
    fname = os.path.basename(fpath)
    stem = os.path.splitext(fname)[0]
    doc = fitz.open(fpath)
    total_pages = len(doc)
    
    # 0. Check curated transcriptions for legacy scanned image PDFs
    if fname in SCANNED_ADVISORIES_DATA:
        sdata = SCANNED_ADVISORIES_DATA[fname]
        segs = []
        direct_found = set()
        implied_found = set()
        for idx, s in enumerate(sdata['segments'], start=1):
            seg_id = f"{stem}_{idx:02d}"
            hint = get_weak_label_hint(s['text'])
            if s['direct']:
                match_type = 'direct'
            elif s['implied']:
                if hint == '2':
                    match_type = 'implied_full_confidence'
                elif hint == '1':
                    match_type = 'implied_discounted'
                else:
                    match_type = 'implied_routine'
            else:
                match_type = 'none'

            segs.append({
                'segment_id': seg_id,
                'pdf_filename': fname,
                'advisory_issue_date': sdata['issue_date'],
                'hazard_date_range': s['date_range'],
                'section': s['section'],
                'section1_was_image': sdata['section1_was_image'],
                'source_method': 'manual_transcription',
                'segment_text': s['text'],
                'direct_locations': ', '.join(s['direct']),
                'implied_locations': ', '.join(s['implied']),
                'matched_region': s.get('matched_region', ''),
                'location_match_type': match_type,
                'weak_label_hint': hint,
                'label': '',
                'annotator_1_label': '',
                'annotator_2_label': '',
                'label_notes': ''
            })
            for d in s['direct']:
                direct_found.add(d)
            for imp in s['implied']:
                implied_found.add(imp)
                
        report_row = {
            'pdf_filename': fname,
            'advisory_issue_date': sdata['issue_date'],
            'hazard_date_range': sdata['hazard_date_range'],
            'section1_was_image': sdata['section1_was_image'],
            'total_pages': total_pages,
            'usable_segments_count': len(segs),
            'direct_locations_found': ', '.join(sorted(list(direct_found))),
            'implied_locations_found': ', '.join(sorted(list(implied_found))),
            'status_and_issues': 'Scanned/image advisory transcribed via visual inspection'
        }
        return segs, report_row

    # 1. Detect if Section 1 was an infographic image map
    has_large_map = False
    for pno in range(min(3, total_pages)):
        for img in doc[pno].get_images():
            try:
                pix = fitz.Pixmap(doc, img[0])
                if pix.width > 400 and pix.height > 400:
                    has_large_map = True
                    break
            except:
                pass
        if has_large_map:
            break

    full_text_pages = [clean_page(p.get_text()) for p in doc]
    full_text = '\n'.join(full_text_pages)
    
    # Normalize bullet characters and unicode symbols
    clean_text = full_text.replace('\ufffd', '•').replace('\uf0d8', '•').replace('\u27a2', '•').replace('\u2022', '•')
    clean_text = re.sub(r'(\b\w+)-\s*\n\s*(\w+\b)', r'\1-\2', clean_text)
    
    # 2. Extract Issue Date
    dm = re.search(r'Dated:\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+\s+[0-9]{4})', clean_text[:2500])
    if not dm:
        dm = re.search(r'Dated:\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+,\s*[0-9]{4})', clean_text[:2500])
    if not dm:
        dm = re.search(r'Date:\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+\s+[0-9]{4})', clean_text[:2500])
    if not dm:
        dm = re.search(r'Dated:\s*([0-9]{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+(?:\s*,\s*|\s+)[0-9]{2,4})', clean_text[:2500])
    if not dm and '19-21 November 2022' in clean_text[:300]:
        advisory_date = '19 November 2022'
    elif not dm and '29 February to 2 March 2024' in clean_text[:300]:
        advisory_date = '29 February 2024'
    else:
        advisory_date = dm.group(1).strip() if dm else 'UNKNOWN'

    # Fallback Year
    year_m = re.search(r'\b(202[1-7])\b', advisory_date)
    fallback_year = int(year_m.group(1)) if year_m else 2024

    # Subject & overall hazard date
    sm = re.search(r'Subject:\s*([^\n\r]+(?:\n[^\n\r]+){0,2})', clean_text[:2500], re.IGNORECASE)
    subject = ' '.join(sm.group(1).split()) if sm else ''
    
    od_m1 = re.search(r'(?:from|during)\s+([0-9]{1,2}(?:st|nd|rd|th)?(?:\s*\([^\)]+\))?\s*(?:to|-|&|and)\s*[0-9]{1,2}(?:st|nd|rd|th)?(?:\s*\([^\)]+\))?\s+[a-zA-Z]+(?:\s*,\s*|\s+)[0-9]{4})', subject + ' ' + clean_text[:2000], re.IGNORECASE)
    od_m2 = re.search(r'([0-9]{1,2}(?:st|nd|rd|th)?(?:\s+[a-zA-Z]+)?\s*(?:to|-|&|and)\s*[0-9]{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+\s+[0-9]{4})', subject, re.IGNORECASE)
    od_m3 = re.search(r'(?:from|during)\s+([0-9]{1,2}(?:st|nd|rd|th)?(?:\s*\([^\)]+\))?\s*(?:to|-|&|and)\s*[0-9]{1,2}(?:st|nd|rd|th)?\s+[a-zA-Z]+)', subject, re.IGNORECASE)
    if not od_m1 and not od_m2 and not od_m3 and '29 February to 2 March 2024' in clean_text[:300]:
        overall_date_raw = '29 February to 2 March 2024'
    else:
        overall_date_raw = od_m1.group(1) if od_m1 else (od_m2.group(1) if od_m2 else (od_m3.group(1) if od_m3 else advisory_date))
    overall_hazard_date = parse_date_range(overall_date_raw, fallback_year)

    # Check text clauses in Section 1
    s2_m = re.search(r'\n\s*2\.\s+(?:Under the influence|Likely Impacts)', clean_text, re.IGNORECASE)
    pre_s2_text = clean_text[:s2_m.start()] if s2_m else clean_text[:2500]
    has_text_prov = bool(re.search(r'(?:[a-d]\.\s*(?:Khyber\s*[-–]?\s*Pakhtunkhwa|KP|Punjab|Gilgit|Kashmir|Balochistan|Sindh))', pre_s2_text, re.IGNORECASE))
    is_glof = 'GLOF' in clean_text[:400]
    is_water = 'Water Levels' in clean_text[:400] or 'Significant Increase' in clean_text[:400]
    section1_was_image = has_large_map and (not has_text_prov) and (not is_glof) and (not is_water)

    # Break into candidate blocks
    raw_blocks = re.split(r'\n\s*(?=[a-z]\.|\([0-9]+\)|\([a-z]\)|[0-9]+\.\s+[A-Z]|•|\*|➢|o(?=\s+[A-Z]|\n))', clean_text)
    blocks = []
    for b in raw_blocks:
        b_str = ' '.join(b.split())
        if len(b_str) > 400 and (is_glof or is_water):
            sents = re.split(r'(?<=[.!?])\s+', b_str)
            blocks.extend(sents)
        else:
            blocks.append(b_str)

    kept_segments = []
    pdf_direct_locs = set()
    pdf_implied_locs = set()
    seg_idx = 1

    for block in blocks:
        b_clean = ' '.join(block.split())
        if len(b_clean) < 25:
            continue
        if is_gov_directive(b_clean) or is_distribution_entry(b_clean):
            continue
        if 'DISTRIBUTION LIST' in b_clean or 'Director (Response)' in b_clean:
            continue

        # Match Direct Locations
        d_hits = []
        for loc, pat in DIRECT_PATTERNS:
            if pat.search(b_clean):
                if loc not in d_hits:
                    d_hits.append(loc)

        # Match Implied Locations and trace matched regions
        imp_hits = set()
        matched_regions = []
        for rname, pat, cov_locs in REGION_PATTERNS:
            if pat.search(b_clean):
                matched_regions.append(rname)
                for cloc in cov_locs:
                    if cloc not in d_hits:
                        imp_hits.add(cloc)

        imp_hits = sorted(list(imp_hits))
        matched_region_str = ', '.join(sorted(matched_regions)) if imp_hits else ''
        if not d_hits and not imp_hits:
            continue

        # Determine Section Name
        if 'Annex' in clean_text and clean_text.find(block) > clean_text.find('Annex'):
            if any(w in b_clean.lower() for w in ['impact', 'landslide', 'disrupt', 'flash flood', 'closure', 'caution']):
                sec_name = 'Annex - Likely Impact'
            else:
                sec_name = 'Annex - Forecast'
        elif s2_m and clean_text.find(block) < s2_m.start():
            sec_name = 'Forecast'
        elif is_glof or is_water:
            sec_name = 'Alert Narrative'
        elif any(w in b_clean.lower() for w in ['impact', 'landslide', 'disrupt', 'flash flood', 'closure', 'caution', 'heavy fall']):
            sec_name = 'Likely Impact'
        else:
            sec_name = 'Forecast'

        # Segment-specific date range
        seg_date_m = re.search(r'(?:from\s+|on\s+|during\s+)?(\d{1,2}(?:st|nd|rd|th)?(?:\s*\([^\)]+\))?\s*(?:to|-|&|and)\s*\d{1,2}(?:st|nd|rd|th)?(?:\s*\([^\)]+\))?\s+[A-Za-z]+(?:\s*,\s*|\s+)?\d{4})', b_clean, re.IGNORECASE)
        if not seg_date_m:
            seg_date_m = re.search(r'(?:from\s+|on\s+|during\s+)?(\d{1,2}(?:st|nd|rd|th)?(?:\s*\([^\)]+\))?\s*(?:to|-|&|and)\s*\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+)', b_clean, re.IGNORECASE)

        if seg_date_m:
            seg_hazard_date = parse_date_range(seg_date_m.group(0), fallback_year)
        else:
            seg_hazard_date = overall_hazard_date

        for d in d_hits:
            pdf_direct_locs.add(d)
        for imp in imp_hits:
            pdf_implied_locs.add(imp)

        seg_id = f"{stem}_{seg_idx:02d}"
        seg_idx += 1

        hint = get_weak_label_hint(b_clean)
        if d_hits:
            match_type = 'direct'
        elif imp_hits:
            if hint == '2':
                match_type = 'implied_full_confidence'
            elif hint == '1':
                match_type = 'implied_discounted'
            else:
                match_type = 'implied_routine'
        else:
            match_type = 'none'

        kept_segments.append({
            'segment_id': seg_id,
            'pdf_filename': fname,
            'advisory_issue_date': advisory_date,
            'hazard_date_range': seg_hazard_date,
            'section': sec_name,
            'section1_was_image': section1_was_image,
            'source_method': 'digital_text',
            'segment_text': b_clean,
            'direct_locations': ', '.join(d_hits),
            'implied_locations': ', '.join(imp_hits),
            'matched_region': matched_region_str,
            'location_match_type': match_type,
            'weak_label_hint': hint,
            'label': '',
            'annotator_1_label': '',
            'annotator_2_label': '',
            'label_notes': ''
        })

    # Document-level audit notes
    notes = []
    if section1_was_image:
        notes.append('Section 1 was image map; extracted text from Section 2')
    if is_glof:
        notes.append('GLOF Alert; narrative structure')
    if is_water:
        notes.append('Water Levels Alert across glaciated regions')
    if 'SOUTHERN' in subject.upper() or 'BALOCHISTAN' in subject.upper() or 'SINDH' in subject.upper() or 'BIPARJOY' in subject.upper():
        if len(kept_segments) == 0:
            notes.append('Southern/coastal hazard advisory only; 0 segments for target northern locations')
    if 'SUTLEJ' in subject.upper() or 'RIVER SUTLEJ' in clean_text.upper():
        if len(kept_segments) == 0:
            notes.append('River Sutlej / Beas plain flood advisory; 0 segments for target northern locations')
    if len(kept_segments) == 0 and not notes:
        notes.append('No clauses matching target northern locations')
    elif not notes:
        notes.append('Standard text advisory parsed cleanly')

    report_row = {
        'pdf_filename': fname,
        'advisory_issue_date': advisory_date,
        'hazard_date_range': overall_hazard_date,
        'section1_was_image': section1_was_image,
        'total_pages': total_pages,
        'usable_segments_count': len(kept_segments),
        'direct_locations_found': ', '.join(sorted(list(pdf_direct_locs))),
        'implied_locations_found': ', '.join(sorted(list(pdf_implied_locs))),
        'status_and_issues': '; '.join(notes)
    }

    return kept_segments, report_row

def clean_prefix_for_dedup(text):
    """
    Normalizes segment text for canonical deduplication by removing list/bullet markers.
    """
    t = text.strip()
    t = re.sub(r'^(?:[a-z]\.|\([a-z0-9]+\)|[0-9]+\.|\u2022|[•*➢\-\–]|\([0-9]+\))\s*', '', t, flags=re.IGNORECASE)
    return ' '.join(t.lower().split())

def update_canonical_sheet(all_segments, canonical_csv_path='labeling_canonical.csv'):
    """
    Groups all_segments into canonical deduplicated clusters.
    Preserves existing is_in_kappa_sample flags and human annotations.
    """
    # 1. Load existing canonical rows if file exists
    existing_meta = {}
    if os.path.exists(canonical_csv_path):
        with open(canonical_csv_path, encoding='utf-8-sig') as f:
            for row in csv.DictReader(f):
                norm = clean_prefix_for_dedup(row['segment_text'])
                existing_meta[norm] = {
                    'is_in_kappa_sample': row.get('is_in_kappa_sample', 'False'),
                    'label': row.get('label', ''),
                    'annotator_1_label': row.get('annotator_1_label', ''),
                    'annotator_2_label': row.get('annotator_2_label', ''),
                    'label_notes': row.get('label_notes', ''),
                    'canonical_segment_id': row.get('canonical_segment_id', '')
                }

    # 2. Cluster current raw segments
    clusters = defaultdict(list)
    for s in all_segments:
        norm = clean_prefix_for_dedup(s['segment_text'])
        clusters[norm].append(s)

    canonical_rows = []
    for norm, items in clusters.items():
        rep = items[0]
        all_pdfs = sorted(list(set(i['pdf_filename'] for i in items)))
        all_seg_ids = [i['segment_id'] for i in items]
        
        meta = existing_meta.get(norm, {})
        can_id = meta.get('canonical_segment_id', rep['segment_id'])
        in_kappa = meta.get('is_in_kappa_sample', 'False')
        label = meta.get('label', '')
        ann1 = meta.get('annotator_1_label', '')
        ann2 = meta.get('annotator_2_label', '')
        notes = meta.get('label_notes', '')

        canonical_rows.append({
            'canonical_segment_id': can_id,
            'segment_text': rep['segment_text'],
            'occurrence_count': len(items),
            'appears_in_pdfs': '; '.join(all_pdfs),
            'appears_in_segment_ids': '; '.join(all_seg_ids),
            'direct_locations': rep['direct_locations'],
            'implied_locations': rep['implied_locations'],
            'matched_region': rep['matched_region'],
            'location_match_type': rep['location_match_type'],
            'weak_label_hint': rep['weak_label_hint'],
            'is_in_kappa_sample': in_kappa,
            'label': label,
            'annotator_1_label': ann1,
            'annotator_2_label': ann2,
            'label_notes': notes
        })

    fieldnames = [
        'canonical_segment_id',
        'segment_text',
        'occurrence_count',
        'appears_in_pdfs',
        'appears_in_segment_ids',
        'direct_locations',
        'implied_locations',
        'matched_region',
        'location_match_type',
        'weak_label_hint',
        'is_in_kappa_sample',
        'label',
        'annotator_1_label',
        'annotator_2_label',
        'label_notes'
    ]
    with open(canonical_csv_path, 'w', newline='', encoding='utf-8-sig') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(canonical_rows)

    return canonical_rows

def run_extraction(target_dirs=('AdvisoryPDFs', 'remainingPDFs'), single_file=None):
    """
    Main extraction driver. Can process a single PDF or scan directories.
    """
    if single_file:
        all_files = [single_file]
    else:
        all_files = []
        for d in target_dirs:
            if os.path.exists(d):
                all_files.extend(sorted(glob.glob(os.path.join(d, '*.pdf'))))
        # Ensure unique files
        seen = set()
        deduped = []
        for f in all_files:
            fn = os.path.basename(f)
            if fn not in seen:
                seen.add(fn)
                deduped.append(f)
        all_files = deduped

    print(f"Total unique PDF files to process: {len(all_files)}")

    all_segments = []
    all_reports = []
    loc_stats = {loc: {'direct': 0, 'implied': 0} for loc, _ in DIRECT_PATTERNS}

    for f in all_files:
        segs, rep = process_single_pdf(f)
        all_segments.extend(segs)
        all_reports.append(rep)

        for s in segs:
            if s['direct_locations']:
                for d in s['direct_locations'].split(', '):
                    if d:
                        loc_stats[d]['direct'] += 1
            if s['implied_locations']:
                for imp in s['implied_locations'].split(', '):
                    if imp:
                        loc_stats[imp]['implied'] += 1

    # Save all_segments.csv with finalized 17-column schema
    csv_segments = 'all_segments.csv'
    fieldnames = [
        'segment_id', 'pdf_filename', 'advisory_issue_date', 'hazard_date_range',
        'section', 'section1_was_image', 'source_method', 'segment_text',
        'direct_locations', 'implied_locations', 'matched_region', 'location_match_type',
        'weak_label_hint', 'label', 'annotator_1_label', 'annotator_2_label', 'label_notes'
    ]
    with open(csv_segments, 'w', newline='', encoding='utf-8-sig') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_segments)
    print(f"Successfully wrote {len(all_segments)} rows to {csv_segments}")

    # Save run_report.csv
    csv_report = 'run_report.csv'
    with open(csv_report, 'w', newline='', encoding='utf-8-sig') as f_out:
        writer = csv.DictWriter(f_out, fieldnames=[
            'pdf_filename', 'advisory_issue_date', 'hazard_date_range', 'section1_was_image',
            'total_pages', 'usable_segments_count', 'direct_locations_found',
            'implied_locations_found', 'status_and_issues'
        ])
        writer.writeheader()
        writer.writerows(all_reports)
    print(f"Successfully wrote {len(all_reports)} rows to {csv_report}")

    # Update canonical sheet
    canonical_rows = update_canonical_sheet(all_segments, 'labeling_canonical.csv')
    print(f"Successfully wrote {len(canonical_rows)} canonical clusters to labeling_canonical.csv")

    kappa_count = sum(1 for c in canonical_rows if str(c.get('is_in_kappa_sample')).lower() == 'true')
    print(f"Kappa double-labeling sample count preserved: {kappa_count} rows")

    print("\n================ EXTRACTION METRICS ================")
    print(f"Total PDFs Processed: {len(all_files)}")
    print(f"Total Segments Extracted: {len(all_segments)}")
    print(f"Total Canonical Clusters: {len(canonical_rows)}")
    print(f"Average Segments per PDF: {len(all_segments) / len(all_files):.2f}")

    zero_reports = [r for r in all_reports if r['usable_segments_count'] == 0]
    print(f"PDFs with 0 segments: {len(zero_reports)}")

    print("\nLocation Mention Statistics:")
    print(f"{'Location':18} | {'Direct':6} | {'Implied':8} | {'Total':6}")
    print("-" * 46)
    for loc, c in loc_stats.items():
        tot = c['direct'] + c['implied']
        print(f"{loc:18} | {c['direct']:6} | {c['implied']:8} | {tot:6}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Extract hazard advisory segments from NDMA/PMD PDFs.")
    parser.add_argument('--file', type=str, help="Path to single PDF to process.")
    parser.add_argument('--dirs', nargs='+', default=['AdvisoryPDFs', 'remainingPDFs'], help="Directories containing PDFs.")
    args = parser.parse_args()

    if args.file:
        segs, rep = process_single_pdf(args.file)
        print(f"\n--- Extracted {len(segs)} segments from {args.file} ---")
        for i, s in enumerate(segs, 1):
            print(f"\n[{i}] ID: {s['segment_id']} | Date: {s['hazard_date_range']}")
            print(f"    Direct: {s['direct_locations']} | Implied: {s['implied_locations']}")
            print(f"    Region: {s['matched_region']} | Hint: {s['weak_label_hint']}")
            print(f"    Text: \"{s['segment_text']}\"")
    else:
        run_extraction(target_dirs=args.dirs)
