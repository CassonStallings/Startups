
"""
Name:        crunchbase_to_mongo.py (was crunchbase2.py)
Purpose:     Pulls data from crunchbase through the API and stores JSON
               documents in MongoDB which may be running on AWS. It
               set up to get all data, not data related to specific
               queries.
               Contains class CrunchbaseApi
Requires:    CrunchbaseApi API key and if used AWS ID and key pair.
Author:      Casson
Created:     3/12/2014
Copyright:   (c) Casson 2014
Licence:     <your licence>

Program is typically run from command line and given parameters
indicating which links to follow.

:param int startid:  first item in entity list to fetch, defaults to 0
:param int count:  number of items to fetch, defaults to 0, fetch all
:param int num_of_list: entity list to use
    1. financial-organizations
    2. people
    3. companies
    4. products
    5. service-providers
:param str log_file: file to store output
"""



import sys, json, cPickle
from Queue import Queue
from time import sleep
from simplejson.decoder import JSONDecodeError
import requests
from pymongo import MongoClient
from boto.s3.key import Key
from boto.s3.connection import S3Connection



fil = None

#from multiprocessing.pool import ThreadPool
sleep_time = 0.0
sleep_time_if_problems = 5.0

crunchbase_api = ''  # Crunchbase API
aws_id = ''  # aws_access_key_id
aws_key = ''  # aws_secret_access_key
mongo_uri = 'mongodb://localhost:27017'  #'mongodb://54.226.78.144:27017'

startid = 201380
count = 500000
num_of_list = 2
log_file = 'progress.txt'

print sys.argv

if len(sys.argv)>=2:
    startid = int(sys.argv[1])
if len(sys.argv)>=3:
    count = int(sys.argv[2])
if len(sys.argv)>=4:
    num_of_list = int(sys.argv[3])
if len(sys.argv)>=5:
    log_file = sys.argv[4]
if len(sys.argv)>=6:
    if 'True' != sys.argv[5]:
        crunchbase_api = jons_api

print 'Running with startid:', startid,'  count:', count, '  num_of_list:', num_of_list, '  log_file:', log_file, '  api:',  crunchbase_api

entity_type_tuples = [('financial-organizations', 'financial-organization'), ('people', 'person'), \
                      ('companies', 'company'), ('products', 'product'), \
                      ('service-providers', 'service-provider')]
fil = None

q = Queue()
mongo_collection = None
num_threads = 10
threads = []
q = Queue()
error_prod = list()

def main():
    global fil
    crunch = CrunchbaseApi(crunchbase_api)

    # Get pertinent lists to drive downloads
    # These are saved in S3/casson_lists
    #crunch.put_entity_list_in_s3(list_type='financial_organizations')
    #crunch.put_entity_list_in_s3(list_type='people')
    #crunch.put_entity_list_in_s3(list_type='companies')


    fil = open(log_file, 'w')

    client = MongoClient(mongo_uri)
    mc = client.crunchbase

    #for entity_type_list, entity_type in entity_type_tuples:
    #    crunch.mongo_collection = mc[entity_type_list]
    #    entity_list = crunch.get_entity_list_and_pickle(entity_type_list, entity_type + '_list.pkl')

    for entity_type_list, entity_type in [entity_type_tuples[num_of_list]]:
        mongo_collection = mc[entity_type_list.replace('-', '_')]
        entity_list = crunch.get_pickled_entity_list(entity_type + '_list.pkl')
        crunch.cycle_through_permalinks(entity_type, entity_list[startid:startid+count], mongo_collection)

    fil.close()
    print 'Done Cycling Through Permalinks'

    # entity_list = crunch.get_entity_list_and_pickle('financial-organizations', 'financial_list.pkl')
    # entity_list = crunch.get_pickled_entity_list('financial_list.pkl')
    # crunch.cycle_through_permalinks('financial-organization', entity_list)

    #OLD
    #print 'store webpages, key dict list', key_dict_lst
    #cnt = crunch.store_webpages(key_dict_lst, entity_type='financial_organization',
    #                                save_bucket='financial_organization_data_store')
    #print 'done cnt', cnt

    # Companies
    #co_key_dict_lst = crunch.get_entity_list_from_s3(entity_type='company', list_bucket='companies_list')
    #cocnt = crunch.store_webpages(co_key_dict_lst, entity_type='company', save_bucket='company_data_store')


    # People
    #pe_key_dict_lst = crunch.get_entity_list_from_s3(entity_type='person', list_bucket='people_list')
    #pecnt = crunch.store_webpages(pe_key_dict_lst, entity_type='person', save_bucket='people_data_store')


