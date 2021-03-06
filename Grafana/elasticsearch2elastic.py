#!/usr/bin/env python
import datetime
import time
import urllib
import json
import subprocess
import urllib2
import os
import sys
import re
from collections import Counter

# ElasticSearch Cluster to Monitor
elasticServer = os.environ.get('ES_METRICS_CLUSTER_URL', 'http://localhost:9200')
interval = int(os.environ.get('ES_METRICS_INTERVAL', '60'))

# ElasticSearch Cluster to Send Metrics
elasticIndex = os.environ.get('ES_METRICS_INDEX_NAME', 'elasticsearch_metrics')
elasticMonitoringCluster = os.environ.get('ES_METRICS_MONITORING_CLUSTER_URL', 'http://localhost:9200')


def fetch_clusterhealth():
    try:
        utc_datetime = datetime.datetime.utcnow()
        endpoint = "/_cluster/health"
        urlData = elasticServer + endpoint
        response = urllib.urlopen(urlData)
        jsonData = json.loads(response.read())
        clusterName = jsonData['cluster_name']
        jsonData['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
        if jsonData['status'] == 'green':
            jsonData['status_code'] = 0
        elif jsonData['status'] == 'yellow':
            jsonData['status_code'] = 1
        elif jsonData['status'] == 'red':
            jsonData['status_code'] = 2
        post_data(jsonData)
        return clusterName
    except IOError as err:
        print "IOError: Maybe can't connect to elasticsearch."
        clusterName = "unknown"
        return clusterName


def fetch_clusterstats():
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_cluster/stats"
    urlData = elasticServer + endpoint
    response = urllib.urlopen(urlData)
    jsonData = json.loads(response.read())
    jsonData['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
    post_data(jsonData)


def fetch_nodestats(clusterName):
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_cat/nodes?v&h=n"
    urlData = elasticServer + endpoint
    response = urllib.urlopen(urlData)
    nodes = response.read()[1:-1].strip().split('\n')
    for node in nodes:
        endpoint = "/_nodes/%s/stats" % node.rstrip()
        urlData = elasticServer + endpoint
        response = urllib.urlopen(urlData)
        jsonData = json.loads(response.read())
        nodeID = jsonData['nodes'].keys()
        try:
            jsonData['nodes'][nodeID[0]]['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
            jsonData['nodes'][nodeID[0]]['cluster_name'] = clusterName
            newJsonData = jsonData['nodes'][nodeID[0]]
            post_data(newJsonData)
        except:
            continue


def fetch_indexstats(clusterName):
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_stats"
    urlData = elasticServer + endpoint
    response = urllib.urlopen(urlData)
    jsonData = json.loads(response.read())
    jsonData['_all']['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
    jsonData['_all']['cluster_name'] = clusterName
    post_data(jsonData['_all'])



def fetch_numberofproperties():
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_mapping?pretty"
    urlData = elasticServer + endpoint
    response = urllib.urlopen(urlData) 
    jsonData = json.loads(response.read())
    properties = {}
    properties['numberOfProperties'] = {}
    properties['numberOfProperties']['indexname'] = {}
    properties['@timestamp'] = str(utc_datetime.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3])
    date = str(utc_datetime.strftime('%Y.%m.%d'))
    for i in jsonData:
        p = re.compile('(\S+)-(\d{4}.\d{2}).\d{2}')    
        m = p.match(i)
        if m != None:
            if date in m.group(0): 
                index = m.group(0)
                url = elasticServer + '/' + index + '/_mapping?pretty'
                p1 = subprocess.Popen(['curl', url],stdout=subprocess.PIPE)
                p2 = subprocess.Popen(['grep', '\"type\"'],stdin=p1.stdout,stdout=subprocess.PIPE)
                p3 = subprocess.Popen(['wc','-l'],stdin = p2.stdout,stdout=subprocess.PIPE)
                p1.stdout.close()
                p2.stdout.close()
                number = int(p3.communicate()[0])    
                properties['numberOfProperties']['indexname'][m.group(1)] = number
    post_data(properties)


def days_between(d1, d2):
    # d1 = datetime.datetime.strptime(d1, "%Y-%m-%d")
    d2 = datetime.datetime.strptime(d2, "%Y-%m-%d")
    return abs((d2 - d1).days)

def fetch_numberofindicesperdate():
    utc_datetime = datetime.datetime.utcnow()
    endpoint = "/_cat/indices"
    urlData = elasticServer + endpoint
    dateDict = {}
    p1 = subprocess.Popen(['curl', urlData],stdout=subprocess.PIPE)
    output = p1.stdout.read()
    for line in iter(output.splitlines()):
        p = re.compile('.*\s+\S+(\d{4}.\d{2}.\d{2})')
        m = p.match(line)
        if m != None:
            day = datetime.datetime.strptime(m.group(1).replace(".","-"),"%Y-%m-%d")
            if (abs((utc_datetime - day).days) < 4*30):
                if dateDict.get(day,0) != 0:
                    dateDict[day] += 1;
                else:
                    dateDict[day] = 1;
            else:
                oldDay = datetime.datetime.strptime("2000-01-01","%Y-%m-%d")
                if dateDict.get(oldDay,0) != 0:
                    dateDict[oldDay] += 1;
                else:
                    dateDict[oldDay] = 1;
    for i in dateDict:
        document = {}
        document['date'] = str(i.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3]) 
        document['number'] = dateDict[i]
        print document
        post_data(document);
             


    

def post_data(data):
    utc_datetime = datetime.datetime.utcnow()
    url_parameters = {'cluster': elasticMonitoringCluster, 'index': elasticIndex,
        'index_period': utc_datetime.strftime("%Y.%m.%d"), }
    url = "%(cluster)s/%(index)s-%(index_period)s/message" % url_parameters
    headers = {'content-type': 'application/json'}
    try:
        req = urllib2.Request(url, headers=headers, data=json.dumps(data))
        f = urllib2.urlopen(req)
        print f
    except Exception as e:
        print "Error:  {}".format(str(e))


def main():
    clusterName = fetch_clusterhealth()
    if clusterName != "unknown":
        fetch_clusterstats()
        fetch_nodestats(clusterName)
        fetch_indexstats(clusterName)
        fetch_numberofproperties()
        fetch_numberofindicesperdate()


if __name__ == '__main__':
    try:
        nextRun = 0
        while True:
            if time.time() >= nextRun:
                nextRun = time.time() + interval
                now = time.time()
                main()
                elapsed = time.time() - now
                print "Total Elapsed Time: %s" % elapsed
                timeDiff = nextRun - time.time()

                # Check timediff , if timediff >=0 sleep, if < 0 send metrics to es
                if timeDiff >= 0:
                    time.sleep(timeDiff)

    except KeyboardInterrupt:
        print 'Interrupted'
        try:
            sys.exit(0)
        except SystemExit:
            os._exit(0)