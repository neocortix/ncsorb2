#!/usr/bin/env python3
"""
analyzes a neocortix event log
"""
# standard library modules
import argparse
import concurrent.futures
import csv
import datetime
import json
import logging
import os
import random
import re
import requests
import shutil
import subprocess
import sys
import time
# third-party modules
#import dateutil
#import dateutil.parser
#import pandas as pd
# neocortix modules


logger = logging.getLogger(__name__)


def startTest( testsUrl, reqParams ):
    reqDataStr = json.dumps( reqParams )
    #logger.debug( 'reqDataStr: %s', reqDataStr )
    resp = requests.post( testsUrl, data=reqDataStr )
    logger.info( 'POST status_code %d', resp.status_code )
    logger.info( 'POST text %s', resp.text )
    respJson = resp.json()
    logger.info( 'POST json %s', respJson )
    testId = respJson['id']
    return testId


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)s %(module)s %(funcName)s %(message)s', datefmt='%Y/%m/%d %H:%M:%S')
    logger.setLevel(logging.INFO)
    logger.debug('the logger is configured')

    ap = argparse.ArgumentParser( description=__doc__, fromfile_prefix_chars='@' )
    ap.add_argument( 'victimHostUrl', help='url of the host to target as victim' )
    ap.add_argument( '--authToken', required=True, help='the NCS authorization token to use' )
    ap.add_argument('--jsonOut', help='file path to write detailed info in json format')
    ap.add_argument( '--masterUrl', default='http://localhost', help='url of the master' )
    ap.add_argument( '--nConcurrent', type=int, default=1, help='number of concurrent tests' )
    ap.add_argument( '--nWorkers', type=int, default=1, help='the # of worker instances to launch (or zero for all available)' )
    args = ap.parse_args()

    masterUrl = args.masterUrl
    logger.info( 'masterUrl: %s', masterUrl )

    # get '/' to test connectivity
    resp = requests.get( masterUrl+'/' )
    logger.info( 'resp.status_code %d', resp.status_code )
    # dont' print the text; that would be the web page source
    #logger.info( 'resp.text %s', resp.text )

    testsUrl = masterUrl+'/api/tests/'
    # get /tests/
    resp = requests.get( testsUrl )
    logger.info( '/api/tests/ status_code %d', resp.status_code )
    logger.info( '/api/tests/ json %s', resp.json() )

    # set params for tests
    nWorkers = args.nWorkers
    startTimeLimit = 30
    susTime = 30
    usersPerWorker = 6
    rampUpRate = nWorkers * 1
    reqParams = [args.victimHostUrl, "<MasterHostUnspecified>",
        "--authToken", args.authToken, "--nWorkers", str(nWorkers),
        "--susTime", str(susTime), "--usersPerWorker", str(usersPerWorker),
        "--rampUpRate", str(rampUpRate), "--startTimeLimit", str(startTimeLimit)
        ]

    nTests = args.nConcurrent
    # start tests
    #testId = startTest( testsUrl, reqParams )
    #testIds = [testId]
    with concurrent.futures.ThreadPoolExecutor( max_workers=nTests ) as executor:
        parIter = executor.map( startTest, [testsUrl]*nTests, [reqParams]*nTests )
        testIds = list( parIter )

    logger.info( 'testIds: %s', testIds )

    # dict of results by testId
    results = {}

    # poll the started tests
    #gotResults = False
    while True:
        anyRunning = False
        for testId in testIds:
            statusUrl = testsUrl + testId
            logger.info( 'polling: %s', statusUrl )
            resp = requests.get( statusUrl )
            if resp.status_code != 200:
                logger.warning( 'poll status_code %d', resp.status_code )
            else:
                #logger.info( 'poll text %s', resp.text )
                respJson = resp.json()
                results[ testId ] = respJson
                #gotResults = True
                #logger.info( 'poll json %s', respJson )
                logger.info( 'poll json state: %s', respJson['state'] )
                logger.info( 'poll json stderr: %s', respJson['stderr'][-400:] )
                anyRunning = anyRunning or respJson['state'] == 'running'
                #if respJson['state'] == 'stopped':
                #    break
        if not anyRunning:
            break
        time.sleep( 5 )

    # print results
    for testId in testIds:
        if not testId in results:
            print( '>>NO results for', testId )
        else:
            print('>>stdout from', testId)
            print( results[testId]['stdout'] )
    # save detailed outputs, if requested
    if args.jsonOut:
        argsToSave = vars(args).copy()
        del argsToSave['authToken']
        toSave = { 'args': argsToSave, 'results': results }
        jsonOutFilePath = os.path.expanduser( os.path.expandvars( args.jsonOut ) )
        with open( jsonOutFilePath, 'w') as outFile:
            json.dump( toSave, outFile, indent=2 )
            #json.dump( toSave, outFile, default=str, indent=2, skipkeys=True )