class CrunchbaseApi():
    """
    Entities, typically identified by a type variable, include:
        financial-organization(s),
        company(ies),
        person(people),
        product(s),
        service_provider(s)
    """

    def __init__(self, api_key):
        """Initialize a CrunchbaseApi object using the crunchbase API key.
        :rtype: CrunchbaseApi
        """
        self.base = 'http://api.crunchbase.com/v/1/'
        self.api_key = api_key

    #    self.num_threads = 10
    #    self.threads = []
    #    self.q = Queue()
    #    self.error_prod = list()

    def api_call(self, link_type_tuple):

        entity_type, mongo_collection, permalink = link_type_tuple
        a = 'http://api.crunchbase.com/v/1/' + entity_type + '/' + permalink + '.js?api_key=' + self.api_key
        try:
            temp = requests.get(a)
            if temp.status_code != 200:
                sleep(3)
                temp = requests.get(a)
            d = temp.json()
            d['_id'] = permalink
            mongo_collection.save(d)

        except JSONDecodeError as de:
            print 'Decode Error on ', temp.status_code, a
            fil.writelines(['\ndecode error: ' + permalink])
            sleep(3)
        except ValueError as ev:
            print 'Expected Value Error, Get Status_code', temp.status_code, 'Retry after sleep'
            sleep(3)
            temp = requests.get(a)
            d = temp.json()
            d['_id'] = permalink
            mongo_collection.save(d)
            if temp.status_code == 200:
                print 'Success for ', a, '\n'
        except BaseException as exp:
            print 'Error in api_call, Text:', exp, link_type_tuple

    def put_entity_list_in_s3(self, list_type='financial_organizations'):
        """Call api for a type and get all current permalinks, store in s3."""
        global aws_id, aws_key, api_key

        conn = S3Connection(aws_id, aws_key)
        bucket = conn.create_bucket(list_type + '_list')
        k = Key(bucket)

        jlist = self.get_entity_list(list_type)
        for num, dlike in enumerate(jlist):
            d = dict(dlike)
            key = d['permalink']
            k.key = key
            k.set_contents_from_string(d)
        print 'Done putting data into', list_type, 'last d, last key', d, key


    def get_entity_list_from_s3(self, entity_type, list_bucket):
        """Get permalinks of one type from s3 and return a list."""
        global aws_id, aws_key
        print 'in get_entity_list_from _s3, type, bucket', entity_type, list_bucket
        cnt = 0
        # Get a list of entities
        conn = S3Connection(aws_id, aws_key)
        list_bucket = conn.get_bucket(list_bucket)
        key_generator = list_bucket.list()
        # print 'count in key_list', len(list(key_generator))
        permalink_list = list()
        for key in key_generator:
            try:
                dstr = key.get_contents_as_string()
                d = dict(dstr)
                permalink = d['permalink']
                cnt += 1
            except:
                continue
            permalink_list.append(permalink)

        print 'Have list of {} keys from {}. '.format(cnt, entity_type)
        return permalink_list

    def cycle_through_permalinks(self, entity_type, permalink_list, mongo_collection):
        global fil
        t0 = i = 0
        #pool = ThreadPool(processes=10)
        for i in xrange(0, len(permalink_list), 10):
            duration = time.time() - t0
            if duration < 1:
                sleep(1.1 - duration)
                print 'sleeping for', 1.1 - duration
            t0 = time.time()
            out_str = 'Starting Iter, time for last 10: ' + entity_type + ' ' + str(i+startid) + ' ' + str(duration) + ' Seconds'
            print out_str
            fil.writelines(['\n',out_str])
            fil.flush()
            links = permalink_list[i:i+10]
            tl0 = time.time()
            for link in links:
                link_dur = time.time() - tl0
                if link_dur < 1:
                    sleep(1-link_dur)
                link_entity_tuples = (entity_type, mongo_collection, link)
                api_call(link_entity_tuples)

    def cycle_through_permalinks_with_pools(self, entity_type, permalink_list, mongo_collection):
        global fil
        t0 = i = 0
        pool = ThreadPool(processes=10)
        for i in xrange(0, len(permalink_list), 10):
            duration = time.time() - t0
            print time.time(), t0, duration
            if duration < 1:
                sleep(1.1 - duration)
                print 'sleeping for', 1.1 - duration
            out_str = 'Entity_type, Iter, time for last 10: ' + entity_type + ' ' + str(i) + ' ' + str(duration)
            print out_str
            fil.writelines([out_str])
            fil.flush()
            links = permalink_list[i:i+10]
            link_entity_tuples = [(entity_type, mongo_collection, links[i]) for i in xrange(10)]

            #print 'tuples', link_entity_tuples
            pool.map(api_call, link_entity_tuples)
            t0 = time.time()

    def store_webpages(self, key_dict_lst, entity_type, save_bucket):
        """OLD---Given list of permalinks (in dicts), download web pages from crunchbase, and save in s3."""
        global aws_id, aws_key

        # Set up bucket for save
        print 'store_webpages'
        conn = S3Connection(aws_id, aws_key)
        bucket = conn.get_bucket(save_bucket)
        k = Key(bucket)

        cnt = 0
        print 'Starting loop to get and store pages:', len(key_dict_lst.keys())
        for cnt, d in enumerate(key_dict_lst):
            print 'looping in enumerate, cnt, d\n      ', cnt, d, 'key=', d['permakey']
            permakey = d['permakey']
            webpage_as_json = self.get_entity(permakey, entity_type=entity_type)
            k = permakey
            cnt += 1
            k.set_contents_from_string(webpage_as_json)
            if cnt > 5:
                break
            print 'store_webpage', cnt
        return cnt

    def get_entity(self, permakey, entity_type='company'):
        """OLD---Gets a single entity type from crunchbase and returns a dictionary."""
        params = {'api_key': crunchbase_api}  ###, 'Entity': type, 'Name': permalink}
        url = self.base + entity_type + '/' + permakey + '.js'
        time.sleep(sleep_time)  # Wait for a bit so we are not hitting it too fast..
        try:
            r = requests.get(url, params=params)
            if r.status_code >= 400:
                print '\nERROR {} while retrieving page {}'.format(r.status_code, url)
                return None
        except:
            print 'Waiting 5 seconds before continuing.', url, params
            time.sleep(sleep_time_if_problems)
            return None
        try:
            result = json.loads(r.content)
        except:
            print '\nERROR in get_entity loading json\n', r.content
            result = None

        return result

    def get_entity_list(self, entity_type):
        """Gets complete list of entity type from crunchbase and returns a list of dictionaries."""
        url = self.base + entity_type + '.js'
        params = {'api_key': self.api_key}
        r = requests.get(url, params=params)

        if r.status_code >= 400:
            print '\nERROR {} while retrieving page {}'.format(r.status_code, url)
            print '   URL attempted:', r.url
            return None
        return json.loads(r.content)

    def get_entity_list_and_pickle(self, entity_type, pickle_file):
        """
        Gets complete list of an entity type from crunchbase and returns it as a list.
        :param str entity_type: an entity type (e.g. people, companies, financial-organizations)
        :param str pickle_file: file to save pickled list
        :rtype list[]: permalinks
        """
        url = self.base + entity_type + '.js'
        params = {'api_key': self.api_key}
        r = requests.get(url, params=params)
        if r.status_code >= 400:
            print '\nERROR {} while retrieving page {}'.format(r.status_code, url)
            print '   URL attempted:', r.url
            return

        d = json.loads(r.content)
        entity_list = list()
        for adict in d:
            entity_list.append(adict['permalink'])
        cPickle.dump(entity_list, open(pickle_file, 'wb'))
        return entity_list

    def get_pickled_entity_list(self, pickle_file):
        """
        Gets a complete entity list from a pickle file and returns a list.
        :param str pickle_file: file where pickle is stored
        :rtype list[]: permalinks
        """
        return cPickle.load(open(pickle_file, 'rb'))



if __name__ == '__main__':
    main()