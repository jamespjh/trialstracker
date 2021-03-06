import time
from collections import defaultdict

from pyquery import PyQuery as pq
import pandas as pd
import requests
from xml.etree import ElementTree


def extract_ctgov_xml(text):
    d = pq(text, parser='xml')
    data = defaultdict(None)
    data['nct_id'] = d('nct_id').text()
    data['title'] = d('brief_title').text().strip()
    data['overall_status'] = d('overall_status').text().strip()
    data['phase'] = d('phase').text().replace("Phase ", "")
    data['lead_sponsor'] = d('lead_sponsor agency').text()
    data['lead_sponsor_class'] = d('lead_sponsor agency_class').text()
    data['study_type'] = d('study_type').text()
    data['completion_date'] = d('primary_completion_date').text()
    data['results_date'] = d('firstreceived_results_date').text()
    data['enrollment'] = d('enrollment').text()
    data['disposition_date'] = \
        d('firstreceived_results_disposition_date').text()
    # The following fields are not currently used, but might
    # be useful in future. Note they aren't tested.
    # data['results_pmids'] = d('results_reference PMID').text()
    data['collaborator'] = d('collaborator')('agency').text()
    data['collaborator_class'] = d('collaborator')('agency_class').text()
    data['has_drug_intervention'] = False
    data['drugs'] = ''
    for it in d('intervention'):
        e = pq(it)
        if e('intervention_type').text() == 'Drug':
            data['has_drug_intervention'] = True
            data['drugs'] += e('intervention_name').text() + '; '
    data['locations'] = d('location_countries country').text()
    for k in data:
        if data[k] and isinstance(data[k], basestring):
            data[k] = data[k].encode('utf8')
    return data


def normalise_phase(x):
    '''
    Set N/A (trials without phases, e.g. device trials) to 5
    (i.e. later than phase 2, which is our cutoff for inclusion).
    And set multi-phase trials to the earlier phase, e.g.
    phase 1/2 trials to 1.
    '''
    if pd.isnull(x):
        x = 5
    return int(str(x).split('/')[0])


def extract_title_from_pubmed_data(text):
    try:
        tree = ElementTree.fromstring(text)
        title = tree.find('.//Article/ArticleTitle')
        if title is not None:
            title = title.text.encode('utf8')
    except ElementTree.ParseError:
        print 'ParseError', text
        title = ''
    return title


def get_pubmed_linked_articles_url(nct_id, completion_date,
                                   query_type):
    url = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/'
    url += 'esearch.fcgi?db=pubmed&retmode=json&term='
    url += '(%s[si] OR %s[Title/Abstract]) ' % (nct_id, nct_id)
    url += 'AND ("%s"[pdat] : ' % completion_date.strftime('%Y/%m/%d')
    url += '"3000"[pdat]) '
    if query_type == 'broad':
        url += "AND ((clinical[Title/Abstract] AND trial[Title/Abstract]) "
        url += "OR clinical trials as topic[MeSH Terms] "
        url += "OR clinical trial[Publication Type] "
        url += "OR random*[Title/Abstract] "
        url += "OR random allocation[MeSH Terms] "
        url += "OR therapeutic use[MeSH Subheading])"
    elif query_type == 'narrow':
        url += "AND (randomized controlled trial[Publication Type] OR "
        url += "(randomized[Title/Abstract] "
        url += "AND controlled[Title/Abstract] AND trial[Title/Abstract]))"
    return url


def extract_pubmed_ids_from_json(data):
    ids = []
    esearchresult = data['esearchresult']
    if 'idlist' in esearchresult:
        ids = esearchresult['idlist']
    return ids


def is_study_protocol(title):
    return (title and 'study protocol' in title.lower())


def get_response(url):
    got_response = False
    while not got_response:
        try:
            resp = requests.get(url)
            got_response = True
        except ValueError, requests.ConnectionError:
            print 'Error, retrying...', url
            time.sleep(10)
    return resp


def get_pubmed_title(pmid):
    '''
    Retrieve the title of a PubMed article, from its PMID.
    '''
    url = 'http://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'
    url += 'db=pubmed&rettype=abstract&id=%s' % pmid
    resp = get_response(url)
    title = extract_title_from_pubmed_data(resp.content)


def get_pubmed_linked_articles(nct_id, completion_date, query_type):
    '''
    Given an NCT ID, search PubMed for related results articles.
    '''
    url = get_pubmed_linked_articles_url(nct_id, completion_date,
                                         query_type)
    resp = get_response(url)
    data = resp.json()
    ids = extract_pubmed_ids_from_json(data)
    for id1 in ids[:]:
        title = get_pubmed_title(id1)
        if is_study_protocol(title):
            ids.remove(id1)
    return ids
