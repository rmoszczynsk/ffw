#!/usr/bin/env python2

import os
import glob
import requests
import sys
import base64
import time
import logging
import pprint

import utils

"""
CrashData Uploader to ffweb.

Uploads the (verified- ) CrashData to the ffweb server
Can use basic authentication.
"""


class Uploader(object):
    def __init__(self, config, server, user, password):
        self.config = config

        self.projectId = None
        if server is None:
            self.server = "http://localhost:8000"
        else:
            self.server = server

        self.user = user
        self.password = password
        self.auth = ()

        if self.user is not None and self.password is not None:
            self.auth = (self.user, self.password)


    def uploadVerifyDir(self):
        outcomesDir = os.path.abspath(self.config["verified_dir"])
        outcomesFiles = glob.glob(os.path.join(outcomesDir, '*.ffw'))

        print("Processing %d outcome files" % len(outcomesFiles))

        if not self.projectExistsInCloud():
            self.createProjectInCloud()

        for outcomeFile in outcomesFiles:
            print "Processing file: " + outcomeFile
            outcome = utils.readPickleFile(outcomeFile)

            if outcome is not None:
                self.uploadData(outcome)


    def projectExistsInCloud(self):
        payload = {'name': self.config["name"]}
        url = self.server + "/api/projects/"
        r = requests.get(url, params=payload, auth=self.auth)

        if r.status_code != 200:
            sys.exit(0)
        j = r.json()

        if not j:
            return False

        j = j[0]  # we get an array atm, so just use first element
        if not j:
            logging.error("project does not exist")
            return False
        else:
            projectId = j["pk"]
            print "project ID: " + str(projectId)
            self.projectId = projectId
            return True


    def createProjectInCloud(self):
        print "Create project: " + self.config["name"]
        url = self.server + "/api/projects/"
        payload = {
            "name": self.config["name"],
            "comment": self.config["target_bin"] + " " + self.config["target_args"],
        }
        r = requests.post(url, json=payload, auth=self.auth)
        j = r.json()
        if not j:
            logging.error("Error parsing answer")
            sys.exit(1)
        else:
            projectId = j["pk"]
            print "project ID: " + str(projectId)
            self.projectId = projectId


    def uploadData(self, outcome):
        print "Upload data"
        url = self.server + "/api/crashdata/"

        fuzzIterData = outcome["fuzzIterData"]
        initialCrashData = outcome["initialCrashData"]
        verifyCrashData = outcome["verifierResult"].verifyCrashData
        gdbVerifyCrashData = outcome["verifierResult"].gdbVerifyCrashData
        asanVerifyCrashData = outcome["verifierResult"].asanVerifyCrashData

        myMsgList = []
        n = 0
        for msg in fuzzIterData["fuzzedData"]:
            m = {
                "index": n,
                "sentBy": msg["from"],
                "msg": base64.b64encode( msg["data"] ),
                "fuzzed": 0,
            }
            if 'isFuzzed' in msg and msg["isFuzzed"]:
                m["fuzzed"] = 1
            myMsgList.append(m)
            n += 1

        # convert some ugly data into more ugly ones
        registers = ''.join('{}={} '.format(key, val) for key, val in verifyCrashData.registers.items())
        backtraceStr = '\n'.join(map(str, verifyCrashData.backtrace))

        asanOut = ""
        gdbOut = ""
        if asanVerifyCrashData is not None and asanVerifyCrashData.analyzerOutput is not None:
            asanOut = asanVerifyCrashData.analyzerOutput
        if gdbVerifyCrashData.analyzerOutput is not None:
            gdbOut = gdbVerifyCrashData.analyzerOutput

        cause_line = verifyCrashData.backtrace[0]

        payload = {
            "project": self.projectId,
            "seed": fuzzIterData["seed"],

            "offset": verifyCrashData.faultOffset,
            "time": "2017-09-09T18:03",
            "signal": verifyCrashData.sig,

            "fuzzerpos": initialCrashData["fuzzerPos"],
            "reallydead": initialCrashData["reallydead"],

            "stdout": "meh",
            "asanoutput": asanOut,
            "gdboutput": gdbOut,
            "backtrace": backtraceStr,
            "cause": verifyCrashData.cause,
            "cause_line": cause_line,
            "codeoff": verifyCrashData.faultOffset,
            "codeaddr": verifyCrashData.faultAddress,
            "messageList": myMsgList,
        }

        r = requests.post(url, json=payload, auth=self.auth)
        if r.status_code < 200 or r.status_code > 299:
            pprint.pprint(payload)
            print "Error response: " + r.text
        else:
            print "Uploading seed " + str(fuzzIterData["seed"]) + " successful"